"""Refresh account data by updating DB with current X API values.

This script:
1. Fetches all accounts with complete data from DB
2. Queries X API for current follower/following counts
3. Caches API responses to avoid duplicate calls
4. Updates the database with fresh values
5. Respects rate limits automatically

Usage:
    python -m scripts.refresh_account_data [--dry-run] [--threshold 5.0]

    # Two-step workflow (recommended):
    python -m scripts.refresh_account_data --dry-run  # Preview changes, cache API data
    python -m scripts.refresh_account_data --use-cache  # Apply cached updates
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from typing import Optional

from src.shadow.x_api_client import XAPIClient, XAPIClientConfig


def parse_args():
    parser = argparse.ArgumentParser(
        description="Refresh account data with current X API values"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't update database, just show what would be updated (caches API data)",
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Use cached API data from previous dry run (avoids duplicate API calls)",
    )
    parser.add_argument(
        "--cache-file",
        type=Path,
        default=Path("data/account_refresh_cache.json"),
        help="Path to cache file (default: data/account_refresh_cache.json)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/cache.db",
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=5.0,
        help="Only update if drift exceeds this percentage (default: 5%%)",
    )
    parser.add_argument(
        "--force-all",
        action="store_true",
        help="Update all accounts regardless of drift threshold",
    )
    return parser.parse_args()


def refresh_accounts(
    api: Optional[XAPIClient],
    db_path: str,
    dry_run: bool,
    threshold: float,
    force_all: bool,
    cache_file: Path,
    use_cache: bool,
):
    """Refresh account data with current X API values."""
    engine = create_engine(f"sqlite:///{db_path}", future=True)

    # Load cache if using cached data
    cached_data = {}
    if use_cache:
        if not cache_file.exists():
            print(f"Error: Cache file not found at {cache_file}", file=sys.stderr)
            print("Run with --dry-run first to populate the cache", file=sys.stderr)
            sys.exit(1)

        with open(cache_file) as f:
            cache_content = json.load(f)
            cached_data = cache_content.get("accounts", {})
            cache_timestamp = cache_content.get("timestamp")

        print(f"Loaded cached data from {cache_file}")
        print(f"Cache timestamp: {cache_timestamp}")
        print(f"Cached accounts: {len(cached_data)}")
        print()

    # Get all accounts with complete data (non-shadow IDs)
    query = text("""
        SELECT username, account_id, followers_count, following_count,
               fetched_at, source_channel
        FROM shadow_account
        WHERE followers_count IS NOT NULL
          AND following_count IS NOT NULL
          AND username IS NOT NULL
          AND account_id NOT LIKE 'shadow:%'
        ORDER BY username
    """)

    update_count = 0
    skip_count = 0
    error_count = 0
    total_processed = 0

    # Cache for storing API results
    api_cache = {}

    with engine.begin() as conn:
        rows = conn.execute(query).fetchall()
        total = len(rows)

        print(f"Found {total} accounts with complete data")
        print(f"Threshold: {threshold}% (only update if drift exceeds this)")
        print(f"Mode: {'DRY RUN (no changes will be made)' if dry_run else 'LIVE UPDATE'}")
        print()

        if not dry_run:
            response = input(f"Proceed to check and update {total} accounts? [y/N]: ").strip().lower()
            if response not in ('y', 'yes'):
                print("Aborted.")
                return

        print("\nProcessing accounts...\n")

        for row in rows:
            total_processed += 1
            username = row.username
            account_id = row.account_id
            db_followers = row.followers_count
            db_following = row.following_count
            fetched_at = row.fetched_at
            source = row.source_channel

            print(f"[{total_processed}/{total}] @{username}...", end=" ", flush=True)

            try:
                # Get data from cache or API
                if use_cache:
                    if username not in cached_data:
                        print("⚠️ Not in cache")
                        skip_count += 1
                        continue

                    cached_account = cached_data[username]
                    api_followers = cached_account["api_followers"]
                    api_following = cached_account["api_following"]
                else:
                    # Fetch current data from X API
                    user_info = api.get_user_info_by_username(username)
                    if not user_info:
                        print("⚠️ API lookup failed")
                        error_count += 1
                        continue

                    metrics = user_info.get("public_metrics", {})
                    api_followers = metrics.get("followers_count")
                    api_following = metrics.get("following_count")

                    if api_followers is None or api_following is None:
                        print("⚠️ Incomplete API data")
                        error_count += 1
                        continue

                    # Store in cache for potential dry run
                    api_cache[username] = {
                        "username": username,
                        "account_id": account_id,
                        "db_followers": db_followers,
                        "db_following": db_following,
                        "api_followers": api_followers,
                        "api_following": api_following,
                        "fetched_at": str(fetched_at),
                        "source": source,
                    }

                # Calculate percentage difference
                followers_diff = abs(api_followers - db_followers)
                following_diff = abs(api_following - db_following)

                followers_pct = (followers_diff / max(db_followers, 1)) * 100
                following_pct = (following_diff / max(db_following, 1)) * 100

                max_drift = max(followers_pct, following_pct)
                needs_update = force_all or max_drift > threshold

                if not needs_update:
                    print(f"✓ Fresh (drift: {max_drift:.1f}%)")
                    skip_count += 1
                    continue

                # Update needed
                status_icon = "🔄" if not dry_run else "📝"
                print(f"{status_icon} Updating (drift: {max_drift:.1f}%)")
                print(f"    Followers: {db_followers:,} → {api_followers:,} ({followers_diff:+,})")
                print(f"    Following: {db_following:,} → {api_following:,} ({following_diff:+,})")

                if not dry_run:
                    # Update database
                    update_stmt = text("""
                        UPDATE shadow_account
                        SET followers_count = :followers,
                            following_count = :following,
                            fetched_at = :fetched_at,
                            checked_at = :checked_at
                        WHERE account_id = :account_id
                    """)

                    conn.execute(update_stmt, {
                        "followers": api_followers,
                        "following": api_following,
                        "fetched_at": datetime.utcnow(),
                        "checked_at": datetime.utcnow(),
                        "account_id": account_id,
                    })

                update_count += 1

            except Exception as e:
                print(f"❌ Error - {e}")
                error_count += 1
                continue

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total processed: {total_processed}")
    print(f"Updated: {update_count}")
    print(f"Skipped (fresh): {skip_count}")
    print(f"Errors: {error_count}")

    # Save cache if this was a dry run or regular run with new API data
    if api_cache and not use_cache:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_content = {
            "timestamp": datetime.utcnow().isoformat(),
            "threshold": threshold,
            "force_all": force_all,
            "total_accounts": len(api_cache),
            "accounts": api_cache,
        }

        with open(cache_file, 'w') as f:
            json.dump(cache_content, f, indent=2)

        print(f"\n💾 Cached {len(api_cache)} API results to {cache_file}")

    if dry_run and update_count > 0:
        print(f"\n⚠️  DRY RUN: No changes were made to the database")
        print(f"Run with --use-cache to apply {update_count} updates instantly (no new API calls)")


def main():
    args = parse_args()

    # Initialize API client (not needed if using cache)
    api = None
    if not args.use_cache:
        load_dotenv()
        bearer_token = os.getenv("X_BEARER_TOKEN")
        if not bearer_token:
            print("Error: X_BEARER_TOKEN not found in environment", file=sys.stderr)
            print("Add it to your .env file first", file=sys.stderr)
            sys.exit(1)

        config = XAPIClientConfig(bearer_token=bearer_token)
        api = XAPIClient(config)

    # Refresh accounts
    refresh_accounts(
        api=api,
        db_path=args.db_path,
        dry_run=args.dry_run,
        threshold=args.threshold,
        force_all=args.force_all,
        cache_file=args.cache_file,
        use_cache=args.use_cache,
    )


if __name__ == "__main__":
    main()
