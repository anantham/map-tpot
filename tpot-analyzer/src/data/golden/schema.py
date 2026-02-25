"""Schema and helper math for golden curation."""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from typing import Any, Dict

from .constants import SIMULACRUM_LABELS


SCHEMA = """
CREATE TABLE IF NOT EXISTS curation_split (
    tweet_id TEXT PRIMARY KEY,
    axis TEXT NOT NULL,
    split TEXT NOT NULL CHECK (split IN ('train','dev','test')),
    assigned_by TEXT NOT NULL,
    assigned_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tweet_label_set (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,
    axis TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    note TEXT,
    context_hash TEXT,
    context_snapshot_json TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL,
    supersedes_label_set_id INTEGER,
    FOREIGN KEY(supersedes_label_set_id) REFERENCES tweet_label_set(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_active_label_unique
ON tweet_label_set(tweet_id, axis, reviewer) WHERE is_active = 1;

CREATE TABLE IF NOT EXISTS tweet_label_prob (
    label_set_id INTEGER NOT NULL,
    label TEXT NOT NULL CHECK (label IN ('l1','l2','l3','l4')),
    probability REAL NOT NULL CHECK (probability >= 0.0 AND probability <= 1.0),
    PRIMARY KEY (label_set_id, label),
    FOREIGN KEY(label_set_id) REFERENCES tweet_label_set(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS model_prediction_set (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,
    axis TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT,
    prompt_version TEXT NOT NULL,
    run_id TEXT NOT NULL,
    context_hash TEXT,
    entropy REAL,
    disagreement REAL,
    queue_score REAL,
    parse_status TEXT NOT NULL,
    raw_response_json TEXT,
    predicted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_prediction_prob (
    prediction_set_id INTEGER NOT NULL,
    label TEXT NOT NULL CHECK (label IN ('l1','l2','l3','l4')),
    probability REAL NOT NULL CHECK (probability >= 0.0 AND probability <= 1.0),
    PRIMARY KEY (prediction_set_id, label),
    FOREIGN KEY(prediction_set_id) REFERENCES model_prediction_set(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS uncertainty_queue (
    tweet_id TEXT NOT NULL,
    axis TEXT NOT NULL,
    latest_prediction_set_id INTEGER NOT NULL,
    entropy REAL NOT NULL,
    disagreement REAL NOT NULL,
    queue_score REAL NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','in_review','resolved','skipped')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tweet_id, axis),
    FOREIGN KEY(latest_prediction_set_id) REFERENCES model_prediction_set(id)
);

CREATE TABLE IF NOT EXISTS evaluation_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    axis TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT,
    prompt_version TEXT NOT NULL,
    split TEXT NOT NULL CHECK (split IN ('train','dev','test')),
    brier_score REAL NOT NULL,
    threshold REAL NOT NULL,
    passed INTEGER NOT NULL CHECK (passed IN (0,1)),
    sample_size INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_curation_split_axis_split ON curation_split(axis, split);
CREATE INDEX IF NOT EXISTS idx_label_set_lookup ON tweet_label_set(tweet_id, axis, reviewer, is_active);
CREATE INDEX IF NOT EXISTS idx_prediction_lookup ON model_prediction_set(tweet_id, axis, model_name, prompt_version);
CREATE INDEX IF NOT EXISTS idx_queue_axis_status ON uncertainty_queue(axis, status, queue_score DESC);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def split_for_tweet(tweet_id: str) -> str:
    bucket = int(hashlib.sha256(tweet_id.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "dev"
    return "test"


def normalized_entropy(distribution: Dict[str, float]) -> float:
    entropy = 0.0
    for prob in distribution.values():
        if prob > 0.0:
            entropy -= prob * math.log(prob)
    max_entropy = math.log(len(SIMULACRUM_LABELS))
    return max(0.0, min(1.0, entropy / max_entropy)) if max_entropy > 0 else 0.0


def total_variation_distance(left: Dict[str, float], right: Dict[str, float]) -> float:
    return 0.5 * sum(abs(left[label] - right[label]) for label in SIMULACRUM_LABELS)


def validate_distribution(distribution: Dict[str, Any]) -> Dict[str, float]:
    if not isinstance(distribution, dict):
        raise ValueError("distribution must be an object with keys l1,l2,l3,l4")
    extras = sorted(set(distribution.keys()) - set(SIMULACRUM_LABELS))
    missing = sorted(set(SIMULACRUM_LABELS) - set(distribution.keys()))
    if extras:
        raise ValueError(f"distribution has unknown labels: {extras}")
    if missing:
        raise ValueError(f"distribution missing labels: {missing}")

    parsed: Dict[str, float] = {}
    for label in SIMULACRUM_LABELS:
        try:
            prob = float(distribution[label])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"distribution[{label}] must be numeric") from exc
        if prob < 0.0 or prob > 1.0:
            raise ValueError(f"distribution[{label}] must be in [0, 1]")
        parsed[label] = prob

    total = sum(parsed.values())
    if abs(total - 1.0) > 0.001:
        raise ValueError(f"distribution must sum to 1.0 (got {total:.6f})")
    return parsed
