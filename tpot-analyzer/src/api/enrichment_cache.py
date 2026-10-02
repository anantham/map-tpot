"""Cache schema shared by bounded fetches and local tweet enrichment."""
import sqlite3

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS tweet_enrichment_cache (
    tweet_id TEXT PRIMARY KEY, media_json TEXT, quote_json TEXT,
    full_text TEXT, links_json TEXT, fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS link_content_cache (
    url_hash TEXT PRIMARY KEY, url TEXT NOT NULL, resolved_url TEXT,
    title TEXT, description TEXT, body_text TEXT, fetched_at TEXT NOT NULL
);
"""


def ensure_cache_table(conn: sqlite3.Connection) -> None:
    conn.executescript(CACHE_SCHEMA)
