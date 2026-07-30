"""Curator-only raw account dossiers for Research Notes preview."""
from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from flask import Blueprint, jsonify, request

from src.api.curator_auth import curator_only
from src.api.responses import error_response
from src.config import DEFAULT_ARCHIVE_DB

logger = logging.getLogger(__name__)

research_notes_bp = Blueprint(
    "research_notes",
    __name__,
    url_prefix="/api/research-notes",
)

_DEFAULT_TWEET_LIMIT = 20
_MAX_TWEET_LIMIT = 100


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


def _parse_limit(raw: Optional[str]) -> int:
    try:
        parsed = int(raw or _DEFAULT_TWEET_LIMIT)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    if parsed < 1 or parsed > _MAX_TWEET_LIMIT:
        raise ValueError(
            f"limit must be between 1 and {_MAX_TWEET_LIMIT}"
        )
    return parsed


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


def _load_tweets(
    conn: sqlite3.Connection,
    *,
    account_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT tweet_id, full_text, created_at, favorite_count, retweet_count,
               fetched_at
        FROM tweets
        WHERE account_id = ?
        ORDER BY
          CASE WHEN julianday(created_at) IS NULL THEN 1 ELSE 0 END,
          julianday(created_at) DESC,
          tweet_id DESC
        LIMIT ?
        """,
        (account_id, limit),
    ).fetchall()
    return [
        {
            "tweetId": str(row["tweet_id"]),
            "text": row["full_text"] if row["full_text"] is not None else "",
            "createdAt": row["created_at"],
            "favoriteCount": row["favorite_count"],
            "retweetCount": row["retweet_count"],
            "fetchedAt": row["fetched_at"],
        }
        for row in rows
    ]


@research_notes_bp.get("/dossiers/<handle>")
@curator_only
def get_dossier(handle: str):
    """Return a mutable local-archive preview with no model recommendations."""

    try:
        if "frameId" in request.args:
            raise ValueError(
                "frame-bound dossiers are not implemented; "
                "use the unbound preview"
            )
        limit = _parse_limit(request.args.get("limit"))
        with closing(_open_archive_readonly()) as conn:
            profile = _resolve_profile(conn, handle)
            account = _profile_payload(profile)
            tweets = _load_tweets(
                conn,
                account_id=account["accountId"],
                limit=limit,
            )
        return jsonify(
            {
                "bindingStatus": "unbound",
                "provenance": {
                    "source": "mutable_local_archive",
                    "snapshotBound": False,
                },
                "account": account,
                "tweets": tweets,
            }
        )
    except DossierNotFoundError as exc:
        return error_response(str(exc), status=404)
    except ValueError as exc:
        return error_response(str(exc))
    except (FileNotFoundError, sqlite3.DatabaseError, RuntimeError) as exc:
        logger.error("Research Notes dossier unavailable: %s", exc)
        return error_response(
            "Research Notes dossier is unavailable",
            status=500,
        )
    except Exception as exc:  # pragma: no cover - defensive API boundary
        logger.exception("Unexpected Research Notes dossier failure: %s", exc)
        return error_response("internal_error", status=500)
