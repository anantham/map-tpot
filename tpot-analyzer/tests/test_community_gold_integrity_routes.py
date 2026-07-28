from __future__ import annotations

from pathlib import Path

import pytest

import src.api.routes.community_gold as community_gold_routes
from src.api.server import create_app
from src.data.community_gold.evaluation_frame import freeze_evaluation_frame
from tests.personal_ontology_fixtures import (
    frame_kwargs,
    seed_community_db,
    terminal_access_receipt,
)

CURATOR_TOKEN = "integrity-route-test-token"


@pytest.fixture
def integrity_client(
    tmp_path: Path,
    temp_snapshot_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    db_path = tmp_path / "archive_tweets.db"
    seed_community_db(db_path)
    monkeypatch.setenv("ARCHIVE_DB_PATH", str(db_path))
    monkeypatch.setenv("TPOT_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", CURATOR_TOKEN)
    community_gold_routes._community_gold_store = None
    community_gold_routes._community_gold_store_path = None
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        client.environ_base[
            "HTTP_X_TPOT_CURATOR_TOKEN"
        ] = CURATOR_TOKEN
        yield client


def _register_study(client):
    ontology = client.post(
        "/api/community-gold/ontologies",
        json={
            "userId": "user-aditya",
            "ontologyId": "personal-subcultures",
            "ontologyVersion": 1,
            "definition": {
                "groups": [
                    {"communityId": "comm-a", "definition": "A"},
                    {"communityId": "comm-b", "definition": "B"},
                ]
            },
        },
    )
    assert ontology.status_code == 201
    task = client.post(
        "/api/community-gold/tasks",
        json={
            "userId": "user-aditya",
            "ontologyId": "personal-subcultures",
            "ontologyVersion": 1,
            "taskId": "affiliation",
            "targetType": "affiliation",
            "definition": {"question": "Affiliation?"},
        },
    )
    assert task.status_code == 201
    frame = freeze_evaluation_frame(**frame_kwargs())
    study = client.post(
        "/api/community-gold/studies",
        json={"frame": frame},
    )
    assert study.status_code == 201
    return frame


@pytest.mark.integration
def test_integrity_routes_are_registered_by_production_app(integrity_client) -> None:
    frame = _register_study(integrity_client)

    response = integrity_client.get(
        f"/api/community-gold/studies/{frame['frameId']}"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["manifestDigest"] == frame["manifestDigest"]
    assert payload["roleIdentitiesWithheld"] is True
    assert "seed" not in payload["roleRegistry"]
    for private_field in (
        "u0AccountIds",
        "fixedTrainingIds",
        "fixedChallengeIds",
        "uEvalAccountIds",
        "uRichAccountIds",
        "strataByAccount",
        "roleAssignments",
        "roleAssignmentsDigest",
    ):
        assert private_field not in payload


@pytest.mark.integration
def test_integrity_routes_fail_closed_without_curator_token(
    integrity_client,
) -> None:
    integrity_client.environ_base.pop(
        "HTTP_X_TPOT_CURATOR_TOKEN",
        None,
    )

    response = integrity_client.post(
        "/api/community-gold/ontologies",
        json={},
    )

    assert response.status_code == 401
    assert "curator token" in response.get_json()["error"]


@pytest.mark.integration
def test_scoped_judgment_routes_enforce_role_access(integrity_client) -> None:
    frame = _register_study(integrity_client)
    development = next(
        row
        for row in frame["roleAssignments"]
        if row["assignedRole"] == "model_development"
    )
    terminal = [
        row
        for row in frame["roleAssignments"]
        if row["assignedRole"] == "terminal_test"
    ]
    judgment_inputs = [(development, "comm-a", "in")]
    for index, assignment in enumerate(terminal):
        for community_id in ("comm-a", "comm-b"):
            judgment_inputs.append(
                (
                    assignment,
                    community_id,
                    ("in", "out", "abstain")[index % 3],
                )
            )
    for assignment, community_id, judgment in judgment_inputs:
        response = integrity_client.post(
            f"/api/community-gold/studies/{frame['frameId']}/judgments",
            json={
                "accountId": assignment["accountId"],
                "communityId": community_id,
                "reviewer": "human",
                "judgment": judgment,
                "evidenceSnapshotId": frame["evidence"]["snapshotId"],
                "evidenceSnapshotHash": frame["evidence"]["snapshotHash"],
                "contextHash": (
                    ("d" if judgment == "in" else "e") * 64
                ),
                "observedAt": "2026-07-25T00:00:00+00:00",
            },
        )
        assert response.status_code == 201
        assert "role" not in response.get_json()

    training = integrity_client.get(
        f"/api/community-gold/studies/{frame['frameId']}/judgments"
        "?purpose=training&reviewer=human"
    )
    assert training.status_code == 200
    training_rows = training.get_json()["judgments"]
    assert [row["accountId"] for row in training_rows] == [
        development["accountId"]
    ]
    assert all("role" not in row for row in training_rows)

    forbidden_get = integrity_client.get(
        f"/api/community-gold/studies/{frame['frameId']}/judgments"
        "?purpose=terminal_evaluation"
    )
    assert forbidden_get.status_code == 400
    assert "terminal-test endpoint" in forbidden_get.get_json()["error"]

    terminal_response = integrity_client.post(
        f"/api/community-gold/studies/{frame['frameId']}/terminal-test",
        json={
            "reviewer": "human",
            "accessedBy": "terminal-verifier",
            "accessReceipt": terminal_access_receipt(),
        },
    )
    assert terminal_response.status_code == 200
    released = terminal_response.get_json()["judgments"]
    assert len(released) == len(terminal) * 2
    assert {row["accountId"] for row in released} == {
        row["accountId"] for row in terminal
    }
    assert all("role" not in row for row in released)
    assert terminal_response.get_json()["terminalAccess"]["coverage"][
        "complete"
    ] is True

    repeated = integrity_client.post(
        f"/api/community-gold/studies/{frame['frameId']}/terminal-test",
        json={
            "reviewer": "human",
            "accessedBy": "terminal-verifier",
            "accessReceipt": {"repeat": True},
        },
    )
    assert repeated.status_code == 409
    assert "already consumed" in repeated.get_json()["error"]


@pytest.mark.integration
def test_prediction_routes_keep_score_semantics_explicit(integrity_client) -> None:
    frame = _register_study(integrity_client)
    account_id = frame["roleAssignments"][0]["accountId"]
    response = integrity_client.post(
        "/api/community-gold/predictions",
        json={
            "predictionId": "prediction-route-1",
            "frameId": frame["frameId"],
            "accountId": account_id,
            "communityId": "comm-a",
            "modelRunId": "local-run",
            "score": 0.75,
            "scoreSemantics": "affinity",
            "evidenceSnapshotId": frame["evidence"]["snapshotId"],
            "evidenceSnapshotHash": frame["evidence"]["snapshotHash"],
            "contextHash": "d" * 64,
            "observedAt": "2026-07-25T00:00:00+00:00",
        },
    )
    assert response.status_code == 201
    assert "role" not in response.get_json()

    listed = integrity_client.get(
        f"/api/community-gold/predictions?frameId={frame['frameId']}"
    )
    assert listed.status_code == 200
    payload = listed.get_json()
    assert payload["count"] == 1
    assert payload["predictions"][0]["scoreSemantics"] == "affinity"
    assert "role" not in payload["predictions"][0]

    legacy = integrity_client.get(
        f"/api/community-gold/labels?accountId={account_id}"
    )
    assert legacy.status_code == 200
    assert legacy.get_json()["labels"] == []
