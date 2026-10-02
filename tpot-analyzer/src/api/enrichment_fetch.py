"""Bounded network boundary for rich tweet HTML, syndication and image fetches."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import re
import sqlite3
import warnings
from datetime import datetime, timezone
from pathlib import Path

from src.api.enrichment_cache import ensure_cache_table
from src.api.url_guard import BlockedURLError, safe_urlopen
from src.config import DEFAULT_ARCHIVE_DB

logger = logging.getLogger(__name__)
HTML_MAX_BYTES = 100_000
SYNDICATION_MAX_BYTES = 1_048_576
IMAGE_MAX_BYTES = 5_242_880
IMAGE_MAX_PIXELS = 16_000_000
HEADERS = {"User-Agent": "Mozilla/5.0"}
_SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token=x"


def fetch_syndication(tweet_id: str) -> dict | None:
    """Fetch bounded JSON via the same public-address/redirect policy as links."""
    if not str(tweet_id).isdigit() or len(str(tweet_id)) > 32:
        logger.warning("Refusing invalid syndication tweet ID")
        return None
    try:
        with safe_urlopen(_SYNDICATION_URL.format(tweet_id=tweet_id), timeout=10,
                          headers=HEADERS, max_bytes=SYNDICATION_MAX_BYTES) as response:
            data = json.loads(response.read())
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("Syndication fetch failed (%s)", type(exc).__name__)
        return None


def resolve_tco_url(tco_url: str) -> str | None:
    """Resolve a guarded short link without reading the destination's body."""
    try:
        with safe_urlopen(tco_url, timeout=5, headers=HEADERS, max_bytes=HTML_MAX_BYTES) as response:
            return response.url
    except Exception as exc:
        logger.debug("Short-link resolution failed (%s)", type(exc).__name__)
        return None


def fetch_link_content(url: str, db_path: Path | None = None) -> dict:
    """Cache HTML only after a successful bounded download; preserve empty fallback."""
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    empty = {"title": None, "description": None, "body_text": None, "url": url, "cached": False}
    conn = sqlite3.connect(str(db_path or DEFAULT_ARCHIVE_DB))
    try:
        ensure_cache_table(conn)
        cached = conn.execute(
            "SELECT title, description, body_text FROM link_content_cache WHERE url_hash = ?",
            (url_hash,),
        ).fetchone()
        if cached:
            return dict(zip(("title", "description", "body_text"), cached), url=url, cached=True)
        with safe_urlopen(url, timeout=10, headers=HEADERS, max_bytes=HTML_MAX_BYTES) as response:
            html = response.read().decode("utf-8", errors="replace")
            resolved_url = response.url
        og_title = re.search(r'<meta\s+(?:property|name)="og:title"\s+content="([^"]*)"', html)
        og_desc = re.search(r'<meta\s+(?:property|name)="og:description"\s+content="([^"]*)"', html)
        title_tag = re.search(r"<title>([^<]*)</title>", html)
        title = og_title.group(1) if og_title else title_tag.group(1) if title_tag else None
        description = og_desc.group(1) if og_desc else None
        clean = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        clean = re.sub(r"<style[^>]*>.*?</style>", "", clean, flags=re.DOTALL)
        clean = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", clean)).strip()
        body_text = clean[:2000] if clean else None
        conn.execute(
            "INSERT OR REPLACE INTO link_content_cache "
            "(url_hash, url, resolved_url, title, description, body_text, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (url_hash, url, resolved_url, title, description, body_text, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return {"title": title, "description": description, "body_text": body_text, "url": url, "cached": False}
    except Exception as exc:
        logger.warning("Link content fetch failed (%s)", type(exc).__name__)
        return empty
    finally:
        conn.close()


def _image_mime(data: bytes) -> str:
    """Validate supported raster bytes before encoding or downstream decoding.

    Single-frame images only: animation frame count cannot multiply the pixel
    budget. Pillow is imported lazily; a missing decoder fails closed.
    """
    from PIL import Image
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as image:
            mime = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp"}.get(image.format)
            if not mime or image.width * image.height > IMAGE_MAX_PIXELS or getattr(image, "n_frames", 1) != 1:
                raise BlockedURLError("image format, pixel or frame limit exceeded")
            image.verify()
        # Force bounded decode as verify() alone does not validate JPEG pixels.
        with Image.open(io.BytesIO(data)) as image:
            image.load()
        return mime


def download_image_base64(url: str) -> str | None:
    """Return a validated raster data URL with byte/pixel limits, or no image."""
    try:
        with safe_urlopen(url, timeout=10, headers=HEADERS, max_bytes=IMAGE_MAX_BYTES) as response:
            data = response.read()
        mime = _image_mime(data)
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    except Exception as exc:
        logger.warning("Image download rejected (%s)", type(exc).__name__)
        return None
