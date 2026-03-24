"""Resolve unresolved account IDs in account_following to usernames.

Fetches user profiles from twitterapi.io in batches of 100 and inserts
into the profiles table. Only resolves IDs that don't already have a profile.

Usage:
    .venv/bin/python3 -m scripts.resolve_follow_usernames
    .venv/bin/python3 -m scripts.resolve_follow_usernames --limit 1000
    .venv/bin/python3 -m scripts.resolve_follow_usernames --dry-run
    .venv/bin/python3 -m scripts.resolve_follow_usernames --labeled-only
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "archive_tweets.db"

# Load API key
API_KEY = None
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.startswith("TWITTERAPI_IO_API_KEY="):
            API_KEY = line.split("=", 1)[1].strip()
            break


def get_unresolved_ids(conn: sqlite3.Connection, labeled_only: bool = False) -> list[str]:
    """Get account IDs from account_following that have no profile."""
    if labeled_only:
        query = """
            SELECT DISTINCT af.following_account_id
            FROM account_following af
            LEFT JOIN profiles p ON p.account_id = af.following_account_id
            WHERE p.username IS NULL
            AND af.account_id IN (
                SELECT DISTINCT t.account_id FROM tweet_tags tt
                JOIN tweets t ON t.tweet_id = tt.tweet_id
                WHERE tt.category = 'bits'
            )
        """
    else:
        query = """
            SELECT DISTINCT af.following_account_id
            FROM account_following af
            LEFT JOIN profiles p ON p.account_id = af.following_account_id
            WHERE p.username IS NULL
        """
    return [r[0] for r in conn.execute(query).fetchall()]


def batch_lookup_users(ids: list[str], api_key: str) -> list[dict]:
    """Look up users by ID via twitterapi.io. Returns list of user objects.

    Endpoint: GET /twitter/user/batch_info_by_ids?userIds=id1,id2,...
    Pricing: 10 credits/user for bulk (100+), 18 credits/user for single.
    """
    url = "https://api.twitterapi.io/twitter/user/batch_info_by_ids"
    ids_str = ",".join(ids[:100])  # max 100 per call

    req = urllib.request.Request(
        f"{url}?userIds={ids_str}",
        headers={
            "X-API-Key": api_key,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    if isinstance(data, dict) and "users" in data:
        return data["users"]
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    if isinstance(data, list):
        return data
    return []


def save_profiles(conn: sqlite3.Connection, users: list[dict]) -> int:
    """Insert resolved user profiles into the profiles table."""
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for u in users:
        # twitterapi.io batch_info_by_ids response format
        aid = str(u.get("id", ""))
        username = u.get("userName", "")
        if not aid or not username:
            continue
        if u.get("unavailable"):
            continue  # Suspended/deleted accounts

        display_name = u.get("name", "")
        bio = u.get("description", "")
        # Also check nested profile_bio
        if not bio and u.get("profile_bio", {}).get("description"):
            bio = u["profile_bio"]["description"]
        location = u.get("location", "")
        website = ""
        pb = u.get("profile_bio", {}).get("entities", {}).get("url", {}).get("urls", [])
        if pb:
            website = pb[0].get("expanded_url", "")

        try:
            conn.execute(
                """INSERT OR IGNORE INTO profiles
                   (account_id, username, display_name, bio, location, website, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (aid, username, display_name, bio, location, website, now),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass  # Already exists
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Resolve follow IDs to usernames")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max IDs to resolve (0 = all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Count without fetching")
    parser.add_argument("--labeled-only", action="store_true",
                        help="Only resolve follows of labeled accounts")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()

    if not API_KEY and not args.dry_run:
        print("ERROR: No API_KEY found in .env")
        return

    conn = sqlite3.connect(str(args.db_path))
    ids = get_unresolved_ids(conn, labeled_only=args.labeled_only)

    if args.limit > 0:
        ids = ids[:args.limit]

    n_batches = (len(ids) + args.batch_size - 1) // args.batch_size
    est_cost = n_batches * 0.15

    print(f"Unresolved IDs: {len(ids):,}")
    print(f"Batches needed: {n_batches}")
    print(f"Estimated cost: ${est_cost:.2f}")

    if args.dry_run:
        print("(dry run)")
        conn.close()
        return

    total_resolved = 0
    total_failed = 0

    for i in range(0, len(ids), args.batch_size):
        batch = ids[i:i + args.batch_size]
        batch_num = i // args.batch_size + 1

        print(f"  Batch {batch_num}/{n_batches} ({len(batch)} IDs)...", end=" ", flush=True)
        try:
            users = batch_lookup_users(batch, API_KEY)
            inserted = save_profiles(conn, users)
            conn.commit()
            total_resolved += inserted
            print(f"✓ {inserted} resolved ({len(batch) - inserted} not found)")
        except Exception as e:
            total_failed += len(batch)
            print(f"✗ {e}")

        time.sleep(1)  # Rate limit

    conn.close()
    print(f"\nDone. Resolved: {total_resolved:,}, Failed: {total_failed:,}")
    print(f"Re-run export to make them searchable on the public site.")


if __name__ == "__main__":
    main()
