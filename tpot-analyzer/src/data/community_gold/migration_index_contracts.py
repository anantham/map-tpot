"""Structural validation for owned Community Gold SQLite indexes."""
from __future__ import annotations

import re
import sqlite3
from typing import Any, Mapping

INDEX_CONTRACTS: Mapping[
    str,
    tuple[str, bool, tuple[str, ...], bool, str | None],
] = {
    "idx_account_community_gold_active_legacy": (
        "account_community_gold_label_set",
        True,
        ("account_id", "community_id", "reviewer"),
        True,
        "where is_active = 1 and identity_status = 'legacy_unbound'",
    ),
    "idx_account_community_gold_scoped_history": (
        "account_community_gold_label_set",
        False,
        ("study_frame_id", "account_id", "community_id", "reviewer", "id"),
        True,
        "where identity_status = 'scoped'",
    ),
    "idx_global_role_one_registry_per_account": (
        "account_community_global_role",
        True,
        ("account_id",),
        False,
        None,
    ),
    "idx_terminal_access_one_per_registry": (
        "account_community_terminal_test_access",
        True,
        ("role_registry_id",),
        False,
        None,
    ),
    "idx_prediction_natural_generation_key": (
        "account_community_prediction",
        True,
        ("frame_id", "account_id", "community_id", "model_run_id"),
        False,
        None,
    ),
}


def _normalized_sql(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _partial_predicate(normalized_sql: str) -> str | None:
    marker = " where "
    if marker not in normalized_sql:
        return None
    return normalized_sql.split(marker, 1)[1].rstrip(";").strip()


def validate_owned_indexes(
    conn: sqlite3.Connection,
    *,
    allow_missing: bool,
) -> None:
    """Validate every present canonical index by structure, not just name."""

    for name, contract in INDEX_CONTRACTS.items():
        table, unique, columns, partial, predicate = contract
        row = conn.execute(
            """
            SELECT tbl_name, sql
            FROM sqlite_master
            WHERE type = 'index' AND name = ?
            """,
            (name,),
        ).fetchone()
        if row is None:
            if allow_missing:
                continue
            raise RuntimeError(
                f"Community Gold migration is missing required index: {name}"
            )
        index_rows = {
            str(item[1]): item
            for item in conn.execute(f"PRAGMA index_list({table})").fetchall()
        }
        metadata = index_rows.get(name)
        observed_columns = tuple(
            str(item[2])
            for item in conn.execute(f"PRAGMA index_info({name})").fetchall()
        )
        normalized = _normalized_sql(row[1])
        expected_predicate = (
            predicate.removeprefix("where ").strip()
            if predicate is not None
            else None
        )
        mismatch = (
            str(row[0]) != table
            or metadata is None
            or bool(int(metadata[2])) is not unique
            or bool(int(metadata[4])) is not partial
            or observed_columns != columns
            or _partial_predicate(normalized) != expected_predicate
        )
        if mismatch:
            raise RuntimeError(
                f"Community Gold index '{name}' is incompatible: "
                f"expected_table={table}, unique={unique}, "
                f"columns={columns}, partial={partial}; "
                f"observed_table={row[0]}, columns={observed_columns}"
            )
