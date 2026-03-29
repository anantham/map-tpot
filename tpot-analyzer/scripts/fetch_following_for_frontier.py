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


def fetch_following(api_key: str, username: str, max_pages: int = 50) -> list[str]:
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


def select_frontier_targets(conn, top: int, min_outbound: int = 108):
    """Original mode: top frontier_ranking accounts by info_value."""
    targets = conn.execute("""
        SELECT fr.account_id,
               COALESCE(p.username, ra.username) as username,
               fr.degree as inbound,
               COALESCE(upc.following, 0) as total_following
        FROM frontier_ranking fr
        LEFT JOIN profiles p ON fr.account_id = p.account_id
        LEFT JOIN resolved_accounts ra ON fr.account_id = ra.account_id
        LEFT JOIN user_profile_cache upc ON fr.account_id = upc.account_id
        LEFT JOIN (
            SELECT account_id, COUNT(*) as cnt
            FROM account_following GROUP BY account_id
        ) outbound ON fr.account_id = outbound.account_id
        WHERE fr.in_holdout = 0
        AND COALESCE(p.username, ra.username) IS NOT NULL
        AND COALESCE(outbound.cnt, 0) < ?
        ORDER BY fr.info_value DESC
        LIMIT ?
    """, (min_outbound, top)).fetchall()
    return [(r[0], r[1], r[2], r[3]) for r in targets]


def select_zero_outbound_targets(conn, max_following: int = 1000, min_inbound: int = 50):
    """Accounts with high inbound but zero outbound edges.

    These are well-connected accounts (50+ TPOT seeds follow them) where
    we have no reciprocity data. Fetching their following lists adds edges
    to the graph and enables directional analysis.
    """
    targets = conn.execute("""
        SELECT ra.account_id, ra.username,
               inb.cnt as inbound,
               COALESCE(upc.following, 0) as total_following
        FROM resolved_accounts ra
        JOIN (
            SELECT following_account_id, COUNT(*) as cnt
            FROM account_following GROUP BY following_account_id
        ) inb ON ra.account_id = inb.following_account_id
        LEFT JOIN (
            SELECT account_id FROM account_following GROUP BY account_id
        ) outb ON ra.account_id = outb.account_id
        LEFT JOIN user_profile_cache upc ON ra.account_id = upc.account_id
        LEFT JOIN tpot_directory_holdout h ON ra.account_id = h.account_id
        WHERE outb.account_id IS NULL
        AND inb.cnt >= ?
        AND COALESCE(upc.following, 0) > 0
        AND COALESCE(upc.following, 0) <= ?
        AND ra.username IS NOT NULL
        AND h.account_id IS NULL
        ORDER BY inb.cnt DESC
    """, (min_inbound, max_following)).fetchall()
    return [(r[0], r[1], r[2], r[3]) for r in targets]


def main():
    parser = argparse.ArgumentParser(description="Fetch following lists for frontier/zero-outbound accounts")
    parser.add_argument("--mode", choices=["frontier", "zero-outbound"], default="frontier",
                        help="frontier: top frontier_ranking. zero-outbound: high-inbound with no outbound edges.")
    parser.add_argument("--top", type=int, default=50, help="Limit accounts (frontier mode)")
    parser.add_argument("--max-following", type=int, default=1000,
                        help="Skip accounts following more than this (zero-outbound mode)")
    parser.add_argument("--min-inbound", type=int, default=50,
                        help="Min inbound edges (zero-outbound mode)")
    parser.add_argument("--budget", type=float, default=5.0, help="Max spend in USD")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = get_api_key()
    conn = sqlite3.connect(str(args.db_path))

    if args.mode == "zero-outbound":
        targets = select_zero_outbound_targets(conn, args.max_following, args.min_inbound)
        print(f"Mode: zero-outbound (inbound >= {args.min_inbound}, following <= {args.max_following})")
    else:
        targets = select_frontier_targets(conn, args.top)
        print(f"Mode: frontier (top {args.top})")

    print(f"Accounts to fetch: {len(targets)}")
    total_pages_est = sum(min(50, (fwing + 19) // 20) for _, _, _, fwing in targets if fwing > 0)
    print(f"Estimated API pages: ~{total_pages_est:,}")
    print(f"Estimated cost: ~${total_pages_est * COST_PER_CALL / 20:.2f}")
    print(f"Budget: ${args.budget:.2f}")
    if args.dry_run:
        print("DRY RUN — no API calls")
        for aid, uname, inb, fwing in targets[:20]:
            print(f"  @{uname:25s} inbound={inb:5d} following={fwing:5d}")
        if len(targets) > 20:
            print(f"  ... and {len(targets) - 20} more")
        conn.close()
        return

    total_cost = 0.0
    total_edges = 0
    fetched = 0

    for aid, username, inb, total_fwing in targets:
        if total_cost >= args.budget:
            print(f"\nBudget exhausted at ${total_cost:.2f}")
            break

        pages = min(50, (total_fwing + 19) // 20) if total_fwing > 0 else 5
        print(f"  [{fetched+1}/{len(targets)}] @{username} (inbound={inb}, following={total_fwing}, ~{pages}p)", end=" ", flush=True)

        following_ids = fetch_following(api_key, username, max_pages=pages)
        est_pages_used = max(1, (len(following_ids) + 19) // 20)
        total_cost += est_pages_used * COST_PER_CALL

        if following_ids:
            added = store_following(conn, aid, following_ids)
            total_edges += added
            print(f"→ {len(following_ids)} fetched, {added} new edges (total: {total_edges:,})")
        else:
            print(f"→ 0 fetched")

        fetched += 1
        time.sleep(0.3)

    print(f"\n{'='*60}")
    print(f"  Fetched: {fetched} accounts")
    print(f"  New edges: {total_edges:,}")
    print(f"  Estimated cost: ${total_cost:.2f}")
    print(f"  Budget remaining: ${args.budget - total_cost:.2f}")
    print(f"{'='*60}")

    conn.close()


if __name__ == "__main__":
    main()
