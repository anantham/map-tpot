"""SQLite-backed storage and reporting for discovery signal feedback.

Persists user feedback across server restarts using a WAL-mode SQLite database.
The DB is stored in the snapshot directory by default (configurable via constructor).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from threading import Lock
from time import time
from typing import Any, Dict, List, Optional

from src.config import get_snapshot_dir
from src.api.feedback_limits import MAX_CONTEXT_BYTES, validate_feedback

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignalFeedbackEvent:
    account_id: str
    signal_name: str
    score: float
    user_label: str
    context: Dict[str, Any]
    timestamp: float
    expires_at: Optional[float] = None


class SignalFeedbackStore:
    """Thread-safe SQLite-backed feedback store used by discovery feedback routes.

    Data persists across server restarts. The in-memory list is loaded from
    SQLite on construction and kept in sync on every write. This keeps the
    existing quality_report() logic unchanged while adding durability.
    """

    _DB_FILENAME = "signal_feedback.db"

    def __init__(self, db_path: Optional[Path] = None, *, max_events: int = 20000,
                 retention_seconds: int = 30 * 86400) -> None:
        if max_events < 1 or retention_seconds < 1:
            raise ValueError("feedback limits must be positive")
        self._max_events = max_events
        self._retention_seconds = retention_seconds
        if db_path is None:
            db_path = get_snapshot_dir() / self._DB_FILENAME
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()
        self._events: List[SignalFeedbackEvent] = self._load_all()
        logger.info(
            "SignalFeedbackStore initialized with %d persisted events from %s",
            len(self._events),
            self._db_path,
        )

    # ------------------------------------------------------------------
    # Database setup
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Return a new connection with WAL mode enabled."""
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        """Create the feedback table if it does not exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback_events (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id  TEXT    NOT NULL,
                    signal_name TEXT    NOT NULL,
                    score       REAL    NOT NULL,
                    user_label  TEXT    NOT NULL,
                    context     TEXT    NOT NULL DEFAULT '{}',
                    timestamp   REAL    NOT NULL
                )
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(feedback_events)")}
            if "expires_at" not in columns:
                conn.execute("ALTER TABLE feedback_events ADD COLUMN expires_at REAL")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fb_expiry ON feedback_events(expires_at)")
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fb_signal
                ON feedback_events(signal_name)
            """)

    def _prune_expired(self, conn) -> None:
        # Legacy rows have no expiry: never silently delete historical curator data.
        conn.execute("DELETE FROM feedback_events WHERE expires_at IS NOT NULL AND expires_at <= ?", (time(),))

    def _load_all(self) -> List[SignalFeedbackEvent]:
        """Load a bounded window of unexpired and legacy events."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT account_id, signal_name, score, user_label, context, timestamp, expires_at "
                "FROM feedback_events WHERE (expires_at IS NULL OR expires_at > ?) "
                "AND length(CAST(context AS BLOB)) <= ? ORDER BY id DESC LIMIT ?",
                (time(), MAX_CONTEXT_BYTES, self._max_events),
            ).fetchall()
        events: List[SignalFeedbackEvent] = []
        for row in reversed(rows):
            if row[4] and len(row[4].encode("utf-8")) > MAX_CONTEXT_BYTES:
                logger.warning("Ignoring oversized legacy feedback context")
                continue
            ctx: Dict[str, Any] = {}
            try:
                ctx = json.loads(row[4]) if row[4] else {}
            except (json.JSONDecodeError, TypeError):
                logger.warning("Corrupt context JSON for account_id=%s, using {}", row[0])
            events.append(SignalFeedbackEvent(
                account_id=row[0],
                signal_name=row[1],
                score=row[2],
                user_label=row[3],
                context=ctx,
                timestamp=row[5],
                expires_at=row[6],
            ))
        return events

    # ------------------------------------------------------------------
    # Public API (unchanged signatures)
    # ------------------------------------------------------------------

    def add_feedback(
        self,
        *,
        account_id: str,
        signal_name: str,
        score: float,
        user_label: str,
        context: Dict[str, Any] | None = None,
    ) -> None:
        context = {} if context is None else context
        encoded_context = validate_feedback(account_id, signal_name, score, user_label, context)
        observed_at = time()
        event = SignalFeedbackEvent(
            account_id=account_id,
            signal_name=signal_name,
            score=float(score),
            user_label=user_label,
            context=context or {},
            timestamp=observed_at,
            expires_at=observed_at + self._retention_seconds,
        )
        with self._lock:
            # Persist to SQLite first so data survives crashes.
            with self._get_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                self._prune_expired(conn)
                count = conn.execute("SELECT COUNT(*) FROM feedback_events").fetchone()[0]
                if count >= self._max_events:
                    raise OverflowError("feedback storage quota reached; review/export existing records")
                conn.execute(
                    "INSERT INTO feedback_events "
                    "(account_id, signal_name, score, user_label, context, timestamp, expires_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.account_id,
                        event.signal_name,
                        event.score,
                        event.user_label,
                        encoded_context,
                        event.timestamp,
                        event.expires_at,
                    ),
                )
            self._events = self._load_all()

    def _expire_memory(self) -> None:
        now = time()
        self._events = [event for event in self._events if event.expires_at is None or event.expires_at > now]

    def event_count(self) -> int:
        with self._lock:
            self._expire_memory()
            return len(self._events)

    def quality_report(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            self._expire_memory()
            events = list(self._events)

        grouped: Dict[str, List[SignalFeedbackEvent]] = {}
        for event in events:
            grouped.setdefault(event.signal_name, []).append(event)

        report: Dict[str, Dict[str, Any]] = {}
        for signal_name, signal_events in grouped.items():
            tpot_scores = [event.score for event in signal_events if event.user_label == "tpot"]
            not_tpot_scores = [event.score for event in signal_events if event.user_label == "not_tpot"]
            total = len(signal_events)
            tpot_ratio = len(tpot_scores) / total if total else 0.0
            mean_tpot = mean(tpot_scores) if tpot_scores else 0.0
            mean_not_tpot = mean(not_tpot_scores) if not_tpot_scores else 0.0
            score_separation = mean_tpot - mean_not_tpot

            if total < 5:
                quality = "low-sample"
            elif abs(score_separation) >= 0.25:
                quality = "high"
            elif abs(score_separation) >= 0.1:
                quality = "medium"
            else:
                quality = "low"

            if total < 5:
                recommended_weight_change = 0.0
            elif tpot_ratio >= 0.6 and score_separation >= 0.1:
                recommended_weight_change = 0.1
            elif tpot_ratio <= 0.4 and score_separation <= -0.1:
                recommended_weight_change = -0.1
            else:
                recommended_weight_change = 0.0

            report[signal_name] = {
                "total_feedback": total,
                "quality": quality,
                "tpot_ratio": tpot_ratio,
                "score_separation": score_separation,
                "recommended_weight_change": recommended_weight_change,
            }

        return report
