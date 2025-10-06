"""CLI utility to pull fresh tables from the Supabase archive into the local cache."""
from __future__ import annotations

import argparse
import logging
from typing import Sequence

from src.data.fetcher import CachedDataFetcher


LOGGER = logging.getLogger(__name__)

TABLE_METHODS = {
    "accounts": "fetch_accounts",
    "profiles": "fetch_profiles",
    "followers": "fetch_followers",
    "following": "fetch_following",
    "tweets": "fetch_tweets",
    "likes": "fetch_likes",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh Supabase tables into the local SQLite cache",
    )
    parser.add_argument(
        "--tables",
        nargs="*",
        choices=sorted(TABLE_METHODS.keys()),
        default=sorted(TABLE_METHODS.keys()),
        help="Subset of tables to sync (default: all supported tables).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force refresh from Supabase even if cache is still fresh.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging for the fetcher.",
    )
    return parser.parse_args()


def sync_tables(tables: Sequence[str], force_refresh: bool) -> dict[str, int]:
    summary: dict[str, int] = {}
    with CachedDataFetcher() as fetcher:
        for table in tables:
            method_name = TABLE_METHODS[table]
            method = getattr(fetcher, method_name)
            LOGGER.info("Syncing %s (force=%s)", table, force_refresh)
            frame = method(force_refresh=force_refresh)
            summary[table] = len(frame)
            LOGGER.info("%s rows: %s", table, summary[table])
    return summary


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    tables = args.tables or sorted(TABLE_METHODS.keys())
    summary = sync_tables(tables, force_refresh=args.force)

    print("\nSync summary")
    print("============")
    for table in tables:
        count = summary.get(table, 0)
        print(f"{table:<10} rows={count}")


if __name__ == "__main__":
    main()
