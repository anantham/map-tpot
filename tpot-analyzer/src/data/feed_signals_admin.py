"""Administrative queries for extension feed signals."""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

_SQLITE_MAX_VARS = 900


def _normalize_seen_at(raw: Any) -> str:
    if raw is None:
        raise ValueError("before_seen_at cannot be null when provided")
    text = str(raw).strip()
    if not text:
        raise ValueError("before_seen_at cannot be empty")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"before_seen_at must be ISO-8601 when provided; received '{raw}'"
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _normalize_account_ids(account_ids: Iterable[Any]) -> List[str]:
    values: List[str] = []
    seen: set[str] = set()
    for raw in account_ids:
        if raw is None:
            continue
        account_id = str(raw).strip()
        if not account_id or account_id in seen:
            continue
        seen.add(account_id)
        values.append(account_id)
    return values


class FeedSignalsAdminStore:
    """Operational helpers for raw-event inspection and scoped deletion."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def fetch_events_by_keys(
        self,
        *,
        workspace_id: str,
        ego: str,
        event_keys: List[str],
    ) -> List[Dict[str, Any]]:
        keys = _normalize_account_ids(event_keys)
        if not keys:
            return []

        events: List[Dict[str, Any]] = []
        with sqlite3.connect(self.db_path) as conn:
            for start in range(0, len(keys), _SQLITE_MAX_VARS):
                chunk = keys[start : start + _SQLITE_MAX_VARS]
                placeholders = ",".join(["?"] * len(chunk))
                rows = conn.execute(
                    f"""
                    SELECT event_key, account_id, username, tweet_id, tweet_text, surface,
                           position, language, tweet_url, seen_at, raw_payload, created_at
                    FROM feed_events
                    WHERE workspace_id = ? AND ego = ? AND event_key IN ({placeholders})
                    ORDER BY seen_at DESC, event_key DESC
                    """,
                    (workspace_id, ego, *chunk),
                ).fetchall()
                events.extend(self._rows_to_events(rows))
        return events

    def list_raw_events(
        self,
        *,
        workspace_id: str,
        ego: str,
        limit: int = 100,
        before_seen_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        bounded_limit = max(1, min(500, int(limit)))
        params: List[Any] = [workspace_id, ego]
        predicate = ""
        if before_seen_at is not None:
            cutoff = _normalize_seen_at(before_seen_at)
            predicate = " AND seen_at < ?"
            params.append(cutoff)
        params.append(bounded_limit + 1)

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT event_key, account_id, username, tweet_id, tweet_text, surface,
                       position, language, tweet_url, seen_at, raw_payload, created_at
                FROM feed_events
                WHERE workspace_id = ? AND ego = ?{predicate}
                ORDER BY seen_at DESC, event_key DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        page = rows[:bounded_limit]
        events = self._rows_to_events(page)
        next_cursor = page[-1][9] if len(rows) > bounded_limit and page else None
        return {
            "workspaceId": workspace_id,
            "ego": ego,
            "events": events,
            "limit": bounded_limit,
            "nextCursor": next_cursor,
        }

    def purge_events_for_accounts(
        self,
        *,
        workspace_id: str,
        ego: str,
        account_ids: Iterable[Any],
    ) -> Dict[str, int]:
        account_list = _normalize_account_ids(account_ids)
        if not account_list:
            return {"accountCount": 0, "deletedEvents": 0, "deletedRollups": 0}

        deleted_events = 0
        deleted_rollups = 0
        with sqlite3.connect(self.db_path) as conn:
            for start in range(0, len(account_list), _SQLITE_MAX_VARS):
                chunk = account_list[start : start + _SQLITE_MAX_VARS]
                placeholders = ",".join(["?"] * len(chunk))
                deleted_events += conn.execute(
                    f"""
                    DELETE FROM feed_events
                    WHERE workspace_id = ? AND ego = ? AND account_id IN ({placeholders})
                    """,
                    (workspace_id, ego, *chunk),
                ).rowcount or 0
                deleted_rollups += conn.execute(
                    f"""
                    DELETE FROM feed_tweet_rollup
                    WHERE workspace_id = ? AND ego = ? AND account_id IN ({placeholders})
                    """,
                    (workspace_id, ego, *chunk),
                ).rowcount or 0

        logger.info(
            "purged feed events by accounts workspace=%s ego=%s accounts=%d deleted_events=%d deleted_rollups=%d",
            workspace_id,
            ego,
            len(account_list),
            deleted_events,
            deleted_rollups,
        )
        return {
            "accountCount": len(account_list),
            "deletedEvents": deleted_events,
            "deletedRollups": deleted_rollups,
        }

    def _rows_to_events(self, rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        for row in rows:
            raw_payload = None
            if row[10]:
                try:
                    raw_payload = json.loads(row[10])
                except Exception:
                    raw_payload = {"raw": row[10]}
            events.append(
                {
                    "eventKey": row[0],
                    "accountId": row[1],
                    "username": row[2],
                    "tweetId": row[3],
                    "tweetText": row[4],
                    "surface": row[5],
                    "position": row[6],
                    "language": row[7],
                    "tweetUrl": row[8],
                    "seenAt": row[9],
                    "createdAt": row[11],
                    "rawPayload": raw_payload,
                }
            )
        return events
