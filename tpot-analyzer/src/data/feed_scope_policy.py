"""Scoped policy storage for extension ingestion and firehose controls."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

_VALID_INGESTION_MODES = {"open", "guarded"}
_VALID_RETENTION_MODES = {"infinite"}
_VALID_PROCESSING_MODES = {"continuous"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_bool(name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{name} must be boolean")


def _normalize_string_list(name: str, value: Any) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array of strings")
    normalized: List[str] = []
    seen: set[str] = set()
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _normalize_mode(name: str, value: Any, valid: set[str]) -> str:
    text = str(value or "").strip().lower()
    if text not in valid:
        allowed = ", ".join(sorted(valid))
        raise ValueError(f"{name} must be one of [{allowed}]")
    return text


def _normalize_firehose_path(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _loads_json_list(raw: Any) -> List[str]:
    if raw in (None, ""):
        return []
    try:
        data = json.loads(str(raw))
    except Exception:
        return []
    return _normalize_string_list("json_list", data)


@dataclass(frozen=True)
class FeedScopePolicy:
    workspace_id: str
    ego: str
    ingestion_mode: str
    retention_mode: str
    processing_mode: str
    allowlist_enabled: bool
    allowlist_accounts: List[str]
    allowlist_tags: List[str]
    firehose_enabled: bool
    firehose_path: Optional[str]
    updated_at: str

    def as_dict(self) -> dict:
        return {
            "workspaceId": self.workspace_id,
            "ego": self.ego,
            "ingestionMode": self.ingestion_mode,
            "retentionMode": self.retention_mode,
            "processingMode": self.processing_mode,
            "allowlistEnabled": self.allowlist_enabled,
            "allowlistAccounts": list(self.allowlist_accounts),
            "allowlistTags": list(self.allowlist_tags),
            "firehoseEnabled": self.firehose_enabled,
            "firehosePath": self.firehose_path,
            "updatedAt": self.updated_at,
        }


class FeedScopePolicyStore:
    """SQLite policy store scoped by (workspace_id, ego)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feed_scope_policy (
                    workspace_id TEXT NOT NULL,
                    ego TEXT NOT NULL,
                    ingestion_mode TEXT NOT NULL,
                    retention_mode TEXT NOT NULL,
                    processing_mode TEXT NOT NULL,
                    allowlist_enabled INTEGER NOT NULL,
                    allowlist_accounts_json TEXT NOT NULL,
                    allowlist_tags_json TEXT NOT NULL,
                    firehose_enabled INTEGER NOT NULL,
                    firehose_path TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (workspace_id, ego)
                )
                """
            )

    def _default_policy(self, *, workspace_id: str, ego: str) -> FeedScopePolicy:
        return FeedScopePolicy(
            workspace_id=workspace_id,
            ego=ego,
            ingestion_mode="open",
            retention_mode="infinite",
            processing_mode="continuous",
            allowlist_enabled=False,
            allowlist_accounts=[],
            allowlist_tags=[],
            firehose_enabled=True,
            firehose_path=None,
            updated_at=_utc_now_iso(),
        )

    def get_policy(self, *, workspace_id: str, ego: str) -> FeedScopePolicy:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT workspace_id, ego, ingestion_mode, retention_mode, processing_mode,
                       allowlist_enabled, allowlist_accounts_json, allowlist_tags_json,
                       firehose_enabled, firehose_path, updated_at
                FROM feed_scope_policy
                WHERE workspace_id = ? AND ego = ?
                """,
                (workspace_id, ego),
            ).fetchone()
        if not row:
            return self._default_policy(workspace_id=workspace_id, ego=ego)
        return FeedScopePolicy(
            workspace_id=row[0],
            ego=row[1],
            ingestion_mode=str(row[2]),
            retention_mode=str(row[3]),
            processing_mode=str(row[4]),
            allowlist_enabled=bool(row[5]),
            allowlist_accounts=_loads_json_list(row[6]),
            allowlist_tags=_loads_json_list(row[7]),
            firehose_enabled=bool(row[8]),
            firehose_path=row[9],
            updated_at=str(row[10]),
        )

    def upsert_policy(
        self,
        *,
        workspace_id: str,
        ego: str,
        ingestion_mode: Any = None,
        retention_mode: Any = None,
        processing_mode: Any = None,
        allowlist_enabled: Any = None,
        allowlist_accounts: Any = None,
        allowlist_tags: Any = None,
        firehose_enabled: Any = None,
        firehose_path: Any = None,
    ) -> FeedScopePolicy:
        current = self.get_policy(workspace_id=workspace_id, ego=ego)
        next_ingestion_mode = current.ingestion_mode
        next_retention_mode = current.retention_mode
        next_processing_mode = current.processing_mode
        next_allowlist_enabled = current.allowlist_enabled
        next_allowlist_accounts = list(current.allowlist_accounts)
        next_allowlist_tags = list(current.allowlist_tags)
        next_firehose_enabled = current.firehose_enabled
        next_firehose_path = current.firehose_path

        if ingestion_mode is not None:
            next_ingestion_mode = _normalize_mode(
                "ingestionMode", ingestion_mode, _VALID_INGESTION_MODES
            )
        if retention_mode is not None:
            next_retention_mode = _normalize_mode(
                "retentionMode", retention_mode, _VALID_RETENTION_MODES
            )
        if processing_mode is not None:
            next_processing_mode = _normalize_mode(
                "processingMode", processing_mode, _VALID_PROCESSING_MODES
            )
        if allowlist_enabled is not None:
            next_allowlist_enabled = _coerce_bool("allowlistEnabled", allowlist_enabled)
        if allowlist_accounts is not None:
            next_allowlist_accounts = _normalize_string_list(
                "allowlistAccounts", allowlist_accounts
            )
        if allowlist_tags is not None:
            next_allowlist_tags = _normalize_string_list("allowlistTags", allowlist_tags)
        if firehose_enabled is not None:
            next_firehose_enabled = _coerce_bool("firehoseEnabled", firehose_enabled)
        if firehose_path is not None:
            next_firehose_path = _normalize_firehose_path(firehose_path)

        now = _utc_now_iso()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO feed_scope_policy (
                    workspace_id, ego, ingestion_mode, retention_mode, processing_mode,
                    allowlist_enabled, allowlist_accounts_json, allowlist_tags_json,
                    firehose_enabled, firehose_path, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id, ego) DO UPDATE SET
                    ingestion_mode = excluded.ingestion_mode,
                    retention_mode = excluded.retention_mode,
                    processing_mode = excluded.processing_mode,
                    allowlist_enabled = excluded.allowlist_enabled,
                    allowlist_accounts_json = excluded.allowlist_accounts_json,
                    allowlist_tags_json = excluded.allowlist_tags_json,
                    firehose_enabled = excluded.firehose_enabled,
                    firehose_path = excluded.firehose_path,
                    updated_at = excluded.updated_at
                """,
                (
                    workspace_id,
                    ego,
                    next_ingestion_mode,
                    next_retention_mode,
                    next_processing_mode,
                    1 if next_allowlist_enabled else 0,
                    json.dumps(next_allowlist_accounts, ensure_ascii=False),
                    json.dumps(next_allowlist_tags, ensure_ascii=False),
                    1 if next_firehose_enabled else 0,
                    next_firehose_path,
                    now,
                ),
            )
        return FeedScopePolicy(
            workspace_id=workspace_id,
            ego=ego,
            ingestion_mode=next_ingestion_mode,
            retention_mode=next_retention_mode,
            processing_mode=next_processing_mode,
            allowlist_enabled=next_allowlist_enabled,
            allowlist_accounts=next_allowlist_accounts,
            allowlist_tags=next_allowlist_tags,
            firehose_enabled=next_firehose_enabled,
            firehose_path=next_firehose_path,
            updated_at=now,
        )
