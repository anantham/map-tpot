"""SQLite-backed store for extension feed impressions and tweet context."""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.data.feed_signals_queries import build_account_summary, build_top_exposed_accounts

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_seen_at(raw: Any) -> str:
    if raw is None or str(raw).strip() == "":
        return _utc_now_iso()
    candidate = str(raw).strip()
    # Allow JS-style "Z" timestamps.
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"seenAt must be ISO-8601; received '{raw}'") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _safe_int(name: str, value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer when provided; received '{value}'") from exc


def _normalize_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class FeedSignalsStore:
    """Persistent storage for feed impressions from the Chrome extension."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feed_events (
                    event_key TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    ego TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    username TEXT,
                    tweet_id TEXT,
                    tweet_text TEXT,
                    surface TEXT NOT NULL,
                    position INTEGER,
                    language TEXT,
                    tweet_url TEXT,
                    seen_at TEXT NOT NULL,
                    raw_payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feed_tweet_rollup (
                    workspace_id TEXT NOT NULL,
                    ego TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    tweet_id TEXT NOT NULL,
                    username TEXT,
                    latest_text TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    seen_count INTEGER NOT NULL,
                    last_surface TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (workspace_id, ego, account_id, tweet_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_feed_events_scope_account ON feed_events(workspace_id, ego, account_id, seen_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_feed_events_scope_surface ON feed_events(workspace_id, ego, surface, seen_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_feed_rollup_scope_account ON feed_tweet_rollup(workspace_id, ego, account_id, last_seen_at DESC)"
            )

    def _normalize_event(self, *, workspace_id: str, ego: str, event: Any) -> Dict[str, Any]:
        if not isinstance(event, dict):
            raise ValueError("event must be an object")
        account_id = _normalize_text(event.get("accountId") or event.get("account_id"))
        if not account_id:
            raise ValueError("accountId is required")
        seen_at = _normalize_seen_at(event.get("seenAt") or event.get("seen_at"))
        surface = _normalize_text(event.get("surface")) or "home"
        position = _safe_int("position", event.get("position"))
        tweet_id = _normalize_text(event.get("tweetId") or event.get("tweet_id"))
        tweet_text = _normalize_text(
            event.get("tweetText") or event.get("tweet_text") or event.get("text")
        )
        username = _normalize_text(event.get("username"))
        language = _normalize_text(event.get("language"))
        tweet_url = _normalize_text(event.get("tweetUrl") or event.get("tweet_url") or event.get("url"))
        event_id = _normalize_text(event.get("eventId") or event.get("event_id"))
        key_material = event_id or (
            f"{account_id}|{tweet_id or ''}|{seen_at}|{surface}|{position if position is not None else ''}|"
            f"{(tweet_text or '')[:160]}"
        )
        digest = hashlib.sha1(f"{workspace_id}|{ego}|{key_material}".encode("utf-8")).hexdigest()
        return {
            "event_key": digest,
            "account_id": account_id,
            "username": username,
            "tweet_id": tweet_id,
            "tweet_text": tweet_text,
            "surface": surface,
            "position": position,
            "language": language,
            "tweet_url": tweet_url,
            "seen_at": seen_at,
            "raw_payload": json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        }

    def ingest_events(
        self,
        *,
        workspace_id: str,
        ego: str,
        events: List[Any],
        collect_inserted_keys: bool = False,
    ) -> Dict[str, Any]:
        """Ingest extension events, dedupe exact duplicates, and update tweet rollups."""
        if not isinstance(events, list):
            raise ValueError("events must be a JSON array")
        inserted = 0
        duplicates = 0
        failed = 0
        error_samples: List[Dict[str, Any]] = []
        inserted_event_keys: List[str] = []
        now = _utc_now_iso()

        with sqlite3.connect(self.db_path) as conn:
            for idx, raw_event in enumerate(events):
                try:
                    event = self._normalize_event(workspace_id=workspace_id, ego=ego, event=raw_event)
                except Exception as exc:
                    failed += 1
                    if len(error_samples) < 10:
                        error_samples.append({"index": idx, "error": str(exc)})
                    continue

                try:
                    conn.execute(
                        """
                        INSERT INTO feed_events (
                            event_key, workspace_id, ego, account_id, username, tweet_id, tweet_text,
                            surface, position, language, tweet_url, seen_at, raw_payload, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event["event_key"],
                            workspace_id,
                            ego,
                            event["account_id"],
                            event["username"],
                            event["tweet_id"],
                            event["tweet_text"],
                            event["surface"],
                            event["position"],
                            event["language"],
                            event["tweet_url"],
                            event["seen_at"],
                            event["raw_payload"],
                            now,
                        ),
                    )
                except sqlite3.IntegrityError:
                    duplicates += 1
                    continue

                inserted += 1
                if collect_inserted_keys:
                    inserted_event_keys.append(event["event_key"])
                if not event["tweet_id"]:
                    continue
                conn.execute(
                    """
                    INSERT INTO feed_tweet_rollup (
                        workspace_id, ego, account_id, tweet_id, username, latest_text,
                        first_seen_at, last_seen_at, seen_count, last_surface, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(workspace_id, ego, account_id, tweet_id) DO UPDATE SET
                        username = COALESCE(excluded.username, feed_tweet_rollup.username),
                        latest_text = CASE
                            WHEN excluded.latest_text IS NOT NULL AND excluded.latest_text != ''
                                THEN excluded.latest_text
                            ELSE feed_tweet_rollup.latest_text
                        END,
                        first_seen_at = MIN(feed_tweet_rollup.first_seen_at, excluded.first_seen_at),
                        last_seen_at = MAX(feed_tweet_rollup.last_seen_at, excluded.last_seen_at),
                        seen_count = feed_tweet_rollup.seen_count + 1,
                        last_surface = excluded.last_surface,
                        updated_at = excluded.updated_at
                    """,
                    (
                        workspace_id,
                        ego,
                        event["account_id"],
                        event["tweet_id"],
                        event["username"],
                        event["tweet_text"],
                        event["seen_at"],
                        event["seen_at"],
                        1,
                        event["surface"],
                        now,
                    ),
                )

        logger.info(
            "feed events ingested: workspace=%s ego=%s total=%d inserted=%d duplicates=%d failed=%d",
            workspace_id,
            ego,
            len(events),
            inserted,
            duplicates,
            failed,
        )
        result: Dict[str, Any] = {
            "total": len(events),
            "inserted": inserted,
            "duplicates": duplicates,
            "failed": failed,
            "errors": error_samples,
        }
        if collect_inserted_keys:
            result["insertedEventKeys"] = inserted_event_keys
        return result

    def account_summary(
        self,
        *,
        workspace_id: str,
        ego: str,
        account_id: str,
        days: int = 30,
        keyword_limit: int = 12,
        sample_limit: int = 8,
    ) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            return build_account_summary(
                conn=conn,
                workspace_id=workspace_id,
                ego=ego,
                account_id=account_id,
                days=days,
                keyword_limit=keyword_limit,
                sample_limit=sample_limit,
            )

    def top_exposed_accounts(self, *, workspace_id: str, ego: str, days: int = 30, limit: int = 20) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            return build_top_exposed_accounts(
                conn=conn,
                workspace_id=workspace_id,
                ego=ego,
                days=days,
                limit=limit,
            )
