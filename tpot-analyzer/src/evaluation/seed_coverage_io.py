"""Input adapters for the read-only named-seed coverage report."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_input(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = Path(path).expanduser().resolve()
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON input {resolved}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON input must be an object: {resolved}")
    return payload, {
        "path": str(resolved),
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def database_receipt(path: Path, connection: sqlite3.Connection) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    stat = resolved.stat()
    wal_path = Path(f"{resolved}-wal")
    wal = None
    if wal_path.is_file():
        wal_stat = wal_path.stat()
        wal = {
            "path": str(wal_path),
            "size_bytes": wal_stat.st_size,
            "mtime_ns": wal_stat.st_mtime_ns,
        }
    return {
        "path": str(resolved),
        "inode": stat.st_ino,
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "wal": wal,
        "journal_mode": connection.execute("PRAGMA journal_mode").fetchone()[0],
        "open_mode": (
            "mode=ro; query_only=ON; read snapshot pinned before receipt"
        ),
        "read_snapshot_established": True,
        "snapshot_semantics": "mutable_query_time_view",
    }


def _columns(connection: sqlite3.Connection, table: str) -> set[str] | None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        return None
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def relation_view(
    connection: sqlite3.Connection,
    *,
    table: str,
    source_column: str,
    target_column: str,
    source_ids: Iterable[str],
    direction: str | None = None,
    timestamp_status: str,
) -> tuple[dict[str, Any], set[str]]:
    required = {source_column, target_column}
    columns = _columns(connection, table)
    if columns is None:
        return {
            "status": "unavailable",
            "distinct_targets": None,
            "reason": f"missing table {table}",
            "timestamp_status": timestamp_status,
        }, set()
    missing = required - columns
    if missing:
        return {
            "status": "unavailable",
            "distinct_targets": None,
            "reason": f"missing columns in {table}: {sorted(missing)}",
            "timestamp_status": timestamp_status,
        }, set()
    ids = sorted(set(source_ids))
    placeholders = ",".join("?" for _ in ids)
    sql = (
        f"SELECT {target_column}"
        + (", fetched_at, source_channel" if {"fetched_at", "source_channel"} <= columns else "")
        + f" FROM {table} WHERE {source_column} IN ({placeholders})"
    )
    params: list[Any] = list(ids)
    if direction is not None:
        if "direction" not in columns:
            return {
                "status": "unavailable",
                "distinct_targets": None,
                "reason": f"missing columns in {table}: ['direction']",
                "timestamp_status": timestamp_status,
            }, set()
        sql += " AND direction=?"
        params.append(direction)
    rows = connection.execute(sql, params).fetchall()
    targets = {str(row[0]) for row in rows if row[0] is not None}
    result: dict[str, Any] = {
        "status": "observed",
        "distinct_targets": len(targets),
        "timestamp_status": timestamp_status,
    }
    if rows and len(rows[0]) == 3:
        times = sorted(str(row[1]) for row in rows if row[1] is not None)
        result["captured_at_min"] = times[0] if times else None
        result["captured_at_max"] = times[-1] if times else None
        result["source_channels"] = sorted(
            {str(row[2]) for row in rows if row[2] is not None}
        )
    return result, targets


def identity_conflicts(
    archive: sqlite3.Connection,
    cache: sqlite3.Connection,
    account_id: str,
    handle: str,
) -> dict[str, Any]:
    normalized = handle.lower().lstrip("@")
    candidates: set[str] = set()
    for connection, tables in (
        (archive, ("profiles", "resolved_accounts", "user_profile_cache")),
        (cache, ("account", "shadow_account")),
    ):
        for table in tables:
            columns = _columns(connection, table)
            if not columns or not {"account_id", "username"} <= columns:
                continue
            for row in connection.execute(
                f"SELECT account_id FROM {table} WHERE lower(username)=?",
                (normalized,),
            ):
                if str(row[0]).isdigit():
                    candidates.add(str(row[0]))
    conflicts = sorted(candidates - {account_id})
    return {
        "status": "conflicting" if conflicts else "pinned",
        "pinned_account_id": account_id,
        "conflicting_numeric_ids": conflicts,
        "resolution_rule": "panel account_id remains authoritative for this report",
    }


def lookup_usernames(
    archive: sqlite3.Connection,
    cache: sqlite3.Connection,
    account_ids: Iterable[str],
) -> dict[str, list[str]]:
    ids = sorted(set(account_ids))
    found: dict[str, set[str]] = {account_id: set() for account_id in ids}
    for account_id in ids:
        if account_id.startswith("shadow:"):
            found[account_id].add(account_id.split(":", 1)[1])
    for connection, tables in (
        (archive, ("profiles", "resolved_accounts", "user_profile_cache")),
        (cache, ("account", "shadow_account")),
    ):
        for table in tables:
            columns = _columns(connection, table)
            if not columns or not {"account_id", "username"} <= columns:
                continue
            for account_id in ids:
                for row in connection.execute(
                    f"SELECT username FROM {table} WHERE account_id=? "
                    "AND username IS NOT NULL",
                    (account_id,),
                ):
                    found[account_id].add(str(row[0]))
    return {
        account_id: sorted(usernames)
        for account_id, usernames in found.items()
        if usernames
    }
