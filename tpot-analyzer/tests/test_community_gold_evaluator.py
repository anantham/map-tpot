"""Behavioral contracts for the legacy account-community evaluator.

Test Intent:
- Keep the legacy scoreboard on the repeatable train-to-development path.
- Expose each method's score meaning without calling diagnostics calibrated.
- Treat missing method output as unknown and report prediction coverage.
- Never emit probability-quality metrics for uncalibrated legacy scores.
"""

from __future__ import annotations

import json
import pickle
import sqlite3
from pathlib import Path

import numpy as np
import pytest
import scipy.sparse as sp

from src.communities.store import init_db, save_memberships, save_run, upsert_community, upsert_community_account
from src.data.community_gold import CommunityGoldStore


def _seed_eval_fixture(snapshot_dir: Path) -> CommunityGoldStore:
    db_path = snapshot_dir / "archive_tweets.db"
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
        save_run(conn, "run-1", k=2, signal="follow+rt", threshold=0.1, account_count=4)
        save_memberships(
            conn,
            "run-1",
            [
                ("acct-1", 0, 0.9),
                ("acct-2", 0, 0.1),
                ("acct-3", 0, 0.95),
                ("acct-4", 0, 0.05),
            ],
        )
        upsert_community(conn, "comm-a", "Community A", color="#111111", seeded_from_run="run-1", seeded_from_idx=0)
        upsert_community(conn, "comm-b", "Community B", color="#222222", seeded_from_run="run-1", seeded_from_idx=1)
        upsert_community_account(conn, "comm-a", "acct-1", 1.0, "human")
        upsert_community_account(conn, "comm-a", "acct-3", 0.9, "human")
        conn.executemany(
            "INSERT INTO profiles (account_id, username, display_name) VALUES (?, ?, ?)",
            [
                ("acct-1", "alice", "Alice"),
                ("acct-2", "bob", "Bob"),
                ("acct-3", "carol", "Carol"),
                ("acct-4", "dave", "Dave"),
            ],
        )
        conn.commit()

    node_ids = np.array(["acct-1", "acct-2", "acct-3", "acct-4"])
    np.savez(snapshot_dir / "graph_snapshot.spectral.npz", node_ids=node_ids)
    (snapshot_dir / "graph_snapshot.louvain.json").write_text(
        json.dumps({"acct-1": 0, "acct-2": 1, "acct-3": 0, "acct-4": 1})
    )
    adjacency = sp.csr_matrix(
        np.array(
            [
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
                [1.0, 0.0, 0.0, 0.2],
                [0.0, 1.0, 0.2, 0.0],
            ]
        )
    )
    with open(snapshot_dir / "adjacency_matrix_cache.pkl", "wb") as handle:
        pickle.dump({"adjacency": adjacency}, handle)

    store = CommunityGoldStore(db_path)
    store.upsert_label(account_id="acct-1", community_id="comm-a", reviewer="human", judgment="in")
    store.upsert_label(account_id="acct-2", community_id="comm-a", reviewer="human", judgment="out")
    store.upsert_label(account_id="acct-3", community_id="comm-a", reviewer="human", judgment="in")
    store.upsert_label(account_id="acct-4", community_id="comm-a", reviewer="human", judgment="out")

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE account_community_gold_split SET split = 'train' WHERE account_id IN ('acct-1', 'acct-2')")
        conn.execute("UPDATE account_community_gold_split SET split = 'dev' WHERE account_id IN ('acct-3', 'acct-4')")
        conn.commit()
    return store


@pytest.mark.integration
def test_evaluate_scoreboard_scores_available_methods(tmp_path: Path) -> None:
    store = _seed_eval_fixture(tmp_path)

    result = store.evaluate_scoreboard(split="dev", reviewer="human", community_ids=["comm-a"])

    assert result["bestMethodByMacroAucPr"] in {"canonical_map", "nmf_seeded", "louvain_transfer", "train_grf"}
    assert len(result["communities"]) == 1
    community = result["communities"][0]
    assert community["communityId"] == "comm-a"
    expected_semantics = {
        "canonical_map": "affinity",
        "nmf_seeded": "simplex",
        "louvain_transfer": "affinity",
        "train_grf": "affinity",
    }
    for method, score_semantics in expected_semantics.items():
        method_result = community["methods"][method]
        assert method_result["available"] is True
        assert method_result["scoreSemantics"] == score_semantics
        assert result["summary"][method]["scoreSemantics"] == score_semantics
        assert method_result["metrics"]["aucPr"] >= 0.99
        assert method_result["metrics"]["f1"] >= 0.99
        assert {"brier", "ece"}.issubset(method_result["metrics"])
        assert method_result["metrics"]["brier"] is None
        assert method_result["metrics"]["ece"] is None
        assert method_result["probabilityMetricsAvailable"] is False
        assert method_result["calibrated"] is False
        assert method_result["metricsInterpretation"] == "diagnostic_only_not_calibrated"


@pytest.mark.integration
def test_evaluate_scoreboard_rejects_same_training_and_evaluation_split(tmp_path: Path) -> None:
    store = _seed_eval_fixture(tmp_path)

    with pytest.raises(ValueError, match="train_split and split must be different"):
        store.evaluate_scoreboard(split="dev", train_split="dev", reviewer="human")


@pytest.mark.integration
@pytest.mark.parametrize(
    ("split", "train_split"),
    [
        ("test", "train"),
        ("train", "dev"),
        ("dev", "test"),
    ],
)
def test_legacy_evaluator_only_allows_train_to_dev(
    tmp_path: Path,
    split: str,
    train_split: str,
) -> None:
    store = _seed_eval_fixture(tmp_path)

    with pytest.raises(ValueError, match="legacy evaluator is limited to train->dev diagnostics"):
        store.evaluate_scoreboard(
            split=split,
            train_split=train_split,
            reviewer="human",
        )


@pytest.mark.integration
def test_small_class_support_is_diagnostic_but_not_calibration_eligible(tmp_path: Path) -> None:
    store = _seed_eval_fixture(tmp_path)

    result = store.evaluate_scoreboard(
        split="dev",
        reviewer="human",
        methods=["canonical_map"],
        community_ids=["comm-a"],
    )

    method_result = result["communities"][0]["methods"]["canonical_map"]
    assert method_result["available"] is True
    assert method_result["calibrationEligible"] is False
    assert method_result["developmentClassSupportMet"] is False
    assert "untouched terminal-test support" in method_result[
        "calibrationReason"
    ]
    assert method_result["calibrated"] is False
    assert method_result["metricsInterpretation"] == "diagnostic_only_not_calibrated"
    assert {"aucPr", "brier", "ece", "f1"}.issubset(method_result["metrics"])


@pytest.mark.integration
def test_evaluator_reports_abstain_and_labelability_coverage(tmp_path: Path) -> None:
    store = _seed_eval_fixture(tmp_path)
    store.upsert_label(
        account_id="acct-abstain",
        community_id="comm-a",
        reviewer="human",
        judgment="abstain",
    )
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            """
            UPDATE account_community_gold_split
            SET split = 'dev'
            WHERE account_id = 'acct-abstain'
            """
        )
        conn.commit()

    result = store.evaluate_scoreboard(
        split="dev",
        reviewer="human",
        methods=["canonical_map"],
        community_ids=["comm-a"],
    )

    community = result["communities"][0]
    assert community["sampleCounts"]["dev"] == {
        "in": 1,
        "out": 1,
        "abstain": 1,
    }
    assert community["coverageBySplit"]["dev"] == {
        "totalReviewed": 3,
        "labelableCount": 2,
        "abstainCount": 1,
        "labelabilityRate": pytest.approx(2 / 3),
    }


@pytest.mark.integration
def test_missing_method_output_is_unknown_and_reported(tmp_path: Path) -> None:
    store = _seed_eval_fixture(tmp_path)
    store.upsert_label(
        account_id="acct-missing",
        community_id="comm-a",
        reviewer="human",
        judgment="out",
    )
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            """
            UPDATE account_community_gold_split
            SET split = 'dev'
            WHERE account_id = 'acct-missing'
            """
        )
        conn.commit()

    result = store.evaluate_scoreboard(
        split="dev",
        reviewer="human",
        methods=["nmf_seeded"],
        community_ids=["comm-a"],
    )

    method = result["communities"][0]["methods"]["nmf_seeded"]
    coverage = method["predictionCoverage"]["dev"]
    assert method["available"] is True
    assert method["missingScorePolicy"] == "unknown_excluded"
    assert coverage["expectedCount"] == 3
    assert coverage["scoredCount"] == 2
    assert coverage["missingCount"] == 1
    assert coverage["missingAccountSample"] == ["acct-missing"]
