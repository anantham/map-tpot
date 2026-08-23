"""Behavioral API and storage contracts for per-tag working notes."""
from __future__ import annotations

import sqlite3

import pytest
from flask import Flask

import src.api.routes.account_tags as account_tag_routes
from src.api.routes.account_tags import account_tags_bp
from src.data.account_tags import AccountTagStore
from src.data.tag_meta_notes import TagMetaNoteStore

CURATOR_TOKEN = "test-curator-token"
AUTH = {
    "X-TPOT-Curator-Token": CURATOR_TOKEN,
    "X-TPOT-Curation-Source": "human_curator_api",
}


@pytest.fixture
def meta_notes_app(monkeypatch, tmp_path) -> Flask:
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", CURATOR_TOKEN)
    account_tag_routes._tag_store = None
    account_tag_routes._meta_note_store = None
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(account_tags_bp)
    return app


@pytest.mark.integration
def test_store_appends_history_under_canonical_ego_and_tag_key(tmp_path) -> None:
    db_path = tmp_path / "account_tags.db"
    store = TagMetaNoteStore(db_path)

    first = store.append_note(
        ego=" @AdityaArpitha ",
        tag=" Dharma ",
        note="People I recognize through practice and discourse.",
        source="human_curator_api",
    )
    second = store.append_note(
        ego="adityaarpitha",
        tag="DHARMA",
        note="Practice-oriented accounts; affiliation is a separate question.",
        source="human_curator_api",
    )
    current, history = store.get_notes(
        ego="@ADITYAARPITHA",
        tag="dharma",
    )

    assert first.ego == "adityaarpitha"
    assert first.tag_key == "dharma"
    assert current == second
    assert [row.note_id for row in history] == [first.note_id, second.note_id]
    assert [row.note for row in history] == [first.note, second.note]

    store.append_note(
        ego="another-curator",
        tag="Dharma",
        note="A separate personal boundary.",
        source="human_curator_api",
    )
    _, original_history = store.get_notes(ego="adityaarpitha", tag="dharma")
    assert len(original_history) == 2

    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            "SELECT ego, tag_key, COUNT(*) FROM tag_meta_notes GROUP BY ego, tag_key"
        ).fetchone()
    assert stored == ("adityaarpitha", "dharma", 2)


@pytest.mark.integration
def test_meta_note_schema_addition_preserves_existing_tag_state(tmp_path) -> None:
    db_path = tmp_path / "account_tags.db"
    tags = AccountTagStore(db_path)
    tags.upsert_tag(
        ego="adityaarpitha",
        account_id="123",
        tag="Dharma",
        polarity=1,
    )

    notes = TagMetaNoteStore(db_path)
    notes.append_note(
        ego="adityaarpitha",
        tag="Dharma",
        note="A working reflection, not an enforced definition.",
        source="human_curator_api",
    )

    assert [tag.tag for tag in tags.list_tags(ego="adityaarpitha", account_id="123")] == [
        "Dharma"
    ]
    assert [event.action for event in tags.list_events(ego="adityaarpitha", account_id="123")] == [
        "set"
    ]


@pytest.mark.integration
def test_store_supports_explicit_clear_without_rewriting_history(tmp_path) -> None:
    store = TagMetaNoteStore(tmp_path / "account_tags.db")
    store.append_note(
        ego="ego",
        tag="Dharma",
        note="Initial working meaning",
        source="human_curator_api",
    )
    cleared = store.append_note(
        ego="ego",
        tag="dharma",
        note="   ",
        source="human_curator_api",
    )

    current, history = store.get_notes(ego="ego", tag="DHARMA")
    assert cleared.note == ""
    assert current == cleared
    assert [row.note for row in history] == ["Initial working meaning", ""]


@pytest.mark.integration
def test_api_reads_and_appends_curator_private_meta_notes(meta_notes_app) -> None:
    client = meta_notes_app.test_client()
    endpoint = "/api/tag-meta-notes?ego=%40AdityaArpitha&tag=Dharma"

    assert client.get(endpoint).status_code == 401
    assert client.post(endpoint, json={"note": "private"}).status_code == 401
    assert client.post(
        endpoint,
        json={"note": "private"},
        headers={"X-TPOT-Curator-Token": CURATOR_TOKEN},
    ).status_code == 400

    response = client.get(endpoint, headers=AUTH)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.get_json() == {
        "current": None,
        "ego": "adityaarpitha",
        "history": [],
        "tag": "Dharma",
        "tagKey": "dharma",
    }

    created = client.post(
        endpoint,
        json={"note": "Accounts I recognize through Dharma practice."},
        headers=AUTH,
    )
    assert created.status_code == 200
    payload = created.get_json()
    assert payload["status"] == "appended"
    assert payload["current"]["note"] == (
        "Accounts I recognize through Dharma practice."
    )
    assert payload["current"]["ego"] == "adityaarpitha"
    assert payload["current"]["tag_key"] == "dharma"
    assert payload["current"]["source"] == "human_curator_api"

    second = client.post(
        "/api/tag-meta-notes?ego=adityaarpitha&tag=DHARMA",
        json={"note": "A changing working intension, subordinate to examples."},
        headers=AUTH,
    )
    assert second.status_code == 200

    response = client.get(
        "/api/tag-meta-notes?ego=ADITYAARPITHA&tag=dharma",
        headers=AUTH,
    )
    history = response.get_json()["history"]
    assert len(history) == 2
    assert response.get_json()["current"] == history[-1]
    assert [row["note_id"] for row in history] == sorted(
        row["note_id"] for row in history
    )


@pytest.mark.unit
def test_api_hides_storage_failures(meta_notes_app, monkeypatch) -> None:
    class BrokenStore:
        def get_notes(self, **_kwargs):
            raise sqlite3.DatabaseError("private database details")

    monkeypatch.setattr(account_tag_routes, "_meta_note_store", BrokenStore())
    response = meta_notes_app.test_client().get(
        "/api/tag-meta-notes?ego=ego&tag=Dharma",
        headers=AUTH,
    )

    assert response.status_code == 500
    assert response.get_json()["error"] == (
        "tag meta-note read failed; inspect the API log"
    )
    assert "private database details" not in response.get_data(as_text=True)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("query", "body", "message"),
    [
        ("ego=ego", {"note": "x"}, "tag query param is required"),
        ("tag=Dharma", {"note": "x"}, "ego query param is required"),
        ("ego=ego&tag=Dharma", [], "JSON object"),
        ("ego=ego&tag=Dharma", {"note": 42}, "note must be a string"),
        (
            "ego=ego&tag=Dharma",
            {"note": "x" * 10_001},
            "note must be at most 10000 characters",
        ),
    ],
)
def test_api_rejects_invalid_meta_note_writes(
    meta_notes_app,
    query,
    body,
    message,
) -> None:
    response = meta_notes_app.test_client().post(
        f"/api/tag-meta-notes?{query}",
        json=body,
        headers=AUTH,
    )
    assert response.status_code == 400
    assert message in response.get_json()["error"]
