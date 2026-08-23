"""SQLite schema for account-tag current state and change history."""
from __future__ import annotations

import sqlite3


def initialize_account_tag_schema(conn: sqlite3.Connection) -> None:
    """Create the mutable projection and its append-only application log."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS account_tags (
            ego TEXT NOT NULL,
            account_id TEXT NOT NULL,
            tag_key TEXT NOT NULL,
            tag_display TEXT NOT NULL,
            polarity INTEGER NOT NULL,
            confidence REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (ego, account_id, tag_key)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_account_tags_ego_account "
        "ON account_tags(ego, account_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_account_tags_ego_tag "
        "ON account_tags(ego, tag_key)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS account_tag_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ego TEXT NOT NULL,
            account_id TEXT NOT NULL,
            tag_key TEXT NOT NULL,
            tag_display TEXT NOT NULL,
            action TEXT NOT NULL CHECK (action IN ('set', 'remove')),
            polarity INTEGER,
            confidence REAL CHECK (
                confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)
            ),
            source TEXT NOT NULL,
            evidence_binding_status TEXT NOT NULL
                CHECK (evidence_binding_status IN ('unbound', 'snapshot_bound')),
            recorded_at TEXT NOT NULL,
            CHECK (
                (action = 'set' AND polarity IN (-1, 1))
                OR (action = 'remove' AND polarity IS NULL)
            )
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_account_tag_events_subject "
        "ON account_tag_events(ego, account_id, event_id)"
    )
    conn.execute(
        """
        INSERT INTO account_tag_events (
            ego, account_id, tag_key, tag_display, action, polarity,
            confidence, source, evidence_binding_status, recorded_at
        )
        SELECT current.ego, current.account_id, current.tag_key,
               current.tag_display, 'set', current.polarity,
               current.confidence, 'legacy_projection_backfill', 'unbound',
               current.updated_at
        FROM account_tags AS current
        WHERE NOT EXISTS (
            SELECT 1 FROM account_tag_events AS event
            WHERE event.ego = current.ego
              AND event.account_id = current.account_id
              AND event.tag_key = current.tag_key
        )
        """
    )
