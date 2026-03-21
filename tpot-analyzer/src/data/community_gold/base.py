"""Write-focused storage primitives for account-community gold labels."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from .schema import SCHEMA, now_iso, split_for_account, validate_confidence, validate_judgment


class BaseCommunityGoldStore:
    """Persistent write-oriented store for leak-proof account-community gold labels."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=60)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._open() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _assert_community_table(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='community'"
        ).fetchone()
        if row is None:
            raise RuntimeError(
                f"Missing community table in {self.db_path}. Run community initialization first."
            )

    def _assert_community_exists(self, conn: sqlite3.Connection, community_id: str) -> None:
        row = conn.execute(
            "SELECT 1 FROM community WHERE id = ?",
            (community_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"community '{community_id}' does not exist")

    def _ensure_account_split(
        self,
        conn: sqlite3.Connection,
        *,
        account_id: str,
        assigned_by: str,
    ) -> str:
        row = conn.execute(
            "SELECT split FROM account_community_gold_split WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        if row is not None:
            return str(row["split"])
        split = split_for_account(account_id)
        conn.execute(
            """
            INSERT INTO account_community_gold_split (account_id, split, assigned_by, assigned_at)
            VALUES (?, ?, ?, ?)
            """,
            (account_id, split, assigned_by, now_iso()),
        )
        return split

    def upsert_label(
        self,
        *,
        account_id: str,
        community_id: str,
        reviewer: str,
        judgment: Any,
        confidence: Any = None,
        note: Optional[str] = None,
        evidence: Optional[Any] = None,
        assigned_by: str = "system",
    ) -> Dict[str, Any]:
        parsed_judgment = validate_judgment(judgment)
        parsed_confidence = validate_confidence(confidence)
        evidence_json = json.dumps(evidence) if evidence is not None else None
        created_at = now_iso()

        with self._open() as conn:
            self._assert_community_table(conn)
            self._assert_community_exists(conn, community_id)
            split = self._ensure_account_split(conn, account_id=account_id, assigned_by=assigned_by)
            prior = conn.execute(
                """
                SELECT id FROM account_community_gold_label_set
                WHERE account_id = ? AND community_id = ? AND reviewer = ? AND is_active = 1
                ORDER BY id DESC LIMIT 1
                """,
                (account_id, community_id, reviewer),
            ).fetchone()
            supersedes = int(prior["id"]) if prior is not None else None
            if supersedes is not None:
                conn.execute(
                    "UPDATE account_community_gold_label_set SET is_active = 0 WHERE id = ?",
                    (supersedes,),
                )

            cursor = conn.execute(
                """
                INSERT INTO account_community_gold_label_set
                (account_id, community_id, reviewer, judgment, confidence, note, evidence_json,
                 is_active, created_at, supersedes_label_set_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    account_id,
                    community_id,
                    reviewer,
                    parsed_judgment,
                    parsed_confidence,
                    note,
                    evidence_json,
                    created_at,
                    supersedes,
                ),
            )
            conn.commit()
            return {
                "labelSetId": int(cursor.lastrowid),
                "accountId": account_id,
                "communityId": community_id,
                "reviewer": reviewer,
                "judgment": parsed_judgment,
                "confidence": parsed_confidence,
                "split": split,
                "createdAt": created_at,
                "supersedesLabelSetId": supersedes,
            }

    def clear_label(self, *, account_id: str, community_id: str, reviewer: str) -> bool:
        with self._open() as conn:
            cur = conn.execute(
                """
                UPDATE account_community_gold_label_set
                SET is_active = 0
                WHERE account_id = ? AND community_id = ? AND reviewer = ? AND is_active = 1
                """,
                (account_id, community_id, reviewer),
            )
            conn.commit()
            return (cur.rowcount or 0) > 0
