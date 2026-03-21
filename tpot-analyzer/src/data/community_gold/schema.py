"""Schema and helper validation for account-community gold labels."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from .constants import JUDGMENT_NAMES


SCHEMA = """
CREATE TABLE IF NOT EXISTS account_community_gold_split (
    account_id TEXT PRIMARY KEY,
    split TEXT NOT NULL CHECK (split IN ('train','dev','test')),
    assigned_by TEXT NOT NULL,
    assigned_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_community_gold_label_set (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    community_id TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    judgment TEXT NOT NULL CHECK (judgment IN ('in','out','abstain')),
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
    note TEXT,
    evidence_json TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL,
    supersedes_label_set_id INTEGER,
    FOREIGN KEY (community_id) REFERENCES community(id) ON DELETE CASCADE,
    FOREIGN KEY (supersedes_label_set_id) REFERENCES account_community_gold_label_set(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_account_community_gold_active
ON account_community_gold_label_set(account_id, community_id, reviewer)
WHERE is_active = 1;

CREATE INDEX IF NOT EXISTS idx_account_community_gold_lookup
ON account_community_gold_label_set(community_id, reviewer, judgment, is_active, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_account_community_gold_account_lookup
ON account_community_gold_label_set(account_id, is_active, created_at DESC);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def split_for_account(account_id: str) -> str:
    bucket = int(hashlib.sha256(account_id.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "dev"
    return "test"


def validate_judgment(value: Any) -> str:
    parsed = str(value or "").strip().lower()
    if parsed in {"in", "positive", "pos", "yes", "true"}:
        return "in"
    if parsed in {"out", "not_in", "not-in", "negative", "neg", "no", "false"}:
        return "out"
    if parsed in {"abstain", "ambiguous", "unsure", "skip"}:
        return "abstain"
    raise ValueError(f"judgment must be one of: {', '.join(JUDGMENT_NAMES)}")


def validate_confidence(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be numeric") from exc
    if not (0.0 <= parsed <= 1.0):
        raise ValueError("confidence must be in [0, 1]")
    return parsed
