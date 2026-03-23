"""Fetch following lists for top-ranked frontier accounts via twitterapi.io.

Adds outbound edges to the follow graph for shadow accounts, transforming
them from dead-end leaves into connected nodes. Each following list adds
~500 edges on average — 50 accounts = ~25K new edges.

Respects cross-validation discipline: NEVER fetches for holdout accounts.

Usage:
    .venv/bin/python3 -m scripts.fetch_following_for_frontier --top 50
    .venv/bin/python3 -m scripts.fetch_following_for_frontier --top 10 --dry-run
    .venv/bin/python3 -m scripts.fetch_following_for_frontier --budget 2.50
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

DB_PATH = Path(__file__).parent.parent / "data" / "archive_tweets.db"
BASE_URL = "https://api.twitterapi.io/twitter"
COST_PER_CALL = 0.05  # estimated $/call for following list

# API key resolution (same candidates as shadow_subset_audit)
KEY_ENV_CANDIDATES = (
    "TWITTERAPI_IO_API_KEY", "TWITTERAPI_API_KEY", "TWITTERAPIIO_API_KEY",
    "TWITTERAPI_KEY", "API_KEY", "X_API_KEY",
)


def get_api_key() -> str:
    for key_name in KEY_ENV_CANDIDATES:
        val = os.getenv(key_name)
        if val:
            return val
    raise RuntimeError("No twitterapi.io API key found in environment")


def fetch_user_info(api_key: str, username: str) -> dict | None:
    """Fetch user profile by username to get bio and other data."""
    try:
        r = httpx.get(
            f"{BASE_URL}/user/info",
            params={"userName": username},
            headers={"X-API-Key": api_key},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "success":
                return data.get("data", {})
        return None
    except Exception:
        return None


def fetch_following(api_key: str, username: str, max_pages: int = 5) -> list[str]:
    """Fetch who this user follows. Returns list of followed account_ids."""
    following_ids = []
    cursor = None

    for page in range(max_pages):
        params = {"userName": username, "count": "200"}
        if cursor:
            params["cursor"] = cursor

        try:
            r = httpx.get(
                f"{BASE_URL}/user/followings",
                params=params,
                headers={"X-API-Key": api_key},
                timeout=20,
            )
            if r.status_code != 200:
                print(f"    API error: {r.status_code}")
                break

            data = r.json()
            if data.get("status") != "success":
                break

            users = data.get("followings", [])
            for u in users:
                fid = u.get("id")
                if fid:
                    following_ids.append(str(fid))

            # Check for next page
            next_cursor = data.get("next_cursor")
            if not next_cursor or next_cursor == "0" or not users:
                break
            cursor = next_cursor

            time.sleep(0.5)  # rate limiting

        except Exception as e:
            print(f"    Fetch error: {e}")
            break

    return following_ids


def store_following(conn: sqlite3.Connection, source_id: str, following_ids: list[str]):
    """Add following edges to account_following table."""
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    for target_id in following_ids:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO account_following (account_id, following_account_id) VALUES (?, ?)",
                (source_id, target_id),
            )
            added += 1
        except Exception:
            pass
    conn.commit()
    return added


def main():
    parser = argparse.ArgumentParser(description="Fetch following lists for frontier accounts")
    parser.add_argument("--top", type=int, default=50, help="Fetch for top N frontier accounts")
    parser.add_argument("--budget", type=float, default=5.0, help="Max spend in USD")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-holdout", action="store_true", default=True,
                        help="Skip holdout accounts (default: True)")
    args = parser.parse_args()

    api_key = get_api_key()
    conn = sqlite3.connect(str(args.db_path))

    # Get ranked frontier accounts with usernames (non-holdout)
    targets = conn.execute("""
        SELECT fr.account_id, fr.info_value, fr.top_community, fr.degree, fr.in_holdout,
               COALESCE(p.username, ra.username) as username
        FROM frontier_ranking fr
        LEFT JOIN profiles p ON fr.account_id = p.account_id
        LEFT JOIN resolved_accounts ra ON fr.account_id = ra.account_id
        WHERE fr.in_holdout = 0
        AND COALESCE(p.username, ra.username) IS NOT NULL
        ORDER BY fr.info_value DESC
        LIMIT ?
    """, (args.top,)).fetchall()

    print(f"Fetching following lists for top {len(targets)} frontier accounts")
    print(f"Budget: ${args.budget:.2f} (~{int(args.budget / COST_PER_CALL)} calls)")
    if args.dry_run:
        print("DRY RUN — no API calls")

    total_cost = 0.0
    total_edges = 0
    fetched = 0

    for aid, iv, comm, deg, holdout, username in targets:
        if total_cost >= args.budget:
            print(f"\nBudget exhausted at ${total_cost:.2f}")
            break

        display = username or aid[:12]
        print(f"\n  [{fetched+1}/{len(targets)}] @{display} (deg={deg}, iv={iv:.1f}, comm={comm})")

        if args.dry_run:
            print(f"    [dry-run] would fetch following list")
            fetched += 1
            continue

        # Step 1: fetch bio (enrichment side effect)
        info = fetch_user_info(api_key, username)
        if info:
            bio = info.get("description", "")
            if bio:
                conn.execute(
                    "UPDATE resolved_accounts SET bio = ? WHERE account_id = ?",
                    (bio, aid),
                )
                conn.commit()
                print(f"    Bio: {bio[:60]}...")
            total_cost += COST_PER_CALL
        else:
            print(f"    Could not fetch user info for @{username}")
            total_cost += COST_PER_CALL

        # Step 2: fetch following list
        following_ids = fetch_following(api_key, username)
        total_cost += COST_PER_CALL

        if following_ids:
            added = store_following(conn, aid, following_ids)
            total_edges += added
            print(f"    Following: {len(following_ids)} accounts, {added} new edges added")
        else:
            print(f"    No following data returned")

        fetched += 1
        time.sleep(1.0)  # rate limiting between accounts

    print(f"\n{'='*60}")
    print(f"  Fetched: {fetched} accounts")
    print(f"  New edges: {total_edges:,}")
    print(f"  Estimated cost: ${total_cost:.2f}")
    print(f"  Budget remaining: ${args.budget - total_cost:.2f}")
    print(f"{'='*60}")

    conn.close()


if __name__ == "__main__":
    main()
