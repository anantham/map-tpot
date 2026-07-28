"""Direct query-contract test for purpose-gated scoped judgment heads."""
from __future__ import annotations

import sqlite3

import pytest

from src.data.community_gold.judgment_rows import current_study_rows
from tests.personal_ontology_fixtures import registered_study_store


@pytest.mark.integration
def test_training_query_returns_no_terminal_role_rows(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    development = next(
        row
        for row in frame["roleAssignments"]
        if row["assignedRole"] == "model_development"
    )
    terminal = next(
        row
        for row in frame["roleAssignments"]
        if row["assignedRole"] == "terminal_test"
    )
    for assignment in (development, terminal):
        store.record_study_judgment(
            frame_id=frame["frameId"],
            account_id=assignment["accountId"],
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
        rows = current_study_rows(
            conn,
            frame_id=frame["frameId"],
            reviewer="human",
            allowed_roles={"model_development"},
            fixed_accounts=set(),
        )

    assert [row["account_id"] for row in rows] == [
        development["accountId"]
    ]
    assert terminal["accountId"] not in {
        str(row["account_id"]) for row in rows
    }
