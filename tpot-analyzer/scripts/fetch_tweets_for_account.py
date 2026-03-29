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
COST_PER_CALL = 0.03  # ~3000 credits/page, plan: 2M credits/$20

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


def fetch_advanced_search(
    api_key: str,
    query: str,
    query_type: str = "Latest",
) -> list[dict]:
    """GET /twitter/tweet/advanced_search?query=X&queryType=Latest|Top

    Args:
        api_key: Twitter API key.
        query: Search query (e.g., "from:username").
        query_type: "Latest" for chronological, "Top" for most-engaged.

    Returns list of tweet dicts.
    Sleeps 0.5s after the call for rate limiting.
    """
    url = f"{BASE_URL}/tweet/advanced_search"
    r = _make_request(api_key, url, {"query": query, "queryType": query_type})

    time.sleep(0.5)

    if r.status_code != 200:
        return []

    data = r.json()
    return data.get("tweets", [])


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_tweet(raw_tweet: dict, username: str) -> dict:
    """Convert a raw API response tweet dict into an enriched_tweets row dict.

    Extracts rich context (quoted tweets, media, URLs) into context_json
    so the LLM labeling prompt can see what images/links/quotes contain.
    """
    entities = raw_tweet.get("entities", {}) or {}
    user_mentions = entities.get("user_mentions", []) or []
    urls = entities.get("urls", []) or []
    ext_media = raw_tweet.get("extendedEntities", {}) or {}
    media_items = ext_media.get("media", []) or []

    mentions_json = json.dumps(
        [m.get("screen_name", "") for m in user_mentions]
    )

    # Build rich context that the LLM will see
    context_parts = []

    # Quoted tweet
    qt = raw_tweet.get("quoted_tweet")
    if qt and isinstance(qt, dict):
        qt_author = qt.get("author", {}).get("userName", "?")
        qt_text = qt.get("text", "")
        if qt_text:
            context_parts.append(f"[Quotes @{qt_author}: \"{qt_text[:200]}\"]")

    # Media (images/video)
    for m in media_items:
        mtype = m.get("type", "photo")
        murl = m.get("media_url_https", "")
        if mtype == "photo" and murl:
            context_parts.append(f"[Image: {murl}]")
        elif mtype == "video":
            context_parts.append("[Video attached]")
        elif mtype == "animated_gif":
            context_parts.append("[GIF attached]")

    # Expanded URLs (link previews)
    for u in urls:
        expanded = u.get("expanded_url", "")
        display = u.get("display_url", "")
        if expanded and not expanded.startswith("https://twitter.com/") and not expanded.startswith("https://x.com/"):
            context_parts.append(f"[Link: {display or expanded[:60]}]")

    # Reply context
    if raw_tweet.get("isReply") and raw_tweet.get("inReplyToUsername"):
        context_parts.append(f"[Replying to @{raw_tweet['inReplyToUsername']}]")

    context_json = json.dumps(context_parts) if context_parts else "[]"

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
        "has_media": 1 if (media_items or urls) else 0,
        "mentions_json": mentions_json,
        "context_json": context_json,
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
# Archive-first loading
# ---------------------------------------------------------------------------


def load_archive_tweets(
    conn: sqlite3.Connection,
    account_id: str,
    username: str,
    limit: int = 100,
) -> tuple[list[dict], int]:
    """Load tweets from the archive (tweets table) into enriched_tweets.

    For archive accounts (those who uploaded to Community Archive), we have
    their full tweet history — no need to pay for API calls.

    Returns (list of parsed tweet dicts, count of newly inserted).
    """
    # Check if this account has archive tweets
    archive_count = conn.execute(
        "SELECT COUNT(*) FROM tweets WHERE account_id = ?", (account_id,)
    ).fetchone()[0]

    if archive_count == 0:
        return [], 0

    tweet_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(tweets)").fetchall()
    }
    text_expr = "full_text" if "full_text" in tweet_columns else "text"
    like_expr = (
        "favorite_count"
        if "favorite_count" in tweet_columns
        else "like_count"
        if "like_count" in tweet_columns
        else "0"
    )
    retweet_expr = "retweet_count" if "retweet_count" in tweet_columns else "0"
    reply_expr = "reply_count" if "reply_count" in tweet_columns else "0"
    reply_user_expr = (
        "reply_to_username"
        if "reply_to_username" in tweet_columns
        else "in_reply_to_user"
        if "in_reply_to_user" in tweet_columns
        else "NULL"
    )

    if text_expr == "text" and "text" not in tweet_columns:
        raise RuntimeError(
            "tweets table is missing both full_text and text columns; "
            "cannot load archive tweets"
        )

    # Load archive tweets, prioritizing high-engagement ones
    rows = conn.execute(
        f"""SELECT tweet_id,
                   {text_expr} AS tweet_text,
                   {like_expr} AS like_count,
                   {retweet_expr} AS retweet_count,
                   {reply_expr} AS reply_count,
                   created_at,
                   lang,
                   {reply_user_expr} AS reply_to_user
            FROM tweets
            WHERE account_id = ?
            ORDER BY ({like_expr} + {retweet_expr} * 2 + {reply_expr}) DESC,
                     created_at DESC
            LIMIT ?""",
        (account_id, limit),
    ).fetchall()

    now = datetime.now(timezone.utc).isoformat()
    parsed = []
    inserted = 0

    for tweet_id, text, likes, rts, replies, created_at, lang, reply_to_user in rows:
        tweet_dict = {
            "tweet_id": str(tweet_id),
            "account_id": account_id,
            "username": username,
            "text": text or "",
            "like_count": likes or 0,
            "retweet_count": rts or 0,
            "reply_count": replies or 0,
            "view_count": 0,
            "created_at": created_at or "",
            "lang": lang or "",
            "is_reply": 1 if reply_to_user or (text or "").startswith("@") else 0,
            "in_reply_to_user": reply_to_user,
            "has_media": 0,
            "mentions_json": "[]",
        }
        parsed.append(tweet_dict)

        cursor = conn.execute(
            """INSERT OR IGNORE INTO enriched_tweets (
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
            )""",
            {
                **tweet_dict,
                "fetch_source": "archive",
                "fetch_query": None,
                "fetched_at": now,
            },
        )
        inserted += cursor.rowcount

    conn.commit()
    return parsed, inserted


# ---------------------------------------------------------------------------
# Multi-scale fetch strategy
# ---------------------------------------------------------------------------

# Default TTL: re-fetch if the most recent fetch is older than this many days
STALE_TTL_DAYS = 30


def is_stale(conn: sqlite3.Connection, account_id: str, ttl_days: int = STALE_TTL_DAYS) -> bool:
    """Check if an account's enriched tweets are stale (older than ttl_days).

    Returns True if account has no enriched tweets, or if the most recent
    fetch is older than ttl_days. Returns False if recently fetched.
    """
    row = conn.execute(
        "SELECT MAX(fetched_at) FROM enriched_tweets WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    if not row or not row[0]:
        return True  # never fetched
    try:
        from dateutil import parser as dp
        last_fetch = dp.parse(row[0])
        now = datetime.now(timezone.utc)
        age_days = (now - last_fetch).days
        return age_days >= ttl_days
    except Exception:
        return True  # can't parse date, treat as stale


def fetch_multi_scale(
    api_key: str | None,
    username: str,
    account_id: str,
    conn: sqlite3.Connection,
    round_num: int = 1,
    budget_limit: float = 5.0,
    archive_only: bool = False,
    archive_limit: int = 100,
) -> tuple[list[dict], int]:
    """Fetch tweets at multiple time scales for representative sampling.

    Strategy (archive-first):
      0. Check archive (tweets table) — if account has archive data, load top 100
         tweets by engagement. FREE, no API calls needed.
      1. Top tweets (queryType=Top): most-engaged originals — strongest identity signal
      2. Recent tweets (last_tweets): current interests — what they're posting NOW
      3. Latest search (queryType=Latest): recent chronological — catches replies, threads
      4. Time-windowed search: tweets from 3-6 months ago for temporal diversity

    Archive tweets are loaded first. API calls supplement with recent activity
    that post-dates the archive snapshot unless archive_only=True.

    Each call is logged. Budget is checked before each call.
    Returns (all parsed tweets, count of new tweets stored).
    """
    all_parsed = []
    total_new = 0

    def _fetch_and_store(tweets_raw, source, query=None):
        nonlocal all_parsed, total_new
        parsed = [parse_tweet(t, username) for t in tweets_raw if t.get("id")]
        new = store_tweets(conn, parsed, source, query)
        log_api_call(conn, account_id, username, round_num, source, len(parsed), query)
        all_parsed.extend(parsed)
        total_new += new
        return len(parsed)

    # 0. Archive-first: load from tweets table if available (FREE)
    archive_parsed, archive_new = load_archive_tweets(
        conn,
        account_id,
        username,
        limit=archive_limit,
    )
    if archive_parsed:
        all_parsed.extend(archive_parsed)
        total_new += archive_new
        import logging
        logging.getLogger(__name__).info(
            "Loaded %d archive tweets for @%s (%d new to enriched_tweets)",
            len(archive_parsed), username, archive_new,
        )

    if archive_only:
        if archive_parsed:
            return all_parsed, total_new
        raise RuntimeError(
            f"Archive-only mode requested for @{username} ({account_id}) "
            "but no archive tweets were found."
        )

    if not api_key:
        raise RuntimeError(
            "Twitter API key required for multi-scale fetch when archive_only is disabled."
        )

    # 1. Top tweets — most-engaged, best identity signal (supplements archive with recent)
    check_budget(conn, budget_limit, raise_on_exceed=True)
    top_tweets = fetch_advanced_search(api_key, f"from:{username}", query_type="Top")
    if top_tweets:
        n = _fetch_and_store(top_tweets, "advanced_search_top", f"from:{username}")

    # 2. Recent timeline — current interests
    check_budget(conn, budget_limit, raise_on_exceed=True)
    recent, author = fetch_last_tweets(api_key, username)
    if recent:
        n = _fetch_and_store(recent, "last_tweets")

    # 3. Latest search — catches different tweets than timeline
    check_budget(conn, budget_limit, raise_on_exceed=True)
    latest = fetch_advanced_search(api_key, f"from:{username}", query_type="Latest")
    if latest:
        n = _fetch_and_store(latest, "advanced_search", f"from:{username}")

    # 4. Time-windowed search for temporal diversity (3-6 months ago)
    # advanced_search supports sinceTime/untilTime but we use date operators in query
    try:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        # 3 months ago window
        since_3m = (now - timedelta(days=120)).strftime("%Y-%m-%d")
        until_3m = (now - timedelta(days=60)).strftime("%Y-%m-%d")
        check_budget(conn, budget_limit, raise_on_exceed=True)
        older = fetch_advanced_search(
            api_key,
            f"from:{username} since:{since_3m} until:{until_3m}",
            query_type="Top",
        )
        if older:
            n = _fetch_and_store(older, "advanced_search_older", f"from:{username} since:{since_3m} until:{until_3m}")
    except BudgetExhaustedError:
        pass  # Skip temporal diversity if budget is tight

    return all_parsed, total_new


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
