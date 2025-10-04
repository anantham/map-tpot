"""Export scrape run metrics to CSV for analysis."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from sqlalchemy import select

from src.config import get_cache_settings
from src.data.shadow_store import get_shadow_store
from src.data.fetcher import CachedDataFetcher


def export_metrics_to_csv(output_path: Path) -> None:
    """Export all scrape run metrics to a CSV file."""
    cache_settings = get_cache_settings()

    with CachedDataFetcher(cache_db=cache_settings.path) as fetcher:
        store = get_shadow_store(fetcher.engine)

        # Query all metrics
        with store._engine.connect() as conn:
            stmt = select(store._metrics_table).order_by(store._metrics_table.c.run_at.desc())
            result = conn.execute(stmt)
            rows = [dict(row._mapping) for row in result]

        if not rows:
            print("No metrics found in database.")
            return

        # Convert coverage values back to percentages
        for row in rows:
            if row["following_coverage"] is not None:
                row["following_coverage"] = round(row["following_coverage"] / 100, 2)
            if row["followers_coverage"] is not None:
                row["followers_coverage"] = round(row["followers_coverage"] / 100, 2)
            if row["followers_you_follow_coverage"] is not None:
                row["followers_you_follow_coverage"] = round(row["followers_you_follow_coverage"] / 100, 2)

        # Write to CSV
        fieldnames = [
            "id",
            "seed_account_id",
            "seed_username",
            "run_at",
            "duration_seconds",
            "following_captured",
            "followers_captured",
            "followers_you_follow_captured",
            "following_claimed_total",
            "followers_claimed_total",
            "followers_you_follow_claimed_total",
            "following_coverage",
            "followers_coverage",
            "followers_you_follow_coverage",
            "accounts_upserted",
            "edges_upserted",
            "discoveries_upserted",
            "skipped",
            "skip_reason",
        ]

        with output_path.open("w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"Exported {len(rows)} metrics records to {output_path}")


if __name__ == "__main__":
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/scrape_metrics.csv")
    export_metrics_to_csv(output)
