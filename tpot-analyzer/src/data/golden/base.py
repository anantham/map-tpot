"""Core storage primitives for golden curation."""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import AXIS_SIMULACRUM, SIMULACRUM_LABELS, SPLIT_NAMES
from .schema import SCHEMA, now_iso, split_for_tweet, validate_distribution

logger = logging.getLogger(__name__)


class BaseGoldenStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._split_counts_cache: Optional[Dict[str, Dict[str, int]]] = None
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

    def _assert_axis(self, axis: str) -> None:
        if axis != AXIS_SIMULACRUM:
            raise ValueError(f"Unsupported axis '{axis}'. Expected '{AXIS_SIMULACRUM}'.")

    def _assert_tweets_table(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tweets'").fetchone()
        if row is None:
            raise RuntimeError(
                f"Missing tweets table in {self.db_path}. Run archive fetch first (scripts/fetch_archive_data.py)."
            )

    def _split_counts(self, conn: sqlite3.Connection, axis: str) -> Dict[str, int]:
        counts = {"train": 0, "dev": 0, "test": 0, "total": 0}
        rows = conn.execute(
            "SELECT split, COUNT(*) AS n FROM curation_split WHERE axis = ? GROUP BY split",
            (axis,),
        ).fetchall()
        for row in rows:
            split = str(row["split"])
            value = int(row["n"])
            counts[split] = value
            counts["total"] += value
        # Cache for subsequent fast-path calls
        if self._split_counts_cache is None:
            self._split_counts_cache = {}
        self._split_counts_cache[axis] = counts
        return counts

    def _split_counts_cached(self, axis: str) -> Optional[Dict[str, int]]:
        """Return cached split counts if available."""
        if self._split_counts_cache and axis in self._split_counts_cache:
            return self._split_counts_cache[axis]
        return None

    def ensure_fixed_splits(self, axis: str, *, assigned_by: str, force_reassign: bool = False) -> Dict[str, int]:
        self._assert_axis(axis)
        with self._open() as conn:
            self._assert_tweets_table(conn)
            if force_reassign:
                conn.execute("DELETE FROM curation_split WHERE axis = ?", (axis,))

            # Fast-path: return cached counts if available, or do a cheap LIMIT 1
            # existence check. Full bootstrap runs only on first call or force_reassign.
            if not force_reassign:
                cached = self._split_counts_cached(axis)
                if cached is not None:
                    return cached
                existing = conn.execute(
                    "SELECT 1 FROM curation_split WHERE axis = ? LIMIT 1", (axis,)
                ).fetchone()
                if existing is not None:
                    return self._split_counts(conn, axis)

            logger.info("Split bootstrap: assigning splits to unassigned tweets")

            # Fetch unassigned tweet IDs in batches to avoid loading millions into memory
            BATCH_SIZE = 10_000
            now = now_iso()
            total_assigned = 0
            while True:
                rows = conn.execute(
                    """
                    SELECT t.tweet_id
                    FROM tweets t
                    LEFT JOIN curation_split s ON s.tweet_id = t.tweet_id AND s.axis = ?
                    WHERE s.tweet_id IS NULL
                    LIMIT ?
                    """,
                    (axis, BATCH_SIZE),
                ).fetchall()
                if not rows:
                    break
                batch = [
                    (str(row["tweet_id"]), axis, split_for_tweet(str(row["tweet_id"])), assigned_by, now)
                    for row in rows
                ]
                conn.executemany(
                    "INSERT OR REPLACE INTO curation_split (tweet_id, axis, split, assigned_by, assigned_at) VALUES (?, ?, ?, ?, ?)",
                    batch,
                )
                conn.commit()
                total_assigned += len(batch)
                if total_assigned % 100_000 == 0:
                    logger.info("Split assignment progress: %d tweets assigned", total_assigned)
            if total_assigned > 0:
                logger.info("Split assignment complete: %d new tweets assigned", total_assigned)
            return self._split_counts(conn, axis)

    def _load_prob_map(self, conn: sqlite3.Connection, table: str, id_column: str, identifier: int) -> Dict[str, float]:
        rows = conn.execute(
            f"SELECT label, probability FROM {table} WHERE {id_column} = ?",
            (identifier,),
        ).fetchall()
        return {str(row["label"]): float(row["probability"]) for row in rows}

    def _load_context(self, conn: sqlite3.Connection, tweet_id: str, reply_to_tweet_id: Optional[str]) -> Dict[str, Any]:
        for candidate in [tweet_id, reply_to_tweet_id]:
            if not candidate:
                continue
            row = conn.execute("SELECT raw_json FROM thread_context_cache WHERE tweet_id = ?", (candidate,)).fetchone()
            if row is None:
                continue
            try:
                payload = json.loads(str(row["raw_json"]))
            except json.JSONDecodeError:
                logger.warning("Invalid thread context JSON for tweet_id=%s", candidate)
                continue
            return {"threadContext": payload, "contextSource": str(candidate)}
        return {"threadContext": [], "contextSource": None}

    def list_candidates(
        self,
        axis: str,
        *,
        split: Optional[str],
        status: str,
        reviewer: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        self._assert_axis(axis)
        if status not in {"all", "labeled", "unlabeled"}:
            raise ValueError("status must be one of: all, labeled, unlabeled")
        if split not in {None, *SPLIT_NAMES}:
            raise ValueError("split must be one of: train, dev, test")

        with self._open() as conn:
            self._assert_tweets_table(conn)

            # For unlabeled status (the common labeling case), use a fast NOT EXISTS
            # query instead of LEFT JOIN + sort across millions of rows.
            if status == "unlabeled":
                return self._list_unlabeled_fast(conn, axis, split=split, reviewer=reviewer, limit=limit)

            conditions = ["s.axis = ?"]
            params: List[Any] = [axis]
            if split is not None:
                conditions.append("s.split = ?")
                params.append(split)
            if status == "labeled":
                conditions.append("ls.id IS NOT NULL")

            query = f"""
                SELECT t.tweet_id, t.account_id, t.username, t.full_text, t.created_at, t.reply_to_tweet_id,
                       s.split, ls.id AS active_label_set_id
                FROM tweets t
                JOIN curation_split s ON s.tweet_id = t.tweet_id
                LEFT JOIN tweet_label_set ls
                    ON ls.tweet_id = t.tweet_id
                   AND ls.axis = s.axis
                   AND ls.reviewer = ?
                   AND ls.is_active = 1
                WHERE {' AND '.join(conditions)}
                ORDER BY t.created_at DESC
                LIMIT ?
            """
            params = [reviewer, *params, int(limit)]
            rows = conn.execute(query, tuple(params)).fetchall()
            return self._rows_to_candidates(conn, rows)

    def _list_unlabeled_fast(
        self,
        conn: sqlite3.Connection,
        axis: str,
        *,
        split: Optional[str],
        reviewer: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Fast path for fetching unlabeled candidates using NOT EXISTS + LIMIT.

        SQLite can satisfy this without sorting millions of rows because
        NOT EXISTS short-circuits per row and we don't need a global sort
        for labeling — any unlabeled tweet is fine.
        """
        conditions = ["s.axis = ?"]
        params: List[Any] = [axis]
        if split is not None:
            conditions.append("s.split = ?")
            params.append(split)

        query = f"""
            SELECT t.tweet_id, t.account_id, t.username, t.full_text, t.created_at, t.reply_to_tweet_id,
                   s.split
            FROM curation_split s
            JOIN tweets t ON t.tweet_id = s.tweet_id
            WHERE {' AND '.join(conditions)}
              AND NOT EXISTS (
                  SELECT 1 FROM tweet_label_set ls
                  WHERE ls.tweet_id = s.tweet_id
                    AND ls.axis = s.axis
                    AND ls.reviewer = ?
                    AND ls.is_active = 1
              )
            LIMIT ?
        """
        params.extend([reviewer, int(limit)])
        rows = conn.execute(query, tuple(params)).fetchall()
        return self._rows_to_candidates(conn, rows, label_status="unlabeled")

    def _rows_to_candidates(
        self,
        conn: sqlite3.Connection,
        rows: list,
        *,
        label_status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for row in rows:
            if label_status:
                status = label_status
            else:
                try:
                    status = "labeled" if row["active_label_set_id"] else "unlabeled"
                except (IndexError, KeyError):
                    status = "unlabeled"
            result.append(
                {
                    "tweetId": str(row["tweet_id"]),
                    "accountId": str(row["account_id"]),
                    "username": str(row["username"]),
                    "text": str(row["full_text"]),
                    "createdAt": row["created_at"],
                    "replyToTweetId": row["reply_to_tweet_id"],
                    "split": str(row["split"]),
                    "labelStatus": status,
                    **self._load_context(conn, str(row["tweet_id"]), row["reply_to_tweet_id"]),
                }
            )
        return result

    def _has_active_label(self, conn: sqlite3.Connection, *, tweet_id: str, axis: str, reviewer: str) -> bool:
        row = conn.execute(
            """
            SELECT 1 FROM tweet_label_set
            WHERE tweet_id = ? AND axis = ? AND reviewer = ? AND is_active = 1
            LIMIT 1
            """,
            (tweet_id, axis, reviewer),
        ).fetchone()
        return row is not None

    def upsert_label(
        self,
        *,
        tweet_id: str,
        axis: str,
        reviewer: str,
        distribution: Dict[str, Any],
        note: Optional[str],
        context_snapshot_json: Optional[Any],
    ) -> int:
        self._assert_axis(axis)
        parsed = validate_distribution(distribution)
        now = now_iso()
        with self._open() as conn:
            prior = conn.execute(
                """
                SELECT id FROM tweet_label_set
                WHERE tweet_id = ? AND axis = ? AND reviewer = ? AND is_active = 1
                ORDER BY id DESC LIMIT 1
                """,
                (tweet_id, axis, reviewer),
            ).fetchone()
            supersedes = int(prior["id"]) if prior is not None else None
            if supersedes is not None:
                conn.execute("UPDATE tweet_label_set SET is_active = 0 WHERE id = ?", (supersedes,))

            context_json = json.dumps(context_snapshot_json) if context_snapshot_json is not None else None
            context_hash = hashlib.sha256(context_json.encode("utf-8")).hexdigest() if context_json else None
            cursor = conn.execute(
                """
                INSERT INTO tweet_label_set
                (tweet_id, axis, reviewer, note, context_hash, context_snapshot_json, is_active, created_at, supersedes_label_set_id)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (tweet_id, axis, reviewer, note, context_hash, context_json, now, supersedes),
            )
            label_set_id = int(cursor.lastrowid)
            conn.executemany(
                "INSERT INTO tweet_label_prob (label_set_id, label, probability) VALUES (?, ?, ?)",
                [(label_set_id, label, parsed[label]) for label in SIMULACRUM_LABELS],
            )
            conn.execute(
                "UPDATE uncertainty_queue SET status = 'resolved', updated_at = ? WHERE tweet_id = ? AND axis = ?",
                (now, tweet_id, axis),
            )
            conn.commit()
            return label_set_id
