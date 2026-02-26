"""Tests for /api/communities/branches endpoints."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from flask import Flask

from src.api.routes.communities import communities_bp
from src.api.routes.branches import branches_bp
from src.communities.store import (
    init_db, save_run,
    upsert_community, upsert_community_account,
    create_branch, capture_snapshot,
)


@pytest.fixture
def branches_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Flask:
    db_path = tmp_path / "archive_tweets.db"
    monkeypatch.setenv("ARCHIVE_DB_PATH", str(db_path))

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        init_db(conn)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                account_id TEXT PRIMARY KEY, username TEXT, display_name TEXT,
                bio TEXT, location TEXT, website TEXT
            );
            CREATE TABLE IF NOT EXISTS account_following (
                account_id TEXT NOT NULL, following_account_id TEXT NOT NULL,
                PRIMARY KEY (account_id, following_account_id)
            );
            CREATE TABLE IF NOT EXISTS account_followers (
                account_id TEXT, follower_account_id TEXT,
                PRIMARY KEY (account_id, follower_account_id)
            );
            CREATE TABLE IF NOT EXISTS tweets (
                tweet_id TEXT PRIMARY KEY, account_id TEXT, full_text TEXT,
                created_at TEXT, favorite_count INTEGER DEFAULT 0, retweet_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS likes (liker_account_id TEXT, full_text TEXT, expanded_url TEXT);
            CREATE TABLE IF NOT EXISTS retweets (account_id TEXT, rt_of_username TEXT);
        """)

        save_run(conn, "run-1", k=3, signal="follow+rt", threshold=0.1, account_count=5)
        upsert_community(conn, "comm-A", "EA", color="#4a90e2",
                         seeded_from_run="run-1", seeded_from_idx=0)
        upsert_community_account(conn, "comm-A", "acct_1", 0.8, "nmf")
        conn.commit()

    app = Flask(__name__)
    app.register_blueprint(communities_bp)
    app.register_blueprint(branches_bp)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(branches_app):
    return branches_app.test_client()


def test_list_branches_bootstraps_main(client):
    """First GET creates 'main' branch."""
    res = client.get("/api/communities/branches")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data) == 1
    assert data[0]["name"] == "main"
    assert data[0]["is_active"] is True


def test_create_branch(client):
    """POST creates a new branch forked from current."""
    # Bootstrap main
    client.get("/api/communities/branches")

    res = client.post("/api/communities/branches", json={
        "name": "experiment",
        "description": "Testing a new framing",
    })
    assert res.status_code == 201
    data = res.get_json()
    assert data["name"] == "experiment"

    # Now two branches
    res2 = client.get("/api/communities/branches")
    assert len(res2.get_json()) == 2


def test_create_duplicate_name_fails(client):
    """Cannot create two branches with the same name."""
    client.get("/api/communities/branches")
    res = client.post("/api/communities/branches", json={"name": "main"})
    assert res.status_code == 409


def test_switch_branch(client):
    """POST switch changes active branch."""
    client.get("/api/communities/branches")

    # Create second branch
    res = client.post("/api/communities/branches", json={"name": "alt"})
    alt_id = res.get_json()["id"]

    # Get main branch id
    branches = client.get("/api/communities/branches").get_json()
    main_id = next(b["id"] for b in branches if b["name"] == "main")

    # Switch back to main
    res = client.post(f"/api/communities/branches/{main_id}/switch",
                      json={"action": "save"})
    assert res.status_code == 200

    active = next(b for b in client.get("/api/communities/branches").get_json()
                  if b["is_active"])
    assert active["name"] == "main"


def test_dirty_check(client):
    """GET dirty returns false for clean branch."""
    client.get("/api/communities/branches")
    branches = client.get("/api/communities/branches").get_json()
    main_id = branches[0]["id"]

    res = client.get(f"/api/communities/branches/{main_id}/dirty")
    assert res.status_code == 200
    assert res.get_json()["dirty"] is False


def test_save_snapshot(client):
    """POST snapshot saves current state."""
    client.get("/api/communities/branches")
    branches = client.get("/api/communities/branches").get_json()
    main_id = branches[0]["id"]

    res = client.post(f"/api/communities/branches/{main_id}/snapshots",
                      json={"name": "checkpoint"})
    assert res.status_code == 201
    assert res.get_json()["name"] == "checkpoint"


def test_list_snapshots(client):
    """GET snapshots returns list for branch."""
    client.get("/api/communities/branches")
    branches = client.get("/api/communities/branches").get_json()
    main_id = branches[0]["id"]

    res = client.get(f"/api/communities/branches/{main_id}/snapshots")
    assert res.status_code == 200
    # Should have 1 snapshot from bootstrap
    assert len(res.get_json()) >= 1


def test_delete_branch(client):
    """DELETE removes non-active branch."""
    client.get("/api/communities/branches")
    client.post("/api/communities/branches", json={"name": "temp"})

    branches = client.get("/api/communities/branches").get_json()
    non_active = next(b for b in branches if not b["is_active"])

    res = client.delete(f"/api/communities/branches/{non_active['id']}")
    assert res.status_code == 200


def test_delete_active_branch_fails(client):
    """Cannot delete the active branch."""
    client.get("/api/communities/branches")
    branches = client.get("/api/communities/branches").get_json()
    active = next(b for b in branches if b["is_active"])

    res = client.delete(f"/api/communities/branches/{active['id']}")
    assert res.status_code == 409


def test_restore_snapshot(client):
    """POST restore reverts Layer 2 to snapshot state."""
    client.get("/api/communities/branches")
    branches = client.get("/api/communities/branches").get_json()
    main_id = branches[0]["id"]

    # Save a snapshot
    snap_res = client.post(f"/api/communities/branches/{main_id}/snapshots",
                           json={"name": "before-change"})
    snap_id = snap_res.get_json()["id"]

    # Rename a community (change Layer 2)
    client.patch("/api/communities/comm-A", json={"name": "RENAMED"})

    # Restore
    res = client.post(f"/api/communities/branches/{main_id}/snapshots/{snap_id}/restore")
    assert res.status_code == 200
    assert res.get_json()["restored"] is True

    # Verify the name is back
    comms = client.get("/api/communities").get_json()
    names = {c["name"] for c in comms}
    assert "EA" in names
    assert "RENAMED" not in names
