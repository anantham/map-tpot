#!/usr/bin/env python3
"""
Fetch community archive data for all accounts in cache.db.

Downloads each account's archive JSON from Supabase blob storage,
parses tweets + likes + note-tweets, and stores in data/archive_tweets.db.

Raw JSON is cached in data/archive_cache/ to avoid re-downloading.

Usage:
    python scripts/fetch_archive_data.py
    python scripts/fetch_archive_data.py --limit 10          # test with first 10 accounts
    python scripts/fetch_archive_data.py --workers 5         # parallel workers (default 10)
    python scripts/fetch_archive_data.py --force             # re-download even if cached
"""

import argparse
import logging
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

# Allow running from project root or scripts/ dir
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from archive.fetcher import fetch_archive
from archive.store import log_fetch_error, log_not_found, store_archive

CACHE_DB   = ROOT / "data" / "cache.db"
ARCHIVE_DB = ROOT / "data" / "archive_tweets.db"
JSON_CACHE = ROOT / "data" / "archive_cache"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def load_accounts(limit: Optional[int] = None) -> list[tuple[str, str]]:
    """Return [(account_id, username)] from cache.db, skipping already-fetched."""
    conn = sqlite3.connect(str(CACHE_DB))
    rows = conn.execute(
        "SELECT account_id, username FROM account WHERE username IS NOT NULL AND username != ''"
    ).fetchall()
    conn.close()

    # Skip only fully-resolved accounts (ok or not_found); retry errors
    try:
        arc = sqlite3.connect(str(ARCHIVE_DB))
        done = {r[0] for r in arc.execute(
            "SELECT username FROM fetch_log WHERE status IN ('ok', 'not_found')"
        ).fetchall()}
        arc.close()
    except Exception:
        done = set()

    pending = [(aid, u) for aid, u in rows if u not in done]
    log.info(
        "Accounts: %d total, %d already resolved, %d pending",
        len(rows), len(rows) - len(pending), len(pending),
    )
    return pending[:limit] if limit else pending


def download_one(account_id: str, username: str, force: bool) -> dict:
    """Download only — no DB writes. Returns archive dict or status."""
    try:
        archive = fetch_archive(username, cache_dir=JSON_CACHE, force_refresh=force)
        if archive is None:
            return {"username": username, "account_id": account_id, "status": "not_found"}
        return {"username": username, "account_id": account_id, "status": "downloaded", "archive": archive}
    except Exception as e:
        return {"username": username, "account_id": account_id, "status": "error", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Fetch community archive data")
    parser.add_argument("--limit",   type=int, default=None, help="Max accounts to fetch")
    parser.add_argument("--workers", type=int, default=10,   help="Parallel download workers")
    parser.add_argument("--force",   action="store_true",    help="Re-download cached archives")
    args = parser.parse_args()

    accounts = load_accounts(args.limit)
    if not accounts:
        log.info("Nothing to fetch.")
        return

    JSON_CACHE.mkdir(parents=True, exist_ok=True)

    total = len(accounts)
    ok = not_found = errors = 0
    total_tweets = total_likes = 0
    done = 0

    log.info("Fetching %d accounts with %d workers (serial DB writes)...", total, args.workers)

    # Download in parallel, write to DB serially to avoid SQLite lock contention
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(download_one, aid, u, args.force): u
            for aid, u in accounts
        }
        for future in as_completed(futures):
            result = future.result()
            done += 1
            username   = result["username"]
            account_id = result["account_id"]

            if result["status"] == "downloaded":
                try:
                    counts = store_archive(ARCHIVE_DB, result["archive"], account_id, username)
                    ok += 1
                    total_tweets += counts["tweet_count"]
                    total_likes  += counts["like_count"]
                    log.info(
                        "[%d/%d] ✓ %-30s  tweets=%d  likes=%d",
                        done, total, username, counts["tweet_count"], counts["like_count"],
                    )
                except Exception as e:
                    errors += 1
                    log_fetch_error(ARCHIVE_DB, username, account_id, str(e))
                    log.warning("[%d/%d] ! %-30s  STORE ERROR: %s", done, total, username, e)

            elif result["status"] == "not_found":
                not_found += 1
                log_not_found(ARCHIVE_DB, username, account_id)
                log.info("[%d/%d] ✗ %-30s  (no archive)", done, total, username)
            else:
                errors += 1
                log_fetch_error(ARCHIVE_DB, username, account_id, result.get("error", ""))
                log.warning(
                    "[%d/%d] ! %-30s  ERROR: %s",
                    done, total, username, result.get("error", "")
                )

    print()
    print("=" * 60)
    print(f"  Done: {ok} ok | {not_found} no archive | {errors} errors")
    print(f"  Tweets stored : {total_tweets:,}")
    print(f"  Likes stored  : {total_likes:,}")
    print(f"  DB            : {ARCHIVE_DB}")
    print("=" * 60)


if __name__ == "__main__":
    main()
