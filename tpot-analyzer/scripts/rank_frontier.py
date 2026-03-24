#!/usr/bin/env python3
"""Rank frontier + bridge accounts by information value for API enrichment.

Scores accounts by how much we'd learn from enriching them (fetching their
full profile, tweets, likes). The formula balances model uncertainty,
graph degree, and "none" weight.

Formula:
    info_value = uncertainty * sqrt(degree) * (1 - none_weight)

    - uncertainty:   model is unsure -> learning opportunity
    - sqrt(degree):  enough connections to matter (sqrt dampens hubs)
    - (1 - none_weight): high "none" accounts are less interesting

tpot_directory_holdout accounts are EXCLUDED from enrichment entirely.
They are the validation set; enriching them would contaminate recall metrics.
Cat 2 holdout accounts (directory-only, not archive) must never be enriched
before the final recall evaluation.

Usage:
    .venv/bin/python3 -m scripts.rank_frontier --top 100
    .venv/bin/python3 -m scripts.rank_frontier --top 50 --dry-run
    .venv/bin/python3 -m scripts.rank_frontier --db-path data/archive_tweets.db
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

# ── Schema ───────────────────────────────────────────────────────────────────

FRONTIER_RANKING_DDL = """\
CREATE TABLE IF NOT EXISTS frontier_ranking (
    account_id   TEXT PRIMARY KEY,
    band         TEXT NOT NULL,
    info_value   REAL NOT NULL,
    top_community TEXT,
    top_weight   REAL,
    degree       INTEGER,
    in_holdout   INTEGER DEFAULT 0,
    created_at   TEXT NOT NULL
);
"""


def load_propagation(npz_path: Path) -> dict:
    """Load community_propagation.npz.

    NOTE: allow_pickle=True is required because numpy's npz format uses
    pickle internally for object/string arrays. This file is our own cached
    propagation output, not untrusted external data.
    """
    data = np.load(str(npz_path), allow_pickle=True)  # own cached data, safe
    return {
        "memberships": data["memberships"],
        "uncertainty": data["uncertainty"],
        "node_ids": data["node_ids"],
        "community_names": data["community_names"],
    }


def load_band_data(conn: sqlite3.Connection) -> dict:
    """Load account_band table into dict keyed by account_id."""
    cur = conn.cursor()
    cur.execute("SELECT account_id, band, top_community, top_weight, degree FROM account_band")
    result = {}
    for row in cur:
        result[row[0]] = {
            "band": row[1],
            "top_community": row[2],
            "top_weight": row[3],
            "degree": row[4],
        }
    return result


def load_holdout_ids(conn: sqlite3.Connection) -> set:
    """Load account_ids from tpot_directory_holdout."""
    cur = conn.cursor()
    cur.execute("SELECT account_id FROM tpot_directory_holdout WHERE account_id IS NOT NULL")
    return {row[0] for row in cur}


def build_username_cache(conn: sqlite3.Connection, account_ids: list[str]) -> dict:
    """Batch-resolve account_ids to usernames."""
    cache = {}
    cur = conn.cursor()

    # Load all profiles
    cur.execute("SELECT account_id, username FROM profiles")
    for row in cur:
        cache[row[0]] = row[1]

    # Load all resolved_accounts (shadows), don't overwrite profiles
    cur.execute("SELECT account_id, username FROM resolved_accounts WHERE username IS NOT NULL AND username != ''")
    for row in cur:
        if row[0] not in cache:
            cache[row[0]] = row[1]

    return cache


def compute_rankings(
    prop: dict,
    band_data: dict,
    holdout_ids: set,
) -> list[dict]:
    """Compute info_value for frontier + bridge accounts.

    Returns list of dicts sorted by info_value descending.
    """
    node_ids = prop["node_ids"]
    uncertainty = prop["uncertainty"]
    none_weight = prop["memberships"][:, -1]
    comm_weights = prop["memberships"][:, :15]
    community_names = prop["community_names"]

    results = []
    for i in range(len(node_ids)):
        nid = str(node_ids[i])
        bd = band_data.get(nid)
        if bd is None:
            continue
        if bd["band"] not in ("frontier", "bridge"):
            continue

        degree = bd["degree"] or 0
        in_holdout = nid in holdout_ids
        if in_holdout:
            continue  # never enrich holdout accounts — protects recall metric integrity
        none_w = float(none_weight[i])
        unc = float(uncertainty[i])

        info_value = unc * math.sqrt(max(degree, 1)) * (1.0 - none_w)

        top_idx = int(comm_weights[i].argmax())
        results.append({
            "account_id": nid,
            "band": bd["band"],
            "info_value": info_value,
            "top_community": str(community_names[top_idx]),
            "top_weight": float(comm_weights[i, top_idx]),
            "degree": degree,
            "in_holdout": 0,  # always 0 — holdout accounts are excluded above
        })

    results.sort(key=lambda r: r["info_value"], reverse=True)
    return results


def write_table(conn: sqlite3.Connection, rankings: list[dict]) -> int:
    """Write frontier_ranking table. Returns row count."""
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS frontier_ranking")
    cur.execute(FRONTIER_RANKING_DDL)

    now = datetime.now(timezone.utc).isoformat()
    rows = [
        (
            r["account_id"],
            r["band"],
            r["info_value"],
            r["top_community"],
            r["top_weight"],
            r["degree"],
            r["in_holdout"],
            now,
        )
        for r in rankings
    ]

    cur.executemany(
        "INSERT INTO frontier_ranking "
        "(account_id, band, info_value, top_community, top_weight, degree, in_holdout, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def print_rankings(rankings: list[dict], username_cache: dict, top_n: int) -> None:
    """Print formatted ranking table."""
    display = rankings[:top_n]
    if not display:
        print("No frontier/bridge accounts to rank.")
        return

    print(f"\nTop {min(top_n, len(display))} frontier/bridge accounts by info_value:\n")
    print(f"{'#':>4}  {'Username':20s}  {'Band':12s}  {'Info Value':>10}  {'Top Community':30s}  {'Weight':>7}  {'Degree':>6}  {'Holdout':>7}")
    print("-" * 105)

    for rank, r in enumerate(display, 1):
        username = username_cache.get(r["account_id"], r["account_id"])
        holdout_marker = "YES" if r["in_holdout"] else ""
        print(
            f"{rank:>4}  {username:20s}  {r['band']:12s}  {r['info_value']:10.2f}  "
            f"{r['top_community']:30s}  {r['top_weight']:7.3f}  {r['degree']:>6}  {holdout_marker:>7}"
        )

    # Summary stats
    bands = {}
    for r in display:
        bands[r["band"]] = bands.get(r["band"], 0) + 1
    print(f"\n  Total ranked: {len(rankings):,}")
    print(f"  Note: tpot_directory_holdout accounts excluded (validation integrity)")
    print(f"  Band split (top {top_n}): {bands}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank frontier/bridge accounts by information value.")
    parser.add_argument("--top", type=int, default=100, help="Number of top accounts to display")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="Path to archive_tweets.db")
    parser.add_argument("--npz-path", type=Path, default=DEFAULT_NPZ_PATH, help="Path to community_propagation.npz")
    parser.add_argument("--dry-run", action="store_true", help="Print rankings without writing to DB")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # 1. Load data
    logger.info("Loading propagation data from %s", args.npz_path)
    prop = load_propagation(args.npz_path)

    conn = sqlite3.connect(str(args.db_path))
    try:
        logger.info("Loading account_band table...")
        band_data = load_band_data(conn)
        if not band_data:
            logger.error("account_band table is empty. Run classify_bands first.")
            return

        logger.info("Loading holdout IDs...")
        holdout_ids = load_holdout_ids(conn)
        logger.info("Holdout accounts with IDs: %d", len(holdout_ids))

        # 2. Compute rankings
        logger.info("Computing info_value rankings...")
        rankings = compute_rankings(prop, band_data, holdout_ids)
        logger.info("Ranked %d frontier/bridge accounts", len(rankings))

        # 3. Resolve usernames for display
        top_ids = [r["account_id"] for r in rankings[:args.top]]
        username_cache = build_username_cache(conn, top_ids)

        # 4. Print
        print_rankings(rankings, username_cache, args.top)

        # 5. Write to DB
        if args.dry_run:
            logger.info("Dry run -- skipping DB write")
        else:
            n_written = write_table(conn, rankings)
            logger.info("Wrote %d rows to frontier_ranking", n_written)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
