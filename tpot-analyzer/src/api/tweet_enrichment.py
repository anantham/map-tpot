"""Tweet enrichment — resolve media, quote tweets, and links via syndication API.

Uses Twitter's syndication API (no auth needed) to fetch:
- Image/video URLs (pbs.twimg.com) + base64-encoded image data for multimodal models
- Quote tweet text and author
- Full tweet text (may differ from archive due to character limits)

Results are cached in tweet_enrichment_cache to avoid redundant API calls.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

from src.config import DEFAULT_ARCHIVE_DB
from src.api.enrichment_cache import CACHE_SCHEMA, ensure_cache_table as _ensure_cache_table
from src.api.enrichment_fetch import (
    download_image_base64, fetch_link_content, fetch_syndication, resolve_tco_url,
)

DB_PATH = DEFAULT_ARCHIVE_DB

def get_thread_context(
    tweet_id: str, db_path: Path | None = None, max_depth: int = 10,
) -> list[dict]:
    """Walk the reply chain to get full thread context.

    Returns list of tweets from root → current, oldest first.
    """
    conn = sqlite3.connect(str(db_path or DB_PATH))
    conn.row_factory = sqlite3.Row

    chain = []
    current = tweet_id
    depth = 0
    while current and depth < max_depth:
        row = conn.execute(
            "SELECT tweet_id, account_id, username, full_text, reply_to_tweet_id, "
            "favorite_count, retweet_count FROM tweets WHERE tweet_id = ?",
            (current,),
        ).fetchone()
        if not row:
            break
        chain.append({
            "tweet_id": row["tweet_id"],
            "username": row["username"],
            "text": (row["full_text"] or "")[:300],
            "engagement": (row["favorite_count"] or 0) + (row["retweet_count"] or 0),
            "is_target": row["tweet_id"] == tweet_id,
        })
        current = row["reply_to_tweet_id"]
        depth += 1

    conn.close()
    chain.reverse()  # root first
    return chain


def resolve_tweet_links(tweet_text: str, db_path: Path | None = None) -> list[dict]:
    """Resolve all t.co links in a tweet to their destinations + content.

    Returns list of {tco_url, resolved_url, type, content}.
    Type is: "media", "quote_tweet", "external"
    """
    import re
    from itertools import islice

    tco_urls = [match.group() for match in islice(re.finditer(r"https://t\.co/\S+", tweet_text or ""), 5)]
    results = []

    for tco in tco_urls:
        resolved = resolve_tco_url(tco)
        if not resolved:
            results.append({"tco_url": tco, "type": "unresolved"})
            continue

        if "/photo/" in resolved or "/video/" in resolved:
            results.append({
                "tco_url": tco, "resolved_url": resolved, "type": "media",
            })
        elif ("x.com" in resolved or "twitter.com" in resolved) and "/status/" in resolved:
            # Extract tweet ID from URL
            match = re.search(r"/status/(\d+)", resolved)
            quote_tid = match.group(1) if match else None
            results.append({
                "tco_url": tco, "resolved_url": resolved, "type": "quote_tweet",
                "quoted_tweet_id": quote_tid,
            })
        else:
            # External link — fetch content
            content = fetch_link_content(resolved, db_path)
            results.append({
                "tco_url": tco, "resolved_url": resolved, "type": "external",
                "title": content.get("title"),
                "description": content.get("description"),
                "body_excerpt": (content.get("body_text") or "")[:500],
            })

    return results


def get_retweet_source(
    tweet_id: str, account_id: str, db_path: Path | None = None,
) -> dict | None:
    """If this tweet_id is a retweet by this account, fetch the original via syndication.

    Returns:
        {"tweet_id": "...", "username": "...", "text": "...", "media": [...]} or None
    """
    conn = sqlite3.connect(str(db_path or DB_PATH))
    row = conn.execute(
        "SELECT rt_of_username FROM retweets WHERE tweet_id = ? AND account_id = ?",
        (tweet_id, account_id),
    ).fetchone()
    conn.close()

    if not row:
        return None

    rt_of = row[0]

    # Try archive first
    conn = sqlite3.connect(str(db_path or DB_PATH))
    archive_row = conn.execute(
        "SELECT full_text, username FROM tweets WHERE tweet_id = ?", (tweet_id,),
    ).fetchone()
    conn.close()

    if archive_row and archive_row[0]:
        return {
            "tweet_id": tweet_id,
            "username": archive_row[1] or rt_of,
            "text": archive_row[0],
            "source": "archive",
        }

    # Fallback to syndication
    data = fetch_syndication(tweet_id)
    if not data:
        return {"tweet_id": tweet_id, "username": rt_of, "text": None, "source": "failed"}

    media = [
        {"type": m.get("type", "unknown"), "url": m.get("media_url_https", "")}
        for m in data.get("mediaDetails", [])
    ]

    return {
        "tweet_id": tweet_id,
        "username": data.get("user", {}).get("screen_name", rt_of),
        "text": data.get("text", ""),
        "media": media,
        "source": "syndication",
    }


def enrich_tweet(tweet_id: str, db_path: Path | None = None) -> dict:
    """Enrich a tweet with media URLs, quote tweet text, and resolved links.

    Returns:
        {
            "media": [{"type": "photo", "url": "https://pbs.twimg.com/..."}],
            "quote_tweet": {"username": "...", "text": "...", "tweet_id": "..."} or None,
            "full_text": "..." (syndication version, may be longer than archive),
            "cached": True/False,
        }
    """
    conn = sqlite3.connect(str(db_path or DB_PATH))
    _ensure_cache_table(conn)

    # Check cache first
    cached = conn.execute(
        "SELECT media_json, quote_json, full_text FROM tweet_enrichment_cache WHERE tweet_id = ?",
        (tweet_id,),
    ).fetchone()

    if cached:
        conn.close()
        return {
            "media": json.loads(cached[0]) if cached[0] else [],
            "quote_tweet": json.loads(cached[1]) if cached[1] else None,
            "full_text": cached[2],
            "cached": True,
        }

    # Fetch from syndication API
    data = fetch_syndication(tweet_id)
    if not data:
        conn.close()
        return {"media": [], "quote_tweet": None, "full_text": None, "cached": False}

    # Extract media
    media = []
    for m in data.get("mediaDetails", []):
        entry = {
            "type": m.get("type", "unknown"),
            "url": m.get("media_url_https", ""),
        }
        # For videos, try to get the video URL
        if m.get("type") == "video":
            variants = m.get("video_info", {}).get("variants", [])
            mp4s = [v for v in variants if v.get("content_type") == "video/mp4"]
            if mp4s:
                best = max(mp4s, key=lambda v: v.get("bitrate", 0))
                entry["video_url"] = best.get("url", "")
        media.append(entry)

    # Extract quote tweet
    quote_tweet = None
    qt = data.get("quoted_tweet")
    if qt:
        qt_user = qt.get("user", {})
        quote_tweet = {
            "tweet_id": qt.get("id_str", ""),
            "username": qt_user.get("screen_name", ""),
            "display_name": qt_user.get("name", ""),
            "text": qt.get("text", ""),
        }

    full_text = data.get("text")

    # Cache result
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO tweet_enrichment_cache (tweet_id, media_json, quote_json, full_text, fetched_at) VALUES (?, ?, ?, ?, ?)",
        (
            tweet_id,
            json.dumps(media) if media else None,
            json.dumps(quote_tweet) if quote_tweet else None,
            full_text,
            now,
        ),
    )
    conn.commit()
    conn.close()

    return {
        "media": media,
        "quote_tweet": quote_tweet,
        "full_text": full_text,
        "cached": False,
    }


def get_image_data_urls(enrichment: dict, max_images: int = 3) -> list[str]:
    """Download media images and return as base64 data URLs for multimodal API calls.

    Args:
        enrichment: Result from enrich_tweet()
        max_images: Max number of images to download (to control token usage)

    Returns:
        List of data URLs like "data:image/jpeg;base64,..."
    """
    data_urls = []
    for m in enrichment.get("media", [])[:max(0, min(max_images, 3))]:
        if m.get("type") == "photo" and m.get("url"):
            data_url = download_image_base64(m["url"])
            if data_url:
                data_urls.append(data_url)
    return data_urls


def enrich_batch(tweet_ids: list[str], db_path: Path | None = None) -> dict[str, dict]:
    """Enrich multiple tweets. Returns {tweet_id: enrichment_dict}."""
    results = {}
    for tid in tweet_ids:
        results[tid] = enrich_tweet(tid, db_path)
    return results
