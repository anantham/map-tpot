#!/usr/bin/env python3
"""Four-band classification: exemplar / specialist / bridge / frontier / unknown.

Reads community_propagation.npz and classifies every account into one of
four meaningful bands (plus unknown) based on membership vector shape.

Band definitions (applied in priority order, highest wins):

  exemplar   — seed accounts with human curation (labeled_mask = True)
  specialist — max community weight >= 0.30, normalized entropy < 0.70
  bridge     — 2+ communities >= 0.15, none_weight < 0.40
  frontier   — max community weight >= 0.08 (some signal, but uncertain)
  unknown    — abstained OR max weight < 0.08 (no meaningful signal)

Usage:
    .venv/bin/python3 -m scripts.classify_bands
    .venv/bin/python3 -m scripts.classify_bands --db-path data/archive_tweets.db
    .venv/bin/python3 -m scripts.classify_bands --dry-run
"""

from __future__ import annotations

import argparse
import logging
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from src.config import DEFAULT_ARCHIVE_DB

DEFAULT_DB_PATH = DEFAULT_ARCHIVE_DB
DEFAULT_NPZ_PATH = ROOT / "data" / "community_propagation.npz"

# ── Band thresholds ──────────────────────────────────────────────────────────

SPECIALIST_MIN_WEIGHT = 0.30
SPECIALIST_MAX_ENTROPY = 0.70
BRIDGE_MIN_WEIGHT = 0.15
BRIDGE_MIN_COMMUNITIES = 2
BRIDGE_MAX_NONE = 0.40
FRONTIER_MIN_WEIGHT = 0.08


# ── Schema ───────────────────────────────────────────────────────────────────

ACCOUNT_BAND_DDL = """\
CREATE TABLE IF NOT EXISTS account_band (
    account_id  TEXT PRIMARY KEY,
    band        TEXT NOT NULL CHECK (band IN ('exemplar', 'specialist', 'bridge', 'frontier', 'unknown')),
    top_community TEXT,
    top_weight  REAL,
    entropy     REAL,
    none_weight REAL,
    degree      INTEGER,
    created_at  TEXT NOT NULL
);
"""


def load_propagation(npz_path: Path) -> dict:
    """Load community_propagation.npz and return a dict of arrays.

    NOTE: allow_pickle=True is required because numpy's npz format uses
    pickle for object arrays (string arrays). This file is our own cached
    propagation output, not untrusted external data.
    """
    data = np.load(str(npz_path), allow_pickle=True)
    required = {"memberships", "abstain_mask", "labeled_mask", "node_ids", "community_names"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"NPZ missing keys: {missing}")

    return {
        "memberships": data["memberships"],       # (N, 16) — 15 communities + none
        "abstain_mask": data["abstain_mask"],      # (N,) bool
        "labeled_mask": data["labeled_mask"],      # (N,) bool
        "node_ids": data["node_ids"],              # (N,) str
        "community_names": data["community_names"],  # (15,) str
        "uncertainty": data.get("uncertainty", np.zeros(len(data["node_ids"]))),
    }


def compute_normalized_entropy(community_weights: np.ndarray) -> np.ndarray:
    """Compute normalized entropy H/log(K) for each row over K community columns.

    Only considers the 15 community columns (not the none column).
    Clips to avoid log(0). Returns array of shape (N,).
    """
    K = community_weights.shape[1]
    # Clip small values to avoid log(0)
    p = np.clip(community_weights, 1e-12, None)
    log_p = np.log(p)
    # Zero out contributions from near-zero entries
    mask = community_weights > 1e-10
    h = -np.sum(np.where(mask, p * log_p, 0.0), axis=1)
    return h / math.log(K)


def classify_bands(prop: dict) -> dict:
    """Classify every account into one of 5 bands.

    Returns dict with arrays: band, top_community_idx, top_weight, entropy, none_weight.
    """
    N = len(prop["node_ids"])
    comm_weights = prop["memberships"][:, :15]   # (N, 15) community columns
    none_weight = prop["memberships"][:, -1]      # (N,) none column
    labeled = prop["labeled_mask"]
    abstain = prop["abstain_mask"]

    max_weight = comm_weights.max(axis=1)
    top_idx = comm_weights.argmax(axis=1)
    entropy = compute_normalized_entropy(comm_weights)
    n_above_bridge = (comm_weights >= BRIDGE_MIN_WEIGHT).sum(axis=1)

    # Start with unknown, then apply bands in ascending priority
    band = np.full(N, "unknown", dtype="U12")

    # Frontier: not abstain, max >= 0.08
    frontier_mask = ~abstain & (max_weight >= FRONTIER_MIN_WEIGHT) & ~labeled
    band[frontier_mask] = "frontier"

    # Bridge: 2+ communities >= 0.15, none < 0.40 (overrides frontier)
    bridge_mask = ~labeled & ~abstain & (n_above_bridge >= BRIDGE_MIN_COMMUNITIES) & (none_weight < BRIDGE_MAX_NONE)
    band[bridge_mask] = "bridge"

    # Specialist: max >= 0.30, entropy < 0.70 (overrides bridge/frontier)
    specialist_mask = ~labeled & ~abstain & (max_weight >= SPECIALIST_MIN_WEIGHT) & (entropy < SPECIALIST_MAX_ENTROPY)
    band[specialist_mask] = "specialist"

    # Exemplar: seed accounts (always wins)
    band[labeled] = "exemplar"

    return {
        "band": band,
        "top_community_idx": top_idx,
        "top_weight": max_weight,
        "entropy": entropy,
        "none_weight": none_weight,
    }


def fetch_degrees(conn: sqlite3.Connection, node_ids: np.ndarray) -> np.ndarray:
    """Count incoming follow edges (followers) for each node_id.

    Uses account_following.following_account_id to count how many accounts
    follow each node.
    """
    N = len(node_ids)
    degrees = np.zeros(N, dtype=np.int32)

    # Build lookup: account_id -> index
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

    cur = conn.cursor()
    cur.execute(
        "SELECT following_account_id, COUNT(*) "
        "FROM account_following "
        "GROUP BY following_account_id"
    )
    for row in cur:
        idx = id_to_idx.get(row[0])
        if idx is not None:
            degrees[idx] = row[1]

    logger.info("Degrees loaded: %d accounts have degree > 0", (degrees > 0).sum())
    return degrees


def write_table(
    conn: sqlite3.Connection,
    prop: dict,
    classification: dict,
    degrees: np.ndarray,
    community_names: np.ndarray,
) -> int:
    """Write account_band table. Returns row count."""
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS account_band")
    cur.execute(ACCOUNT_BAND_DDL)

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for i in range(len(prop["node_ids"])):
        top_comm_name = str(community_names[classification["top_community_idx"][i]])
        rows.append((
            str(prop["node_ids"][i]),
            str(classification["band"][i]),
            top_comm_name,
            float(classification["top_weight"][i]),
            float(classification["entropy"][i]),
            float(classification["none_weight"][i]),
            int(degrees[i]),
            now,
        ))

    cur.executemany(
        "INSERT INTO account_band (account_id, band, top_community, top_weight, entropy, none_weight, degree, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def print_summary(classification: dict) -> None:
    """Print band distribution summary."""
    bands = classification["band"]
    unique, counts = np.unique(bands, return_counts=True)
    band_counts = dict(zip(unique, counts))

    print("\nBand distribution:")
    for band_name in ["exemplar", "specialist", "bridge", "frontier", "unknown"]:
        count = band_counts.get(band_name, 0)
        print(f"  {band_name:12s}: {count:>8,}")
    print(f"  {'total':12s}: {len(bands):>8,}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Four-band classification of propagated community memberships.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="Path to archive_tweets.db")
    parser.add_argument("--npz-path", type=Path, default=DEFAULT_NPZ_PATH, help="Path to community_propagation.npz")
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing to DB")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # 1. Load propagation results
    logger.info("Loading %s", args.npz_path)
    prop = load_propagation(args.npz_path)
    N = len(prop["node_ids"])
    logger.info("Loaded %d accounts, %d communities", N, len(prop["community_names"]))

    # 2. Classify bands
    classification = classify_bands(prop)
    print_summary(classification)

    if args.dry_run:
        logger.info("Dry run -- skipping DB write")
        return

    # 3. Fetch degrees and write to DB
    conn = sqlite3.connect(str(args.db_path))
    try:
        logger.info("Fetching degrees from account_following...")
        degrees = fetch_degrees(conn, prop["node_ids"])
        logger.info("Writing account_band table...")
        n_written = write_table(conn, prop, classification, degrees, prop["community_names"])
        logger.info("Wrote %d rows to account_band", n_written)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
