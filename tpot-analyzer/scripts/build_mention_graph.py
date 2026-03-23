"""Build mention_graph from Supabase user_mentions table.

Fetches user_mentions with FK join to tweets (for author account_id),
aggregates into pairwise mention counts, stores in archive_tweets.db.

Features:
  - Keyset pagination (id > cursor) -- no offset degradation at millions of rows
  - Resume capability -- cursor saved after each batch, survives interrupts
  - Staging table -- edges persisted incrementally, bounded memory

A mention = "account_id mentioned mentioned_user_id in tweet tweet_id."

Usage:
    .venv/bin/python3 -m scripts.build_mention_graph                # full fetch + write
    .venv/bin/python3 -m scripts.build_mention_graph --dry-run      # fetch to staging only
    .venv/bin/python3 -m scripts.build_mention_graph --reset        # clear staging, start fresh
    .venv/bin/python3 -m scripts.build_mention_graph --aggregate-only  # just aggregate existing staging
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
CURSOR_PATH = ROOT / "data" / ".mention_cursor.json"

MENTION_GRAPH_DDL = """\
CREATE TABLE IF NOT EXISTS mention_graph (
    source_id     TEXT NOT NULL,
    target_id     TEXT NOT NULL,
    mention_count INTEGER NOT NULL,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (source_id, target_id)
);
"""

STAGING_DDL = """\
CREATE TABLE IF NOT EXISTS _mention_staging (
    sid  TEXT PRIMARY KEY,
    src  TEXT NOT NULL,
    tgt  TEXT NOT NULL
);
"""

PAGE_SIZE = 1000
MAX_RETRIES = 5
BACKOFF_BASE = 2


# ── Cursor persistence ────────────────────────────────────────────────────────

def load_cursor() -> dict | None:
    if CURSOR_PATH.exists():
        return json.loads(CURSOR_PATH.read_text())
    return None


def save_cursor(last_id: str, rows_fetched: int, edges_stored: int) -> None:
    CURSOR_PATH.write_text(json.dumps({
        "last_id": last_id,
        "rows_fetched": rows_fetched,
        "edges_stored": edges_stored,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))


def clear_cursor() -> None:
    if CURSOR_PATH.exists():
        CURSOR_PATH.unlink()


# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_page(
    client: httpx.Client,
    url: str,
    headers: dict,
    after_id: str | None,
) -> list[dict]:
    """Fetch one page using keyset pagination (id > after_id)."""
    params = {
        "select": "id,mentioned_user_id,tweets(account_id)",
        "limit": str(PAGE_SIZE),
        "order": "id.asc",
    }
    if after_id is not None:
        params["id"] = f"gt.{after_id}"

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
            print(f"  Error (attempt {attempt+1}/{MAX_RETRIES}): {exc}")
            time.sleep(wait)
    raise RuntimeError(f"Failed after {MAX_RETRIES} retries (cursor={after_id})")


def fetch_to_staging(
    db: sqlite3.Connection,
    url: str,
    headers: dict,
    limit: int,
) -> int:
    """Fetch mentions via keyset pagination into staging table.

    Resumes from cursor if available. Returns total edges in staging.
    """
    db.executescript(STAGING_DDL)

    cursor_data = load_cursor()
    if cursor_data:
        after_id = cursor_data["last_id"]
        rows_fetched = cursor_data["rows_fetched"]
        edges_stored = cursor_data["edges_stored"]
        print(f"  Resuming: id > {after_id}  ({rows_fetched:,} rows, {edges_stored:,} edges already)")
    else:
        after_id = None
        rows_fetched = 0
        edges_stored = 0

    t0 = time.time()
    resume_rows = rows_fetched

    with httpx.Client() as client:
        while rows_fetched < limit:
            page = fetch_page(client, url, headers, after_id)
            if not page:
                print(f"  End of data at {rows_fetched:,} rows.")
                break

            batch = []
            for row in page:
                tweets_data = row.get("tweets")
                if tweets_data and tweets_data.get("account_id"):
                    author_id = str(tweets_data["account_id"])
                    mentioned_id = str(row["mentioned_user_id"])
                    if author_id != mentioned_id:
                        batch.append((str(row["id"]), author_id, mentioned_id))

            if batch:
                db.executemany(
                    "INSERT OR IGNORE INTO _mention_staging (sid, src, tgt) VALUES (?, ?, ?)",
                    batch,
                )
                db.commit()
                edges_stored += len(batch)

            after_id = str(page[-1]["id"])
            rows_fetched += len(page)
            save_cursor(after_id, rows_fetched, edges_stored)

            if rows_fetched % 50000 < PAGE_SIZE:
                elapsed = time.time() - t0
                new_rows = rows_fetched - resume_rows
                rate = new_rows / elapsed if elapsed > 0 else 0
                pct = rows_fetched / limit * 100 if limit else 0
                print(f"  {rows_fetched:>10,} rows  |  {edges_stored:>10,} edges  |  "
                      f"{rate:,.0f} rows/s  |  ~{pct:.1f}%")

            if len(page) < PAGE_SIZE:
                print(f"  End of data at {rows_fetched:,} rows.")
                break

    return edges_stored


# ── Aggregate ─────────────────────────────────────────────────────────────────

def aggregate_and_write(db: sqlite3.Connection) -> int:
    """Aggregate staging table into mention_graph. Returns pair count."""
    print("Aggregating staging -> mention_graph...")

    staging_count = db.execute("SELECT COUNT(*) FROM _mention_staging").fetchone()[0]
    print(f"  Staging rows: {staging_count:,}")

    db.executescript(MENTION_GRAPH_DDL)
    db.execute("DELETE FROM mention_graph")

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO mention_graph (source_id, target_id, mention_count, created_at) "
        "SELECT src, tgt, COUNT(*), ? FROM _mention_staging GROUP BY src, tgt",
        (now,),
    )
    db.commit()

    count = db.execute("SELECT COUNT(*) FROM mention_graph").fetchone()[0]
    total = db.execute("SELECT SUM(mention_count) FROM mention_graph").fetchone()[0]
    print(f"  Written: {count:,} unique pairs, {total:,} total mentions")

    db.execute("DROP TABLE IF EXISTS _mention_staging")
    db.commit()
    clear_cursor()
    print("  Staging cleaned up, cursor cleared.")

    return count


def print_top_accounts(db: sqlite3.Connection) -> None:
    """Print top mentioned and mentioning accounts."""
    print("\nTop 10 most-mentioned:")
    for rank, (tid, cnt) in enumerate(db.execute(
        "SELECT target_id, SUM(mention_count) FROM mention_graph "
        "GROUP BY target_id ORDER BY SUM(mention_count) DESC LIMIT 10"
    ).fetchall(), 1):
        row = db.execute(
            "SELECT username FROM profiles WHERE account_id = ?", (tid,)
        ).fetchone()
        name = f"@{row[0]}" if row else tid
        print(f"  {rank:>2}. {name:<25} {cnt:>6,} mentions")

    print("\nTop 10 most-mentioning:")
    for rank, (sid, cnt) in enumerate(db.execute(
        "SELECT source_id, SUM(mention_count) FROM mention_graph "
        "GROUP BY source_id ORDER BY SUM(mention_count) DESC LIMIT 10"
    ).fetchall(), 1):
        row = db.execute(
            "SELECT username FROM profiles WHERE account_id = ?", (sid,)
        ).fetchone()
        name = f"@{row[0]}" if row else sid
        print(f"  {rank:>2}. {name:<25} {cnt:>6,} mentions sent")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Build mention graph from Supabase")
    parser.add_argument("--limit", type=int, default=12_000_000,
                        help="Max rows to fetch (default: 12M, above total ~10.6M)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch to staging only, don't aggregate into mention_graph")
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
    print("MENTION GRAPH BUILD (keyset pagination + resume)")
    print("=" * 70)

    if args.reset:
        print("Resetting staging and cursor...")
        db.execute("DROP TABLE IF EXISTS _mention_staging")
        db.commit()
        clear_cursor()
        print("  Done.\n")

    if not args.aggregate_only:
        print(f"Fetching user_mentions (limit={args.limit:,})...")
        print(f"  Supabase: {cfg.url}")
        t0 = time.time()
        edges = fetch_to_staging(db, cfg.url, cfg.rest_headers, args.limit)
        print(f"\nFetch complete: {edges:,} edges in {time.time() - t0:.1f}s")

    if args.dry_run:
        print("\nDRY RUN — staging preserved, mention_graph unchanged.")
        try:
            n = db.execute("SELECT COUNT(*) FROM _mention_staging").fetchone()[0]
            print(f"  Staging rows: {n:,}")
        except sqlite3.OperationalError:
            print("  No staging table.")
        db.close()
        return

    try:
        db.execute("SELECT COUNT(*) FROM _mention_staging").fetchone()
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
