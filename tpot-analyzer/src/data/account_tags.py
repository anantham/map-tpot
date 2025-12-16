"""SQLite-backed store for account-level semantic tags."""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_SQLITE_MAX_VARS = 900


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_tag(tag: str) -> tuple[str, str]:
    """Return (tag_key, tag_display)."""
    display = (tag or "").strip()
    if not display:
        raise ValueError("tag cannot be empty")
    key = display.casefold()
    return key, display


@dataclass(frozen=True)
class AccountTag:
    ego: str
    account_id: str
    tag: str
    polarity: int  # 1 = in tag, -1 = not in tag
    confidence: Optional[float]
    updated_at: str


class AccountTagStore:
    """Persistent tag store scoped by ego and account."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
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
                "CREATE INDEX IF NOT EXISTS idx_account_tags_ego_account ON account_tags(ego, account_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_account_tags_ego_tag ON account_tags(ego, tag_key)"
            )

    def list_tags(self, *, ego: str, account_id: str) -> List[AccountTag]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                SELECT ego, account_id, tag_display, polarity, confidence, updated_at
                FROM account_tags
                WHERE ego = ? AND account_id = ?
                ORDER BY tag_key ASC
                """,
                (ego, account_id),
            )
            rows = cur.fetchall()
        return [
            AccountTag(
                ego=row[0],
                account_id=row[1],
                tag=row[2],
                polarity=int(row[3]),
                confidence=float(row[4]) if row[4] is not None else None,
                updated_at=row[5],
            )
            for row in rows
        ]

    def list_distinct_tags(self, *, ego: str) -> List[str]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                SELECT DISTINCT tag_display
                FROM account_tags
                WHERE ego = ?
                ORDER BY tag_display ASC
                """,
                (ego,),
            )
            rows = cur.fetchall()
        return [row[0] for row in rows]

    def list_tags_for_accounts(self, *, ego: str, account_ids: List[str]) -> List[AccountTag]:
        """List all tags for the given accounts (scoped by ego).

        This method batches queries to avoid SQLite's variable limit.
        """
        ids = [str(a) for a in account_ids if a is not None and str(a) != ""]
        if not ids:
            return []
        tags: List[AccountTag] = []
        with sqlite3.connect(self.db_path) as conn:
            for start in range(0, len(ids), _SQLITE_MAX_VARS):
                chunk = ids[start : start + _SQLITE_MAX_VARS]
                placeholders = ",".join(["?"] * len(chunk))
                cur = conn.execute(
                    f"""
                    SELECT ego, account_id, tag_display, polarity, confidence, updated_at
                    FROM account_tags
                    WHERE ego = ? AND account_id IN ({placeholders})
                    """,
                    (ego, *chunk),
                )
                rows = cur.fetchall()
                tags.extend(
                    [
                        AccountTag(
                            ego=row[0],
                            account_id=row[1],
                            tag=row[2],
                            polarity=int(row[3]),
                            confidence=float(row[4]) if row[4] is not None else None,
                            updated_at=row[5],
                        )
                        for row in rows
                    ]
                )
        return tags

    def upsert_tag(
        self,
        *,
        ego: str,
        account_id: str,
        tag: str,
        polarity: int,
        confidence: Optional[float] = None,
    ) -> AccountTag:
        if polarity not in (1, -1):
            raise ValueError("polarity must be 1 (in) or -1 (not_in)")
        if confidence is not None and not (0.0 <= confidence <= 1.0):
            raise ValueError("confidence must be in [0, 1]")
        tag_key, tag_display = _normalize_tag(tag)
        now = _utc_now_iso()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO account_tags (ego, account_id, tag_key, tag_display, polarity, confidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ego, account_id, tag_key) DO UPDATE SET
                    tag_display = excluded.tag_display,
                    polarity = excluded.polarity,
                    confidence = excluded.confidence,
                    updated_at = excluded.updated_at
                """,
                (ego, account_id, tag_key, tag_display, polarity, confidence, now, now),
            )
        return AccountTag(
            ego=ego,
            account_id=account_id,
            tag=tag_display,
            polarity=polarity,
            confidence=confidence,
            updated_at=now,
        )

    def delete_tag(self, *, ego: str, account_id: str, tag: str) -> bool:
        tag_key, _ = _normalize_tag(tag)
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM account_tags WHERE ego = ? AND account_id = ? AND tag_key = ?",
                (ego, account_id, tag_key),
            )
            deleted = cur.rowcount or 0
        return deleted > 0
