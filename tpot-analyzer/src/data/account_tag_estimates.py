"""Append-only curator estimate trajectories for account tags."""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.data.account_tag_schema import initialize_account_tag_schema
from src.data.tag_meta_notes import normalize_ego, normalize_tag


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be empty")
    return normalized


def _require_estimate(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{field} must be finite")
    if not 0.0 <= parsed <= 1.0:
        raise ValueError(f"{field} must be between 0 and 1")
    return parsed


@dataclass(frozen=True)
class AccountTagEstimateEvent:
    event_id: int
    ego: str
    account_id: str
    tag_key: str
    tag: str
    point_estimate: float
    plausible_low: float
    plausible_high: float
    review_session_id: str
    source: str
    evidence_binding_status: str
    recorded_at: str


class AccountTagEstimateStore:
    """Persistent append-only estimate events keyed by curator/account/tag."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            initialize_account_tag_schema(conn)

    def append_estimate(
        self,
        *,
        ego: str,
        account_id: str,
        tag: str,
        point_estimate: float,
        plausible_low: float,
        plausible_high: float,
        review_session_id: str,
        source: str,
    ) -> AccountTagEstimateEvent:
        canonical_ego = normalize_ego(ego)
        normalized_account = _require_text(account_id, "account_id")
        tag_key, tag_display = normalize_tag(tag)
        point = _require_estimate(point_estimate, "point_estimate")
        low = _require_estimate(plausible_low, "plausible_low")
        high = _require_estimate(plausible_high, "plausible_high")
        if not low <= point <= high:
            raise ValueError(
                "estimate range must satisfy low <= point <= high"
            )
        session = _require_text(review_session_id, "review_session_id")
        normalized_source = _require_text(source, "source")
        recorded_at = _utc_now_iso()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO account_tag_estimate_events (
                    ego, account_id, tag_key, tag_display, point_estimate,
                    plausible_low, plausible_high, review_session_id, source,
                    evidence_binding_status, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'unbound', ?)
                """,
                (
                    canonical_ego,
                    normalized_account,
                    tag_key,
                    tag_display,
                    point,
                    low,
                    high,
                    session,
                    normalized_source,
                    recorded_at,
                ),
            )
        return AccountTagEstimateEvent(
            event_id=int(cursor.lastrowid),
            ego=canonical_ego,
            account_id=normalized_account,
            tag_key=tag_key,
            tag=tag_display,
            point_estimate=point,
            plausible_low=low,
            plausible_high=high,
            review_session_id=session,
            source=normalized_source,
            evidence_binding_status="unbound",
            recorded_at=recorded_at,
        )

    def get_estimates(
        self, *, ego: str, account_id: str, tag: str, limit: int = 50
    ) -> tuple[Optional[AccountTagEstimateEvent], list[AccountTagEstimateEvent]]:
        canonical_ego = normalize_ego(ego)
        normalized_account = _require_text(account_id, "account_id")
        tag_key, _ = normalize_tag(tag)
        bounded_limit = max(1, min(int(limit), 200))
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT event_id, ego, account_id, tag_key, tag_display,
                       point_estimate, plausible_low, plausible_high,
                       review_session_id, source, evidence_binding_status,
                       recorded_at
                FROM (
                    SELECT event_id, ego, account_id, tag_key, tag_display,
                           point_estimate, plausible_low, plausible_high,
                           review_session_id, source, evidence_binding_status,
                           recorded_at
                    FROM account_tag_estimate_events
                    WHERE ego = ? AND account_id = ? AND tag_key = ?
                    ORDER BY event_id DESC
                    LIMIT ?
                )
                ORDER BY event_id ASC
                """,
                (canonical_ego, normalized_account, tag_key, bounded_limit),
            ).fetchall()
        history = [
            AccountTagEstimateEvent(
                event_id=int(row[0]),
                ego=str(row[1]),
                account_id=str(row[2]),
                tag_key=str(row[3]),
                tag=str(row[4]),
                point_estimate=float(row[5]),
                plausible_low=float(row[6]),
                plausible_high=float(row[7]),
                review_session_id=str(row[8]),
                source=str(row[9]),
                evidence_binding_status=str(row[10]),
                recorded_at=str(row[11]),
            )
            for row in rows
        ]
        return (history[-1] if history else None), history
