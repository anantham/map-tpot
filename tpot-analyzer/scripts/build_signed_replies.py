#!/usr/bin/env python3
"""R1-R2: Build signed reply signals from free heuristics.

Two heuristics sign the unsigned reply graph:
  R1 (author_liked): Tweet author liked the reply → positive endorsement
  R2 (mutual_follow): Mutual followers replying to each other → likely positive

Results are stored in the `signed_reply` table for later NMF integration.

Usage:
    python scripts/build_signed_replies.py
    python scripts/build_signed_replies.py --db data/archive_tweets.db
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_DB = ROOT / "data" / "archive_tweets.db"


# ── table management ─────────────────────────────────────────────────────────

def create_signed_reply_table(con):
    """Create the signed_reply table if it doesn't exist."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS signed_reply (
            replier_id  TEXT NOT NULL,
            author_id   TEXT NOT NULL,
            reply_count INTEGER NOT NULL,
            heuristic   TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            PRIMARY KEY (replier_id, author_id, heuristic)
        )
    """)
    con.commit()


def store_signed_replies(con, rows):
    """Insert or update signed reply rows.

    rows: list of (replier_id, author_id, reply_count, heuristic)
    """
    now = datetime.now(timezone.utc).isoformat()
    con.executemany(
        "INSERT OR REPLACE INTO signed_reply "
        "(replier_id, author_id, reply_count, heuristic, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [(r[0], r[1], r[2], r[3], now) for r in rows],
    )
    con.commit()


# ── R1: author-liked-reply ───────────────────────────────────────────────────

def find_author_liked_replies(con):
    """R1: Find replies where the original tweet's author liked the reply.

    Returns list of (replier_id, author_id, count).
    Self-replies are excluded.
    """
    rows = con.execute("""
        SELECT r.account_id AS replier, t_orig.account_id AS author, COUNT(*) AS cnt
        FROM tweets r
        JOIN tweets t_orig ON r.reply_to_tweet_id = t_orig.tweet_id
        JOIN likes l ON l.tweet_id = r.tweet_id AND l.liker_account_id = t_orig.account_id
        WHERE r.reply_to_tweet_id IS NOT NULL
          AND r.account_id != t_orig.account_id
        GROUP BY r.account_id, t_orig.account_id
    """).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


# ── R2: mutual-follow reply ─────────────────────────────────────────────────

def find_mutual_follow_replies(con):
    """R2: Find replies between mutual follows.

    Returns list of (replier_id, author_id, count).
    Self-replies are excluded.
    """
    rows = con.execute("""
        SELECT r.account_id AS replier, t_orig.account_id AS author, COUNT(*) AS cnt
        FROM tweets r
        JOIN tweets t_orig ON r.reply_to_tweet_id = t_orig.tweet_id
        WHERE r.reply_to_tweet_id IS NOT NULL
          AND r.account_id != t_orig.account_id
          AND EXISTS (
              SELECT 1 FROM account_following af1
              WHERE af1.account_id = r.account_id
                AND af1.following_account_id = t_orig.account_id
          )
          AND EXISTS (
              SELECT 1 FROM account_following af2
              WHERE af2.account_id = t_orig.account_id
                AND af2.following_account_id = r.account_id
          )
        GROUP BY r.account_id, t_orig.account_id
    """).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Build signed reply signals from R1/R2 heuristics",
    )
    parser.add_argument(
        "--db", type=str, default=str(DEFAULT_DB),
        help="Path to archive_tweets.db",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        sys.exit(1)

    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL")

    # Get total reply count for coverage stats
    total_replies = con.execute(
        "SELECT COUNT(*) FROM tweets WHERE reply_to_tweet_id IS NOT NULL"
    ).fetchone()[0]
    print(f"Total replies in DB: {total_replies:,}")

    # R1: author-liked-reply
    print("\nR1: Finding author-liked replies...", end=" ", flush=True)
    r1_results = find_author_liked_replies(con)
    r1_reply_count = sum(r[2] for r in r1_results)
    print(f"{len(r1_results):,} pairs, {r1_reply_count:,} replies")

    # R2: mutual-follow reply
    print("R2: Finding mutual-follow replies...", end=" ", flush=True)
    r2_results = find_mutual_follow_replies(con)
    r2_reply_count = sum(r[2] for r in r2_results)
    print(f"{len(r2_results):,} pairs, {r2_reply_count:,} replies")

    # Combine and store
    create_signed_reply_table(con)

    r1_rows = [(r[0], r[1], r[2], "author_liked") for r in r1_results]
    r2_rows = [(r[0], r[1], r[2], "mutual_follow") for r in r2_results]
    all_rows = r1_rows + r2_rows

    store_signed_replies(con, all_rows)
    print(f"\nStored {len(all_rows):,} signed reply rows in signed_reply table")

    # Coverage stats
    # Unique signed replies (union of R1 and R2 reply counts, with overlap)
    r1_pairs = {(r[0], r[1]) for r in r1_results}
    r2_pairs = {(r[0], r[1]) for r in r2_results}
    overlap_pairs = r1_pairs & r2_pairs
    unique_pairs = r1_pairs | r2_pairs

    # Total signed replies (rough: sum of both, minus overlap estimate)
    signed_total = r1_reply_count + r2_reply_count
    print(f"\n── Coverage ──────────────────────────────")
    print(f"  R1 (author-liked):   {len(r1_pairs):,} pairs, {r1_reply_count:,} replies")
    print(f"  R2 (mutual-follow):  {len(r2_pairs):,} pairs, {r2_reply_count:,} replies")
    print(f"  Overlap:             {len(overlap_pairs):,} pairs in both")
    print(f"  Union:               {len(unique_pairs):,} unique pairs")
    print(f"  Signed replies:      {signed_total:,} / {total_replies:,} total "
          f"({100*signed_total/max(total_replies,1):.1f}%)")

    con.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
