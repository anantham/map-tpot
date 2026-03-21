from __future__ import annotations

import json
import pickle
import sqlite3
from pathlib import Path

import numpy as np
import pytest
import scipy.sparse as sp
from flask import Flask

import src.api.routes.community_gold as community_gold_routes
from src.api.routes.community_gold import community_gold_bp
from src.communities.store import init_db, save_memberships, save_run, upsert_community, upsert_community_account


def _seed_archive_schema(db_path: Path) -> None:
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
        upsert_community(conn, "comm-b", "Community B", color="#222222")
        upsert_community_account(conn, "comm-a", "acct-1", 0.8, "human")
        upsert_community_account(conn, "comm-b", "acct-2", 0.7, "human")
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


@pytest.fixture
def community_gold_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Flask:
    db_path = tmp_path / "archive_tweets.db"
    _seed_archive_schema(db_path)
    np.savez(tmp_path / "graph_snapshot.spectral.npz", node_ids=np.array(["acct-1", "acct-2", "acct-3", "acct-4"]))
    (tmp_path / "graph_snapshot.louvain.json").write_text(
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
    with open(tmp_path / "adjacency_matrix_cache.pkl", "wb") as handle:
        pickle.dump({"adjacency": adjacency}, handle)
    monkeypatch.setenv("ARCHIVE_DB_PATH", str(db_path))
    community_gold_routes._community_gold_store = None
    community_gold_routes._community_gold_store_path = None

    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(community_gold_bp)
    return app


@pytest.mark.integration
def test_upsert_and_list_labels_roundtrip(community_gold_app: Flask) -> None:
    client = community_gold_app.test_client()

    first = client.post(
        "/api/community-gold/labels",
        json={
            "accountId": "acct-1",
            "communityId": "comm-a",
            "reviewer": "human",
            "judgment": "in",
            "confidence": 0.9,
            "note": "clear positive",
        },
    )
    assert first.status_code == 200
    first_payload = first.get_json()
    assert first_payload["status"] == "ok"

    second = client.post(
        "/api/community-gold/labels",
        json={
            "accountId": "acct-1",
            "communityId": "comm-b",
            "reviewer": "human",
            "judgment": "out",
        },
    )
    assert second.status_code == 200
    assert second.get_json()["split"] == first_payload["split"]

    labels_resp = client.get("/api/community-gold/labels?accountId=acct-1&limit=10")
    assert labels_resp.status_code == 200
    labels = labels_resp.get_json()["labels"]
    assert len(labels) == 2
    assert labels[0]["accountId"] == "acct-1"
    assert {row["judgment"] for row in labels} == {"in", "out"}


@pytest.mark.integration
def test_metrics_and_delete_label(community_gold_app: Flask) -> None:
    client = community_gold_app.test_client()

    client.post(
        "/api/community-gold/labels",
        json={"accountId": "acct-1", "communityId": "comm-a", "judgment": "in"},
    )
    client.post(
        "/api/community-gold/labels",
        json={"accountId": "acct-2", "communityId": "comm-a", "judgment": "abstain"},
    )

    metrics = client.get("/api/community-gold/metrics")
    assert metrics.status_code == 200
    payload = metrics.get_json()
    assert payload["totalActiveLabels"] == 2
    assert payload["leakageChecks"]["accountsWithMultipleSplits"] == 0
    assert any(row["goldLabelCount"] == 2 for row in payload["communities"] if row["id"] == "comm-a")

    delete_resp = client.delete(
        "/api/community-gold/labels",
        json={"accountId": "acct-2", "communityId": "comm-a", "reviewer": "human"},
    )
    assert delete_resp.status_code == 200
    assert delete_resp.get_json()["status"] == "deleted"

    labels_resp = client.get("/api/community-gold/labels?communityId=comm-a&limit=10")
    labels = labels_resp.get_json()["labels"]
    assert len(labels) == 1
    assert labels[0]["accountId"] == "acct-1"


@pytest.mark.integration
def test_candidates_route_round_robins_cold_start(community_gold_app: Flask) -> None:
    client = community_gold_app.test_client()

    resp = client.get("/api/community-gold/candidates?reviewer=human&limit=2")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["count"] == 2
    assert {row["communityId"] for row in payload["candidates"]} == {"comm-a", "comm-b"}
    assert all(row["selectionMode"] == "cold" for row in payload["candidates"])
    assert all("queueScore" in row and row["queueScore"] > 0 for row in payload["candidates"])


@pytest.mark.integration
def test_candidates_route_uses_warm_scoring_when_train_labels_exist(community_gold_app: Flask) -> None:
    client = community_gold_app.test_client()

    client.post("/api/community-gold/labels", json={"accountId": "acct-1", "communityId": "comm-a", "judgment": "in"})
    client.post("/api/community-gold/labels", json={"accountId": "acct-2", "communityId": "comm-a", "judgment": "out"})

    db_path = Path(community_gold_routes._community_gold_store_path or "")
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE account_community_gold_split SET split = 'train' WHERE account_id IN ('acct-1', 'acct-2')")
        conn.commit()

    resp = client.get("/api/community-gold/candidates?reviewer=human&communityId=comm-a&limit=2")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["count"] == 2
    assert all(row["selectionMode"] == "warm" for row in payload["candidates"])
    assert all(row["uncertainty"] is not None for row in payload["candidates"])
    assert all("train_grf" in row["methodScores"] for row in payload["candidates"])


@pytest.mark.integration
def test_evaluate_route_returns_scoreboard(community_gold_app: Flask) -> None:
    client = community_gold_app.test_client()

    client.post("/api/community-gold/labels", json={"accountId": "acct-1", "communityId": "comm-a", "judgment": "in"})
    client.post("/api/community-gold/labels", json={"accountId": "acct-2", "communityId": "comm-a", "judgment": "out"})
    client.post("/api/community-gold/labels", json={"accountId": "acct-3", "communityId": "comm-a", "judgment": "in"})
    client.post("/api/community-gold/labels", json={"accountId": "acct-4", "communityId": "comm-a", "judgment": "out"})

    db_path = Path(community_gold_routes._community_gold_store_path or "")
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE account_community_gold_split SET split = 'train' WHERE account_id IN ('acct-1', 'acct-2')")
        conn.execute("UPDATE account_community_gold_split SET split = 'dev' WHERE account_id IN ('acct-3', 'acct-4')")
        conn.commit()

    resp = client.post(
        "/api/community-gold/evaluate",
        json={"split": "dev", "reviewer": "human", "communityIds": ["comm-a"]},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["split"] == "dev"
    assert payload["summary"]["canonical_map"]["scoredCommunities"] == 1
    community = payload["communities"][0]
    assert community["communityId"] == "comm-a"
    assert community["methods"]["train_grf"]["available"] is True
