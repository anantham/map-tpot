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
    links_json  TEXT,
    fetched_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS link_content_cache (
    url_hash    TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    resolved_url TEXT,
    title       TEXT,
    description TEXT,
    body_text   TEXT,
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


def resolve_tco_url(tco_url: str) -> str | None:
    """Resolve a t.co short URL to its final destination."""
    try:
        req = urllib.request.Request(tco_url)
        req.add_header("User-Agent", "Mozilla/5.0")
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.url
    except Exception as e:
        logger.debug("Failed to resolve %s: %s", tco_url, e)
        return None


def fetch_link_content(url: str, db_path: Path | None = None) -> dict:
    """Fetch external link content — title, description, body text. Cached."""
    import hashlib
    import re

    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    conn = sqlite3.connect(str(db_path or DB_PATH))
    _ensure_cache_table(conn)

    cached = conn.execute(
        "SELECT title, description, body_text FROM link_content_cache WHERE url_hash = ?",
        (url_hash,),
    ).fetchone()
    if cached:
        conn.close()
        return {"title": cached[0], "description": cached[1],
                "body_text": cached[2], "url": url, "cached": True}

    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode("utf-8", errors="replace")[:100000]

        # Extract og:title, og:description
        og_title = re.search(r'<meta\s+(?:property|name)="og:title"\s+content="([^"]*)"', html)
        og_desc = re.search(r'<meta\s+(?:property|name)="og:description"\s+content="([^"]*)"', html)
        title_tag = re.search(r"<title>([^<]*)</title>", html)

        title = (og_title.group(1) if og_title else
                 title_tag.group(1) if title_tag else None)
        description = og_desc.group(1) if og_desc else None

        # Extract body text (strip scripts/styles/tags)
        clean = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        clean = re.sub(r"<style[^>]*>.*?</style>", "", clean, flags=re.DOTALL)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        # Truncate to ~2000 chars for context
        body_text = clean[:2000] if clean else None

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO link_content_cache "
            "(url_hash, url, resolved_url, title, description, body_text, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (url_hash, url, url, title, description, body_text, now),
        )
        conn.commit()
        conn.close()
        return {"title": title, "description": description,
                "body_text": body_text, "url": url, "cached": False}
    except Exception as e:
        logger.warning("Failed to fetch link content %s: %s", url, e)
        conn.close()
        return {"title": None, "description": None,
                "body_text": None, "url": url, "cached": False}


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

    tco_urls = re.findall(r"https://t\.co/\S+", tweet_text or "")
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
