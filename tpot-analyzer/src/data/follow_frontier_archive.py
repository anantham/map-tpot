"""Read-only archive queries used by the target follow frontier."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

_QUERY_CHUNK = 800


class TargetFrontierError(RuntimeError):
    """Raised when the local evidence view cannot support the frontier."""


def _chunks(values: Iterable[str]) -> Iterable[tuple[str, ...]]:
    items = tuple(sorted(set(values)))
    for start in range(0, len(items), _QUERY_CHUNK):
        yield items[start : start + _QUERY_CHUNK]


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def open_archive_readonly(path: Path) -> sqlite3.Connection:
    """Open one query-only transaction so all frontier reads share a view."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise TargetFrontierError(f"archive database not found: {resolved}")
    try:
        conn = sqlite3.connect(
            f"{resolved.as_uri()}?mode=ro",
            uri=True,
            timeout=30,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return conn
    except sqlite3.Error as exc:
        if "conn" in locals():
            conn.close()
        raise TargetFrontierError(f"archive database is not readable: {exc}") from exc


def load_follow_edges(
    conn: sqlite3.Connection,
    source_ids: Iterable[str],
) -> list[tuple[str, str]]:
    required = {"account_id", "following_account_id"}
    if not required <= _columns(conn, "account_following"):
        raise TargetFrontierError("archive lacks the account_following edge view")
    edges: list[tuple[str, str]] = []
    for chunk in _chunks(source_ids):
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            "SELECT account_id, following_account_id FROM account_following "
            f"WHERE account_id IN ({placeholders})",
            chunk,
        )
        edges.extend((str(row[0]), str(row[1])) for row in rows)
    return edges


def load_claimed_following_counts(
    conn: sqlite3.Connection,
    account_ids: Iterable[str],
) -> dict[str, int | None]:
    """Load optional counts without assuming either supported table exists."""
    claims: dict[str, int | None] = {}
    sources = (
        ("user_profile_cache", "following"),
        ("profiles", "following_count"),
    )
    for table, count_column in sources:
        if not {"account_id", count_column} <= _columns(conn, table):
            continue
        for chunk in _chunks(account_ids):
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"SELECT account_id, {count_column} FROM {table} "
                f"WHERE account_id IN ({placeholders})",
                chunk,
            )
            for row in rows:
                if (
                    str(row[0]) not in claims
                    and type(row[1]) is int
                    and row[1] >= 0
                ):
                    claims[str(row[0])] = int(row[1])
    return claims


def load_usernames(
    conn: sqlite3.Connection,
    account_ids: Iterable[str],
) -> dict[str, str]:
    usernames: dict[str, str] = {}
    for table in ("profiles", "resolved_accounts", "user_profile_cache"):
        if not {"account_id", "username"} <= _columns(conn, table):
            continue
        for chunk in _chunks(account_ids):
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"SELECT account_id, username FROM {table} "
                f"WHERE account_id IN ({placeholders}) AND username IS NOT NULL",
                chunk,
            )
            for row in rows:
                username = str(row[1]).strip()
                if username:
                    usernames.setdefault(str(row[0]), username)
    return usernames
