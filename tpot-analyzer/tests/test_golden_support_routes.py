"""Tests for golden support routes: profile, replies, engagement, interpret/models.

These endpoints were added after the core golden CRUD routes and had zero
backend test coverage (doc audit finding 2026-03-19).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from flask import Flask

from src.api.routes.golden import golden_bp
import src.api.routes.golden as golden_routes
from src.archive.store import SCHEMA as ARCHIVE_SCHEMA


@pytest.fixture
def support_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Flask:
    """Fixture with archive DB seeded for profile/replies/engagement tests."""
    db_path = tmp_path / "archive_tweets.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(ARCHIVE_SCHEMA)

        # --- Profiles ---
        conn.execute(
            """INSERT INTO profiles
               (account_id, username, display_name, bio, location, website, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("acct_001", "alice", "Alice A", "thinker", "NYC", "https://alice.dev", "2020-01-01"),
        )
        conn.execute(
            """INSERT INTO profiles
               (account_id, username, display_name, bio, location, website, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("acct_002", "bob", "Bob B", "builder", "SF", None, "2021-06-15"),
        )

        # --- Tweets (mix of originals and replies) ---
        tweets = [
            # Alice's tweets: 3 originals, 2 replies
            ("t001", "acct_001", "alice", "original thought 1", "2026-03-01T12:00:00+00:00", None, None, 10, 2),
            ("t002", "acct_001", "alice", "original thought 2", "2026-03-02T12:00:00+00:00", None, None, 25, 5),
            ("t003", "acct_001", "alice", "original thought 3", "2026-03-03T12:00:00+00:00", None, None, 3, 0),
            ("t004", "acct_001", "alice", "reply to bob", "2026-03-04T12:00:00+00:00", "t099", "bob", 1, 0),
            ("t005", "acct_001", "alice", "another reply", "2026-03-05T12:00:00+00:00", "t011", "carol", 0, 0),
            # Bob's tweet (target for replies/engagement)
            ("t010", "acct_002", "bob", "what do you think?", "2026-03-01T10:00:00+00:00", None, None, 50, 10),
            # Replies to t010 from various accounts
            ("t020", "acct_001", "alice", "I think X", "2026-03-01T11:00:00+00:00", "t010", "bob", 5, 0),
            ("t021", "acct_003", "carol", "I think Y", "2026-03-01T12:00:00+00:00", "t010", "bob", 8, 1),
            ("t022", "acct_004", "dave", "I think Z", "2026-03-01T13:00:00+00:00", "t010", "bob", 2, 0),
        ]
        conn.executemany(
            """INSERT INTO tweets
               (tweet_id, account_id, username, full_text, created_at,
                reply_to_tweet_id, reply_to_username, favorite_count, retweet_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            tweets,
        )

        # --- Likes on t010 ---
        likes = [
            ("acct_001", "alice", "t010", None, None, "2026-03-01"),
            ("acct_003", "carol", "t010", None, None, "2026-03-01"),
            ("acct_005", "eve", "t010", None, None, "2026-03-01"),
        ]
        conn.executemany(
            "INSERT INTO likes (liker_account_id, liker_username, tweet_id, full_text, expanded_url, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
            likes,
        )

        # --- Retweets of t010 ---
        # NOTE: retweets table has tweet_id as PK. The engagement endpoint queries
        # WHERE r.tweet_id = <original_tweet_id>. This means it treats tweet_id as
        # the original tweet's ID, limiting to one retweeter per original tweet.
        # This is a schema limitation — PK constraint means only one RT per original.
        conn.execute(
            "INSERT INTO retweets (tweet_id, account_id, username, rt_of_username, created_at) VALUES (?, ?, ?, ?, ?)",
            ("t010", "acct_004", "dave", "bob", "2026-03-01"),
        )

        # --- Follow graph (for follower/following counts) ---
        conn.executemany(
            "INSERT INTO account_following (account_id, following_account_id) VALUES (?, ?)",
            [("acct_001", "acct_002"), ("acct_001", "acct_003"), ("acct_001", "acct_004")],
        )
        conn.executemany(
            "INSERT INTO account_following (account_id, following_account_id) VALUES (?, ?)",
            [("acct_002", "acct_001"), ("acct_003", "acct_001"), ("acct_004", "acct_001"), ("acct_005", "acct_001")],
        )

        # --- Fetch log ---
        conn.execute(
            "INSERT INTO fetch_log (username, account_id, status, tweet_count, like_count, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("alice", "acct_001", "ok", 500, 2000, "2026-02-25"),
        )

        # --- Community tables (needed by profile endpoint) ---
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS community (
                id TEXT PRIMARY KEY, name TEXT, color TEXT, description TEXT,
                seeded_from_run TEXT, seeded_from_idx INTEGER,
                created_at TEXT, updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS community_account (
                community_id TEXT, account_id TEXT, weight REAL,
                source TEXT DEFAULT 'nmf', updated_at TEXT,
                PRIMARY KEY (community_id, account_id)
            );
            CREATE TABLE IF NOT EXISTS account_note (
                account_id TEXT PRIMARY KEY, note TEXT, updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS resolved_accounts (
                account_id TEXT PRIMARY KEY, status TEXT
            );
        """)

        # Alice is in two communities
        conn.execute("INSERT INTO community (id, name, color) VALUES ('c1', 'Rationalists', '#3366cc')")
        conn.execute("INSERT INTO community (id, name, color) VALUES ('c2', 'Dharma', '#cc6633')")
        conn.execute("INSERT INTO community_account (community_id, account_id, weight) VALUES ('c1', 'acct_001', 0.7)")
        conn.execute("INSERT INTO community_account (community_id, account_id, weight) VALUES ('c2', 'acct_001', 0.3)")
        # Eve is in one community (for engagement test)
        conn.execute("INSERT INTO community_account (community_id, account_id, weight) VALUES ('c1', 'acct_005', 0.9)")

        conn.execute("INSERT INTO account_note (account_id, note) VALUES ('acct_001', 'prolific poster')")
        conn.execute("INSERT INTO resolved_accounts (account_id, status) VALUES ('acct_001', 'active')")

        conn.commit()

    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.delenv("GOLDEN_INTERPRET_ALLOWED_MODELS", raising=False)
    monkeypatch.delenv("GOLDEN_INTERPRET_ALLOW_REMOTE", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    golden_routes._golden_store = None

    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(golden_bp)
    return app


# ---------------------------------------------------------------------------
# /accounts/<username>/profile
# ---------------------------------------------------------------------------

class TestAccountProfile:
    @pytest.mark.integration
    def test_profile_assembles_full_data(self, support_app: Flask) -> None:
        """Profile endpoint returns community, followers, tweets, note."""
        client = support_app.test_client()
        resp = client.get("/api/golden/accounts/alice/profile")
        assert resp.status_code == 200
        payload = resp.get_json()

        assert payload["username"] == "alice"
        profile = payload["profile"]
        assert profile["accountId"] == "acct_001"
        assert profile["displayName"] == "Alice A"
        assert profile["bio"] == "thinker"

        # Community: picks highest weight (Rationalists at 0.7)
        assert profile["community"] is not None
        assert profile["community"]["name"] == "Rationalists"
        assert profile["community"]["weight"] == 0.7

        # Archive follow counts (4 accounts follow alice, alice follows 3)
        assert profile["archiveFollowers"] == 4
        assert profile["archiveFollowing"] == 3

        # Fetch log data
        assert profile["totalTweets"] == 500
        assert profile["totalLikesGiven"] == 2000

        # Resolved status + note
        assert profile["resolvedStatus"] == "active"
        assert profile["accountNote"] == "prolific poster"

        # Recent tweets: only non-replies, ordered DESC
        tweets = payload["recentTweets"]
        assert len(tweets) == 3  # 3 originals, 2 replies excluded
        assert tweets[0]["tweetId"] == "t003"  # most recent first

    @pytest.mark.integration
    def test_profile_unknown_user_returns_null(self, support_app: Flask) -> None:
        """Profile for nonexistent user returns null profile, empty tweets."""
        client = support_app.test_client()
        resp = client.get("/api/golden/accounts/nobody/profile")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["profile"] is None
        assert payload["recentTweets"] == []

    @pytest.mark.integration
    def test_profile_no_community_returns_null(self, support_app: Flask) -> None:
        """Profile for user with no community membership returns community=null."""
        client = support_app.test_client()
        resp = client.get("/api/golden/accounts/bob/profile")
        assert resp.status_code == 200
        profile = resp.get_json()["profile"]
        assert profile is not None
        assert profile["community"] is None

    @pytest.mark.integration
    def test_profile_camelcase_keys(self, support_app: Flask) -> None:
        """Profile response uses camelCase keys per API convention."""
        client = support_app.test_client()
        resp = client.get("/api/golden/accounts/alice/profile")
        profile = resp.get_json()["profile"]
        assert "accountId" in profile
        assert "displayName" in profile
        assert "createdAt" in profile
        assert "archiveFollowers" in profile
        assert "totalTweets" in profile
        assert "resolvedStatus" in profile
        assert "accountNote" in profile
        # Verify no snake_case leakage
        assert "account_id" not in profile
        assert "display_name" not in profile


# ---------------------------------------------------------------------------
# /tweets/<tweet_id>/replies
# ---------------------------------------------------------------------------

class TestTweetReplies:
    @pytest.mark.integration
    def test_replies_returns_direct_replies(self, support_app: Flask) -> None:
        """Only direct replies to the target tweet are returned."""
        client = support_app.test_client()
        resp = client.get("/api/golden/tweets/t010/replies")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["tweetId"] == "t010"
        assert payload["count"] == 3  # alice, carol, dave replied
        usernames = {r["username"] for r in payload["replies"]}
        assert usernames == {"alice", "carol", "dave"}

    @pytest.mark.integration
    def test_replies_ordered_by_created_at_asc(self, support_app: Flask) -> None:
        """Replies come in chronological order (oldest first)."""
        client = support_app.test_client()
        replies = client.get("/api/golden/tweets/t010/replies").get_json()["replies"]
        timestamps = [r["createdAt"] for r in replies]
        assert timestamps == sorted(timestamps)

    @pytest.mark.integration
    def test_replies_respects_limit(self, support_app: Flask) -> None:
        """Limit parameter caps results."""
        client = support_app.test_client()
        resp = client.get("/api/golden/tweets/t010/replies?limit=2")
        assert resp.status_code == 200
        assert resp.get_json()["count"] == 2

    @pytest.mark.integration
    def test_replies_no_replies_returns_empty(self, support_app: Flask) -> None:
        """Tweet with no replies returns empty list."""
        client = support_app.test_client()
        resp = client.get("/api/golden/tweets/t001/replies")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["replies"] == []
        assert payload["count"] == 0

    @pytest.mark.integration
    def test_replies_camelcase_keys(self, support_app: Flask) -> None:
        """Reply objects use camelCase keys."""
        client = support_app.test_client()
        replies = client.get("/api/golden/tweets/t010/replies").get_json()["replies"]
        reply = replies[0]
        assert "tweetId" in reply
        assert "createdAt" in reply
        assert "likeCount" in reply
        assert "retweetCount" in reply


# ---------------------------------------------------------------------------
# /tweets/<tweet_id>/engagement
# ---------------------------------------------------------------------------

class TestTweetEngagement:
    @pytest.mark.integration
    def test_engagement_separates_likers_retweeters(self, support_app: Flask) -> None:
        """Likers and retweeters are separate lists."""
        client = support_app.test_client()
        resp = client.get("/api/golden/tweets/t010/engagement")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["tweetId"] == "t010"
        assert len(payload["likers"]) == 3  # alice, carol, eve
        assert len(payload["retweeters"]) == 1  # dave

    @pytest.mark.integration
    def test_engagement_includes_community_info(self, support_app: Flask) -> None:
        """Likers/retweeters with community membership include community data."""
        client = support_app.test_client()
        payload = client.get("/api/golden/tweets/t010/engagement").get_json()

        # Eve is in Rationalists with weight 0.9
        eve = next(l for l in payload["likers"] if l["username"] == "eve")
        assert eve["community"] is not None
        assert eve["community"]["name"] == "Rationalists"

    @pytest.mark.integration
    def test_engagement_null_community_for_unassigned(self, support_app: Flask) -> None:
        """Accounts with no community membership have community=null."""
        client = support_app.test_client()
        payload = client.get("/api/golden/tweets/t010/engagement").get_json()

        # carol (acct_003) has no community_account row
        carol = next(l for l in payload["likers"] if l["username"] == "carol")
        assert carol["community"] is None

    @pytest.mark.integration
    def test_engagement_no_likes_or_rts_returns_empty(self, support_app: Flask) -> None:
        """Tweet with no engagement returns empty lists."""
        client = support_app.test_client()
        resp = client.get("/api/golden/tweets/t001/engagement")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["likers"] == []
        assert payload["retweeters"] == []

    @pytest.mark.integration
    def test_engagement_liker_picks_max_weight_community(self, support_app: Flask) -> None:
        """When liker belongs to multiple communities, the highest-weight one is picked."""
        client = support_app.test_client()
        payload = client.get("/api/golden/tweets/t010/engagement").get_json()

        # alice has c1=0.7 and c2=0.3, should pick Rationalists (0.7)
        alice = next(l for l in payload["likers"] if l["username"] == "alice")
        assert alice["community"]["name"] == "Rationalists"


# ---------------------------------------------------------------------------
# /interpret/models
# ---------------------------------------------------------------------------

class TestInterpretModels:
    @pytest.mark.integration
    def test_models_returns_defaults_when_env_unset(self, support_app: Flask) -> None:
        """Default model list when GOLDEN_INTERPRET_ALLOWED_MODELS is unset."""
        client = support_app.test_client()
        resp = client.get("/api/golden/interpret/models")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert "moonshotai/kimi-k2" in payload["models"]
        assert "anthropic/claude-sonnet-4-5" in payload["models"]
        assert payload["default"] == "moonshotai/kimi-k2"

    @pytest.mark.integration
    def test_models_respects_env_override(self, support_app: Flask, monkeypatch: pytest.MonkeyPatch) -> None:
        """GOLDEN_INTERPRET_ALLOWED_MODELS restricts returned models."""
        monkeypatch.setenv("GOLDEN_INTERPRET_ALLOWED_MODELS", "model-a,model-b")
        client = support_app.test_client()
        resp = client.get("/api/golden/interpret/models")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert set(payload["models"]) == {"model-a", "model-b"}

    @pytest.mark.integration
    def test_models_default_field(self, support_app: Flask) -> None:
        """Default field always points to the configured default model."""
        client = support_app.test_client()
        payload = client.get("/api/golden/interpret/models").get_json()
        assert payload["default"] == "moonshotai/kimi-k2"
