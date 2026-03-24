"""Fetch tweets for a given account from twitterapi.io.

Supports two fetch modes:
  - last_tweets: GET /twitter/user/last_tweets — recent timeline for a user
  - advanced_search: GET /twitter/tweet/advanced_search — arbitrary query

All tweets are stored in enriched_tweets (INSERT OR IGNORE for dedup).
Every API call is logged in enrichment_log for cost tracking.

Budget guard: check_budget() compares cumulative estimated_cost against a
limit and can raise BudgetExhaustedError before any call is made.

Cross-validation guard: assert_not_holdout() blocks enrichment of accounts
in tpot_directory_holdout, preserving evaluation integrity.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.twitterapi.io/twitter"
COST_PER_CALL = 0.05  # estimated $/call

KEY_ENV_CANDIDATES = (
    "TWITTERAPI_IO_API_KEY",
    "TWITTERAPI_API_KEY",
    "TWITTERAPIIO_API_KEY",
    "TWITTERAPI_KEY",
    "API_KEY",
)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class BudgetExhaustedError(Exception):
    """Raised when cumulative API spend has reached the configured limit."""


# ---------------------------------------------------------------------------
# API key resolution
# ---------------------------------------------------------------------------

def get_api_key() -> str:
    """Resolve Twitter API key from environment.

    Tries KEY_ENV_CANDIDATES in order; raises RuntimeError if none found.
    """
    for key_name in KEY_ENV_CANDIDATES:
        val = os.getenv(key_name)
        if val:
            return val
    raise RuntimeError(
        f"No twitterapi.io API key found. Tried: {', '.join(KEY_ENV_CANDIDATES)}"
    )


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def _make_request(api_key: str, url: str, params: dict) -> httpx.Response:
    """Make a single GET request with retry logic for 429 and 5xx."""
    r = httpx.get(url, params=params, headers={"X-API-Key": api_key}, timeout=20)

    if r.status_code == 429:
        time.sleep(60)
        r = httpx.get(url, params=params, headers={"X-API-Key": api_key}, timeout=20)

    elif r.status_code >= 500:
        time.sleep(5)
        r = httpx.get(url, params=params, headers={"X-API-Key": api_key}, timeout=20)

    if 400 <= r.status_code < 500 and r.status_code != 429:
        r.raise_for_status()

    return r


def fetch_last_tweets(api_key: str, username: str) -> tuple[list[dict], dict | None]:
    """GET /twitter/user/last_tweets?userName=X

    Returns (list of tweet dicts, author info dict or None).
    Sleeps 0.5s after the call for rate limiting.
    """
    url = f"{BASE_URL}/user/last_tweets"
    r = _make_request(api_key, url, {"userName": username})

    time.sleep(0.5)

    if r.status_code != 200:
        return [], None

    data = r.json()
    # API nests tweets under data.data.tweets or data.tweets depending on endpoint
    inner = data.get("data", {})
    if isinstance(inner, dict):
        tweets = inner.get("tweets", [])
    else:
        tweets = data.get("tweets", [])

    # Author info from first tweet
    author = None
    if tweets:
        author = tweets[0].get("author")
    if author is None:
        author = data.get("author") or data.get("user")

    return tweets, author


def fetch_advanced_search(api_key: str, query: str) -> list[dict]:
    """GET /twitter/tweet/advanced_search?query=X&queryType=Latest

    Returns list of tweet dicts.
    Sleeps 0.5s after the call for rate limiting.
    """
    url = f"{BASE_URL}/tweet/advanced_search"
    r = _make_request(api_key, url, {"query": query, "queryType": "Latest"})

    time.sleep(0.5)

    if r.status_code != 200:
        return []

    data = r.json()
    return data.get("tweets", [])


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_tweet(raw_tweet: dict, username: str) -> dict:
    """Convert a raw API response tweet dict into an enriched_tweets row dict."""
    entities = raw_tweet.get("entities", {}) or {}
    user_mentions = entities.get("user_mentions", []) or []
    urls = entities.get("urls", []) or []

    mentions_json = json.dumps(
        [m.get("screen_name", "") for m in user_mentions]
    )

    return {
        "tweet_id": str(raw_tweet["id"]),
        "account_id": str(raw_tweet["author"]["id"]),
        "username": username,
        "text": raw_tweet.get("text", ""),
        "like_count": raw_tweet.get("likeCount", 0),
        "retweet_count": raw_tweet.get("retweetCount", 0),
        "reply_count": raw_tweet.get("replyCount", 0),
        "view_count": raw_tweet.get("viewCount", 0),
        "created_at": raw_tweet.get("createdAt", ""),
        "lang": raw_tweet.get("lang", ""),
        "is_reply": 1 if raw_tweet.get("isReply", False) else 0,
        "in_reply_to_user": raw_tweet.get("inReplyToUsername"),
        "has_media": 1 if urls else 0,
        "mentions_json": mentions_json,
    }


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def store_tweets(
    conn: sqlite3.Connection,
    parsed_tweets: list[dict],
    fetch_source: str,
    fetch_query: str | None = None,
) -> int:
    """INSERT OR IGNORE parsed tweet dicts into enriched_tweets.

    Returns the count of newly inserted rows (ignores duplicates).
    """
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0

    for tweet in parsed_tweets:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO enriched_tweets (
                tweet_id, account_id, username, text,
                like_count, retweet_count, reply_count, view_count,
                created_at, lang, is_reply, in_reply_to_user,
                has_media, mentions_json,
                fetch_source, fetch_query, fetched_at
            ) VALUES (
                :tweet_id, :account_id, :username, :text,
                :like_count, :retweet_count, :reply_count, :view_count,
                :created_at, :lang, :is_reply, :in_reply_to_user,
                :has_media, :mentions_json,
                :fetch_source, :fetch_query, :fetched_at
            )
            """,
            {
                **tweet,
                "fetch_source": fetch_source,
                "fetch_query": fetch_query,
                "fetched_at": now,
            },
        )
        inserted += cursor.rowcount

    conn.commit()
    return inserted


# ---------------------------------------------------------------------------
# Budget tracking
# ---------------------------------------------------------------------------

def check_budget(
    conn: sqlite3.Connection,
    limit: float = 5.0,
    raise_on_exceed: bool = False,
) -> bool:
    """Return True if cumulative spend is under limit, False otherwise.

    If raise_on_exceed is True and the budget is exhausted, raises
    BudgetExhaustedError instead of returning False.
    """
    row = conn.execute(
        "SELECT COALESCE(SUM(estimated_cost), 0.0) FROM enrichment_log"
    ).fetchone()
    total = row[0] if row else 0.0

    if total >= limit:
        if raise_on_exceed:
            raise BudgetExhaustedError(
                f"Budget exhausted: ${total:.4f} spent >= ${limit:.2f} limit"
            )
        return False

    return True


# ---------------------------------------------------------------------------
# Holdout guard
# ---------------------------------------------------------------------------

def assert_not_holdout(conn: sqlite3.Connection, account_id: str) -> None:
    """Raise ValueError if account_id is in tpot_directory_holdout.

    This preserves cross-validation integrity by preventing enrichment of
    accounts reserved for evaluation.
    """
    # Table may not exist yet in all environments; treat absence as non-holdout.
    try:
        row = conn.execute(
            "SELECT 1 FROM tpot_directory_holdout WHERE account_id = ? LIMIT 1",
            (account_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        # Table doesn't exist — no holdout accounts defined
        return

    if row is not None:
        raise ValueError(
            f"Cannot enrich holdout account {account_id}: "
            "this account is reserved for evaluation and must not be enriched."
        )


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_api_call(
    conn: sqlite3.Connection,
    account_id: str,
    username: str,
    round_num: int,
    action: str,
    tweets_fetched: int,
    query: str | None = None,
    cost: float = COST_PER_CALL,
) -> None:
    """INSERT a row into enrichment_log for one API call."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO enrichment_log (
            account_id, username, round, action,
            query, api_calls, tweets_fetched,
            estimated_cost, created_at
        ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (account_id, username, round_num, action, query, tweets_fetched, cost, now),
    )
    conn.commit()
