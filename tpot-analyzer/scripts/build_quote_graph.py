"""Build quote_graph from Supabase quote_tweets table.

Fetches quote_tweets with FK join to tweets (for quoter account_id),
then batch-resolves quoted_tweet_id → account_id, aggregates into
pairwise quote counts, stores in archive_tweets.db.

A quote = "the author of tweet_id quoted the author of quoted_tweet_id."

Usage:
    .venv/bin/python3 -m scripts.build_quote_graph
    .venv/bin/python3 -m scripts.build_quote_graph --limit 50000
    .venv/bin/python3 -m scripts.build_quote_graph --dry-run
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
CREATE TABLE IF NOT EXISTS quote_graph (
    source_id   TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    quote_count INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (source_id, target_id)
);
"""

PAGE_SIZE = 1000
TWEET_BATCH_SIZE = 200  # Supabase IN filter batch size
MAX_RETRIES = 5
BACKOFF_BASE = 2  # seconds


def _request_with_retry(
    client: httpx.Client,
    url: str,
    params: dict,
    headers: dict,
    label: str = "",
) -> httpx.Response:
    """GET with exponential backoff retry on rate-limit or transport errors."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(url, params=params, headers=headers, timeout=60)
            if resp.status_code == 429:
                wait = BACKOFF_BASE * (2 ** attempt)
                print(f"  Rate limited ({label}), sleeping {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            wait = BACKOFF_BASE * (2 ** attempt)
            print(f"  Request error ({label}, attempt {attempt+1}/{MAX_RETRIES}): {exc}")
            print(f"  Retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError(f"Failed after {MAX_RETRIES} retries ({label})")


def fetch_quote_tweets(
    client: httpx.Client,
    url: str,
    headers: dict,
    limit: int,
) -> list[dict]:
    """Fetch quote_tweets with FK join for quoter's account_id.

    Returns list of dicts: {quoter_account_id, quoted_tweet_id}
    """
    rows: list[dict] = []
    offset = 0
    t0 = time.time()

    while offset < limit:
        page_size = min(PAGE_SIZE, limit - offset)
        params = {
            "select": "tweet_id,quoted_tweet_id,tweets(account_id)",
            "limit": str(page_size),
            "offset": str(offset),
            "order": "tweet_id.asc",
        }
        resp = _request_with_retry(
            client, f"{url}/rest/v1/quote_tweets", params, headers,
            label=f"quote_tweets offset={offset}",
        )
        page = resp.json()
        if not page:
            print(f"  No more rows at offset {offset}. Total fetched: {len(rows):,}")
            break

        for row in page:
            tweets_data = row.get("tweets")
            if tweets_data and tweets_data.get("account_id"):
                rows.append({
                    "quoter_account_id": str(tweets_data["account_id"]),
                    "quoted_tweet_id": str(row["quoted_tweet_id"]),
                })

        offset += len(page)

        if offset % 10000 < PAGE_SIZE:
            elapsed = time.time() - t0
            rate = offset / elapsed if elapsed > 0 else 0
            print(f"  Fetched {offset:>9,} rows  |  {len(rows):>9,} usable  |  {rate:,.0f} rows/s")

        if len(page) < PAGE_SIZE:
            print(f"  End of data at offset {offset}. Total fetched: {len(rows):,}")
            break

    return rows


def resolve_tweet_authors(
    client: httpx.Client,
    url: str,
    headers: dict,
    tweet_ids: list[str],
) -> dict[str, str]:
    """Batch-resolve tweet_id → account_id via Supabase tweets table.

    Returns {tweet_id: account_id} mapping.
    """
    result: dict[str, str] = {}
    total = len(tweet_ids)
    t0 = time.time()

    for i in range(0, total, TWEET_BATCH_SIZE):
        batch = tweet_ids[i : i + TWEET_BATCH_SIZE]
        # Supabase IN filter: tweet_id=in.(id1,id2,...)
        in_filter = f"in.({','.join(batch)})"
        params = {
            "select": "tweet_id,account_id",
            "tweet_id": in_filter,
        }
        resp = _request_with_retry(
            client, f"{url}/rest/v1/tweets", params, headers,
            label=f"tweets batch {i//TWEET_BATCH_SIZE + 1}",
        )
        for row in resp.json():
            result[str(row["tweet_id"])] = str(row["account_id"])

        resolved = len(result)
        if (i + TWEET_BATCH_SIZE) % 10000 < TWEET_BATCH_SIZE:
            elapsed = time.time() - t0
            rate = (i + len(batch)) / elapsed if elapsed > 0 else 0
            print(f"  Resolved {resolved:>9,} / {total:>9,} tweet authors  |  {rate:,.0f} tweets/s")

    return result


def build_quote_graph(db_path: Path, limit: int, dry_run: bool) -> None:
    cfg = get_supabase_config()
    headers = cfg.rest_headers

    print(f"Fetching quote_tweets (limit={limit:,}) from Supabase...")
    print(f"  URL: {cfg.url}")
    t_start = time.time()

    with httpx.Client() as client:
        # Phase 1: Fetch quote_tweets with quoter's account_id
        raw_quotes = fetch_quote_tweets(client, cfg.url, headers, limit)
        print(f"\nPhase 1 complete: {len(raw_quotes):,} quote rows with quoter account_id")

        # Phase 2: Resolve quoted tweet authors
        quoted_tweet_ids = list({r["quoted_tweet_id"] for r in raw_quotes})
        print(f"\nResolving {len(quoted_tweet_ids):,} unique quoted tweet authors...")
        quoted_authors = resolve_tweet_authors(
            client, cfg.url, headers, quoted_tweet_ids
        )
        resolved = len(quoted_authors)
        print(f"Resolved {resolved:,} / {len(quoted_tweet_ids):,} quoted tweet authors")

    elapsed = time.time() - t_start
    print(f"\nFetch complete in {elapsed:.1f}s")

    # Aggregate into pairwise counts
    pair_counts: Counter[tuple[str, str]] = Counter()
    unresolved = 0
    for row in raw_quotes:
        quoter = row["quoter_account_id"]
        quoted_author = quoted_authors.get(row["quoted_tweet_id"])
        if not quoted_author:
            unresolved += 1
            continue
        if quoter != quoted_author:  # exclude self-quotes
            pair_counts[(quoter, quoted_author)] += 1

    total_quotes = sum(pair_counts.values())
    unique_pairs = len(pair_counts)
    print(f"Aggregated: {unique_pairs:,} unique pairs, {total_quotes:,} total quotes")
    if unresolved:
        print(f"  ({unresolved:,} quotes unresolved — quoted tweet not in archive)")

    # Top 10 most-quoted (by incoming quote count)
    target_counts: Counter[str] = Counter()
    for (_, tgt), cnt in pair_counts.items():
        target_counts[tgt] += cnt

    conn = sqlite3.connect(str(db_path))

    print(f"\nTop 10 most-quoted accounts (by total incoming quotes):")
    for rank, (target_id, cnt) in enumerate(target_counts.most_common(10), 1):
        row = conn.execute(
            "SELECT username FROM profiles WHERE account_id = ?", (target_id,)
        ).fetchone()
        name = f"@{row[0]}" if row else target_id
        print(f"  {rank:>2}. {name:<25} {cnt:>6,} quotes received")

    # Top 10 most-quoting (by outgoing quote count)
    source_counts: Counter[str] = Counter()
    for (src, _), cnt in pair_counts.items():
        source_counts[src] += cnt

    print(f"\nTop 10 most-quoting accounts (by total outgoing quotes):")
    for rank, (source_id, cnt) in enumerate(source_counts.most_common(10), 1):
        row = conn.execute(
            "SELECT username FROM profiles WHERE account_id = ?", (source_id,)
        ).fetchone()
        name = f"@{row[0]}" if row else source_id
        print(f"  {rank:>2}. {name:<25} {cnt:>6,} quotes sent")

    if dry_run:
        print("\nDRY RUN — no changes written to database.")
        conn.close()
        return

    # Write to DB
    now = datetime.now(timezone.utc).isoformat()
    print(f"\nWriting {unique_pairs:,} rows to quote_graph...")

    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM quote_graph")  # clear previous data

    batch = [
        (src, tgt, cnt, now)
        for (src, tgt), cnt in pair_counts.items()
    ]
    conn.executemany(
        "INSERT INTO quote_graph (source_id, target_id, quote_count, created_at) "
        "VALUES (?, ?, ?, ?)",
        batch,
    )
    conn.commit()

    written = conn.execute("SELECT COUNT(*) FROM quote_graph").fetchone()[0]
    total = conn.execute("SELECT SUM(quote_count) FROM quote_graph").fetchone()[0]
    print(f"Written: {written:,} rows, {total:,} total quotes")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build quote graph from Supabase quote_tweets"
    )
    parser.add_argument(
        "--limit", type=int, default=2_000_000,
        help="Max rows to fetch (default: 2000000)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing DB")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    args = parser.parse_args()

    build_quote_graph(args.db_path, args.limit, args.dry_run)
