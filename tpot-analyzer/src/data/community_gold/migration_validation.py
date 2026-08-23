"""Fail-closed preflight and postflight checks for Community Gold migrations."""
from __future__ import annotations

import sqlite3
from typing import Mapping, Set

from .integrity_trigger_registry import TRIGGER_NAMES
from .migration_index_contracts import validate_owned_indexes
from .migration_table_contracts import validate_table_constraints

_REQUIRED_COLUMNS: Mapping[str, Set[str]] = {
    "account_community_gold_schema_version": {"version", "applied_at"},
    "personal_ontology_version": {
        "user_id", "ontology_id", "ontology_version", "definition_json",
        "definition_hash", "supersedes_version", "created_at",
    },
    "personal_ontology_group": {
        "user_id", "ontology_id", "ontology_version", "community_id",
        "boundary_definition",
    },
    "personal_ontology_task": {
        "user_id", "ontology_id", "ontology_version", "task_id",
        "target_type", "definition_json", "definition_hash", "created_at",
    },
    "account_community_role_registry": {
        "role_registry_id", "registry_json", "registry_digest", "created_at",
    },
    "account_community_global_role": {
        "role_registry_id", "account_id", "assigned_role", "role_json",
        "role_hash",
    },
    "account_community_evaluation_frame": {
        "frame_id", "user_id", "ontology_id", "ontology_version", "task_id",
        "manifest_json", "manifest_digest", "evidence_snapshot_id",
        "evidence_snapshot_hash", "graph_manifest_hash", "evidence_cutoff",
        "role_registry_id", "created_at",
    },
    "account_community_evaluation_role": {
        "frame_id", "account_id", "stratum", "assigned_role",
        "assigned_probability", "terminal_test_probability",
        "role_probabilities_json",
    },
    "account_community_gold_head": {
        "frame_id", "account_id", "community_id", "reviewer",
        "label_set_id", "updated_at",
    },
    "account_community_terminal_test_access": {
        "frame_id", "role_registry_id", "accessed_by",
        "access_receipt_json", "access_receipt_hash", "release_manifest_json",
        "release_manifest_hash", "access_envelope_hash",
        "released_label_head_count", "accessed_at",
    },
    "account_community_prediction": {
        "prediction_id", "frame_id", "account_id", "community_id",
        "model_run_id", "score", "score_semantics",
        "calibration_record_hash", "evidence_snapshot_id",
        "evidence_snapshot_hash", "context_hash", "observed_at",
        "predicted_at", "payload_hash",
    },
}

_PRE_V3_ACCESS_COLUMNS = {
    "frame_id", "accessed_by", "access_receipt_json",
    "access_receipt_hash", "accessed_at",
}

_PRIMARY_KEYS: Mapping[str, tuple[str, ...]] = {
    "account_community_gold_schema_version": ("version",),
    "personal_ontology_version": (
        "user_id", "ontology_id", "ontology_version",
    ),
    "personal_ontology_group": (
        "user_id", "ontology_id", "ontology_version", "community_id",
    ),
    "personal_ontology_task": (
        "user_id", "ontology_id", "ontology_version", "task_id",
    ),
    "account_community_role_registry": ("role_registry_id",),
    "account_community_global_role": ("role_registry_id", "account_id"),
    "account_community_evaluation_frame": ("frame_id",),
    "account_community_evaluation_role": ("frame_id", "account_id"),
    "account_community_gold_head": (
        "frame_id", "account_id", "community_id", "reviewer",
    ),
    "account_community_terminal_test_access": ("frame_id",),
    "account_community_prediction": ("prediction_id",),
}

def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        """
        SELECT 1 FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table,),
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _primary_key(conn: sqlite3.Connection, table: str) -> tuple[str, ...]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return tuple(
        str(row[1])
        for row in sorted(rows, key=lambda item: int(item[5]))
        if int(row[5]) > 0
    )


def _require_shape(
    conn: sqlite3.Connection,
    *,
    table: str,
    required: set[str],
    constraints: bool = True,
) -> None:
    observed = _columns(conn, table)
    missing = sorted(required - observed)
    if missing:
        raise RuntimeError(
            f"Community Gold table '{table}' is incompatible; "
            f"missing required columns: {missing}"
        )
    expected_pk = _PRIMARY_KEYS.get(table)
    if expected_pk is not None:
        observed_pk = _primary_key(conn, table)
        if observed_pk != expected_pk:
            raise RuntimeError(
                f"Community Gold table '{table}' has incompatible primary "
                f"key: expected={expected_pk}, observed={observed_pk}"
            )
    if constraints:
        validate_table_constraints(conn, table=table)


def refuse_future_schema(
    conn: sqlite3.Connection,
    *,
    supported_version: int,
) -> None:
    table = "account_community_gold_schema_version"
    if not _table_exists(conn, table):
        return
    _require_shape(
        conn,
        table=table,
        required=_REQUIRED_COLUMNS[table],
    )
    current = conn.execute(
        "SELECT MAX(version) FROM account_community_gold_schema_version"
    ).fetchone()[0]
    if current is not None and int(current) > supported_version:
        raise RuntimeError(
            "Community Gold database schema is newer than this code: "
            f"database={current}, supported={supported_version}"
        )


def preflight_existing_schema(conn: sqlite3.Connection) -> None:
    """Reject unknown partial tables before making any migration mutation."""

    for table, required in _REQUIRED_COLUMNS.items():
        if not _table_exists(conn, table):
            continue
        preflight_required = (
            _PRE_V3_ACCESS_COLUMNS
            if table == "account_community_terminal_test_access"
            else required
        )
        validate_constraints = (
            table != "account_community_terminal_test_access"
            or set(required) <= _columns(conn, table)
        )
        _require_shape(
            conn,
            table=table,
            required=set(preflight_required),
            constraints=validate_constraints,
        )
    validate_owned_indexes(conn, allow_missing=True)


def validate_migrated_schema(conn: sqlite3.Connection) -> None:
    """Validate tables, keys, indexes, triggers, and generation bindings."""

    missing_tables = sorted(
        table
        for table in _REQUIRED_COLUMNS
        if not _table_exists(conn, table)
    )
    if missing_tables:
        raise RuntimeError(
            "Community Gold migration is missing required tables: "
            f"{missing_tables}"
        )
    for table, required in _REQUIRED_COLUMNS.items():
        _require_shape(conn, table=table, required=set(required))

    validate_owned_indexes(conn, allow_missing=False)

    triggers = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        ).fetchall()
    }
    missing_triggers = sorted(set(TRIGGER_NAMES) - triggers)
    if missing_triggers:
        raise RuntimeError(
            "Community Gold migration is missing required triggers: "
            f"{missing_triggers}"
        )

    unbound_access = conn.execute(
        """
        SELECT frame_id
        FROM account_community_terminal_test_access
        WHERE role_registry_id IS NULL
        LIMIT 1
        """
    ).fetchone()
    if unbound_access is not None:
        raise RuntimeError(
            "Community Gold terminal access cannot be bound to a role "
            f"registry: frame_id={unbound_access[0]}"
        )

    foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        sample = [tuple(row) for row in foreign_key_errors[:5]]
        raise RuntimeError(
            "Community Gold migration found foreign-key violations; "
            f"sample={sample}"
        )
