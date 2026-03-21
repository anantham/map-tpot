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
    for method in ("canonical_map", "nmf_seeded", "louvain_transfer", "train_grf"):
        assert community["methods"][method]["available"] is True
        assert community["methods"][method]["metrics"]["aucPr"] >= 0.99
        assert community["methods"][method]["metrics"]["f1"] >= 0.99
