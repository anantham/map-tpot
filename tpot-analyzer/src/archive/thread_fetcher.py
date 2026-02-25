"""
Fetch tweet thread context from twitterapi.io, with local SQLite cache.

Every result is saved to archive_tweets.db (thread_context_cache table)
so we never pay for the same tweet twice.

Cost: ~$0.15/1000 calls. Use strategically — only for tweets we need
to classify that are replies to accounts outside our 334.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import httpx

TWITTERAPI_BASE = "https://api.twitterapi.io/twitter/tweet/thread_context"

log = logging.getLogger(__name__)


def _get_api_key() -> str:
    for var in ("TWITTERAPI_IO_API_KEY", "TWITTERAPI_API_KEY", "API_KEY"):
        v = os.environ.get(var)
        if v:
            return v
    raise RuntimeError(
        "No twitterapi.io key found. Set TWITTERAPI_IO_API_KEY or API_KEY in .env"
    )


def _open(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    # Ensure table exists (idempotent)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS thread_context_cache (
            tweet_id   TEXT PRIMARY KEY,
            raw_json   TEXT NOT NULL,
            fetched_at TEXT
        )
    """)
    conn.commit()
    return conn


def get_thread_context(
    tweet_id: str,
    db_path: Path,
    force_refresh: bool = False,
) -> Optional[List[dict]]:
    """
    Return the ordered list of tweets in a thread, from the top.
    Uses local cache — only hits the API if not already cached.

    Returns None if the tweet can't be found or the API errors.
    """
    conn = _open(db_path)

    if not force_refresh:
        row = conn.execute(
            "SELECT raw_json FROM thread_context_cache WHERE tweet_id = ?",
            (tweet_id,)
        ).fetchone()
        if row:
            log.debug("Thread cache hit for %s", tweet_id)
            conn.close()
            return json.loads(row[0])

    api_key = _get_api_key()
    log.info("Fetching thread context for %s (API call)", tweet_id)

    try:
        response = httpx.get(
            TWITTERAPI_BASE,
            params={"tweetId": tweet_id},
            headers={"X-API-Key": api_key},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        tweets = data.get("tweets", [])

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO thread_context_cache (tweet_id, raw_json, fetched_at) VALUES (?,?,?)",
            (tweet_id, json.dumps(tweets), now),
        )
        conn.commit()
        conn.close()
        return tweets

    except Exception as e:
        log.error("Failed to fetch thread context for %s: %s", tweet_id, e)
        conn.close()
        return None


def format_thread_for_prompt(tweets: List[dict], target_tweet_id: str) -> str:
    """
    Format a thread as a readable string for inclusion in an LLM prompt.
    Marks the target tweet clearly so the model knows what to classify.
    """
    lines = []
    for t in tweets:
        author = t.get("author", {}).get("userName", "?")
        text = t.get("text", "").strip()
        tid = t.get("id", "")
        marker = " ← CLASSIFY THIS" if tid == target_tweet_id else ""
        lines.append(f"@{author}: {text}{marker}")
    return "\n".join(lines)
