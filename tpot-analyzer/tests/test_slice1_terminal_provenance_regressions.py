"""Behavioral regressions for terminal ontology and access provenance."""
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


def _access_count(db_path: Any) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM account_community_terminal_test_access"
            ).fetchone()[0]
        )


def _release(store: Any, frame: dict[str, Any]) -> None:
    store.list_study_judgments(
        frame_id=frame["frameId"],
        purpose="terminal_evaluation",
        reviewer="human",
        accessed_by="terminal-verifier",
        access_receipt=terminal_access_receipt(),
    )


@pytest.mark.parametrize(
    ("table", "trigger", "where_sql"),
    [
        (
            "personal_ontology_version",
            "prevent_immutable_ontology_version_update",
            "user_id = 'user-aditya' AND ontology_id = "
            "'personal-subcultures' AND ontology_version = 1",
        ),
        (
            "personal_ontology_task",
            "prevent_immutable_ontology_task_update",
            "user_id = 'user-aditya' AND ontology_id = "
            "'personal-subcultures' AND ontology_version = 1 "
            "AND task_id = 'affiliation'",
        ),
    ],
)
def test_definition_hash_corruption_blocks_release(
    tmp_path,
    table: str,
    trigger: str,
    where_sql: str,
) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    record_complete_terminal_judgments(store, frame)

    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(f"DROP TRIGGER {trigger}")
            conn.execute(
                f"UPDATE {table} SET definition_hash = ? WHERE {where_sql}",
                ("f" * 64,),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        assert _access_count(db_path) == 0
        return

    with pytest.raises(
        (ValueError, RuntimeError, sqlite3.IntegrityError),
        match="ontology|task|definition|hash|terminal",
    ):
        _release(store, frame)
    assert _access_count(db_path) == 0


def test_forged_terminal_actor_and_time_are_rejected(tmp_path) -> None:
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
                SET accessed_by = 'forged-actor',
                    accessed_at = '2026-07-26T05:00:00+00:00'
                WHERE frame_id = ?
                """,
                (frame["frameId"],),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        return

    with pytest.raises(
        (ValueError, RuntimeError),
        match="access|receipt|provenance|hash|actor|time",
    ):
        store.get_study(frame["frameId"])
