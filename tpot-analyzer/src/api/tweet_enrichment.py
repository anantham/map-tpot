"""Tweet enrichment — resolve media, quote tweets, and links via syndication API.

Uses Twitter's syndication API (no auth needed) to fetch:
- Image/video URLs (pbs.twimg.com) + base64-encoded image data for multimodal models
- Quote tweet text and author
- Full tweet text (may differ from archive due to character limits)

Results are cached in tweet_enrichment_cache to avoid redundant API calls.
"""
from __future__ import annotations

import base64
import json
import logging
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data" / "archive_tweets.db"

_SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token=x"

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS tweet_enrichment_cache (
    tweet_id    TEXT PRIMARY KEY,
    media_json  TEXT,
    quote_json  TEXT,
    full_text   TEXT,
    fetched_at  TEXT NOT NULL
);
"""


def _ensure_cache_table(conn: sqlite3.Connection) -> None:
    conn.executescript(CACHE_SCHEMA)


def fetch_syndication(tweet_id: str) -> dict | None:
    """Fetch tweet data from Twitter syndication API. Returns parsed JSON or None."""
    url = _SYNDICATION_URL.format(tweet_id=tweet_id)
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        logger.warning("Syndication fetch failed for %s: %s", tweet_id, e)
        return None


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


def download_image_base64(url: str) -> str | None:
    """Download an image and return as base64 data URL for multimodal models."""
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")
        resp = urllib.request.urlopen(req, timeout=10)
        img_data = resp.read()
        # Determine content type from URL
        if url.endswith(".png"):
            mime = "image/png"
        elif url.endswith(".gif"):
            mime = "image/gif"
        elif url.endswith(".webp"):
            mime = "image/webp"
        else:
            mime = "image/jpeg"
        b64 = base64.b64encode(img_data).decode("utf-8")
        return f"data:{mime};base64,{b64}"
    except Exception as e:
        logger.warning("Failed to download image %s: %s", url, e)
        return None


def get_image_data_urls(enrichment: dict, max_images: int = 3) -> list[str]:
    """Download media images and return as base64 data URLs for multimodal API calls.

    Args:
        enrichment: Result from enrich_tweet()
        max_images: Max number of images to download (to control token usage)

    Returns:
        List of data URLs like "data:image/jpeg;base64,..."
    """
    data_urls = []
    for m in enrichment.get("media", [])[:max_images]:
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
