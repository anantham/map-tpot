"""Signal event system for observable pipeline and validation."""

import json
import sqlite3
import threading
import zlib
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal
from uuid import uuid4
import logging

logger = logging.getLogger(__name__)

SignalPhase = Literal["pre_compute", "post_compute", "feedback", "validation"]
SignalName = Literal["neighbor_overlap", "pagerank", "community", "path_distance", "composite"]


@dataclass
class SignalEvent:
    """Represents a single signal computation event."""

    id: str
    signal_name: SignalName
    phase: SignalPhase
    timestamp: datetime
    candidate_id: Optional[str] = None
    seeds: Optional[List[str]] = None
    score: Optional[float] = None
    metadata: Dict[str, Any] = None
    warnings: List[str] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.warnings is None:
            self.warnings = []
        if self.id is None:
            self.id = str(uuid4())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat() if self.timestamp else None
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SignalEvent':
        """Create from dictionary."""
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class SignalEventStore:
    """SQLite storage for signal events with automatic rotation."""

    MAX_SIZE_GB = 2.0
    ALERT_THRESHOLD_GB = 1.8

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize the event store.

        Args:
            db_path: Path to SQLite database. Defaults to data/signal_events.db
        """
        if db_path is None:
            db_path = Path(__file__).parents[2] / "data" / "signal_events.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._init_database()
        self._check_size()

    def _init_database(self):
        """Create tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signal_events (
                    id TEXT PRIMARY KEY,
                    signal_name TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    candidate_id TEXT,
                    timestamp REAL NOT NULL,
                    score REAL,
                    metadata_compressed BLOB,
                    warnings TEXT,
                    error TEXT,
                    created_at REAL DEFAULT (unixepoch('now'))
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signal_timestamp
                ON signal_events(signal_name, timestamp DESC)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_candidate_signal
                ON signal_events(candidate_id, signal_name)
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS signal_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    signal_name TEXT NOT NULL,
                    score REAL NOT NULL,
                    user_label TEXT NOT NULL,
                    feedback_type TEXT NOT NULL,
                    context TEXT,
                    timestamp REAL DEFAULT (unixepoch('now')),
                    UNIQUE(account_id, signal_name, user_label)
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_feedback_signal
                ON signal_feedback(signal_name, user_label)
            """)

    def store_event(self, event: SignalEvent) -> None:
        """Store a signal event, with automatic rotation if needed.

        Args:
            event: The signal event to store
        """
        with self._lock:
            # Check database size
            if self._get_db_size_gb() > self.MAX_SIZE_GB:
                self._rotate_oldest_events()
                logger.warning(f"Signal event DB exceeded {self.MAX_SIZE_GB}GB, rotating old events")
            elif self._get_db_size_gb() > self.ALERT_THRESHOLD_GB:
                logger.warning(f"Signal event DB approaching size limit: {self._get_db_size_gb():.2f}GB")

            # Compress metadata
            metadata_json = json.dumps(event.metadata) if event.metadata else "{}"
            metadata_compressed = zlib.compress(metadata_json.encode())

            warnings_json = json.dumps(event.warnings) if event.warnings else None

            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO signal_events
                    (id, signal_name, phase, candidate_id, timestamp, score,
                     metadata_compressed, warnings, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.id,
                    event.signal_name,
                    event.phase,
                    event.candidate_id,
                    event.timestamp.timestamp(),
                    event.score,
                    metadata_compressed,
                    warnings_json,
                    event.error
                ))

    def get_events(
        self,
        signal_name: Optional[SignalName] = None,
        candidate_id: Optional[str] = None,
        phase: Optional[SignalPhase] = None,
        limit: int = 100
    ) -> List[SignalEvent]:
        """Retrieve events matching the criteria.

        Args:
            signal_name: Filter by signal name
            candidate_id: Filter by candidate ID
            phase: Filter by event phase
            limit: Maximum number of events to return

        Returns:
            List of matching SignalEvent objects
        """
        query = "SELECT * FROM signal_events WHERE 1=1"
        params = []

        if signal_name:
            query += " AND signal_name = ?"
            params.append(signal_name)
        if candidate_id:
            query += " AND candidate_id = ?"
            params.append(candidate_id)
        if phase:
            query += " AND phase = ?"
            params.append(phase)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)

            events = []
            for row in cursor:
                # Decompress metadata
                metadata = {}
                if row['metadata_compressed']:
                    try:
                        metadata_json = zlib.decompress(row['metadata_compressed']).decode()
                        metadata = json.loads(metadata_json)
                    except Exception as e:
                        logger.error(f"Failed to decompress metadata: {e}")

                # Parse warnings
                warnings = []
                if row['warnings']:
                    try:
                        warnings = json.loads(row['warnings'])
                    except Exception as e:
                        logger.error(f"Failed to parse warnings: {e}")

                events.append(SignalEvent(
                    id=row['id'],
                    signal_name=row['signal_name'],
                    phase=row['phase'],
                    candidate_id=row['candidate_id'],
                    timestamp=datetime.fromtimestamp(row['timestamp']),
                    score=row['score'],
                    metadata=metadata,
                    warnings=warnings,
                    error=row['error']
                ))

        return events

    def store_feedback(
        self,
        account_id: str,
        signal_name: SignalName,
        score: float,
        user_label: str,
        feedback_type: str = "binary",
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Store user feedback on a signal.

        Args:
            account_id: The account being evaluated
            signal_name: The signal that generated the score
            score: The score that was shown to the user
            user_label: User's label (e.g., "tpot", "not_tpot")
            feedback_type: Type of feedback (e.g., "binary", "rating")
            context: Additional context about the feedback
        """
        context_json = json.dumps(context) if context else None

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO signal_feedback
                (account_id, signal_name, score, user_label, feedback_type, context)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (account_id, signal_name, score, user_label, feedback_type, context_json))

    def get_feedback_stats(self, signal_name: Optional[SignalName] = None) -> Dict[str, Any]:
        """Get statistics about user feedback.

        Args:
            signal_name: Filter by signal name, or None for all signals

        Returns:
            Dictionary with feedback statistics per signal
        """
        query = """
            SELECT
                signal_name,
                user_label,
                COUNT(*) as count,
                AVG(score) as avg_score,
                MIN(score) as min_score,
                MAX(score) as max_score
            FROM signal_feedback
        """

        if signal_name:
            query += " WHERE signal_name = ?"
            params = [signal_name]
        else:
            params = []

        query += " GROUP BY signal_name, user_label"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)

            stats = {}
            for row in cursor:
                sig_name = row['signal_name']
                if sig_name not in stats:
                    stats[sig_name] = {}

                stats[sig_name][row['user_label']] = {
                    'count': row['count'],
                    'avg_score': row['avg_score'],
                    'min_score': row['min_score'],
                    'max_score': row['max_score']
                }

        return stats

    def _get_db_size_gb(self) -> float:
        """Get the database size in GB."""
        if not self.db_path.exists():
            return 0.0
        return self.db_path.stat().st_size / (1024 ** 3)

    def _check_size(self) -> None:
        """Check database size and log if approaching limit."""
        size_gb = self._get_db_size_gb()
        if size_gb > self.ALERT_THRESHOLD_GB:
            logger.warning(
                f"Signal event database is {size_gb:.2f}GB, "
                f"approaching {self.MAX_SIZE_GB}GB limit"
            )

    def _rotate_oldest_events(self, keep_ratio: float = 0.7) -> None:
        """Remove oldest events to free up space.

        Args:
            keep_ratio: Fraction of events to keep (by recency)
        """
        with sqlite3.connect(self.db_path) as conn:
            # Count total events
            count = conn.execute("SELECT COUNT(*) FROM signal_events").fetchone()[0]

            if count == 0:
                return

            # Calculate how many to keep
            keep_count = int(count * keep_ratio)

            # Delete oldest events
            conn.execute("""
                DELETE FROM signal_events
                WHERE id NOT IN (
                    SELECT id FROM signal_events
                    ORDER BY timestamp DESC
                    LIMIT ?
                )
            """, (keep_count,))

            # Vacuum to reclaim space
            conn.execute("VACUUM")

            logger.info(f"Rotated signal events, kept {keep_count} of {count} events")


# Global event store instance
_event_store = None

def get_event_store() -> SignalEventStore:
    """Get the global event store instance."""
    global _event_store
    if _event_store is None:
        _event_store = SignalEventStore()
    return _event_store