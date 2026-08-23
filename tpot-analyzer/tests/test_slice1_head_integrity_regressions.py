"""Behavioral regressions for scoped judgment-head integrity."""
from __future__ import annotations

import sqlite3
from typing import Any, Mapping

import pytest

from tests.personal_ontology_fixtures import (
    record_complete_terminal_judgments,
    registered_study_store,
    terminal_access_receipt,
)


pytestmark = pytest.mark.integration


def _access_count(db_path: Any) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM account_community_terminal_test_access"
            ).fetchone()[0]
        )


def _insert_successor(
    conn: sqlite3.Connection,
    *,
    prior: sqlite3.Row,
    account_id: str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO account_community_gold_label_set
        (account_id, community_id, reviewer, judgment, confidence, note,
         evidence_json, is_active, created_at, supersedes_label_set_id,
         user_id, ontology_id, ontology_version, task_id, study_frame_id,
         evidence_snapshot_id, evidence_snapshot_hash, context_hash,
         observed_at, identity_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                'scoped')
        """,
        (
            account_id,
            prior["community_id"],
            prior["reviewer"],
            "out" if prior["judgment"] != "out" else "in",
            prior["confidence"],
            "adversarial successor",
            prior["evidence_json"],
            "2026-07-25T23:00:00+00:00",
            prior["id"],
            prior["user_id"],
            prior["ontology_id"],
            prior["ontology_version"],
            prior["task_id"],
            prior["study_frame_id"],
            prior["evidence_snapshot_id"],
            prior["evidence_snapshot_hash"],
            "e" * 64,
            prior["observed_at"],
        ),
    )
    return int(cursor.lastrowid)


def _head_row(
    conn: sqlite3.Connection,
    label_set_id: int,
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM account_community_gold_label_set WHERE id = ?",
        (label_set_id,),
    ).fetchone()
    assert row is not None
    return row


def test_stale_terminal_head_cannot_consume_access(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    terminal_heads = record_complete_terminal_judgments(store, frame)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        prior = _head_row(conn, terminal_heads[0]["labelSetId"])
        try:
            _insert_successor(
                conn,
                prior=prior,
                account_id=str(prior["account_id"]),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            assert _access_count(db_path) == 0
            return

    with pytest.raises(
        (ValueError, RuntimeError, sqlite3.IntegrityError),
        match="head|successor|lineage|current|terminal",
    ):
        store.list_study_judgments(
            frame_id=frame["frameId"],
            purpose="terminal_evaluation",
            reviewer="human",
            accessed_by="terminal-verifier",
            access_receipt=terminal_access_receipt(),
        )

    assert _access_count(db_path) == 0


def test_head_update_cannot_move_natural_identity(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    development = [
        row
        for row in frame["roleAssignments"]
        if row["assignedRole"] == "model_development"
    ]
    first = store.record_study_judgment(
        frame_id=frame["frameId"],
        account_id=development[0]["accountId"],
        community_id="comm-a",
        reviewer="human",
        judgment="in",
        evidence_snapshot_id=frame["evidence"]["snapshotId"],
        evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
        context_hash="d" * 64,
        observed_at="2026-07-25T00:00:00+00:00",
    )

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        prior = _head_row(conn, first["labelSetId"])
        with pytest.raises(
            sqlite3.IntegrityError,
            match="identity|head|supersed",
        ):
            successor_id = _insert_successor(
                conn,
                prior=prior,
                account_id=development[1]["accountId"],
            )
            conn.execute(
                """
                UPDATE account_community_gold_head
                SET account_id = ?, label_set_id = ?,
                    updated_at = '2026-07-25T23:00:00+00:00'
                WHERE label_set_id = ?
                """,
                (
                    development[1]["accountId"],
                    successor_id,
                    prior["id"],
                ),
            )
