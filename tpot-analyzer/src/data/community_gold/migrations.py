"""Transactional, idempotent migrations for versioned Community Gold."""
from __future__ import annotations

import sqlite3
from typing import Dict

from .integrity_trigger_registry import drop_integrity_triggers_sql
from .integrity_triggers import INTEGRITY_TRIGGERS
from .migration_schema import (
    COMMUNITY_GOLD_SCHEMA_VERSION,
    VERSIONED_INDEXES,
    VERSIONED_TABLES,
)
from .migration_validation import (
    preflight_existing_schema,
    refuse_future_schema,
    validate_migrated_schema,
)

_LABEL_COLUMNS: Dict[str, str] = {
    "user_id": "TEXT",
    "ontology_id": "TEXT",
    "ontology_version": "INTEGER",
    "task_id": "TEXT",
    "study_frame_id": "TEXT",
    "evidence_snapshot_id": "TEXT",
    "evidence_snapshot_hash": "TEXT",
    "context_hash": "TEXT",
    "observed_at": "TEXT",
    "identity_status": (
        "TEXT NOT NULL DEFAULT 'legacy_unbound' "
        "CHECK (identity_status IN ('legacy_unbound','scoped'))"
    ),
}

def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _alter_missing_columns(
    conn: sqlite3.Connection,
    *,
    table: str,
    definitions: Dict[str, str],
) -> list[str]:
    observed = _columns(conn, table)
    return [
        f"ALTER TABLE {table} ADD COLUMN {name} {definition};"
        for name, definition in definitions.items()
        if name not in observed
    ]


def _access_rebuild_statements(conn: sqlite3.Connection) -> list[str]:
    table = "account_community_terminal_test_access"
    observed = _columns(conn, table)
    required = {
        "frame_id",
        "role_registry_id",
        "accessed_by",
        "access_receipt_json",
        "access_receipt_hash",
        "release_manifest_json",
        "release_manifest_hash",
        "access_envelope_hash",
        "released_label_head_count",
        "accessed_at",
    }
    if not observed or required <= observed:
        return []
    row_count = int(
        conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    )
    if row_count:
        raise RuntimeError(
            "cannot automatically upgrade a non-empty pre-v3 terminal "
            "access table because its release coverage is unverifiable; "
            f"rows={row_count}"
        )
    return [f"DROP TABLE {table};"]


def migrate_community_gold(conn: sqlite3.Connection) -> None:
    """Upgrade additively and commit only after validating the full shape."""

    refuse_future_schema(
        conn,
        supported_version=COMMUNITY_GOLD_SCHEMA_VERSION,
    )
    preflight_existing_schema(conn)
    label_alters = _alter_missing_columns(
        conn,
        table="account_community_gold_label_set",
        definitions=_LABEL_COLUMNS,
    )
    access_rebuild = _access_rebuild_statements(conn)
    script = "\n".join(
        [
            "BEGIN IMMEDIATE;",
            *label_alters,
            *access_rebuild,
            VERSIONED_TABLES,
            VERSIONED_INDEXES,
            drop_integrity_triggers_sql(),
            INTEGRITY_TRIGGERS,
        ]
    )
    try:
        conn.executescript(script)
        validate_migrated_schema(conn)
        conn.execute(
            """
            INSERT INTO account_community_gold_schema_version
            (version, applied_at)
            VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            ON CONFLICT(version) DO NOTHING
            """,
            (COMMUNITY_GOLD_SCHEMA_VERSION,),
        )
        recorded = conn.execute(
            """
            SELECT 1
            FROM account_community_gold_schema_version
            WHERE version = ?
            """,
            (COMMUNITY_GOLD_SCHEMA_VERSION,),
        ).fetchone()
        if recorded is None:
            raise RuntimeError(
                "Community Gold migration did not record supported schema "
                f"version {COMMUNITY_GOLD_SCHEMA_VERSION}"
            )
        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
