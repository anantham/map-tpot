"""Adversarial falsifiers for Community Gold Slice 1 integrity claims.

Direct SQL is limited to claimed database invariants and tamper detection.
"""
from __future__ import annotations

from copy import deepcopy
import json
import sqlite3
from typing import Any, Mapping

import pytest

from src.communities.store import upsert_community
from src.data.community_gold.evaluation_frame import freeze_evaluation_frame
from tests.personal_ontology_fixtures import (
    frame_kwargs,
    registered_study_store,
    terminal_access_receipt,
)


pytestmark = pytest.mark.integration


def _assignment(frame: Mapping[str, Any], role: str) -> Mapping[str, Any]:
    return next(row for row in frame["roleAssignments"]
                if row["assignedRole"] == role)


def _record_judgment(
    store: Any,
    frame: Mapping[str, Any],
    assignment: Mapping[str, Any],
    *,
    community_id: str = "comm-a",
    reviewer: str = "human",
    judgment: str = "in",
    context_byte: str = "d",
) -> dict[str, Any]:
    return store.record_study_judgment(
        frame_id=frame["frameId"],
        account_id=assignment["accountId"],
        community_id=community_id,
        reviewer=reviewer,
        judgment=judgment,
        evidence_snapshot_id=frame["evidence"]["snapshotId"],
        evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
        context_hash=context_byte * 64,
        observed_at="2026-07-25T00:00:00+00:00",
    )


def _record_all_terminal_heads(store: Any, frame: Mapping[str, Any]) -> None:
    terminal_rows = [
        row
        for row in frame["roleAssignments"]
        if row["assignedRole"] == "terminal_test"
    ]
    for index, assignment in enumerate(terminal_rows):
        for community_id in ("comm-a", "comm-b"):
            _record_judgment(
                store,
                frame,
                assignment,
                community_id=community_id,
                judgment="in" if index % 2 == 0 else "out",
                context_byte="d" if community_id == "comm-a" else "e",
            )


def _release_terminal(store: Any, frame: Mapping[str, Any]) -> None:
    _record_all_terminal_heads(store, frame)
    store.list_study_judgments(
        frame_id=frame["frameId"],
        purpose="terminal_evaluation",
        reviewer="human",
        accessed_by="terminal-verifier",
        access_receipt=terminal_access_receipt(),
    )


def _freeze_sibling_frame(store: Any) -> dict[str, Any]:
    store.register_ontology_task(
        user_id="user-aditya",
        ontology_id="personal-subcultures",
        ontology_version=1,
        task_id="competence",
        target_type="competence",
        definition={"question": "Does this account demonstrate competence?"},
    )
    kwargs = deepcopy(frame_kwargs())
    kwargs["frame_id"] = "synthetic-frame-competence-v1"
    kwargs["scope"]["taskId"] = "competence"
    frame = freeze_evaluation_frame(**kwargs)
    store.freeze_study(frame)
    return frame


def test_empty_terminal_release_does_not_consume_study(tmp_path) -> None:
    store, frame = registered_study_store(tmp_path / "archive_tweets.db")

    with pytest.raises(
        ValueError,
        match="terminal|release|coverage|judgment",
    ):
        store.list_study_judgments(
            frame_id=frame["frameId"],
            purpose="terminal_evaluation",
            accessed_by="terminal-verifier",
            access_receipt=terminal_access_receipt(),
        )

    assert store.get_study(frame["frameId"])["terminalAccessConsumed"] is False
    _record_judgment(
        store,
        frame,
        _assignment(frame, "model_development"),
    )


def test_reviewer_filtered_empty_release_does_not_consume_study(tmp_path) -> None:
    store, frame = registered_study_store(tmp_path / "archive_tweets.db")
    terminal = _assignment(frame, "terminal_test")
    _record_judgment(store, frame, terminal, reviewer="human")

    with pytest.raises(
        ValueError,
        match="terminal|release|coverage|judgment",
    ):
        store.list_study_judgments(
            frame_id=frame["frameId"],
            purpose="terminal_evaluation",
            reviewer="reviewer-typo",
            accessed_by="terminal-verifier",
            access_receipt=terminal_access_receipt(),
        )

    assert store.get_study(frame["frameId"])["terminalAccessConsumed"] is False
    _record_judgment(store, frame, terminal, reviewer="human",
                     judgment="out", context_byte="e")


def test_registered_ontology_rejects_appended_group(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    registered_study_store(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        upsert_community(conn, "comm-c", "Community C", color="#333333")
        with pytest.raises(sqlite3.IntegrityError, match="immutable ontology"):
            conn.execute(
                """
                INSERT INTO personal_ontology_group (
                    user_id, ontology_id, ontology_version, community_id,
                    boundary_definition
                ) VALUES ('user-aditya', 'personal-subcultures', 1,
                          'comm-c', 'injected boundary')
                """
            )


def test_scoped_judgment_head_rejects_delete(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    stored = _record_judgment(
        store, frame, _assignment(frame, "model_development")
    )

    with sqlite3.connect(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="head|immutable"):
            conn.execute(
                "DELETE FROM account_community_gold_head WHERE label_set_id = ?",
                (stored["labelSetId"],),
            )


def test_scoped_judgment_head_rejects_rewind(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    assignment = _assignment(frame, "model_development")
    first = _record_judgment(store, frame, assignment)
    _record_judgment(store, frame, assignment, judgment="out",
                     context_byte="e")

    with sqlite3.connect(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError,
                           match="head|rewind|supersed"):
            conn.execute(
                """
                UPDATE account_community_gold_head
                SET label_set_id = ?
                WHERE frame_id = ? AND account_id = ?
                  AND community_id = 'comm-a' AND reviewer = 'human'
                """,
                (
                    first["labelSetId"],
                    frame["frameId"],
                    assignment["accountId"],
                ),
            )


@pytest.mark.parametrize("write_kind", ["judgment", "prediction"])
def test_terminal_release_seals_frames_sharing_role_registry(
    tmp_path, write_kind: str
) -> None:
    store, released_frame = registered_study_store(
        tmp_path / "archive_tweets.db")
    sibling = _freeze_sibling_frame(store)
    _release_terminal(store, released_frame)
    account = _assignment(sibling, "model_development")

    with pytest.raises(ValueError, match="sealed|terminal release"):
        if write_kind == "judgment":
            _record_judgment(store, sibling, account)
        else:
            store.record_prediction(
                prediction_id="sibling-after-release",
                frame_id=sibling["frameId"],
                account_id=account["accountId"],
                community_id="comm-a",
                model_run_id="late-run",
                score=0.4,
                score_semantics="affinity",
                evidence_snapshot_id=sibling["evidence"]["snapshotId"],
                evidence_snapshot_hash=sibling["evidence"]["snapshotHash"],
                context_hash="d" * 64,
                observed_at="2026-07-25T00:00:00+00:00",
            )


@pytest.mark.parametrize("column", [
    "access_receipt_json",
    "release_manifest_json",
])
def test_terminal_access_rejects_forged_payload_on_read(
    tmp_path, column: str
) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    _release_terminal(store, frame)

    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TRIGGER prevent_immutable_terminal_access_update")
        conn.execute(
            f"""UPDATE account_community_terminal_test_access
                SET {column} = ? WHERE frame_id = ?""",
            (json.dumps({"forged": True}), frame["frameId"]),
        )
        conn.commit()

    with pytest.raises(
        (ValueError, RuntimeError),
        match="terminal|receipt|manifest|hash",
    ):
        store.get_study(frame["frameId"])


def test_database_rejects_direct_calibrated_probability_insert(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    _, frame = registered_study_store(db_path)
    account = _assignment(frame, "model_development")

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError, match="calibrat"):
            conn.execute(
                """
                INSERT INTO account_community_prediction
                (prediction_id, frame_id, account_id, community_id,
                 model_run_id, score, score_semantics,
                 calibration_record_hash, evidence_snapshot_id,
                 evidence_snapshot_hash, context_hash, observed_at,
                 predicted_at, payload_hash)
                VALUES (?, ?, ?, 'comm-a', 'forged-run', 0.8,
                        'calibrated_probability', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "forged-calibrated-probability",
                    frame["frameId"],
                    account["accountId"],
                    "9" * 64,
                    frame["evidence"]["snapshotId"],
                    frame["evidence"]["snapshotHash"],
                    "d" * 64,
                    "2026-07-25T00:00:00+00:00",
                    "2026-07-25T01:00:00+00:00",
                    "f" * 64,
                ),
            )
