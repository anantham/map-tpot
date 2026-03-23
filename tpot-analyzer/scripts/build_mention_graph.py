"""Build mention_graph from Supabase user_mentions table.

Fetches user_mentions with FK join to tweets (for author account_id),
aggregates into pairwise mention counts, stores in archive_tweets.db.

A mention = "account_id mentioned mentioned_user_id in tweet tweet_id."

Usage:
    .venv/bin/python3 -m scripts.build_mention_graph
    .venv/bin/python3 -m scripts.build_mention_graph --limit 50000
    .venv/bin/python3 -m scripts.build_mention_graph --dry-run
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import get_supabase_config

DB_PATH = ROOT / "data" / "archive_tweets.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS mention_graph (
    source_id     TEXT NOT NULL,
    target_id     TEXT NOT NULL,
    mention_count INTEGER NOT NULL,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (source_id, target_id)
);
"""

PAGE_SIZE = 1000
MAX_RETRIES = 5
BACKOFF_BASE = 2  # seconds


def fetch_page(
    client: httpx.Client,
    url: str,
    headers: dict,
    offset: int,
    limit: int,
) -> list[dict]:
    """Fetch one page of user_mentions with FK join to tweets."""
    params = {
        "select": "mentioned_user_id,tweets(account_id)",
        "limit": str(min(PAGE_SIZE, limit - offset)),
        "offset": str(offset),
        "order": "id.asc",
    }
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(
                f"{url}/rest/v1/user_mentions",
                params=params,
                headers=headers,
                timeout=60,
            )
            if resp.status_code == 429:
                wait = BACKOFF_BASE * (2 ** attempt)
                print(f"  Rate limited, sleeping {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            wait = BACKOFF_BASE * (2 ** attempt)
            print(f"  Request error (attempt {attempt+1}/{MAX_RETRIES}): {exc}")
            print(f"  Retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError(f"Failed after {MAX_RETRIES} retries at offset {offset}")


def fetch_all_mentions(
    url: str,
    headers: dict,
    limit: int,
) -> list[tuple[str, str]]:
    """Fetch mentions and return list of (author_account_id, mentioned_user_id)."""
    edges: list[tuple[str, str]] = []
    offset = 0
    t0 = time.time()

    with httpx.Client() as client:
        while offset < limit:
            page = fetch_page(client, url, headers, offset, limit)
            if not page:
                print(f"  No more rows at offset {offset}. Total fetched: {len(edges):,}")
                break

            for row in page:
                tweets_data = row.get("tweets")
                if tweets_data and tweets_data.get("account_id"):
                    author_id = tweets_data["account_id"]
                    mentioned_id = row["mentioned_user_id"]
                    if author_id != mentioned_id:  # exclude self-mentions
                        edges.append((str(author_id), str(mentioned_id)))

            offset += len(page)

            if offset % 10000 < PAGE_SIZE:
                elapsed = time.time() - t0
                rate = offset / elapsed if elapsed > 0 else 0
                print(f"  Fetched {offset:>9,} rows  |  {len(edges):>9,} edges  |  {rate:,.0f} rows/s")

            if len(page) < PAGE_SIZE:
                print(f"  End of data at offset {offset}. Total fetched: {len(edges):,}")
                break

    return edges


def build_mention_graph(db_path: Path, limit: int, dry_run: bool) -> None:
    cfg = get_supabase_config()
    headers = cfg.rest_headers

    print(f"Fetching user_mentions (limit={limit:,}) from Supabase...")
    print(f"  URL: {cfg.url}")
    t_start = time.time()

    edges = fetch_all_mentions(cfg.url, headers, limit)

    elapsed = time.time() - t_start
    print(f"\nFetch complete: {len(edges):,} edges in {elapsed:.1f}s")

    # Aggregate into pairwise counts
    pair_counts: Counter[tuple[str, str]] = Counter()
    for src, tgt in edges:
        pair_counts[(src, tgt)] += 1

    total_mentions = sum(pair_counts.values())
    unique_pairs = len(pair_counts)
    print(f"Aggregated: {unique_pairs:,} unique pairs, {total_mentions:,} total mentions")

    # Top 10 most-mentioned (by incoming mention count)
    target_counts: Counter[str] = Counter()
    for (_, tgt), cnt in pair_counts.items():
        target_counts[tgt] += cnt

    print(f"\nTop 10 most-mentioned accounts (by total incoming mentions):")
    conn = sqlite3.connect(str(db_path))
    for rank, (target_id, cnt) in enumerate(target_counts.most_common(10), 1):
        row = conn.execute(
            "SELECT username FROM profiles WHERE account_id = ?", (target_id,)
        ).fetchone()
        name = f"@{row[0]}" if row else target_id
        print(f"  {rank:>2}. {name:<25} {cnt:>6,} mentions")

    # Top 10 most-mentioning (by outgoing mention count)
    source_counts: Counter[str] = Counter()
    for (src, _), cnt in pair_counts.items():
        source_counts[src] += cnt

    print(f"\nTop 10 most-mentioning accounts (by total outgoing mentions):")
    for rank, (source_id, cnt) in enumerate(source_counts.most_common(10), 1):
        row = conn.execute(
            "SELECT username FROM profiles WHERE account_id = ?", (source_id,)
        ).fetchone()
        name = f"@{row[0]}" if row else source_id
        print(f"  {rank:>2}. {name:<25} {cnt:>6,} mentions sent")

    if dry_run:
        print("\nDRY RUN — no changes written to database.")
        conn.close()
        return

    # Write to DB
    now = datetime.now(timezone.utc).isoformat()
    print(f"\nWriting {unique_pairs:,} rows to mention_graph...")

    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM mention_graph")  # clear previous data

    batch = [
        (src, tgt, cnt, now)
        for (src, tgt), cnt in pair_counts.items()
    ]
    conn.executemany(
        "INSERT INTO mention_graph (source_id, target_id, mention_count, created_at) "
        "VALUES (?, ?, ?, ?)",
        batch,
    )
    conn.commit()

    written = conn.execute("SELECT COUNT(*) FROM mention_graph").fetchone()[0]
    total = conn.execute("SELECT SUM(mention_count) FROM mention_graph").fetchone()[0]
    print(f"Written: {written:,} rows, {total:,} total mentions")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build mention graph from Supabase user_mentions"
    )
    parser.add_argument(
        "--limit", type=int, default=100_000,
        help="Max rows to fetch (default: 100000)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing DB")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    args = parser.parse_args()

    build_mention_graph(args.db_path, args.limit, args.dry_run)
