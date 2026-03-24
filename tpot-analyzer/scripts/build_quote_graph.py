"""Build quote_graph from Supabase quote_tweets table.

Fetches quote_tweets with FK join to tweets (for quoter account_id),
then batch-resolves quoted_tweet_id -> account_id, aggregates into
pairwise quote counts, stores in archive_tweets.db.

Features:
  - Keyset pagination (tweet_id > cursor) -- no offset degradation at high rows
  - Resume capability -- cursor saved after each batch, survives interrupts
  - Staging table -- edges persisted incrementally, bounded memory

A quote = "the author of tweet_id quoted the author of quoted_tweet_id."

Usage:
    .venv/bin/python3 -m scripts.build_quote_graph                  # full fetch + write
    .venv/bin/python3 -m scripts.build_quote_graph --dry-run        # fetch to staging only
    .venv/bin/python3 -m scripts.build_quote_graph --reset          # clear staging, start fresh
    .venv/bin/python3 -m scripts.build_quote_graph --aggregate-only # just aggregate existing staging
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import get_supabase_config

DB_PATH = ROOT / "data" / "archive_tweets.db"
CURSOR_PATH = ROOT / "data" / ".quote_cursor.json"

QUOTE_GRAPH_DDL = """\
CREATE TABLE IF NOT EXISTS quote_graph (
    source_id   TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    quote_count INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (source_id, target_id)
);
"""

STAGING_DDL = """\
CREATE TABLE IF NOT EXISTS _quote_staging (
    tweet_id          TEXT PRIMARY KEY,
    quoter_account_id TEXT NOT NULL,
    quoted_tweet_id   TEXT NOT NULL
);
"""

PAGE_SIZE = 1000
TWEET_BATCH_SIZE = 200
MAX_RETRIES = 5
BACKOFF_BASE = 2


# -- Cursor persistence -------------------------------------------------------

def load_cursor() -> dict | None:
    if CURSOR_PATH.exists():
        return json.loads(CURSOR_PATH.read_text())
    return None


def save_cursor(last_tweet_id: str, rows_fetched: int, rows_staged: int) -> None:
    CURSOR_PATH.write_text(json.dumps({
        "last_tweet_id": last_tweet_id,
        "rows_fetched": rows_fetched,
        "rows_staged": rows_staged,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))


def clear_cursor() -> None:
    if CURSOR_PATH.exists():
        CURSOR_PATH.unlink()


# -- HTTP helper ---------------------------------------------------------------

def _request_with_retry(
    client: httpx.Client,
    url: str,
    params: dict,
    headers: dict,
    label: str = "",
) -> httpx.Response:
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
            print(f"  Error ({label}, attempt {attempt+1}/{MAX_RETRIES}): {exc}")
            time.sleep(wait)
    raise RuntimeError(f"Failed after {MAX_RETRIES} retries ({label})")


# -- Phase 1: Fetch quote_tweets to staging -----------------------------------

def fetch_page(
    client: httpx.Client,
    url: str,
    headers: dict,
    after_tweet_id: str | None,
) -> list[dict]:
    """Fetch one page using keyset pagination (tweet_id > after_tweet_id)."""
    params = {
        "select": "tweet_id,quoted_tweet_id,tweets(account_id)",
        "limit": str(PAGE_SIZE),
        "order": "tweet_id.asc",
    }
    if after_tweet_id is not None:
        params["tweet_id"] = f"gt.{after_tweet_id}"

    resp = _request_with_retry(
        client, f"{url}/rest/v1/quote_tweets", params, headers,
        label=f"quote_tweets after={after_tweet_id}",
    )
    return resp.json()


def fetch_to_staging(
    db: sqlite3.Connection,
    url: str,
    headers: dict,
    limit: int,
) -> int:
    """Fetch quote_tweets via keyset pagination into staging table.

    Resumes from cursor if available. Returns total rows in staging.
    """
    db.executescript(STAGING_DDL)

    cursor_data = load_cursor()
    if cursor_data:
        after_tweet_id = cursor_data["last_tweet_id"]
        rows_fetched = cursor_data["rows_fetched"]
        rows_staged = cursor_data["rows_staged"]
        print(f"  Resuming: tweet_id > {after_tweet_id}  ({rows_fetched:,} rows, {rows_staged:,} staged)")
    else:
        after_tweet_id = None
        rows_fetched = 0
        rows_staged = 0

    t0 = time.time()
    resume_rows = rows_fetched

    with httpx.Client() as client:
        while rows_fetched < limit:
            page = fetch_page(client, url, headers, after_tweet_id)
            if not page:
                print(f"  End of data at {rows_fetched:,} rows.")
                break

            batch = []
            for row in page:
                tweets_data = row.get("tweets")
                if tweets_data and tweets_data.get("account_id"):
                    batch.append((
                        str(row["tweet_id"]),
                        str(tweets_data["account_id"]),
                        str(row["quoted_tweet_id"]),
                    ))

            if batch:
                db.executemany(
                    "INSERT OR IGNORE INTO _quote_staging "
                    "(tweet_id, quoter_account_id, quoted_tweet_id) VALUES (?, ?, ?)",
                    batch,
                )
                db.commit()
                rows_staged += len(batch)

            after_tweet_id = str(page[-1]["tweet_id"])
            rows_fetched += len(page)
            save_cursor(after_tweet_id, rows_fetched, rows_staged)

            if rows_fetched % 50000 < PAGE_SIZE:
                elapsed = time.time() - t0
                new_rows = rows_fetched - resume_rows
                rate = new_rows / elapsed if elapsed > 0 else 0
                pct = rows_fetched / limit * 100 if limit else 0
                print(f"  {rows_fetched:>10,} rows  |  {rows_staged:>10,} staged  |  "
                      f"{rate:,.0f} rows/s  |  ~{pct:.1f}%")

            if len(page) < PAGE_SIZE:
                print(f"  End of data at {rows_fetched:,} rows.")
                break

    return rows_staged


# -- Phase 2: Resolve quoted tweet authors ------------------------------------

def resolve_quoted_authors(
    db: sqlite3.Connection,
    url: str,
    headers: dict,
) -> int:
    """Batch-resolve quoted_tweet_id -> account_id, store in resolved column.

    Uses a separate resolution table to avoid re-resolving on resume.
    """
    db.execute("""\
        CREATE TABLE IF NOT EXISTS _quote_tweet_authors (
            tweet_id   TEXT PRIMARY KEY,
            account_id TEXT NOT NULL
        )
    """)
    db.commit()

    # Find unresolved quoted_tweet_ids
    unresolved = [r[0] for r in db.execute("""
        SELECT DISTINCT qs.quoted_tweet_id
        FROM _quote_staging qs
        LEFT JOIN _quote_tweet_authors qa ON qa.tweet_id = qs.quoted_tweet_id
        WHERE qa.tweet_id IS NULL
    """).fetchall()]

    if not unresolved:
        total = db.execute("SELECT COUNT(*) FROM _quote_tweet_authors").fetchone()[0]
        print(f"  All quoted tweets already resolved ({total:,} cached).")
        return total

    print(f"  Resolving {len(unresolved):,} quoted tweet authors...")
    t0 = time.time()
    resolved_count = 0
    total = len(unresolved)
    n_batches = (total + TWEET_BATCH_SIZE - 1) // TWEET_BATCH_SIZE

    with httpx.Client() as client:
        for i in range(0, total, TWEET_BATCH_SIZE):
            batch = unresolved[i : i + TWEET_BATCH_SIZE]
            in_filter = f"in.({','.join(batch)})"
            params = {
                "select": "tweet_id,account_id",
                "tweet_id": in_filter,
            }
            resp = _request_with_retry(
                client, f"{url}/rest/v1/tweets", params, headers,
                label=f"tweets batch {i // TWEET_BATCH_SIZE + 1}/{n_batches}",
            )
            rows = [(str(r["tweet_id"]), str(r["account_id"])) for r in resp.json()]
            if rows:
                db.executemany(
                    "INSERT OR IGNORE INTO _quote_tweet_authors (tweet_id, account_id) "
                    "VALUES (?, ?)",
                    rows,
                )
                db.commit()
                resolved_count += len(rows)

            batch_num = i // TWEET_BATCH_SIZE + 1
            if batch_num % 100 == 0 or batch_num == n_batches:
                elapsed = time.time() - t0
                rate = (i + len(batch)) / elapsed if elapsed > 0 else 0
                print(f"    {resolved_count:>9,} / {total:>9,} resolved  |  {rate:,.0f} tweets/s")

    total_resolved = db.execute("SELECT COUNT(*) FROM _quote_tweet_authors").fetchone()[0]
    print(f"  Resolved {total_resolved:,} quoted tweet authors total.")
    return total_resolved


# -- Aggregate -----------------------------------------------------------------

def aggregate_and_write(db: sqlite3.Connection) -> int:
    """Aggregate staging + resolved authors into quote_graph. Returns pair count."""
    print("Aggregating staging -> quote_graph...")

    staging_count = db.execute("SELECT COUNT(*) FROM _quote_staging").fetchone()[0]
    author_count = db.execute("SELECT COUNT(*) FROM _quote_tweet_authors").fetchone()[0]
    print(f"  Staging rows: {staging_count:,}")
    print(f"  Resolved authors: {author_count:,}")

    db.executescript(QUOTE_GRAPH_DDL)
    db.execute("DELETE FROM quote_graph")

    now = datetime.now(timezone.utc).isoformat()
    db.execute("""
        INSERT INTO quote_graph (source_id, target_id, quote_count, created_at)
        SELECT qs.quoter_account_id, qa.account_id, COUNT(*), ?
        FROM _quote_staging qs
        JOIN _quote_tweet_authors qa ON qa.tweet_id = qs.quoted_tweet_id
        WHERE qs.quoter_account_id != qa.account_id
        GROUP BY qs.quoter_account_id, qa.account_id
    """, (now,))
    db.commit()

    count = db.execute("SELECT COUNT(*) FROM quote_graph").fetchone()[0]
    total = db.execute("SELECT SUM(quote_count) FROM quote_graph").fetchone()[0] or 0
    unresolved = db.execute("""
        SELECT COUNT(*) FROM _quote_staging qs
        LEFT JOIN _quote_tweet_authors qa ON qa.tweet_id = qs.quoted_tweet_id
        WHERE qa.tweet_id IS NULL
    """).fetchone()[0]
    print(f"  Written: {count:,} unique pairs, {total:,} total quotes")
    if unresolved:
        print(f"  ({unresolved:,} quotes unresolved -- quoted tweet not in archive)")

    # Cleanup
    db.execute("DROP TABLE IF EXISTS _quote_staging")
    db.execute("DROP TABLE IF EXISTS _quote_tweet_authors")
    db.commit()
    clear_cursor()
    print("  Staging cleaned up, cursor cleared.")

    return count


def print_top_accounts(db: sqlite3.Connection) -> None:
    """Print top quoted and quoting accounts."""
    print("\nTop 10 most-quoted:")
    for rank, (tid, cnt) in enumerate(db.execute(
        "SELECT target_id, SUM(quote_count) FROM quote_graph "
        "GROUP BY target_id ORDER BY SUM(quote_count) DESC LIMIT 10"
    ).fetchall(), 1):
        row = db.execute(
            "SELECT username FROM profiles WHERE account_id = ?", (tid,)
        ).fetchone()
        name = f"@{row[0]}" if row else tid
        print(f"  {rank:>2}. {name:<25} {cnt:>6,} quotes received")

    print("\nTop 10 most-quoting:")
    for rank, (sid, cnt) in enumerate(db.execute(
        "SELECT source_id, SUM(quote_count) FROM quote_graph "
        "GROUP BY source_id ORDER BY SUM(quote_count) DESC LIMIT 10"
    ).fetchall(), 1):
        row = db.execute(
            "SELECT username FROM profiles WHERE account_id = ?", (sid,)
        ).fetchone()
        name = f"@{row[0]}" if row else sid
        print(f"  {rank:>2}. {name:<25} {cnt:>6,} quotes sent")


# -- Main ----------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Build quote graph from Supabase")
    parser.add_argument("--limit", type=int, default=2_000_000,
                        help="Max rows to fetch (default: 2M)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch to staging only, don't aggregate into quote_graph")
    parser.add_argument("--reset", action="store_true",
                        help="Clear staging + cursor, start fresh")
    parser.add_argument("--aggregate-only", action="store_true",
                        help="Skip fetch, aggregate existing staging data")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    args = parser.parse_args()

    cfg = get_supabase_config()
    db = sqlite3.connect(str(args.db_path))
    db.execute("PRAGMA journal_mode=WAL")

    print("=" * 70)
    print("QUOTE GRAPH BUILD (keyset pagination + resume)")
    print("=" * 70)

    if args.reset:
        print("Resetting staging and cursor...")
        db.execute("DROP TABLE IF EXISTS _quote_staging")
        db.execute("DROP TABLE IF EXISTS _quote_tweet_authors")
        db.commit()
        clear_cursor()
        print("  Done.\n")

    if not args.aggregate_only:
        # Phase 1: Fetch quote_tweets
        print(f"Phase 1: Fetching quote_tweets (limit={args.limit:,})...")
        print(f"  Supabase: {cfg.url}")
        t0 = time.time()
        staged = fetch_to_staging(db, cfg.url, cfg.rest_headers, args.limit)
        print(f"\nPhase 1 complete: {staged:,} rows staged in {time.time() - t0:.1f}s")

        # Phase 2: Resolve quoted tweet authors
        print(f"\nPhase 2: Resolving quoted tweet authors...")
        t0 = time.time()
        resolve_quoted_authors(db, cfg.url, cfg.rest_headers)
        print(f"Phase 2 complete in {time.time() - t0:.1f}s")

    if args.dry_run:
        print("\nDRY RUN -- staging preserved, quote_graph unchanged.")
        try:
            n = db.execute("SELECT COUNT(*) FROM _quote_staging").fetchone()[0]
            print(f"  Staging rows: {n:,}")
        except sqlite3.OperationalError:
            print("  No staging table.")
        db.close()
        return

    try:
        db.execute("SELECT COUNT(*) FROM _quote_staging").fetchone()
    except sqlite3.OperationalError:
        print("No staging table found. Run fetch first (without --aggregate-only).")
        db.close()
        return

    aggregate_and_write(db)
    print_top_accounts(db)
    db.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
