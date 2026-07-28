"""HTTP behavior for first terminal release, replay, and conflict."""
from __future__ import annotations

import sqlite3

import pytest
from flask import Flask

from src.api.routes.community_gold_integrity import (
    community_gold_integrity_bp,
)
from tests.personal_ontology_fixtures import (
    record_complete_terminal_judgments,
    registered_study_store,
    terminal_access_receipt,
)


CURATOR_TOKEN = "terminal-delivery-route-token"


@pytest.fixture
def delivery_client(tmp_path, monkeypatch):
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    record_complete_terminal_judgments(store, frame)
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", CURATOR_TOKEN)
    monkeypatch.setattr(
        "src.api.routes.community_gold._get_store",
        lambda: store,
    )
    app = Flask(__name__)
    app.testing = False
    app.register_blueprint(community_gold_integrity_bp)
    client = app.test_client()
    client.environ_base["HTTP_X_TPOT_CURATOR_TOKEN"] = CURATOR_TOKEN
    return client, db_path, store, frame


def _body(receipt=None):
    return {
        "reviewer": "human",
        "accessedBy": "terminal-verifier",
        "accessReceipt": (
            terminal_access_receipt()
            if receipt is None
            else receipt
        ),
    }


@pytest.mark.integration
def test_route_does_not_reload_study_after_release_and_can_replay(
    delivery_client,
    monkeypatch,
) -> None:
    client, db_path, store, frame = delivery_client

    def forbidden_post_commit_reload(_frame_id):
        raise AssertionError("terminal route must not reload study")

    monkeypatch.setattr(store, "get_study", forbidden_post_commit_reload)
    path = (
        f"/api/community-gold/studies/{frame['frameId']}/terminal-test"
    )

    first = client.post(path, json=_body())
    replay = client.post(path, json=_body())

    assert first.status_code == 200
    assert replay.status_code == 200
    first_payload = first.get_json()
    replay_payload = replay.get_json()
    assert first_payload["replayed"] is False
    assert replay_payload["replayed"] is True
    assert replay_payload["judgments"] == first_payload["judgments"]
    assert replay_payload["terminalAccess"] == first_payload["terminalAccess"]
    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) "
            "FROM account_community_terminal_test_access"
        ).fetchone()[0]
    assert count == 1


@pytest.mark.integration
def test_route_maps_release_mismatch_to_409_without_rows(
    delivery_client,
) -> None:
    client, _db_path, _store, frame = delivery_client
    path = (
        f"/api/community-gold/studies/{frame['frameId']}/terminal-test"
    )
    first = client.post(path, json=_body())
    changed = {
        **terminal_access_receipt(),
        "runManifestHash": "6" * 64,
    }

    conflict = client.post(path, json=_body(changed))

    assert first.status_code == 200
    assert conflict.status_code == 409
    payload = conflict.get_json()
    assert "already consumed" in payload["error"]
    assert "judgments" not in payload
