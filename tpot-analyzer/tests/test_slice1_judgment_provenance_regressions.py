"""Regressions for complete terminal judgment and lineage provenance."""
from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from tests.personal_ontology_fixtures import (
    record_complete_terminal_judgments,
    registered_study_store,
    terminal_access_receipt,
)


pytestmark = pytest.mark.integration


def _release(store: Any, frame: dict[str, Any]) -> None:
    store.list_study_judgments(
        frame_id=frame["frameId"],
        purpose="terminal_evaluation",
        reviewer="human",
        accessed_by="terminal-verifier",
        access_receipt=terminal_access_receipt(),
    )


def _head_row(db_path: Any, frame_id: str) -> sqlite3.Row:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT ls.*
            FROM account_community_gold_head head
            JOIN account_community_gold_label_set ls
              ON ls.id = head.label_set_id
            WHERE head.frame_id = ?
            ORDER BY ls.id
            LIMIT 1
            """,
            (frame_id,),
        ).fetchone()
    assert row is not None
    return row


def _insert_successor(
    db_path: Any,
    *,
    prior: sqlite3.Row,
    observed_at: str,
) -> int:
    with sqlite3.connect(db_path) as conn:
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
                prior["account_id"],
                prior["community_id"],
                prior["reviewer"],
                prior["judgment"],
                prior["confidence"],
                prior["note"],
                prior["evidence_json"],
                "2026-07-25T02:00:00+00:00",
                prior["id"],
                prior["user_id"],
                prior["ontology_id"],
                prior["ontology_version"],
                prior["task_id"],
                prior["study_frame_id"],
                prior["evidence_snapshot_id"],
                prior["evidence_snapshot_hash"],
                prior["context_hash"],
                observed_at,
            ),
        )
        successor = int(cursor.lastrowid)
        conn.execute(
            """
            UPDATE account_community_gold_head
            SET label_set_id = ?, updated_at = ?
            WHERE label_set_id = ?
            """,
            (
                successor,
                "2026-07-25T02:00:00+00:00",
                prior["id"],
            ),
        )
        conn.commit()
    return successor


def test_terminal_release_rejects_head_observed_after_cutoff(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    record_complete_terminal_judgments(store, frame)
    prior = _head_row(db_path, frame["frameId"])
    _insert_successor(
        db_path,
        prior=prior,
        observed_at="2027-01-01T00:00:00+00:00",
    )

    with pytest.raises(ValueError, match="cutoff|observed_at"):
        _release(store, frame)
    assert store.get_study(frame["frameId"])["terminalAccessConsumed"] is False


def test_terminal_verifier_detects_full_judgment_tamper(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    record_complete_terminal_judgments(store, frame)
    _release(store, frame)

    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TRIGGER prevent_scoped_gold_update")
        conn.execute(
            """
            UPDATE account_community_gold_label_set
            SET confidence = 0.123, note = 'forged',
                evidence_json = '{"forged":true}',
                user_id = 'forged-user',
                evidence_snapshot_id = 'forged-snapshot'
            WHERE id = (
                SELECT label_set_id
                FROM account_community_gold_head
                WHERE frame_id = ?
                ORDER BY label_set_id
                LIMIT 1
            )
            """,
            (frame["frameId"],),
        )
        conn.commit()

    with pytest.raises(ValueError, match="judgment|payload|identity|snapshot"):
        store.get_study(frame["frameId"])


def test_terminal_verifier_detects_historical_lineage_tamper(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    record_complete_terminal_judgments(store, frame)
    prior = _head_row(db_path, frame["frameId"])
    successor = _insert_successor(
        db_path,
        prior=prior,
        observed_at=str(prior["observed_at"]),
    )
    _release(store, frame)

    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TRIGGER prevent_scoped_gold_update")
        conn.execute(
            """
            UPDATE account_community_gold_label_set
            SET note = 'forged historical note'
            WHERE id = ?
            """,
            (prior["id"],),
        )
        conn.commit()

    assert successor != int(prior["id"])
    with pytest.raises(ValueError, match="lineage|manifest|provenance|hash"):
        store.get_study(frame["frameId"])


def test_fractional_terminal_count_is_rejected(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    record_complete_terminal_judgments(store, frame)
    _release(store, frame)

    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "DROP TRIGGER prevent_immutable_terminal_access_update"
            )
            conn.execute(
                """
                UPDATE account_community_terminal_test_access
                SET released_label_head_count =
                    released_label_head_count + 0.5
                WHERE frame_id = ?
                """,
                (frame["frameId"],),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        return

    with pytest.raises(ValueError, match="integer|count|provenance"):
        store.get_study(frame["frameId"])
