"""Summarize enrichment pipeline metrics from scrape_run_metrics table."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, select

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data.shadow_store import ShadowStore


def summarize_metrics(days: int = 7, db_path: str = "data/cache.db"):
    """Summarize enrichment metrics from the last N days."""
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    store = ShadowStore(engine)

    # Calculate date cutoff
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Query metrics
    with engine.connect() as conn:
        stmt = (
            select(store._metrics_table)
            .where(store._metrics_table.c.run_at >= cutoff)
            .order_by(store._metrics_table.c.run_at.desc())
        )
        result = conn.execute(stmt)
        rows = [dict(row._mapping) for row in result]

    if not rows:
        print(f"No enrichment runs found in the last {days} days.")
        return

    # Aggregate metrics
    total_seeds = len(rows)
    succeeded = sum(1 for r in rows if not r["skipped"] and r["edges_upserted"] > 0 and r["error_type"] is None)
    skipped = sum(1 for r in rows if r["skipped"])
    errored = sum(1 for r in rows if r["error_type"] is not None)

    total_accounts = sum(r["accounts_upserted"] for r in rows if not r["skipped"])
    total_edges = sum(r["edges_upserted"] for r in rows if not r["skipped"])
    total_duration = sum(r["duration_seconds"] for r in rows if not r["skipped"])

    # Calculate averages
    successful_runs = [r for r in rows if not r["skipped"] and r["error_type"] is None]
    avg_duration = total_duration / len(successful_runs) if successful_runs else 0
    avg_accounts = total_accounts / len(successful_runs) if successful_runs else 0
    avg_edges = total_edges / len(successful_runs) if successful_runs else 0

    # Calculate coverage
    coverage_values = [
        r["following_coverage"] / 10000.0
        for r in rows
        if r["following_coverage"] is not None and not r["skipped"]
    ]
    avg_coverage = sum(coverage_values) / len(coverage_values) if coverage_values else 0

    # Error breakdown
    error_types = Counter(r["error_type"] for r in rows if r["error_type"] is not None)

    # Skip reasons
    skip_reasons = Counter(r["skip_reason"] for r in rows if r["skipped"] and r["skip_reason"])

    # Performance metrics
    accounts_per_minute = (total_accounts / total_duration * 60) if total_duration > 0 else 0

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"Enrichment Summary (Last {days} Days)")
    print(f"{'=' * 60}\n")

    print(f"Total Seeds: {total_seeds}")
    print(f"  Success: {succeeded} ({succeeded/total_seeds*100:.1f}%)")
    print(f"  Skipped: {skipped} ({skipped/total_seeds*100:.1f}%)")
    print(f"  Errors: {errored} ({errored/total_seeds*100:.1f}%)\n")

    if error_types:
        print("Error Breakdown:")
        for error_type, count in error_types.most_common():
            print(f"  {error_type}: {count}")
        print()

    if skip_reasons:
        print("Skip Reasons:")
        for reason, count in list(skip_reasons.most_common())[:5]:
            truncated = (reason[:47] + '...') if len(reason) > 50 else reason
            print(f"  {truncated}: {count}")
        print()

    print("Performance:")
    print(f"  Avg Duration: {avg_duration:.1f}s per seed")
    print(f"  Avg Accounts Captured: {avg_accounts:.1f}")
    print(f"  Avg Edges Captured: {avg_edges:.1f}")
    print(f"  Avg Coverage: {avg_coverage*100:.1f}%")
    print(f"  Rate: {accounts_per_minute:.1f} accounts/minute\n")

    print(f"Totals:")
    print(f"  Accounts: {total_accounts:,}")
    print(f"  Edges: {total_edges:,}")
    print(f"  Duration: {total_duration/3600:.1f}h\n")

    # Recent failures
    recent_errors = [r for r in rows if r["error_type"] is not None][:5]
    if recent_errors:
        print("Recent Errors:")
        for r in recent_errors:
            error_details = (r["error_details"] or "")[:60]
            print(f"  @{r['seed_username']}: {r['error_type']} - {error_details}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Summarize enrichment pipeline metrics"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to summarize (default: 7)",
    )
    parser.add_argument(
        "--db",
        default="data/cache.db",
        help="Path to cache database (default: data/cache.db)",
    )

    args = parser.parse_args()
    summarize_metrics(days=args.days, db_path=args.db)


if __name__ == "__main__":
    main()
