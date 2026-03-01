"""Dry-run the active-learning acquisition scorer against real data.

Prints a ranked candidate table — no Selenium, no scraping.

Usage:
    .venv/bin/python3 -m scripts.dry_run_acquisition [--top-k N] [--run-id RUN_ID]
"""
from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine

from src.data.shadow_store import ShadowStore
from src.data.fetcher import CachedDataFetcher
from src.shadow.acquisition import score_candidates, AcquisitionWeights
from src.shadow.enricher import SeedAccount
from src.graph.seeds import load_seed_candidates
from src.config import get_cache_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(message)s",
)
LOGGER = logging.getLogger(__name__)


_ARCHIVE_DB_DEFAULT = ROOT / "data" / "archive_tweets.db"
_CACHE_DB_DEFAULT = ROOT / "data" / "cache.db"


def _build_seeds(cache_db_path: Path) -> list[SeedAccount]:
    """Replicate the default seed-building logic from enrich_shadow_graph.py."""
    with CachedDataFetcher(cache_db=cache_db_path) as fetcher:
        accounts = fetcher.fetch_accounts()
        id_to_username: dict[str, str] = {}
        for _, row in accounts.iterrows():
            account_id = str(row["account_id"])
            raw = row.get("username")
            id_to_username[account_id] = raw.strip().lower() if isinstance(raw, str) else ""

        username_to_id = {u: aid for aid, u in id_to_username.items() if u}

        preset_usernames = sorted(load_seed_candidates())
        archive_usernames = [
            row.get("username").lower()
            for _, row in accounts.iterrows()
            if row.get("username")
        ]
        seed_usernames = preset_usernames + [
            u for u in sorted(archive_usernames) if u not in preset_usernames
        ]

        seeds: list[SeedAccount] = []
        for uname in seed_usernames:
            norm = uname.lower()
            aid = username_to_id.get(norm, f"shadow:{norm}")
            seeds.append(SeedAccount(account_id=aid, username=norm))

    return seeds


def _lookup_usernames(community_conn: sqlite3.Connection, account_ids: list[str]) -> dict[str, str]:
    """Try to resolve account_ids to usernames via resolved_accounts or profiles table."""
    result: dict[str, str] = {}
    # Try resolved_accounts first (built by resolve_follow_targets.py)
    try:
        placeholders = ",".join("?" * len(account_ids))
        rows = community_conn.execute(
            f"SELECT account_id, username FROM resolved_accounts WHERE account_id IN ({placeholders})",
            account_ids,
        ).fetchall()
        result.update({r[0]: r[1] for r in rows if r[1]})
    except Exception:
        pass

    # Fill gaps from profiles table
    missing = [aid for aid in account_ids if aid not in result]
    if missing:
        try:
            placeholders = ",".join("?" * len(missing))
            rows = community_conn.execute(
                f"SELECT account_id, username FROM profiles WHERE account_id IN ({placeholders})",
                missing,
            ).fetchall()
            result.update({r[0]: r[1] for r in rows if r[1]})
        except Exception:
            pass

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run acquisition scorer (no scraping)")
    parser.add_argument("--top-k", type=int, default=30, help="Candidates to display (default 30)")
    parser.add_argument("--run-id", type=str, default=None, help="NMF run_id (default: latest)")
    parser.add_argument("--mmr-lambda", type=float, default=0.7, help="MMR λ (default 0.7)")
    parser.add_argument(
        "--archive-db", type=Path, default=_ARCHIVE_DB_DEFAULT,
        help=f"Path to archive_tweets.db (default: {_ARCHIVE_DB_DEFAULT})",
    )
    parser.add_argument(
        "--cache-db", type=Path, default=_CACHE_DB_DEFAULT,
        help=f"Path to cache.db (default: {_CACHE_DB_DEFAULT})",
    )
    args = parser.parse_args()

    # ── Connect to both databases ────────────────────────────────────────────
    if not args.archive_db.exists():
        LOGGER.error("archive_tweets.db not found at %s", args.archive_db)
        sys.exit(1)
    if not args.cache_db.exists():
        LOGGER.error("cache.db not found at %s", args.cache_db)
        sys.exit(1)

    community_conn = sqlite3.connect(str(args.archive_db))
    engine = create_engine(f"sqlite:///{args.cache_db}")
    shadow_store = ShadowStore(engine)

    # ── NMF run info ─────────────────────────────────────────────────────────
    run_id = args.run_id
    if run_id is None:
        row = community_conn.execute(
            "SELECT run_id, k, account_count, created_at FROM community_run ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            LOGGER.error("No NMF runs found in archive_tweets.db")
            sys.exit(1)
        run_id, k, account_count, created_at = row
        LOGGER.info("Using latest NMF run: %s  (K=%d, %d accounts, created %s)", run_id, k, account_count, created_at)
    else:
        row = community_conn.execute(
            "SELECT k, account_count, created_at FROM community_run WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            LOGGER.error("NMF run_id '%s' not found", run_id)
            sys.exit(1)
        k, account_count, created_at = row
        LOGGER.info("Using NMF run: %s  (K=%d, %d accounts, created %s)", run_id, k, account_count, created_at)

    # ── Build seed list ───────────────────────────────────────────────────────
    LOGGER.info("Building seed list from cache.db...")
    seeds = _build_seeds(args.cache_db)
    LOGGER.info("Total candidates: %d", len(seeds))

    # ── Run scorer ───────────────────────────────────────────────────────────
    LOGGER.info("Running acquisition scorer (λ_mmr=%.2f)...", args.mmr_lambda)
    ranked = score_candidates(
        seeds,
        shadow_store=shadow_store,
        community_conn=community_conn,
        run_id=run_id,
        top_k=None,   # score all; we display top_k below
        lambda_mmr=args.mmr_lambda,
    )
    community_conn.close()

    # ── Pull per-account signal detail for display ────────────────────────────
    # Re-open to fetch display data (scorer already closed conn above... reopen)
    community_conn2 = sqlite3.connect(str(args.archive_db))

    # Resolve usernames for display (seeds already have username from archive)
    seed_username_map = {s.account_id: s.username for s in seeds}

    # Fetch entropy/boundary details for top candidates
    top_ids = [s.account_id for s in ranked[:args.top_k]]
    membership_detail: dict[str, list[tuple[int, float]]] = {}
    if top_ids:
        placeholders = ",".join("?" * len(top_ids))
        rows = community_conn2.execute(
            f"SELECT account_id, community_idx, weight FROM community_membership"
            f" WHERE run_id = ? AND account_id IN ({placeholders})"
            f" ORDER BY account_id, weight DESC",
            [run_id, *top_ids],
        ).fetchall()
        for aid, cidx, w in rows:
            membership_detail.setdefault(aid, []).append((cidx, round(w, 3)))

    # Fetch scrape history counts for top candidates
    scrape_counts: dict[str, int] = {}
    if top_ids:
        placeholders = ",".join("?" * len(top_ids))
        engine2 = create_engine(f"sqlite:///{args.cache_db}")
        from sqlalchemy.sql import text as sa_text
        with engine2.connect() as conn:
            rows2 = conn.execute(
                sa_text(
                    f"SELECT seed_account_id, COUNT(*) as n"
                    f" FROM scrape_run_metrics"
                    f" WHERE seed_account_id IN ({','.join(':id'+str(i) for i in range(len(top_ids)))})"
                    f"   AND skipped = 0"
                    f" GROUP BY seed_account_id"
                ),
                {f"id{i}": aid for i, aid in enumerate(top_ids)},
            ).fetchall()
        scrape_counts = {r[0]: r[1] for r in rows2}

    community_conn2.close()

    # ── Print ranked table ────────────────────────────────────────────────────
    print()
    print("=" * 100)
    print(f"  ACQUISITION SCORER DRY-RUN  |  NMF run: {run_id}  |  K={k}  |  λ_mmr={args.mmr_lambda}")
    print("=" * 100)
    header = (
        f"{'#':>3}  {'username':<22}  {'account_id':<22}  "
        f"{'community top-2':<22}  {'scrapes':>7}  {'status':<12}"
    )
    print(header)
    print("-" * 100)

    for rank, seed in enumerate(ranked[:args.top_k], 1):
        username = seed.username or seed_username_map.get(seed.account_id, "?")
        aid = seed.account_id

        # Community membership summary
        memberships = membership_detail.get(aid, [])
        if memberships:
            top2 = memberships[:2]
            comm_str = "  ".join(f"c{cidx}:{w:.2f}" for cidx, w in top2)
            if len(memberships) > 2:
                comm_str += f" (+{len(memberships)-2})"
        else:
            comm_str = "no NMF data"

        n_scrapes = scrape_counts.get(aid, 0)
        status = "scraped" if n_scrapes > 0 else "COLD START"

        print(
            f"{rank:>3}. {username:<22}  {aid:<22}  "
            f"{comm_str:<22}  {n_scrapes:>7}  {status:<12}"
        )

    print("-" * 100)
    remaining = len(ranked) - args.top_k
    if remaining > 0:
        print(f"  ... {remaining} more candidates not shown (use --top-k to increase)")
    print(f"\n  Total ranked: {len(ranked)}  |  Showing top {min(args.top_k, len(ranked))}")
    print("=" * 100)


if __name__ == "__main__":
    main()
