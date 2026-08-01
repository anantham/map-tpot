"""Read one logical historical-holdout snapshot without mutating SQLite."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import sqlite3
from typing import Any

from .acquisition_manifest import canonical_json_hash


class HoldoutSnapshotError(ValueError):
    """Raised when the exclusion snapshot cannot be established safely."""


@dataclass(frozen=True)
class HoldoutSnapshot:
    logical_sha256: str
    normalized_handle_count: int
    account_id_count: int
    panel_handle_overlap_count: int
    handles: frozenset[str] = field(repr=False)
    account_ids: frozenset[str] = field(repr=False)


_DECIMAL_ID = re.compile(r"[0-9]+")


def _handle(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HoldoutSnapshotError("holdout handles must be text or null")
    normalized = value.strip().lstrip("@").lower()
    return normalized or None


def _account_id(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        raise HoldoutSnapshotError("holdout account IDs must be decimal text")
    normalized = value.strip()
    if not normalized:
        return None
    if _DECIMAL_ID.fullmatch(normalized) is None:
        raise HoldoutSnapshotError("holdout account IDs must be decimal text")
    return normalized


def _read_rows(db_path: Path) -> list[tuple[Any, Any]]:
    if not db_path.is_file():
        raise HoldoutSnapshotError("archive DB does not exist or is not a file")
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            connection.execute("PRAGMA query_only = ON")
            connection.execute("BEGIN")
            table = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'tpot_directory_holdout'"
            ).fetchone()
            if table is None:
                raise HoldoutSnapshotError(
                    "archive DB lacks required holdout table"
                )
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(tpot_directory_holdout)"
                )
            }
            if not {"handle", "account_id"}.issubset(columns):
                raise HoldoutSnapshotError(
                    "required holdout table requires handle and account_id columns"
                )
            return connection.execute(
                "SELECT handle, account_id FROM tpot_directory_holdout"
            ).fetchall()
    except HoldoutSnapshotError:
        raise
    except sqlite3.DatabaseError as error:
        raise HoldoutSnapshotError(
            f"archive DB could not be read safely: {error}"
        ) from error


def read_holdout_snapshot(
    db_path: Path,
    panel_handles: frozenset[str],
) -> HoldoutSnapshot:
    """Return a consistent logical exclusion snapshot from a read-only DB."""
    if (
        not isinstance(panel_handles, frozenset)
        or not panel_handles
        or any(not isinstance(value, str) or not value for value in panel_handles)
    ):
        raise HoldoutSnapshotError(
            "panel handles must be a nonempty normalized frozenset"
        )
    handles: set[str] = set()
    account_ids: set[str] = set()
    for raw_handle, raw_account_id in _read_rows(db_path):
        handle = _handle(raw_handle)
        account_id = _account_id(raw_account_id)
        if handle is not None:
            handles.add(handle)
        if account_id is not None:
            account_ids.add(account_id)
    if not handles and not account_ids:
        raise HoldoutSnapshotError("holdout snapshot has no usable identities")
    logical = {
        "schema_version": 1,
        "normalized_handles": sorted(handles),
        "account_ids": sorted(account_ids),
    }
    return HoldoutSnapshot(
        logical_sha256=canonical_json_hash(logical),
        normalized_handle_count=len(handles),
        account_id_count=len(account_ids),
        panel_handle_overlap_count=len(handles & panel_handles),
        handles=frozenset(handles),
        account_ids=frozenset(account_ids),
    )
