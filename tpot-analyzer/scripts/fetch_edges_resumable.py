"""Resumable edge fetcher with cursor persistence.

Saves pagination cursor to edge_fetch_state table so we never re-pay
for pages already fetched. Supports continuing from where we left off.

Usage:
    # Fetch for specific accounts (up to 10 pages each)
    .venv/bin/python3 -m scripts.fetch_edges_resumable --accounts hormeze,vgr --max-pages 10

    # Continue all incomplete accounts
    .venv/bin/python3 -m scripts.fetch_edges_resumable --continue-incomplete --max-pages 10

    # Fetch Tier 1 priority accounts
    .venv/bin/python3 -m scripts.fetch_edges_resumable --tier1 --max-pages 10
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "archive_tweets.db"
API_URL = "https://api.twitterapi.io/twitter/user/followings"


def get_api_key() -> str:
    for key in ("TWITTERAPI_IO_API_KEY", "TWITTERAPI_API_KEY", "API_KEY"):
        val = os.getenv(key)
        if val:
            return val
    raise RuntimeError("No API key found")


def fetch_followings_resumable(
    conn: sqlite3.Connection,
    api_key: str,
    account_id: str,
    username: str,
    max_pages: int = 10,
) -> int:
    """Fetch followings for one account, resuming from saved cursor.

    Returns number of NEW edges added this call.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Load saved state
    state = conn.execute(
        "SELECT last_cursor, pages_fetched, edges_stored, is_complete FROM edge_fetch_state WHERE account_id = ?",
        (account_id,),
    ).fetchone()

    if state and state[3]:  # is_complete
        return 0

    cursor = state[0] if state else None  # Resume from saved cursor
    pages_done = state[1] if state else 0
    edges_before = state[2] if state else 0

    new_edges = 0
    pages_this_run = 0

    while pages_done + pages_this_run < max_pages:
        params = {"userName": username}
        if cursor:
            params["cursor"] = cursor

        try:
            resp = httpx.get(
                API_URL,
                params=params,
                headers={"X-API-Key": api_key},
                timeout=15,
            )
        except Exception as e:
            print(f"    Error: {e}")
            break

        if resp.status_code == 402:
            print(f"    Credits exhausted (402)")
            # Save cursor so we can resume later
            _save_state(conn, account_id, username, cursor,
                       pages_done + pages_this_run, edges_before + new_edges,
                       is_complete=False, now=now)
            return new_edges

        if resp.status_code == 429:
            print(f"    Rate limited, sleeping 60s...")
            time.sleep(60)
            continue

        if resp.status_code != 200:
            print(f"    HTTP {resp.status_code}")
            break

        data = resp.json()
        users = data.get("followings", [])  # CORRECT KEY

        if not users:
            # No more data — we've reached the end
            _save_state(conn, account_id, username, cursor,
                       pages_done + pages_this_run, edges_before + new_edges,
                       is_complete=True, now=now)
            return new_edges

        for u in users:
            fid = str(u.get("id", ""))
            if fid:
                conn.execute(
                    "INSERT OR IGNORE INTO account_following (account_id, following_account_id) VALUES (?, ?)",
                    (account_id, fid),
                )
                new_edges += 1

        pages_this_run += 1

        # Save cursor after EVERY page (crash-safe)
        next_cursor = data.get("next_cursor")
        has_next = data.get("has_next_page", False)

        _save_state(conn, account_id, username, next_cursor,
                   pages_done + pages_this_run, edges_before + new_edges,
                   is_complete=not has_next, now=now)
        conn.commit()

        if not has_next or not next_cursor:
            return new_edges

        cursor = next_cursor
        time.sleep(0.3)

    # Hit max_pages limit
    _save_state(conn, account_id, username, cursor,
               pages_done + pages_this_run, edges_before + new_edges,
               is_complete=False, now=now)
    conn.commit()
    return new_edges


def _save_state(conn, account_id, username, cursor, pages, edges, is_complete, now):
    conn.execute("""
        INSERT INTO edge_fetch_state
        (account_id, username, last_cursor, pages_fetched, edges_stored, is_complete, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id) DO UPDATE SET
            last_cursor = excluded.last_cursor,
            pages_fetched = excluded.pages_fetched,
            edges_stored = excluded.edges_stored,
            is_complete = excluded.is_complete,
            updated_at = excluded.updated_at
    """, (account_id, username, cursor, pages, edges, int(is_complete), now))


def main():
    parser = argparse.ArgumentParser(description="Resumable edge fetcher")
    parser.add_argument("--accounts", type=str, help="Comma-separated usernames")
    parser.add_argument("--continue-incomplete", action="store_true",
                       help="Continue all accounts with is_complete=0")
    parser.add_argument("--max-pages", type=int, default=10,
                       help="Max total pages per account (default: 10)")
    parser.add_argument("--limit", type=int, default=100,
                       help="Max accounts to process (default: 100)")
    args = parser.parse_args()

    api_key = get_api_key()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")

    targets = []

    if args.accounts:
        for uname in args.accounts.split(","):
            uname = uname.strip()
            ra = conn.execute("SELECT account_id FROM resolved_accounts WHERE username = ?", (uname,)).fetchone()
            if not ra:
                ra = conn.execute("SELECT account_id FROM profiles WHERE username = ?", (uname,)).fetchone()
            if ra:
                targets.append((ra[0], uname))
            else:
                print(f"@{uname}: not found, skip")

    elif args.continue_incomplete:
        rows = conn.execute("""
            SELECT account_id, username FROM edge_fetch_state
            WHERE is_complete = 0 AND username IS NOT NULL
            ORDER BY edges_stored DESC
            LIMIT ?
        """, (args.limit,)).fetchall()
        targets = [(r[0], r[1]) for r in rows]

    else:
        print("Specify --accounts or --continue-incomplete")
        return

    print(f"Fetching for {len(targets)} accounts (max {args.max_pages} pages each)\n")

    total_new = 0
    for i, (aid, uname) in enumerate(targets):
        print(f"  [{i+1}/{len(targets)}] @{uname}...", end=" ", flush=True)
        new = fetch_followings_resumable(conn, api_key, aid, uname, args.max_pages)
        total_new += new

        state = conn.execute(
            "SELECT pages_fetched, edges_stored, is_complete FROM edge_fetch_state WHERE account_id = ?",
            (aid,),
        ).fetchone()
        status = "complete" if state and state[2] else f"pg={state[0]}" if state else "?"
        print(f"{new} new edges ({status})")

        if new == 0 and state and not state[2]:
            # Might be 402 — check by trying to continue
            pass

    total_graph = conn.execute("SELECT COUNT(*) FROM account_following").fetchone()[0]
    print(f"\nTotal new edges: {total_new}")
    print(f"Graph total: {total_graph}")


if __name__ == "__main__":
    main()
