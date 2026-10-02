"""Test intent: rich enrichment preserves fallback UX while bounding inputs.

- Oversized encoded/decoded HTML fails without poisoning the local cache.
- Valid bounded HTML and syndication preserve their existing public results.
- Images use verified bytes for MIME and reject pixel bombs/invalid/animated data.
- Caller-provided counts cannot exceed fixed per-enrichment work caps.
Every HTTP socket and cache database is synthetic or temporary.
"""
from __future__ import annotations

import base64
import gzip
import io
import sqlite3
import struct
import zlib

import pytest

from src.api import tweet_enrichment
from src.api.enrichment_fetch import HTML_MAX_BYTES, IMAGE_MAX_BYTES
from tests.test_outbound_transport import network, wire


def png(width=1, height=1):
    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0\0\xff\0\xff")) + chunk(b"IEND", b""))


@pytest.mark.parametrize("body,headers", [
    (b"x" * (HTML_MAX_BYTES + 1), b""),
    (gzip.compress(b"x" * (HTML_MAX_BYTES + 1)), b"Content-Encoding: gzip\r\n"),
])
def test_oversized_html_returns_fallback_without_cache_write(network, tmp_path, body, headers):
    pending, sockets = network
    pending.append((wire(body, headers),))
    db = tmp_path / "cache.db"
    result = tweet_enrichment.fetch_link_content("http://public.example/article", db)
    assert result["body_text"] is None
    assert result["cached"] is False
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM link_content_cache").fetchone()[0] == 0
    assert sockets[0].closed


def test_valid_html_remains_cacheable_and_closes_responses(network, tmp_path):
    pending, sockets = network
    pending.append((wire(b'<title>Test article</title><p>A short article.</p>'),))
    db = tmp_path / "cache.db"
    url = "http://public.example/article"
    result = tweet_enrichment.fetch_link_content(url, db)
    assert result["title"] == "Test article"
    assert result["body_text"] == "Test article A short article."
    assert tweet_enrichment.fetch_link_content(url, db)["cached"] is True
    assert len(sockets) == 1 and sockets[0].closed


def test_syndication_is_bounded_and_retains_json_result(network, tmp_path):
    pending, sockets = network
    # Synthetic HTTP avoids a real TLS connection while exercising same fetch.
    from src.api import enrichment_fetch
    original = enrichment_fetch._SYNDICATION_URL
    enrichment_fetch._SYNDICATION_URL = "http://public.example/?id={tweet_id}"
    try:
        pending.append((wire(b'{"text":"example"}'),))
        assert tweet_enrichment.fetch_syndication("123") == {"text": "example"}
        assert tweet_enrichment.fetch_syndication("not-a-number") is None
    finally:
        enrichment_fetch._SYNDICATION_URL = original
    assert len(sockets) == 1 and sockets[0].closed


def test_short_link_resolution_closes_without_body_download(network):
    pending, sockets = network
    pending.append((wire(b"body that need not be read"),))
    assert tweet_enrichment.resolve_tco_url("http://public.example/") == "http://public.example/"
    assert sockets[0].closed


def test_valid_image_uses_detected_format_instead_of_extension(network):
    pending, sockets = network
    data = png()
    pending.append((wire(data),))
    result = tweet_enrichment.download_image_base64("http://public.example/looks-like.jpg")
    assert result == "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    assert sockets[0].closed


@pytest.mark.parametrize("data", [png(4001, 4000), png(20_000, 20_000), b"not an image", b"\xff\xd8\xff\xe0broken JPEG"])
def test_image_pixel_bomb_and_invalid_images_fail_closed(network, data):
    pending, sockets = network
    pending.append((wire(data),))
    assert tweet_enrichment.download_image_base64("http://public.example/image.png") is None
    assert sockets[0].closed


def test_animated_image_fails_closed(network):
    from PIL import Image
    image = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(image, format="GIF", save_all=True,
                                        append_images=[Image.new("RGB", (2, 2), "blue")])
    pending, _ = network
    pending.append((wire(image.getvalue()),))
    assert tweet_enrichment.download_image_base64("http://public.example/image.gif") is None


def test_missing_image_decoder_fails_closed(network, monkeypatch):
    import sys
    pending, _ = network
    pending.append((wire(png()),))
    monkeypatch.setitem(sys.modules, "PIL", None)
    assert tweet_enrichment.download_image_base64("http://public.example/image.png") is None


def test_oversized_image_is_stopped_before_base64(network):
    pending, sockets = network
    pending.append((wire(b"x" * (IMAGE_MAX_BYTES + 1)),))
    assert tweet_enrichment.download_image_base64("http://public.example/image.jpg") is None
    assert sockets[0].closed


def test_caller_cannot_raise_image_count(monkeypatch):
    observed = []
    def download(url):
        observed.append(url)
        return "data:image/png;base64,synthetic"
    monkeypatch.setattr(tweet_enrichment, "download_image_base64", download)
    result = tweet_enrichment.get_image_data_urls(
        {"media": [{"type": "photo", "url": f"http://public.example/{i}"} for i in range(10)]},
        max_images=100,
    )
    assert len(result) == len(observed) == 3


def test_link_count_is_bounded(monkeypatch):
    observed = []
    def resolve(url):
        observed.append(url)
        return None
    monkeypatch.setattr(tweet_enrichment, "resolve_tco_url", resolve)
    result = tweet_enrichment.resolve_tweet_links(" ".join(f"https://t.co/{i}" for i in range(20)))
    assert len(result) == len(observed) == 5
