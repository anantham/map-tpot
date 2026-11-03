"""Read-only adapter for private, historical Archive following observations.

These records are custody evidence from a local snapshot, not current follows,
public profiles, or admitted graph edges.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

from src.data.saved_evidence import saved_profile_locators
from src.data.following_capture import read_following_capture


_HANDLE = re.compile(r"[A-Za-z0-9_]{1,15}\Z")
_ACCOUNT_ID = re.compile(r"[0-9]+\Z")
_MAX_ACCOUNTS = 20_000
_BATCH_SIZE = 800
logger = logging.getLogger(__name__)


def _handle(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if value.startswith("@"):
        value = value[1:]
    return value.casefold() if _HANDLE.fullmatch(value) else None


def _readonly(path):
    resolved = Path(path).resolve(strict=True)
    uri = f"file:{quote(resolved.as_posix(), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _require_columns(db, table, required):
    exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if exists is None:
        raise RuntimeError(f"Required {table} table is missing")
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    if not required.issubset(columns):
        raise RuntimeError(f"Malformed {table} schema; required columns are missing")


def _max_text(left, right):
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def _load_tags(path, ego, account_ids):
    if not Path(path).exists():
        return "unavailable", {}
    tags = {account_id: [] for account_id in account_ids}
    try:
        db = _readonly(path)
    except (OSError, sqlite3.Error) as error:
        raise RuntimeError("Existing tag store cannot be read") from error
    with closing(db):
        _require_columns(db, "account_tags", {"ego", "account_id", "tag_display", "polarity"})
        for start in range(0, len(account_ids), _BATCH_SIZE):
            batch = account_ids[start:start + _BATCH_SIZE]
            if not batch:
                continue
            marks = ",".join("?" for _ in batch)
            rows = db.execute(
                f"SELECT account_id, tag_display, polarity FROM account_tags "
                f"WHERE ego=? AND account_id IN ({marks}) ORDER BY account_id, tag_display",
                (ego, *batch),
            )
            for row in rows:
                account_id, label, polarity = row
                if account_id not in tags:
                    continue
                if type(polarity) is not int or polarity not in (-1, 1):
                    raise RuntimeError("Malformed account_tags polarity; expected -1 or 1")
                if not isinstance(label, str) or not label.strip():
                    raise RuntimeError("Malformed account_tags display label")
                tags[account_id].append({"tag": label, "polarity": polarity})
    return "available", tags


def load_following_roster(cache_path, tag_path, *, ego, graph_path=None,
                          capture_path=None, source='latest'):
    """Read a curator's captured or historical roster without writing stores."""
    if source not in ('latest', 'historical'):
        raise ValueError('source must be latest or historical')
    normalized_ego = _handle(ego)
    if normalized_ego is None:
        raise ValueError("ego must be a valid X handle")
    try:
        db = _readonly(cache_path)
    except (OSError, sqlite3.Error) as error:
        raise RuntimeError("Following cache is unavailable or unreadable") from error
    with closing(db):
        _require_columns(db, "account", {"account_id", "username", "account_display_name"})
        _require_columns(db, "archive_following", {
            "account_id", "following_account_id", "uploaded_at", "imported_at"
        })
        ego_rows = db.execute(
            "SELECT account_id, username, account_display_name FROM account "
            "WHERE lower(trim(username)) IN (?, ?)",
            (normalized_ego, "@" + normalized_ego),
        ).fetchall()
        matches = [row for row in ego_rows if _handle(row["username"]) == normalized_ego]
        ego_ids = {row["account_id"] for row in matches}
        if len(ego_ids) > 1:
            raise RuntimeError("Following curator handle is ambiguous across account IDs")
        if not ego_ids:
            tag_status, _ = _load_tags(tag_path, normalized_ego, [])
            return {
                "status": "not_present", "ego": normalized_ego, "accountId": None,
                "rosterKind": "historical_local_archive_following",
                "currentRosterVerified": False, "total": 0, "tagStatus": tag_status,
                "accounts": [],
                "profileLocatorStatus": "not_requested",
                "counts": {"withHandle": 0, "withoutHandle": 0, "taggedAccounts": 0},
            }
        ego_id = next(iter(ego_ids))
        if not isinstance(ego_id, str) or not _ACCOUNT_ID.fullmatch(ego_id):
            raise RuntimeError("Resolved curator account ID is not numeric")
        observed = {}
        for row in db.execute(
            "SELECT following_account_id, uploaded_at, imported_at FROM archive_following "
            "WHERE account_id=?", (ego_id,)
        ):
            account_id = row["following_account_id"]
            if not isinstance(account_id, str) or not _ACCOUNT_ID.fullmatch(account_id):
                raise RuntimeError("Following target account ID is not numeric")
            prior = observed.setdefault(account_id, {"uploadedAt": None, "importedAt": None})
            prior["uploadedAt"] = _max_text(prior["uploadedAt"], row["uploaded_at"])
            prior["importedAt"] = _max_text(prior["importedAt"], row["imported_at"])
            if len(observed) > _MAX_ACCOUNTS:
                raise RuntimeError(f"Following roster exceeds the {_MAX_ACCOUNTS} account limit")
        capture = (read_following_capture(capture_path, ego=normalized_ego, account_id=ego_id)
                   if capture_path and source == 'latest' else None)
        if capture is not None:
            observed = capture['observed']
        account_ids = sorted(observed)
        account_rows = {}
        for start in range(0, len(account_ids), _BATCH_SIZE):
            batch = account_ids[start:start + _BATCH_SIZE]
            marks = ",".join("?" for _ in batch)
            for row in db.execute(
                f"SELECT account_id, username, account_display_name FROM account "
                f"WHERE account_id IN ({marks})", batch
            ):
                account_id = row["account_id"]
                value = (_handle(row["username"]), row["account_display_name"])
                if account_id in account_rows and account_rows[account_id] != value:
                    raise RuntimeError("Target account ID has conflicting local account records")
                account_rows[account_id] = value

    tag_status, tag_map = _load_tags(tag_path, normalized_ego, account_ids)
    profiles, profile_status = {}, "not_configured"
    if graph_path:
        try:
            profiles = saved_profile_locators(graph_path, account_ids)
            profile_status = "available"
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
            logger.warning('Saved following profile locators unavailable (%s)', type(error).__name__)
            profile_status = "unavailable"
    accounts = []
    for account_id in account_ids:
        username, display_name = account_rows.get(account_id, (None, None))
        locator_source = {"kind": "historical_archive_account"}
        profile = profiles.get(account_id)
        if profile and (saved_handle := _handle(profile["username"])):
            username = saved_handle
            display_name = profile.get("displayName") or display_name
            locator_source = {"kind": profile.get("sourceKind") or "saved_october_profile",
                "capturedAt": profile.get("fetchedAt"), "evidenceRef": profile["evidenceRef"]}
        times = observed[account_id]
        accounts.append({
            "accountId": account_id, "username": username,
            "displayName": display_name, "tags": tag_map.get(account_id, []),
            "uploadedAt": times["uploadedAt"], "importedAt": times["importedAt"],
            "sourcePointer": times.get("sourcePointer"),
            "locatorSource": locator_source,
        })
    accounts.sort(key=lambda row: (row["username"] is None,
                                  row["username"] or "", row["accountId"]))
    with_handle = sum(row["username"] is not None for row in accounts)
    return {
        "status": "available", "ego": normalized_ego, "accountId": ego_id,
        "rosterKind": "saved_provider_following_capture" if capture else "historical_local_archive_following",
        "currentRosterVerified": False, "total": len(accounts),
        "captureCountReconciled": capture is not None,
        "capturedFrom": capture['capturedFrom'] if capture else None,
        "capturedTo": capture['capturedTo'] if capture else None,
        "tagStatus": tag_status, "accounts": accounts,
        "profileLocatorStatus": profile_status,
        "counts": {"withHandle": with_handle, "withoutHandle": len(accounts) - with_handle,
                   "taggedAccounts": sum(bool(row["tags"]) for row in accounts)},
    }
