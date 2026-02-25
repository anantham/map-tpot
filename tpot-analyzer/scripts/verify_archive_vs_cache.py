#!/usr/bin/env python3
"""
Data quality comparison: archive_tweets.db vs cache.db

Answers:
  1. Which accounts fetched successfully? Which have no archive?
  2. For accounts with data in both: do tweet IDs overlap?
     - Tweets in cache.db NOT in archive (scraped but not uploaded by user)
     - Tweets in archive NOT in cache.db (user uploaded but we never scraped)
  3. Are account-reported tweet counts (cache.db account.num_tweets) consistent
     with actual archive tweet counts?

Usage:
    python scripts/verify_archive_vs_cache.py
    python scripts/verify_archive_vs_cache.py --account eigenrobot
"""

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CACHE_DB   = ROOT / "data" / "cache.db"
ARCHIVE_DB = ROOT / "data" / "archive_tweets.db"


def pct(n, total):
    return f"{100*n/total:.0f}%" if total else "n/a"


def check_fetch_coverage():
    arc = sqlite3.connect(str(ARCHIVE_DB))
    rows = arc.execute("SELECT status, COUNT(*) FROM fetch_log GROUP BY status").fetchall()
    arc.close()

    print("\n── Fetch coverage ─────────────────────────────────────────")
    total = sum(r[1] for r in rows)
    for status, count in sorted(rows):
        print(f"  {status:<12} {count:>5}  ({pct(count, total)})")
    print(f"  {'TOTAL':<12} {total:>5}")


def check_tweet_counts():
    cache = sqlite3.connect(str(CACHE_DB))
    arc   = sqlite3.connect(str(ARCHIVE_DB))

    cache_counts = dict(cache.execute(
        "SELECT account_id, num_tweets FROM account"
    ).fetchall())

    archive_counts = dict(arc.execute(
        "SELECT account_id, COUNT(*) FROM tweets GROUP BY account_id"
    ).fetchall())

    cache.close()
    arc.close()

    print("\n── Tweet count comparison (cache.db reported vs archive actual) ─")
    print(f"  {'username':<25} {'reported':>10}  {'archive':>10}  {'diff':>8}")
    print(f"  {'-'*25} {'-'*10}  {'-'*10}  {'-'*8}")

    big_gaps = []
    for account_id, reported in sorted(cache_counts.items(), key=lambda x: -x[1]):
        actual = archive_counts.get(account_id, 0)
        diff = actual - reported
        if reported > 100:  # skip low-tweet accounts
            big_gaps.append((account_id, reported, actual, diff))

    big_gaps.sort(key=lambda x: abs(x[3]), reverse=True)
    for account_id, reported, actual, diff in big_gaps[:20]:
        flag = "  ← large gap" if abs(diff) > 1000 else ""
        print(f"  {account_id:<25} {reported:>10,}  {actual:>10,}  {diff:>+8,}{flag}")

    if len(big_gaps) > 20:
        print(f"  ... and {len(big_gaps)-20} more accounts")


def check_tweet_overlap(account_filter=None):
    cache = sqlite3.connect(str(CACHE_DB))
    arc   = sqlite3.connect(str(ARCHIVE_DB))

    if account_filter:
        # Resolve username → account_id
        row = cache.execute(
            "SELECT account_id FROM account WHERE username=?", (account_filter,)
        ).fetchone()
        if not row:
            print(f"\n  Account '{account_filter}' not found in cache.db")
            cache.close(); arc.close()
            return
        account_ids = [row[0]]
        print(f"\n── Tweet overlap for @{account_filter} ─────────────────────────────")
    else:
        account_ids = [r[0] for r in cache.execute(
            "SELECT DISTINCT account_id FROM tweets"
        ).fetchall()]
        print(f"\n── Tweet overlap (all {len(account_ids)} accounts with cached tweets) ──")

    only_in_cache = only_in_archive = in_both = 0

    for account_id in account_ids:
        cache_ids = {r[0] for r in cache.execute(
            "SELECT tweet_id FROM tweets WHERE account_id=?", (account_id,)
        ).fetchall()}
        archive_ids = {r[0] for r in arc.execute(
            "SELECT tweet_id FROM tweets WHERE account_id=?", (account_id,)
        ).fetchall()}

        in_both        += len(cache_ids & archive_ids)
        only_in_cache  += len(cache_ids - archive_ids)
        only_in_archive += len(archive_ids - cache_ids)

        if account_filter:
            print(f"  cache.db tweets    : {len(cache_ids):,}")
            print(f"  archive tweets     : {len(archive_ids):,}")
            print(f"  in both            : {len(cache_ids & archive_ids):,}  ({pct(len(cache_ids & archive_ids), len(cache_ids | archive_ids))} overlap)")
            print(f"  only in cache.db   : {len(cache_ids - archive_ids):,}  (scraped but not uploaded)")
            print(f"  only in archive    : {len(archive_ids - cache_ids):,}  (uploaded but not scraped)")

            if cache_ids - archive_ids:
                print(f"\n  Sample tweets only in cache.db:")
                for tid in list(cache_ids - archive_ids)[:3]:
                    text = cache.execute(
                        "SELECT full_text FROM tweets WHERE tweet_id=?", (tid,)
                    ).fetchone()
                    print(f"    [{tid}] {text[0][:80] if text else '?'}...")

    if not account_filter:
        total = in_both + only_in_cache + only_in_archive
        print(f"  In both            : {in_both:,}")
        print(f"  Only in cache.db   : {only_in_cache:,}  (scraped but not in archive)")
        print(f"  Only in archive    : {only_in_archive:,}  (archive but not scraped)")
        print(f"  Cache overlap rate : {pct(in_both, in_both + only_in_cache)}")

    cache.close()
    arc.close()


def summary_stats():
    arc = sqlite3.connect(str(ARCHIVE_DB))
    tweet_total = arc.execute("SELECT COUNT(*) FROM tweets").fetchone()[0]
    like_total  = arc.execute("SELECT COUNT(*) FROM likes").fetchone()[0]
    accounts    = arc.execute("SELECT COUNT(DISTINCT account_id) FROM tweets").fetchone()[0]
    note_tweets = arc.execute("SELECT COUNT(*) FROM tweets WHERE is_note_tweet=1").fetchone()[0]
    arc.close()

    print("\n── Archive DB summary ──────────────────────────────────────")
    print(f"  Accounts with tweets : {accounts:,}")
    print(f"  Total tweets         : {tweet_total:,}")
    print(f"  Note-tweets          : {note_tweets:,}")
    print(f"  Total likes          : {like_total:,}")


def main():
    parser = argparse.ArgumentParser(description="Verify archive vs cache data quality")
    parser.add_argument("--account", type=str, default=None,
                        help="Focus on a specific account (username)")
    args = parser.parse_args()

    if not ARCHIVE_DB.exists():
        print("archive_tweets.db not found. Run fetch_archive_data.py first.")
        sys.exit(1)

    summary_stats()
    check_fetch_coverage()
    check_tweet_counts()
    check_tweet_overlap(args.account)

    print("\n── Next steps ──────────────────────────────────────────────")
    print("  • Run with --account <username> for per-account overlap detail")
    print("  • Large gaps in tweet counts → account has old tweets pre-dating archive upload")
    print("  • Tweets only in cache.db → scraped from timeline but user didn't upload archive")
    print("  • archive_tweets.db is the authoritative source for classification")
    print()


if __name__ == "__main__":
    main()
