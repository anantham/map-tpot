"""
Parses community archive JSON and stores tweets/likes into archive_tweets.db.

Schema:
  tweets     — original tweets + replies + note-tweets + community-tweets (no RTs)
  likes      — tweets liked by an account
  fetch_log  — one row per account, records status + counts
"""

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_db_lock = threading.Lock()

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tweets (
    tweet_id          TEXT PRIMARY KEY,
    account_id        TEXT NOT NULL,
    username          TEXT NOT NULL,
    full_text         TEXT NOT NULL,
    created_at        TEXT,
    reply_to_tweet_id TEXT,
    reply_to_username TEXT,
    favorite_count    INTEGER DEFAULT 0,
    retweet_count     INTEGER DEFAULT 0,
    lang              TEXT,
    is_note_tweet     INTEGER DEFAULT 0,
    fetched_at        TEXT
);

CREATE TABLE IF NOT EXISTS likes (
    liker_account_id  TEXT NOT NULL,
    liker_username    TEXT NOT NULL,
    tweet_id          TEXT NOT NULL,
    full_text         TEXT,
    expanded_url      TEXT,
    fetched_at        TEXT,
    PRIMARY KEY (liker_account_id, tweet_id)
);

CREATE TABLE IF NOT EXISTS fetch_log (
    username          TEXT PRIMARY KEY,
    account_id        TEXT,
    status            TEXT,
    tweet_count       INTEGER DEFAULT 0,
    like_count        INTEGER DEFAULT 0,
    error_message     TEXT,
    fetched_at        TEXT
);

CREATE TABLE IF NOT EXISTS thread_context_cache (
    tweet_id      TEXT PRIMARY KEY,
    raw_json      TEXT NOT NULL,
    fetched_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_tweets_account ON tweets(account_id);
CREATE INDEX IF NOT EXISTS idx_tweets_created ON tweets(created_at);
CREATE INDEX IF NOT EXISTS idx_likes_account  ON likes(liker_account_id);

CREATE TABLE IF NOT EXISTS profiles (
    account_id    TEXT PRIMARY KEY,
    username      TEXT NOT NULL,
    display_name  TEXT,
    bio           TEXT,
    location      TEXT,
    website       TEXT,
    created_at    TEXT,
    fetched_at    TEXT
);

-- Who an account follows (their intentional choices — strongest community signal)
CREATE TABLE IF NOT EXISTS account_following (
    account_id           TEXT NOT NULL,
    following_account_id TEXT NOT NULL,
    PRIMARY KEY (account_id, following_account_id)
);
CREATE INDEX IF NOT EXISTS idx_following_account ON account_following(account_id);
CREATE INDEX IF NOT EXISTS idx_following_target  ON account_following(following_account_id);

-- Who follows an account (inbound, separate from following because archive stores both)
CREATE TABLE IF NOT EXISTS account_followers (
    account_id          TEXT NOT NULL,
    follower_account_id TEXT NOT NULL,
    PRIMARY KEY (account_id, follower_account_id)
);
CREATE INDEX IF NOT EXISTS idx_followers_account ON account_followers(account_id);

-- Retweet metadata: who they amplify, without storing the RT text (not their words)
CREATE TABLE IF NOT EXISTS retweets (
    tweet_id         TEXT PRIMARY KEY,
    account_id       TEXT NOT NULL,
    username         TEXT NOT NULL,
    rt_of_username   TEXT,
    created_at       TEXT,
    fetched_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_retweets_account ON retweets(account_id);
CREATE INDEX IF NOT EXISTS idx_retweets_rt_of   ON retweets(rt_of_username);
"""


def _open(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _parse_tweets(archive: dict, account_id: str, username: str, now: str) -> list:
    """
    Extract tweet rows from archive dict.
    Combines tweets, community-tweets, note-tweets.
    Skips retweets (RT @...).
    """
    rows = []

    # Regular tweets + community tweets
    for section, is_note in [("tweets", 0), ("community-tweet", 0)]:
        for item in archive.get(section, []):
            t = item.get("tweet", {})
            text = t.get("full_text", "")
            if text.startswith("RT @"):
                continue  # skip retweets — not authored content
            rows.append((
                t.get("id_str") or t.get("id", ""),
                account_id,
                username,
                text,
                t.get("created_at"),
                t.get("in_reply_to_status_id_str") or None,
                t.get("in_reply_to_screen_name") or None,
                int(t.get("favorite_count") or 0),
                int(t.get("retweet_count") or 0),
                t.get("lang"),
                is_note,
                now,
            ))

    # Note-tweets (long-form posts — different schema)
    for item in archive.get("note-tweet", []):
        nt = item.get("noteTweet", {})
        core = nt.get("core", {})
        rows.append((
            nt.get("noteTweetId", ""),
            account_id,
            username,
            core.get("text", ""),
            nt.get("createdAt"),
            None,
            None,
            0,
            0,
            None,
            1,  # is_note_tweet
            now,
        ))

    return rows


def _parse_likes(archive: dict, account_id: str, username: str, now: str) -> list:
    rows = []
    for item in archive.get("like", []):
        lk = item.get("like", {})
        tweet_id = lk.get("tweetId", "")
        if not tweet_id:
            continue
        rows.append((
            account_id,
            username,
            tweet_id,
            lk.get("fullText"),
            lk.get("expandedUrl"),
            now,
        ))
    return rows


def _parse_profile(archive: dict, account_id: str, username: str, now: str) -> Optional[tuple]:
    """Extract one profile row from archive, combining profile + account sections."""
    profile_items = archive.get("profile", [])
    if not profile_items:
        return None
    p = profile_items[0].get("profile", {})
    desc = p.get("description", {})
    bio = desc.get("bio") or ""
    location = desc.get("location") or ""
    website = desc.get("website") or ""

    display_name = ""
    created_at = ""
    account_items = archive.get("account", [])
    if account_items:
        a = account_items[0].get("account", {})
        display_name = a.get("accountDisplayName") or ""
        created_at = a.get("createdAt") or ""
        # Prefer accountId from archive over caller-supplied (may be empty string)
        if not account_id:
            account_id = a.get("accountId") or ""

    return (account_id, username, display_name, bio, location, website, created_at, now)


def _parse_following(archive: dict, account_id: str) -> list:
    """Extract (account_id, following_account_id) pairs from the following section."""
    rows = []
    for item in archive.get("following", []):
        f = item.get("following", {})
        target_id = f.get("accountId", "")
        if target_id:
            rows.append((account_id, target_id))
    return rows


def _parse_followers(archive: dict, account_id: str) -> list:
    """Extract (account_id, follower_account_id) pairs from the follower section."""
    rows = []
    for item in archive.get("follower", []):
        f = item.get("follower", {})
        follower_id = f.get("accountId", "")
        if follower_id:
            rows.append((account_id, follower_id))
    return rows


def _parse_retweets(archive: dict, account_id: str, username: str, now: str) -> list:
    """
    Extract retweet metadata from tweets/community-tweets.
    Captures who they amplify without storing the RT text (not their own words).
    Parses 'RT @username: ...' to extract retweeted-from username.
    """
    rows = []
    for section in ("tweets", "community-tweet"):
        for item in archive.get(section, []):
            t = item.get("tweet", {})
            text = t.get("full_text", "")
            if not text.startswith("RT @"):
                continue
            rest = text[4:]  # strip "RT @"
            rt_of_username = rest.split(":")[0].strip() if ":" in rest else ""
            if not rt_of_username:
                continue
            rows.append((
                t.get("id_str") or t.get("id", ""),
                account_id,
                username,
                rt_of_username,
                t.get("created_at"),
                now,
            ))
    return rows


def store_archive(
    db_path: Path,
    archive: dict,
    account_id: str,
    username: str,
) -> dict:
    """
    Parse and insert one account's archive into the DB.

    Returns a summary dict: {tweet_count, like_count}.
    Uses INSERT OR IGNORE so re-running is safe.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = _open(db_path)

    tweet_rows    = _parse_tweets(archive, account_id, username, now)
    like_rows     = _parse_likes(archive, account_id, username, now)
    profile_row   = _parse_profile(archive, account_id, username, now)
    following_rows = _parse_following(archive, account_id)
    follower_rows  = _parse_followers(archive, account_id)
    retweet_rows   = _parse_retweets(archive, account_id, username, now)

    conn.executemany(
        """INSERT OR IGNORE INTO tweets
           (tweet_id, account_id, username, full_text, created_at,
            reply_to_tweet_id, reply_to_username, favorite_count,
            retweet_count, lang, is_note_tweet, fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        tweet_rows,
    )
    conn.executemany(
        """INSERT OR IGNORE INTO likes
           (liker_account_id, liker_username, tweet_id, full_text, expanded_url, fetched_at)
           VALUES (?,?,?,?,?,?)""",
        like_rows,
    )
    if profile_row:
        conn.execute(
            """INSERT OR REPLACE INTO profiles
               (account_id, username, display_name, bio, location, website, created_at, fetched_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            profile_row,
        )
    conn.executemany(
        "INSERT OR IGNORE INTO account_following (account_id, following_account_id) VALUES (?,?)",
        following_rows,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO account_followers (account_id, follower_account_id) VALUES (?,?)",
        follower_rows,
    )
    conn.executemany(
        """INSERT OR IGNORE INTO retweets
           (tweet_id, account_id, username, rt_of_username, created_at, fetched_at)
           VALUES (?,?,?,?,?,?)""",
        retweet_rows,
    )
    conn.execute(
        """INSERT OR REPLACE INTO fetch_log
           (username, account_id, status, tweet_count, like_count, fetched_at)
           VALUES (?,?,?,?,?,?)""",
        (username, account_id, "ok", len(tweet_rows), len(like_rows), now),
    )
    conn.commit()
    conn.close()

    return {
        "tweet_count":     len(tweet_rows),
        "like_count":      len(like_rows),
        "following_count": len(following_rows),
        "follower_count":  len(follower_rows),
        "retweet_count":   len(retweet_rows),
    }


def log_fetch_error(db_path: Path, username: str, account_id: Optional[str], error: str):
    now = datetime.now(timezone.utc).isoformat()
    conn = _open(db_path)
    conn.execute(
        """INSERT OR REPLACE INTO fetch_log
           (username, account_id, status, error_message, fetched_at)
           VALUES (?,?,?,?,?)""",
        (username, account_id, "error", error, now),
    )
    conn.commit()
    conn.close()


def log_not_found(db_path: Path, username: str, account_id: Optional[str]):
    now = datetime.now(timezone.utc).isoformat()
    conn = _open(db_path)
    conn.execute(
        """INSERT OR REPLACE INTO fetch_log
           (username, account_id, status, fetched_at)
           VALUES (?,?,?,?)""",
        (username, account_id, "not_found", now),
    )
    conn.commit()
    conn.close()
