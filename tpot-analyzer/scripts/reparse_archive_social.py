#!/usr/bin/env python3
"""
Re-parse cached archive JSONs to extract profiles, following, followers, and retweet metadata.

Reads from data/archive_cache/*.json (already downloaded, no network calls).
Stores into archive_tweets.db using INSERT OR IGNORE — safe to run multiple times.

Usage:
    python scripts/reparse_archive_social.py
    python scripts/reparse_archive_social.py --limit 10   # test with first 10
    python scripts/reparse_archive_social.py --verbose     # print every account
"""

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from archive.store import store_archive

CACHE_DIR  = ROOT / "data" / "archive_cache"
ARCHIVE_DB = ROOT / "data" / "archive_tweets.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def get_account_id_from_archive(archive: dict) -> str:
    """Pull accountId from the archive's own account section (more reliable than cache.db lookup)."""
    account_items = archive.get("account", [])
    if account_items:
        return account_items[0].get("account", {}).get("accountId", "")
    return ""


def main():
    parser = argparse.ArgumentParser(description="Re-parse cached archives for social graph data")
    parser.add_argument("--limit",   type=int,  default=None, help="Max archives to process")
    parser.add_argument("--verbose", action="store_true",     help="Print every account, not just every 10th")
    args = parser.parse_args()

    jsons = sorted(CACHE_DIR.glob("*.json"))
    if args.limit:
        jsons = jsons[: args.limit]

    log.info("Processing %d cached archives from %s", len(jsons), CACHE_DIR)

    totals = dict(tweet_count=0, like_count=0, following_count=0, follower_count=0, retweet_count=0)
    ok = errors = 0

    for i, path in enumerate(jsons, 1):
        # Derive username from filename (strip .json)
        username = path.stem

        try:
            with open(path) as f:
                archive = json.load(f)

            account_id = get_account_id_from_archive(archive)
            counts = store_archive(ARCHIVE_DB, archive, account_id, username)

            for k in totals:
                totals[k] += counts.get(k, 0)
            ok += 1

            if args.verbose or i % 10 == 0 or i == len(jsons):
                log.info(
                    "[%d/%d] %-28s  following=%d  followers=%d  rts=%d  bio=%s",
                    i, len(jsons), username,
                    counts.get("following_count", 0),
                    counts.get("follower_count", 0),
                    counts.get("retweet_count", 0),
                    "✓" if counts.get("following_count", 0) > 0 else "—",
                )

        except Exception as e:
            errors += 1
            log.warning("[%d/%d] ! %-28s  ERROR: %s", i, len(jsons), username, e)

    print()
    print("=" * 60)
    print(f"  Archives processed : {ok}  ({errors} errors)")
    print(f"  Profiles stored    : {ok}")
    print(f"  Following edges    : {totals['following_count']:,}")
    print(f"  Follower edges     : {totals['follower_count']:,}")
    print(f"  Retweet records    : {totals['retweet_count']:,}")
    print(f"  DB                 : {ARCHIVE_DB}")
    print("=" * 60)
    print()
    print("Next: run scripts/verify_social_graph.py to inspect what was stored")


if __name__ == "__main__":
    main()
