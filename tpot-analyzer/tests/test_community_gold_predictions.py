from __future__ import annotations

import sqlite3

import pytest

from tests.personal_ontology_fixtures import (
    record_complete_terminal_judgments,
    registered_study_store,
    terminal_access_receipt,
)


@pytest.mark.integration
def test_predictions_are_immutable_scoped_and_not_human_judgments(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    account_id = frame["roleAssignments"][0]["accountId"]

    created = store.record_prediction(
        prediction_id="prediction-1",
        frame_id=frame["frameId"],
        account_id=account_id,
        community_id="comm-a",
        model_run_id="local-model-run-1",
        score=0.73,
        score_semantics="affinity",
        evidence_snapshot_id=frame["evidence"]["snapshotId"],
        evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
        context_hash="d" * 64,
        observed_at="2026-07-25T00:00:00+00:00",
    )
    exact = store.record_prediction(
        prediction_id="prediction-1",
        frame_id=frame["frameId"],
        account_id=account_id,
        community_id="comm-a",
        model_run_id="local-model-run-1",
        score=0.73,
        score_semantics="affinity",
        evidence_snapshot_id=frame["evidence"]["snapshotId"],
        evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
        context_hash="d" * 64,
        observed_at="2026-07-25T00:00:00+00:00",
    )

    assert created["created"] is True
    assert exact["created"] is False
    predictions = store.list_predictions(frame_id=frame["frameId"])
    assert len(predictions) == 1
    assert predictions[0]["scoreSemantics"] == "affinity"
    assert predictions[0]["ontologyScope"]["taskId"] == "affiliation"
    assert store.list_study_judgments(
        frame_id=frame["frameId"],
        purpose="training",
    ) == []

    with pytest.raises(ValueError, match="immutable prediction"):
        store.record_prediction(
            prediction_id="prediction-1",
            frame_id=frame["frameId"],
            account_id=account_id,
            community_id="comm-a",
            model_run_id="local-model-run-1",
            score=0.20,
            score_semantics="affinity",
            evidence_snapshot_id=frame["evidence"]["snapshotId"],
            evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
            context_hash="d" * 64,
            observed_at="2026-07-25T00:00:00+00:00",
        )


@pytest.mark.integration
def test_calibrated_probability_requires_calibration_receipt(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    account_id = frame["roleAssignments"][0]["accountId"]

    with pytest.raises(ValueError, match="calibration_record_hash"):
        store.record_prediction(
            prediction_id="prediction-probability",
            frame_id=frame["frameId"],
            account_id=account_id,
            community_id="comm-a",
            model_run_id="model-run",
            score=0.6,
            score_semantics="calibrated_probability",
            evidence_snapshot_id=frame["evidence"]["snapshotId"],
            evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
            context_hash="d" * 64,
            observed_at="2026-07-25T00:00:00+00:00",
        )

    with pytest.raises(ValueError, match="not available"):
        store.record_prediction(
            prediction_id="prediction-forged-probability",
            frame_id=frame["frameId"],
            account_id=account_id,
            community_id="comm-a",
            model_run_id="model-run",
            score=0.6,
            score_semantics="calibrated_probability",
            calibration_record_hash="9" * 64,
            evidence_snapshot_id=frame["evidence"]["snapshotId"],
            evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
            context_hash="d" * 64,
            observed_at="2026-07-25T00:00:00+00:00",
        )


@pytest.mark.integration
def test_prediction_rejects_wrong_evidence_generation(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    account_id = frame["roleAssignments"][0]["accountId"]

    with pytest.raises(ValueError, match="evidence_snapshot_hash mismatch"):
        store.record_prediction(
            prediction_id="prediction-wrong-evidence",
            frame_id=frame["frameId"],
            account_id=account_id,
            community_id="comm-a",
            model_run_id="model-run",
            score=0.6,
            score_semantics="affinity",
            evidence_snapshot_id=frame["evidence"]["snapshotId"],
            evidence_snapshot_hash="f" * 64,
            context_hash="d" * 64,
            observed_at="2026-07-25T00:00:00+00:00",
        )


@pytest.mark.integration
def test_terminal_release_seals_new_predictions(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    record_complete_terminal_judgments(store, frame)
    store.list_study_judgments(
        frame_id=frame["frameId"],
        purpose="terminal_evaluation",
        reviewer="human",
        accessed_by="terminal-verifier",
        access_receipt=terminal_access_receipt(),
    )

    with pytest.raises(ValueError, match="sealed"):
        store.record_prediction(
            prediction_id="too-late",
            frame_id=frame["frameId"],
            account_id=frame["roleAssignments"][0]["accountId"],
            community_id="comm-a",
            model_run_id="late-run",
            score=0.4,
            score_semantics="affinity",
            evidence_snapshot_id=frame["evidence"]["snapshotId"],
            evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
            context_hash="d" * 64,
            observed_at="2026-07-25T00:00:00+00:00",
        )


@pytest.mark.integration
def test_prediction_rows_are_database_immutable_and_digest_checked(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    account_id = frame["roleAssignments"][0]["accountId"]
    store.record_prediction(
        prediction_id="prediction-tamper-check",
        frame_id=frame["frameId"],
        account_id=account_id,
        community_id="comm-a",
        model_run_id="model-run",
        score=0.6,
        score_semantics="affinity",
        evidence_snapshot_id=frame["evidence"]["snapshotId"],
        evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
        context_hash="d" * 64,
        observed_at="2026-07-25T00:00:00+00:00",
    )
    with sqlite3.connect(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="immutable prediction"):
            conn.execute(
                """
                UPDATE account_community_prediction
                SET score = 0.2
                WHERE prediction_id = 'prediction-tamper-check'
                """
            )
        conn.execute("DROP TRIGGER prevent_scoped_prediction_update")
        conn.execute(
            """
            UPDATE account_community_prediction
            SET score = 0.2
            WHERE prediction_id = 'prediction-tamper-check'
            """
        )
        conn.commit()

    with pytest.raises(ValueError, match="prediction payload hash mismatch"):
        store.list_predictions(frame_id=frame["frameId"])
