"""Tests for /api/communities endpoints."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from flask import Flask

from src.api.routes.communities import communities_bp
from src.communities.store import (
    init_db, save_run,
    upsert_community, upsert_community_account,
)


@pytest.fixture
def communities_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Flask:
    """Flask app with communities blueprint and test data."""
    db_path = tmp_path / "archive_tweets.db"
    monkeypatch.setenv("ARCHIVE_DB_PATH", str(db_path))

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        init_db(conn)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS account_following (
                account_id TEXT NOT NULL,
                following_account_id TEXT NOT NULL,
                PRIMARY KEY (account_id, following_account_id)
            );
            CREATE TABLE IF NOT EXISTS account_followers (
                account_id TEXT NOT NULL,
                follower_account_id TEXT NOT NULL,
                PRIMARY KEY (account_id, follower_account_id)
            );
            CREATE TABLE IF NOT EXISTS profiles (
                account_id TEXT PRIMARY KEY,
                username TEXT,
                display_name TEXT,
                bio TEXT,
                location TEXT,
                website TEXT,
                followers_count INTEGER,
                following_count INTEGER,
                profile_image_url TEXT
            );
            CREATE TABLE IF NOT EXISTS tweets (
                tweet_id TEXT PRIMARY KEY,
                account_id TEXT,
                full_text TEXT,
                created_at TEXT,
                favorite_count INTEGER DEFAULT 0,
                retweet_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS likes (
                liker_account_id TEXT,
                full_text TEXT,
                expanded_url TEXT
            );
            CREATE TABLE IF NOT EXISTS retweets (
                account_id TEXT,
                rt_of_username TEXT
            );
        """)

        save_run(conn, "run-1", k=3, signal="follow+rt", threshold=0.1, account_count=5)

        upsert_community(conn, "comm-A", "EA / forecasting",
                         color="#4a90e2", seeded_from_run="run-1", seeded_from_idx=0)
        upsert_community(conn, "comm-B", "Rationalist",
                         color="#e67e22", seeded_from_run="run-1", seeded_from_idx=1)

        upsert_community_account(conn, "comm-A", "acct_1", 0.8, "nmf")
        upsert_community_account(conn, "comm-A", "acct_2", 0.6, "nmf")
        upsert_community_account(conn, "comm-B", "acct_3", 0.9, "nmf")
        upsert_community_account(conn, "comm-B", "acct_1", 1.0, "human")

        conn.executemany(
            "INSERT INTO profiles (account_id, username, bio) VALUES (?, ?, ?)",
            [("acct_1", "thezvi", "EA writer"),
             ("acct_2", "nunosempere", "Forecaster"),
             ("acct_3", "eigenrobot", "Rationalist")],
        )

        conn.executemany(
            "INSERT INTO account_following VALUES (?, ?)",
            [("ego_1", "acct_1"), ("ego_1", "acct_3")],
        )
        conn.commit()

    app = Flask(__name__)
    app.register_blueprint(communities_bp)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(communities_app):
    return communities_app.test_client()


# ── Read endpoints ───────────────────────────────────────────────────────

def test_list_communities(client):
    res = client.get("/api/communities")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data) == 2
    names = {c["name"] for c in data}
    assert "EA / forecasting" in names
    assert "Rationalist" in names
    ea = next(c for c in data if c["name"] == "EA / forecasting")
    assert ea["member_count"] == 2
    assert ea["color"] == "#4a90e2"


def test_get_community_members(client):
    res = client.get("/api/communities/comm-A/members")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["members"]) == 2
    usernames = {m["username"] for m in data["members"]}
    assert "thezvi" in usernames


def test_get_community_members_with_ego(client):
    """Members endpoint includes i_follow flag when ego param provided."""
    res = client.get("/api/communities/comm-A/members?ego=ego_1")
    assert res.status_code == 200
    data = res.get_json()
    by_user = {m["username"]: m for m in data["members"]}
    assert by_user["thezvi"]["i_follow"] is True
    assert by_user["nunosempere"]["i_follow"] is False


def test_get_account_communities(client):
    res = client.get("/api/communities/account/acct_1")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["communities"]) == 2


def test_community_not_found(client):
    res = client.get("/api/communities/nonexistent/members")
    assert res.status_code == 404


# ── Write endpoints ──────────────────────────────────────────────────────

def test_assign_account_to_community(client):
    """PUT assigns account with source='human', weight=1.0."""
    res = client.put("/api/communities/comm-A/members/acct_3")
    assert res.status_code == 200
    data = res.get_json()
    assert data["source"] == "human"
    assert data["weight"] == 1.0

    res2 = client.get("/api/communities/comm-A/members")
    usernames = {m["username"] for m in res2.get_json()["members"]}
    assert "eigenrobot" in usernames


def test_remove_account_from_community(client):
    res = client.delete("/api/communities/comm-A/members/acct_2")
    assert res.status_code == 200

    res2 = client.get("/api/communities/comm-A/members")
    acct_ids = {m["account_id"] for m in res2.get_json()["members"]}
    assert "acct_2" not in acct_ids


def test_rename_community(client):
    res = client.patch(
        "/api/communities/comm-A",
        json={"name": "EA / x-risk"},
    )
    assert res.status_code == 200

    res2 = client.get("/api/communities")
    names = {c["name"] for c in res2.get_json()}
    assert "EA / x-risk" in names
    assert "EA / forecasting" not in names


def test_update_community_color(client):
    res = client.patch(
        "/api/communities/comm-B",
        json={"color": "#ff0000"},
    )
    assert res.status_code == 200
    assert res.get_json()["color"] == "#ff0000"


def test_assign_to_nonexistent_community_404(client):
    res = client.put("/api/communities/nonexistent/members/acct_1")
    assert res.status_code == 404


def test_patch_nonexistent_community_404(client):
    res = client.patch(
        "/api/communities/nonexistent",
        json={"name": "nope"},
    )
    assert res.status_code == 404


def test_delete_community(client):
    """DELETE removes community and cascades to memberships."""
    res = client.delete("/api/communities/comm-A")
    assert res.status_code == 200
    assert res.get_json()["deleted"] is True

    # Verify gone from list
    res2 = client.get("/api/communities")
    ids = {c["id"] for c in res2.get_json()}
    assert "comm-A" not in ids


def test_delete_nonexistent_community_404(client):
    res = client.delete("/api/communities/nonexistent")
    assert res.status_code == 404


# ── Preview, Note, Weights endpoints ─────────────────────────────────


def test_account_preview(client):
    """Preview returns profile, communities, tweets, tpot_score."""
    res = client.get("/api/communities/account/acct_1/preview")
    assert res.status_code == 200
    data = res.get_json()
    assert data["account_id"] == "acct_1"
    assert data["profile"]["username"] == "thezvi"
    assert len(data["communities"]) == 2
    assert "tpot_score" in data
    assert "tpot_score_max" in data
    assert data["note"] is None


def test_account_preview_with_ego(client):
    """Preview with ego param returns mutual follows."""
    res = client.get("/api/communities/account/acct_1/preview?ego=ego_1")
    assert res.status_code == 200
    data = res.get_json()
    assert "mutual_follows" in data
    assert "mutual_follow_count" in data


def test_save_and_get_note(client):
    """PUT note then verify it appears in preview."""
    res = client.put(
        "/api/communities/account/acct_1/note",
        json={"note": "Key EA figure"},
    )
    assert res.status_code == 200
    assert res.get_json()["note"] == "Key EA figure"

    # Verify note appears in preview
    res2 = client.get("/api/communities/account/acct_1/preview")
    assert res2.get_json()["note"] == "Key EA figure"


def test_save_note_empty(client):
    """Saving empty note works."""
    res = client.put(
        "/api/communities/account/acct_1/note",
        json={"note": ""},
    )
    assert res.status_code == 200


def test_save_weights(client):
    """PUT weights updates community assignments."""
    res = client.put(
        "/api/communities/account/acct_2/weights",
        json={"weights": [
            {"community_id": "comm-A", "weight": 0.5},
            {"community_id": "comm-B", "weight": 0.3},
        ]},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["communities"]) == 2
    by_comm = {c["community_id"]: c for c in data["communities"]}
    assert by_comm["comm-A"]["weight"] == 0.5
    assert by_comm["comm-A"]["source"] == "human"
    assert by_comm["comm-B"]["weight"] == 0.3


def test_save_weights_nonexistent_community(client):
    """Saving weight to nonexistent community returns 404."""
    res = client.put(
        "/api/communities/account/acct_1/weights",
        json={"weights": [{"community_id": "nonexistent", "weight": 0.5}]},
    )
    assert res.status_code == 404
