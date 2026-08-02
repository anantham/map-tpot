"""Append-only event records for the mutable account-tag projection."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class AccountTagEvent:
    event_id: int
    ego: str
    account_id: str
    tag: str
    action: str  # set | remove
    polarity: Optional[int]
    confidence: Optional[float]
    source: str
    evidence_binding_status: str
    recorded_at: str


def append_event(
    conn: sqlite3.Connection,
    *,
    ego: str,
    account_id: str,
    tag_key: str,
    tag_display: str,
    action: str,
    polarity: Optional[int],
    confidence: Optional[float],
    source: str,
    evidence_binding_status: str,
    recorded_at: str,
) -> AccountTagEvent:
    cursor = conn.execute(
        """
        INSERT INTO account_tag_events (
            ego, account_id, tag_key, tag_display, action,
            polarity, confidence, source, evidence_binding_status, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ego,
            account_id,
            tag_key,
            tag_display,
            action,
            polarity,
            confidence,
            source,
            evidence_binding_status,
            recorded_at,
        ),
    )
    return AccountTagEvent(
        event_id=int(cursor.lastrowid),
        ego=ego,
        account_id=account_id,
        tag=tag_display,
        action=action,
        polarity=polarity,
        confidence=confidence,
        source=source,
        evidence_binding_status=evidence_binding_status,
        recorded_at=recorded_at,
    )


def list_events(
    conn: sqlite3.Connection,
    *,
    ego: str,
    account_id: str,
    limit: int,
) -> List[AccountTagEvent]:
    rows = conn.execute(
        """
        SELECT event_id, ego, account_id, tag_display, action,
               polarity, confidence, source, evidence_binding_status, recorded_at
        FROM (
            SELECT event_id, ego, account_id, tag_display, action,
                   polarity, confidence, source, evidence_binding_status, recorded_at
            FROM account_tag_events
            WHERE ego = ? AND account_id = ?
            ORDER BY event_id DESC
            LIMIT ?
        )
        ORDER BY event_id ASC
        """,
        (ego, account_id, limit),
    ).fetchall()
    return [
        AccountTagEvent(
            event_id=int(row[0]),
            ego=row[1],
            account_id=row[2],
            tag=row[3],
            action=row[4],
            polarity=int(row[5]) if row[5] is not None else None,
            confidence=float(row[6]) if row[6] is not None else None,
            source=row[7],
            evidence_binding_status=row[8],
            recorded_at=row[9],
        )
        for row in rows
    ]
