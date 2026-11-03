"""Test intent for the private, frozen discovery packet.

- Expose ordered evidence, not methods, scores, seeds, or prefilled judgments.
- Require curator auth and complete, valid personal answers for every save.
- Resume from durable storage; preserve revisions as separate answer events.
- Isolate packet revisions and never initialize tables in a legacy source DB.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from src.api.server import create_app


AUTH = {"X-TPOT-Curator-Token": "review-test-token"}
BASE = "/api/discovery-review"


@pytest.fixture
def review_context(tmp_path, monkeypatch, temp_snapshot_dir):
    packet = {
        "review_order": ["200", "100"],
        "freeze": {"ego": "test-curator", "extension": {"in": ["seed-secret"]}},
        "methods": {"method-secret": [{"account_id": "200", "rank": 1}]},
        "shuffle_seed": 123,
        "evidence": {
            "200": {
                "account_id": "200", "username": "example",
                "rank": "card-rank-secret", "raw_support": "support-secret",
                "profile": {
                    "account_id": "200", "username": "example",
                    "display_name": "Example", "bio": "Local profile evidence",
                    "location": "Somewhere", "fetched_at": "2026-09-22",
                    "method": "profile-method-secret",
                },
                "posts": [{
                    "tweet_id": "999", "text": "Local authored post",
                    "created_at": "2026-09-20", "fetched_at": "2026-09-22",
                    "source": "tweets", "url": "https://x.com/i/status/999",
                    "seed": "post-seed-secret",
                }],
            },
            "100": {"account_id": "100", "username": None, "profile": None, "posts": []},
        },
    }
    manifest = tmp_path / "packet" / "manifest.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps(packet))
    db_path = tmp_path / "private" / "discovery_review_answers.db"
    monkeypatch.setenv("TPOT_DISCOVERY_REVIEW_PACKET", str(manifest))
    monkeypatch.setenv("TPOT_DISCOVERY_REVIEW_DB", str(db_path))
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", AUTH["X-TPOT-Curator-Token"])
    monkeypatch.setenv("TPOT_LOG_DIR", str(tmp_path / "logs"))
    return manifest, db_path


def new_client():
    return create_app({"TESTING": True, "RATELIMIT_ENABLED": False}).test_client()


def valid_answer(packet_id, **changes):
    body = {"packetId": packet_id, "relevance": "IN", "known": "NO", "glad": "YES", "note": "Personal note"}
    body.update(changes)
    return body


def event_count(db_path):
    if not db_path.exists():
        return 0
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM discovery_review_answer_events").fetchone()[0]


def test_get_masks_selection_fields_and_preserves_card_order(review_context):
    manifest, db_path = review_context
    response = new_client().get(BASE, headers=AUTH)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    payload = response.get_json()
    assert set(payload) == {"packetId", "curator", "targetTag", "purpose", "cards", "answers", "completedCount", "totalCount"}
    assert payload["packetId"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert payload["curator"] == "test-curator"
    assert payload["targetTag"] == "dharma"
    assert [c["accountId"] for c in payload["cards"]] == ["200", "100"]
    assert payload["answers"] == {}
    assert payload["completedCount"] == 0
    assert payload["totalCount"] == 2
    first, missing = payload["cards"]
    assert set(first) == {"accountId", "username", "profile", "posts"}
    assert first["profile"] == {
        "accountId": "200", "username": "example", "displayName": "Example",
        "bio": "Local profile evidence", "location": "Somewhere", "fetchedAt": "2026-09-22",
    }
    assert first["posts"] == [{
        "tweetId": "999", "text": "Local authored post", "createdAt": "2026-09-20",
        "fetchedAt": "2026-09-22", "source": "tweets", "url": "https://x.com/i/status/999",
    }]
    assert missing == {"accountId": "100", "username": None, "profile": None, "posts": []}
    assert "secret" not in response.get_data(as_text=True)
    assert event_count(db_path) == 0


@pytest.mark.parametrize("method", ["get", "put"])
@pytest.mark.parametrize("token,status", [(None, 401), ("wrong", 401), ("unconfigured", 503)])
def test_private_routes_require_curator_auth(review_context, monkeypatch, method, token, status):
    _, db_path = review_context
    if token == "unconfigured":
        monkeypatch.delenv("TPOT_CURATOR_TOKEN")
    headers = {} if token is None else {"X-TPOT-Curator-Token": token}
    path = BASE if method == "get" else f"{BASE}/answers/200"
    response = getattr(new_client(), method)(path, headers=headers, json=valid_answer("fake"))
    assert response.status_code == status
    assert response.headers["Cache-Control"] == "private, no-store"
    assert not db_path.exists()


def test_save_resumes_in_fresh_app_and_correction_keeps_original_event(review_context):
    _, db_path = review_context
    client = new_client()
    packet_id = client.get(BASE, headers=AUTH).get_json()["packetId"]
    body = valid_answer(packet_id)
    first_response = client.put(f"{BASE}/answers/200", headers=AUTH, json=body)
    assert first_response.status_code == 200
    first = first_response.get_json()
    assert first["status"] == "appended"
    assert first["accountId"] == "200"
    assert first["packetId"] == packet_id
    assert first["completedCount"] == 1 and first["totalCount"] == 2
    assert set(first["answer"]) == {"relevance", "known", "glad", "note", "updatedAt", "eventId"}
    resumed = new_client().get(BASE, headers=AUTH).get_json()
    assert resumed["answers"] == {"200": first["answer"]}
    corrected = new_client().put(
        f"{BASE}/answers/200", headers=AUTH,
        json=valid_answer(packet_id, relevance="ABSTAIN", known="UNSURE", glad="NO", note="Reconsidered"),
    )
    assert corrected.status_code == 200
    second = corrected.get_json()["answer"]
    assert second["eventId"] > first["answer"]["eventId"]
    assert new_client().get(BASE, headers=AUTH).get_json()["answers"]["200"] == second
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT packet_id, curator, account_id, relevance, known, glad, note "
            "FROM discovery_review_answer_events ORDER BY event_id"
        ).fetchall()
    assert rows == [
        (packet_id, "test-curator", "200", "IN", "NO", "YES", "Personal note"),
        (packet_id, "test-curator", "200", "ABSTAIN", "UNSURE", "NO", "Reconsidered"),
    ]
    assert db_path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("changes", [
    {"relevance": "MAYBE"}, {"known": "MAYBE"}, {"glad": "MAYBE"},
    {"relevance": None}, {"known": None}, {"glad": None},
    {"relevance": ["IN"]}, {"packetId": "different"}, {"note": 42},
])
def test_invalid_answer_writes_no_events(review_context, changes):
    _, db_path = review_context
    client = new_client()
    packet_id = client.get(BASE, headers=AUTH).get_json()["packetId"]
    response = client.put(f"{BASE}/answers/200", headers=AUTH, json=valid_answer(packet_id, **changes))
    assert response.status_code == 400
    assert response.get_json()["error"]
    assert response.headers["Cache-Control"] == "private, no-store"
    assert event_count(db_path) == 0


def test_missing_answers_unknown_account_and_nonobject_body_are_rejected(review_context):
    _, db_path = review_context
    client = new_client()
    packet_id = client.get(BASE, headers=AUTH).get_json()["packetId"]
    for body in [{"packetId": packet_id}, ["IN", "NO", "YES"]]:
        assert client.put(f"{BASE}/answers/200", headers=AUTH, json=body).status_code == 400
    assert client.put(f"{BASE}/answers/unknown", headers=AUTH, json=valid_answer(packet_id)).status_code == 400
    assert event_count(db_path) == 0


def test_packet_revision_has_separate_answer_projection(review_context):
    manifest, db_path = review_context
    client = new_client()
    packet_id = client.get(BASE, headers=AUTH).get_json()["packetId"]
    assert client.put(f"{BASE}/answers/200", headers=AUTH, json=valid_answer(packet_id)).status_code == 200
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    revised = new_client().get(BASE, headers=AUTH).get_json()
    assert revised["packetId"] != packet_id
    assert revised["answers"] == {} and revised["completedCount"] == 0
    assert event_count(db_path) == 1


def test_unrelated_database_is_rejected_without_changes(review_context):
    _, db_path = review_context
    db_path.parent.mkdir()
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE account_tags (account_id TEXT)")
        conn.execute("INSERT INTO account_tags VALUES ('legacy')")
    before = db_path.read_bytes()
    response = new_client().get(BASE, headers=AUTH)
    assert response.status_code == 503
    assert "separate" in response.get_json()["error"]
    assert db_path.read_bytes() == before


@pytest.mark.parametrize("variable,value", [
    ("TPOT_DISCOVERY_REVIEW_PACKET", ""), ("TPOT_DISCOVERY_REVIEW_DB", "relative.db"),
])
def test_missing_or_relative_server_config_fails_closed(review_context, monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    response = new_client().get(BASE, headers=AUTH)
    assert response.status_code == 503
    assert variable in response.get_json()["error"]
    assert response.headers["Cache-Control"] == "private, no-store"


def test_app_config_overrides_environment_paths(review_context, monkeypatch):
    manifest, db_path = review_context
    monkeypatch.setenv("TPOT_DISCOVERY_REVIEW_PACKET", "wrong-relative-manifest")
    monkeypatch.setenv("TPOT_DISCOVERY_REVIEW_DB", "wrong-relative-db")
    app = create_app({
        "TESTING": True, "RATELIMIT_ENABLED": False,
        "TPOT_DISCOVERY_REVIEW_PACKET": str(manifest),
        "TPOT_DISCOVERY_REVIEW_DB": str(db_path),
    })
    response = app.test_client().get(BASE, headers=AUTH)
    assert response.status_code == 200
    assert response.get_json()["totalCount"] == 2
    assert event_count(db_path) == 0


@pytest.mark.parametrize("kind,status", [("missing", 500), ("malformed", 503)])
def test_unavailable_or_malformed_packet_has_clear_error_and_no_answers(review_context, kind, status):
    manifest, db_path = review_context
    if kind == "missing":
        manifest.unlink()
    else:
        manifest.write_text("{not valid JSON}")
    response = new_client().get(BASE, headers=AUTH)
    assert response.status_code == status
    assert "packet" in response.get_json()["error"]
    assert response.headers["Cache-Control"] == "private, no-store"
    assert not db_path.exists()
