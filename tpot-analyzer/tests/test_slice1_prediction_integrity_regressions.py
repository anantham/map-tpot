"""Behavioral regressions for prediction-domain validation on persisted rows."""
from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from src.artifacts.digests import json_sha256
from tests.personal_ontology_fixtures import registered_study_store


pytestmark = pytest.mark.integration


def _insert_prediction(
    db_path: Any,
    *,
    frame: dict[str, Any],
    prediction_id: str,
    account_id: str,
    score: float,
    semantics: str,
) -> None:
    payload = {
        "predictionId": prediction_id,
        "frameId": frame["frameId"],
        "accountId": account_id,
        "communityId": "comm-a",
        "modelRunId": "adversarial-run",
        "score": score,
        "scoreSemantics": semantics,
        "calibrationRecordHash": None,
        "evidenceSnapshotId": frame["evidence"]["snapshotId"],
        "evidenceSnapshotHash": frame["evidence"]["snapshotHash"],
        "contextHash": "d" * 64,
        "observedAt": "2026-07-25T00:00:00+00:00",
        "predictedAt": "2026-07-25T01:00:00+00:00",
    }
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO account_community_prediction
            (prediction_id, frame_id, account_id, community_id, model_run_id,
             score, score_semantics, calibration_record_hash,
             evidence_snapshot_id, evidence_snapshot_hash, context_hash,
             observed_at, predicted_at, payload_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["predictionId"],
                payload["frameId"],
                payload["accountId"],
                payload["communityId"],
                payload["modelRunId"],
                payload["score"],
                payload["scoreSemantics"],
                payload["calibrationRecordHash"],
                payload["evidenceSnapshotId"],
                payload["evidenceSnapshotHash"],
                payload["contextHash"],
                payload["observedAt"],
                payload["predictedAt"],
                json_sha256(payload),
            ),
        )
        conn.commit()


def _insert_then_read(
    store: Any,
    db_path: Any,
    *,
    frame: dict[str, Any],
    prediction_id: str,
    account_id: str,
    score: float,
    semantics: str,
) -> None:
    _insert_prediction(
        db_path,
        frame=frame,
        prediction_id=prediction_id,
        account_id=account_id,
        score=score,
        semantics=semantics,
    )
    store.list_predictions(frame_id=frame["frameId"])


def test_valid_hash_prediction_outside_u0_is_rejected(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)

    with pytest.raises(
        (ValueError, sqlite3.IntegrityError),
        match="account|U0|study frame|outside",
    ):
        _insert_then_read(
            store,
            db_path,
            frame=frame,
            prediction_id="outside-u0",
            account_id="not-in-u0",
            score=0.7,
            semantics="affinity",
        )


def test_valid_hash_invalid_simplex_score_is_rejected(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)

    with pytest.raises(
        (ValueError, sqlite3.IntegrityError),
        match="simplex|score|range|\\[0, 1\\]",
    ):
        _insert_then_read(
            store,
            db_path,
            frame=frame,
            prediction_id="invalid-simplex",
            account_id=frame["roleAssignments"][0]["accountId"],
            score=2.0,
            semantics="simplex",
        )
