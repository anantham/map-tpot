"""Behavioral isolation checks for the legacy Community Gold adapter.

Test intent:
- Scoped judgments never appear in legacy label, count, or metric responses.
- Scoped judgments neither suppress nor train the legacy candidate queue.
- Scoped judgments never change the legacy evaluator's samples.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.data.community_gold import CommunityGoldStore
from tests.personal_ontology_fixtures import seed_community_db


REVIEWER = "human"


def _insert_scoped_label(
    conn: sqlite3.Connection,
    *,
    account_id: str,
    community_id: str,
    judgment: str,
    split: str,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO account_community_gold_split
        (account_id, split, assigned_by, assigned_at)
        VALUES (?, ?, 'scoped-fixture', '2026-07-26T00:00:00+00:00')
        """,
        (account_id, split),
    )
    conn.execute(
        """
        INSERT INTO account_community_gold_label_set
        (account_id, community_id, reviewer, judgment, confidence, note,
         evidence_json, is_active, created_at, supersedes_label_set_id,
         user_id, ontology_id, ontology_version, task_id, study_frame_id,
         evidence_snapshot_id, evidence_snapshot_hash, context_hash,
         observed_at, identity_status)
        VALUES (
            ?, ?, ?, ?, 0.8, 'scoped fixture', '{}', 1,
            '2026-07-26T00:01:00+00:00', NULL,
            'user-aditya', 'personal-subcultures', 1, 'affiliation',
            'frame-scoped-v1', 'snapshot-scoped-v1', ?, ?,
            '2026-07-25T00:00:00+00:00', 'scoped'
        )
        """,
        (
            account_id,
            community_id,
            REVIEWER,
            judgment,
            "a" * 64,
            "b" * 64,
        ),
    )


def _seed_mixed_store(db_path: Path) -> CommunityGoldStore:
    seed_community_db(db_path)
    store = CommunityGoldStore(db_path)

    legacy_rows = (
        ("legacy-train-in", "in", "train"),
        ("legacy-train-out", "out", "train"),
        ("legacy-dev-in", "in", "dev"),
        ("legacy-dev-out", "out", "dev"),
    )
    for account_id, judgment, _split in legacy_rows:
        store.upsert_label(
            account_id=account_id,
            community_id="comm-a",
            reviewer=REVIEWER,
            judgment=judgment,
        )

    with sqlite3.connect(db_path) as conn:
        for account_id, _judgment, split in legacy_rows:
            conn.execute(
                """
                UPDATE account_community_gold_split
                SET split = ?
                WHERE account_id = ?
                """,
                (split, account_id),
            )

        scoped_a = (
            ("scoped-train-in", "in", "train"),
            ("scoped-train-out", "out", "train"),
            ("scoped-dev-in", "in", "dev"),
            ("scoped-dev-out", "out", "dev"),
        )
        for account_id, judgment, split in scoped_a:
            _insert_scoped_label(
                conn,
                account_id=account_id,
                community_id="comm-a",
                judgment=judgment,
                split=split,
            )

        for account_id, judgment in (
            ("scoped-b-in", "in"),
            ("scoped-b-out", "out"),
        ):
            _insert_scoped_label(
                conn,
                account_id=account_id,
                community_id="comm-b",
                judgment=judgment,
                split="train",
            )

        canonical_rows = [
            (account_id, "comm-a", weight)
            for account_id, weight in (
                ("legacy-train-in", 0.9),
                ("legacy-train-out", 0.1),
                ("legacy-dev-in", 0.8),
                ("legacy-dev-out", 0.2),
                ("scoped-train-in", 0.7),
                ("scoped-train-out", 0.3),
                ("scoped-dev-in", 0.6),
                ("scoped-dev-out", 0.4),
            )
        ]
        canonical_rows.extend(
            [
                ("scoped-b-in", "comm-b", 0.8),
                ("scoped-b-out", "comm-b", 0.2),
                ("legacy-b-candidate", "comm-b", 0.6),
            ]
        )
        conn.executemany(
            """
            INSERT INTO community_account
            (account_id, community_id, weight, source, updated_at)
            VALUES (?, ?, ?, 'human', '2026-07-26T00:02:00+00:00')
            """,
            canonical_rows,
        )
        conn.commit()

    (db_path.parent / "graph_snapshot.louvain.json").write_text(
        json.dumps(
            {
                "scoped-b-in": 1,
                "scoped-b-out": 2,
                "legacy-b-candidate": 1,
            }
        ),
        encoding="utf-8",
    )
    return store


@pytest.mark.integration
def test_legacy_read_surfaces_exclude_scoped_labels(tmp_path: Path) -> None:
    store = _seed_mixed_store(tmp_path / "archive_tweets.db")

    labels = store.list_labels(reviewer=REVIEWER, include_inactive=True)
    assert {row["accountId"] for row in labels} == {
        "legacy-train-in",
        "legacy-train-out",
        "legacy-dev-in",
        "legacy-dev-out",
    }
    assert {row["identityStatus"] for row in labels} == {"legacy_unbound"}

    communities = {row["id"]: row for row in store.list_communities()}
    assert communities["comm-a"]["goldLabelCount"] == 4
    assert communities["comm-b"]["goldLabelCount"] == 0

    metrics = store.metrics()
    assert metrics["totalActiveLabels"] == 4
    assert metrics["labeledAccountCount"] == 4
    assert metrics["judgmentCounts"] == {"in": 2, "out": 2, "abstain": 0}
    assert metrics["reviewerCounts"] == {REVIEWER: 4}
    assert metrics["splitCounts"]["train"]["labelCount"] == 2
    assert metrics["splitCounts"]["dev"]["labelCount"] == 2


@pytest.mark.integration
def test_legacy_candidate_and_evaluator_ignore_scoped_labels(
    tmp_path: Path,
) -> None:
    store = _seed_mixed_store(tmp_path / "archive_tweets.db")

    candidates = store.list_review_candidates(
        reviewer=REVIEWER,
        community_id="comm-b",
        limit=10,
    )
    by_account = {row["accountId"]: row for row in candidates}
    assert {"scoped-b-in", "scoped-b-out", "legacy-b-candidate"} <= set(
        by_account
    )
    assert {row["selectionMode"] for row in candidates} == {"cold"}

    result = store.evaluate_scoreboard(
        split="dev",
        train_split="train",
        reviewer=REVIEWER,
        methods=["canonical_map"],
        community_ids=["comm-a"],
    )
    counts = result["communities"][0]["sampleCounts"]
    assert counts["train"] == {"in": 1, "out": 1, "abstain": 0}
    assert counts["dev"] == {"in": 1, "out": 1, "abstain": 0}
