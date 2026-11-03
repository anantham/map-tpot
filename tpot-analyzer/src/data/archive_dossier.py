"""Read-only archive profile/post reader shared by the private Review API."""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from src.config import DEFAULT_ARCHIVE_DB


class DossierNotFoundError(ValueError):
    """Raised when a requested raw account profile does not exist."""


def _open_archive_readonly() -> sqlite3.Connection:
    db_path = Path(
        os.getenv("ARCHIVE_DB_PATH", str(DEFAULT_ARCHIVE_DB))
    )
    if not db_path.is_file():
        raise FileNotFoundError(f"archive database not found: {db_path}")
    encoded_path = quote(str(db_path.resolve()), safe="/")
    conn = sqlite3.connect(
        f"file:{encoded_path}?mode=ro",
        uri=True,
        timeout=30,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _resolve_profile(
    conn: sqlite3.Connection,
    handle: str,
) -> sqlite3.Row:
    normalized = str(handle or "").strip()
    if not normalized:
        raise ValueError("handle is required")
    rows = conn.execute(
        """
        SELECT account_id, username, display_name, bio, location, website,
               fetched_at
        FROM profiles
        WHERE username = ? COLLATE NOCASE
        ORDER BY account_id
        LIMIT 2
        """,
        (normalized,),
    ).fetchall()
    if not rows:
        raise DossierNotFoundError(
            f"account handle '{normalized}' was not found in raw profiles"
        )
    if len(rows) > 1:
        raise ValueError(
            f"account handle '{normalized}' resolves to multiple account IDs"
        )
    return rows[0]


def _profile_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "accountId": str(row["account_id"]),
        "username": str(row["username"]),
        "displayName": row["display_name"],
        "bio": row["bio"],
        "location": row["location"],
        "website": row["website"],
        "fetchedAt": row["fetched_at"],
    }


def _twitter_julian(value: str | None) -> float | None:
    """Use the same chronological scale as SQLite for acquired Twitter dates."""
    try:
        parsed = datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")
        return parsed.timestamp() / 86400 + 2440587.5
    except (TypeError, ValueError, OverflowError):
        return None


def _load_tweets(
    conn: sqlite3.Connection,
    *,
    account_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    source_sql = """
        SELECT tweet_id, full_text, created_at, favorite_count, retweet_count,
               fetched_at, 'archive' AS source, NULL AS fetch_source,
               julianday(created_at) AS sort_date
        FROM tweets
        WHERE account_id = ?
    """
    params: list[Any] = [account_id]
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='enriched_tweets'"
    ).fetchone():
        conn.create_function("dossier_twitter_date", 1, _twitter_julian)
        # Preserve the existing archive observation when both tables hold a post.
        source_sql += """
            UNION ALL
            SELECT e.tweet_id, e.text, e.created_at, e.like_count, e.retweet_count,
                   e.fetched_at, 'enriched', e.fetch_source,
                   COALESCE(julianday(e.created_at), dossier_twitter_date(e.created_at))
            FROM enriched_tweets e
            WHERE e.account_id = ? AND NOT EXISTS (
                SELECT 1 FROM tweets t
                WHERE t.tweet_id = e.tweet_id AND t.account_id = e.account_id
            )
        """
        params.append(account_id)
    rows = conn.execute(
        f"SELECT * FROM ({source_sql}) "
        "ORDER BY sort_date IS NULL, sort_date DESC, tweet_id DESC LIMIT ?",
        [*params, limit],
    ).fetchall()
    return [
        {
            "tweetId": str(row["tweet_id"]),
            "text": row["full_text"] if row["full_text"] is not None else "",
            "createdAt": row["created_at"],
            "favoriteCount": row["favorite_count"],
            "retweetCount": row["retweet_count"],
            "fetchedAt": row["fetched_at"],
            "source": row["source"],
            "fetchSource": row["fetch_source"],
        }
        for row in rows
    ]


def load_archive_dossier(handle: str, limit: int, fallback_account=None):
    with closing(_open_archive_readonly()) as conn:
        try:
            account = _profile_payload(_resolve_profile(conn, handle))
        except DossierNotFoundError:
            if fallback_account is None:
                raise
            account = fallback_account
        return account, _load_tweets(conn, account_id=account["accountId"], limit=limit)
