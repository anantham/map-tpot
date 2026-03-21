from __future__ import annotations

import sqlite3

import pytest

from src.communities.store import init_db, upsert_community, upsert_community_account
from src.data.community_gold import CommunityGoldStore


def _seed_archive_schema(db_path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        init_db(conn)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                account_id TEXT PRIMARY KEY,
                username TEXT,
                display_name TEXT
            );
            """
        )
        upsert_community(conn, "comm-a", "Community A", color="#111111")
        upsert_community(conn, "comm-b", "Community B", color="#222222")
        upsert_community_account(conn, "comm-a", "acct-1", 0.8, "human")
        conn.execute(
            "INSERT INTO profiles (account_id, username, display_name) VALUES (?, ?, ?)",
            ("acct-1", "alice", "Alice"),
        )
        conn.commit()


@pytest.mark.integration
def test_community_gold_store_split_is_per_account_and_history_is_immutable(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    _seed_archive_schema(db_path)
    store = CommunityGoldStore(db_path)

    first = store.upsert_label(
        account_id="acct-1",
        community_id="comm-a",
        reviewer="human",
        judgment="in",
        confidence=0.9,
        note="core member",
    )
    second = store.upsert_label(
        account_id="acct-1",
        community_id="comm-b",
        reviewer="human",
        judgment="out",
        confidence=0.7,
        note="explicit boundary",
    )
    assert first["split"] == second["split"]

    updated = store.upsert_label(
        account_id="acct-1",
        community_id="comm-a",
        reviewer="human",
        judgment="abstain",
    )
    assert updated["supersedesLabelSetId"] == first["labelSetId"]

    labels = store.list_labels(account_id="acct-1", include_inactive=True, limit=10)
    active = [row for row in labels if row["isActive"]]
    inactive = [row for row in labels if not row["isActive"]]
    assert len(active) == 2
    assert len(inactive) == 1
    assert any(row["judgment"] == "abstain" for row in active)
    assert any(row["judgment"] == "in" for row in inactive)


@pytest.mark.integration
def test_community_gold_metrics_report_zero_split_leakage(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    _seed_archive_schema(db_path)
    store = CommunityGoldStore(db_path)

    store.upsert_label(account_id="acct-1", community_id="comm-a", reviewer="human", judgment="in")
    store.upsert_label(account_id="acct-2", community_id="comm-a", reviewer="human", judgment="out")

    metrics = store.metrics()
    assert metrics["totalActiveLabels"] == 2
    assert metrics["judgmentCounts"]["in"] == 1
    assert metrics["judgmentCounts"]["out"] == 1
    assert metrics["leakageChecks"]["duplicateActiveLabels"] == 0
    assert metrics["leakageChecks"]["accountsWithMultipleSplits"] == 0
