"""Tests for R1-R2: signed reply heuristics.

Covers:
  - R1: author-liked-reply detection
  - R2: mutual-follow reply detection
  - Self-reply exclusion
  - Table creation and data storage
"""

import sqlite3

import pytest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from build_signed_replies import (
    find_author_liked_replies,
    find_mutual_follow_replies,
    create_signed_reply_table,
    store_signed_replies,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_reply_db(tweets, likes=None, followings=None):
    """Create in-memory SQLite with tweets, likes, and account_following tables.

    tweets: list of (tweet_id, account_id, username, full_text, created_at,
                      reply_to_tweet_id, reply_to_username, ...)
    likes: list of (liker_account_id, liker_username, tweet_id, full_text, expanded_url, fetched_at)
    followings: list of (account_id, following_account_id)
    """
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE tweets ("
        "  tweet_id TEXT PRIMARY KEY,"
        "  account_id TEXT NOT NULL,"
        "  username TEXT NOT NULL,"
        "  full_text TEXT NOT NULL,"
        "  created_at TEXT,"
        "  reply_to_tweet_id TEXT,"
        "  reply_to_username TEXT,"
        "  favorite_count INTEGER DEFAULT 0,"
        "  retweet_count INTEGER DEFAULT 0,"
        "  lang TEXT,"
        "  is_note_tweet INTEGER DEFAULT 0,"
        "  fetched_at TEXT"
        ")"
    )
    con.execute(
        "CREATE TABLE likes ("
        "  liker_account_id TEXT NOT NULL,"
        "  liker_username TEXT NOT NULL,"
        "  tweet_id TEXT NOT NULL,"
        "  full_text TEXT,"
        "  expanded_url TEXT,"
        "  fetched_at TEXT,"
        "  PRIMARY KEY (liker_account_id, tweet_id)"
        ")"
    )
    con.execute(
        "CREATE TABLE account_following ("
        "  account_id TEXT NOT NULL,"
        "  following_account_id TEXT NOT NULL,"
        "  PRIMARY KEY (account_id, following_account_id)"
        ")"
    )

    for t in (tweets or []):
        con.execute(
            "INSERT INTO tweets (tweet_id, account_id, username, full_text, "
            "created_at, reply_to_tweet_id, reply_to_username) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            t[:7],
        )
    for l in (likes or []):
        con.execute(
            "INSERT INTO likes (liker_account_id, liker_username, tweet_id, "
            "full_text, expanded_url, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
            l,
        )
    for f in (followings or []):
        con.execute(
            "INSERT INTO account_following (account_id, following_account_id) "
            "VALUES (?, ?)",
            f,
        )
    con.commit()
    return con


# ── Test data ────────────────────────────────────────────────────────────────

# Scenario:
# alice (a1) posts tweet t_orig
# bob (a2) replies to alice's tweet → reply t_reply
# alice likes bob's reply → R1 signal
# alice and bob mutually follow → R2 signal
# carol (a3) replies to alice but alice doesn't like it, no mutual follow

TWEETS = [
    # (tweet_id, account_id, username, full_text, created_at, reply_to_tweet_id, reply_to_username)
    ("t_orig", "a1", "alice", "Original tweet", "Mon Mar 20 12:00:00 +0000 2026", None, None),
    ("t_reply_bob", "a2", "bob", "Great point!", "Mon Mar 20 13:00:00 +0000 2026", "t_orig", "alice"),
    ("t_reply_carol", "a3", "carol", "I disagree", "Mon Mar 20 14:00:00 +0000 2026", "t_orig", "alice"),
    # Second reply by bob to alice's tweet (to test aggregation)
    ("t_orig2", "a1", "alice", "Another tweet", "Tue Mar 21 12:00:00 +0000 2026", None, None),
    ("t_reply_bob2", "a2", "bob", "Also agree!", "Tue Mar 21 13:00:00 +0000 2026", "t_orig2", "alice"),
]

# alice likes bob's first reply
LIKES = [
    ("a1", "alice", "t_reply_bob", "Great point!", None, "2026-03-22"),
]

# alice <-> bob mutual follow
FOLLOWINGS = [
    ("a1", "a2"),  # alice follows bob
    ("a2", "a1"),  # bob follows alice
]


# ── TestAuthorLikedReply (R1) ───────────────────────────────────────────────

class TestAuthorLikedReply:
    """Tests for find_author_liked_replies() — R1 heuristic."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.con = _make_reply_db(TWEETS, LIKES, FOLLOWINGS)
        yield
        self.con.close()

    def test_detects_author_liked_reply(self):
        """Bob's reply that alice liked should be detected."""
        results = find_author_liked_replies(self.con)
        # Should find (replier=a2/bob, author=a1/alice)
        pairs = {(r[0], r[1]) for r in results}
        assert ("a2", "a1") in pairs

    def test_does_not_detect_unliked_reply(self):
        """Carol's reply that alice didn't like should NOT be detected."""
        results = find_author_liked_replies(self.con)
        pairs = {(r[0], r[1]) for r in results}
        assert ("a3", "a1") not in pairs

    def test_excludes_self_replies(self):
        """If alice replies to her own tweet and likes it, it should be excluded."""
        tweets = [
            ("t_self_orig", "a1", "alice", "My tweet", "Mon Mar 20 12:00:00 +0000 2026", None, None),
            ("t_self_reply", "a1", "alice", "My reply", "Mon Mar 20 13:00:00 +0000 2026", "t_self_orig", "alice"),
        ]
        likes = [
            ("a1", "alice", "t_self_reply", "My reply", None, "2026-03-22"),
        ]
        con = _make_reply_db(tweets, likes)
        results = find_author_liked_replies(con)
        pairs = {(r[0], r[1]) for r in results}
        # Self-reply should NOT appear
        assert ("a1", "a1") not in pairs
        con.close()

    def test_returns_reply_count(self):
        """Result should include the count of author-liked replies per pair."""
        results = find_author_liked_replies(self.con)
        # bob -> alice: only 1 liked reply (t_reply_bob; t_reply_bob2 is not liked)
        for replier, author, count in results:
            if replier == "a2" and author == "a1":
                assert count == 1


# ── TestMutualFollowReply (R2) ──────────────────────────────────────────────

class TestMutualFollowReply:
    """Tests for find_mutual_follow_replies() — R2 heuristic."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.con = _make_reply_db(TWEETS, LIKES, FOLLOWINGS)
        yield
        self.con.close()

    def test_detects_mutual_follow_reply(self):
        """Bob's replies to alice (who mutually follow) should be detected."""
        results = find_mutual_follow_replies(self.con)
        pairs = {(r[0], r[1]) for r in results}
        assert ("a2", "a1") in pairs

    def test_does_not_detect_non_mutual_reply(self):
        """Carol's reply to alice (no mutual follow) should NOT be detected."""
        results = find_mutual_follow_replies(self.con)
        pairs = {(r[0], r[1]) for r in results}
        assert ("a3", "a1") not in pairs

    def test_counts_multiple_replies(self):
        """Bob replied to alice twice — count should be 2."""
        results = find_mutual_follow_replies(self.con)
        for replier, author, count in results:
            if replier == "a2" and author == "a1":
                assert count == 2

    def test_excludes_self_replies(self):
        """If alice replies to herself (and follows herself somehow), exclude it."""
        tweets = [
            ("t_self_orig", "a1", "alice", "My tweet", "Mon Mar 20 12:00:00 +0000 2026", None, None),
            ("t_self_reply", "a1", "alice", "My reply", "Mon Mar 20 13:00:00 +0000 2026", "t_self_orig", "alice"),
        ]
        followings = [("a1", "a1")]  # self-follow edge case
        con = _make_reply_db(tweets, followings=followings)
        results = find_mutual_follow_replies(con)
        pairs = {(r[0], r[1]) for r in results}
        assert ("a1", "a1") not in pairs
        con.close()

    def test_one_way_follow_not_detected(self):
        """If alice follows carol but carol doesn't follow alice, no detection."""
        tweets = [
            ("t_c_orig", "a3", "carol", "Carol's tweet", "Mon Mar 20 12:00:00 +0000 2026", None, None),
            ("t_a_reply", "a1", "alice", "Nice", "Mon Mar 20 13:00:00 +0000 2026", "t_c_orig", "carol"),
        ]
        followings = [("a1", "a3")]  # alice follows carol, but NOT vice versa
        con = _make_reply_db(tweets, followings=followings)
        results = find_mutual_follow_replies(con)
        pairs = {(r[0], r[1]) for r in results}
        assert ("a1", "a3") not in pairs
        con.close()


# ── TestTableCreation ───────────────────────────────────────────────────────

class TestSignedReplyStorage:
    """Tests for create_signed_reply_table() and store_signed_replies()."""

    def test_creates_table(self):
        """create_signed_reply_table() should create the signed_reply table."""
        con = sqlite3.connect(":memory:")
        create_signed_reply_table(con)
        tables = [
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "signed_reply" in tables
        con.close()

    def test_stores_and_retrieves(self):
        """store_signed_replies() should insert rows correctly."""
        con = sqlite3.connect(":memory:")
        create_signed_reply_table(con)
        rows = [
            ("a2", "a1", 3, "author_liked"),
            ("a2", "a1", 5, "mutual_follow"),
        ]
        store_signed_replies(con, rows)

        stored = con.execute(
            "SELECT replier_id, author_id, reply_count, heuristic FROM signed_reply"
        ).fetchall()
        assert len(stored) == 2
        assert ("a2", "a1", 3, "author_liked") in stored
        assert ("a2", "a1", 5, "mutual_follow") in stored
        con.close()

    def test_upsert_updates_count(self):
        """Storing the same (replier, author, heuristic) again should update count."""
        con = sqlite3.connect(":memory:")
        create_signed_reply_table(con)
        store_signed_replies(con, [("a2", "a1", 3, "author_liked")])
        store_signed_replies(con, [("a2", "a1", 7, "author_liked")])

        stored = con.execute(
            "SELECT reply_count FROM signed_reply "
            "WHERE replier_id='a2' AND author_id='a1' AND heuristic='author_liked'"
        ).fetchone()
        assert stored[0] == 7
        con.close()
