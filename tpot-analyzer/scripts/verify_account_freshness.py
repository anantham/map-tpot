"""Verify account data freshness by comparing DB values with X API.

This script samples accounts from the database and checks if their
follower/following counts are still accurate via the X API.

Usage:
    python -m scripts.verify_account_freshness [--sample-size 10] [--show-stale]
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from src.shadow.x_api_client import XAPIClient, XAPIClientConfig


def parse_args():
    parser = argparse.ArgumentParser(
        description="Verify account data freshness via X API"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=10,
        help="Number of accounts to sample (default: 10)",
    )
    parser.add_argument(
        "--show-stale",
        action="store_true",
        help="Only show accounts with stale data (>5%% difference)",
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
        help="Percentage threshold to consider data stale (default: 5%%)",
    )
    return parser.parse_args()


def verify_accounts(api: XAPIClient, db_path: str, sample_size: int, threshold: float, show_stale: bool):
    """Compare DB account data with current X API data."""
    engine = create_engine(f"sqlite:///{db_path}", future=True)

    # Get random sample of accounts with complete data
    query = text("""
        SELECT username, account_id, followers_count, following_count,
               fetched_at, source_channel
        FROM shadow_account
        WHERE followers_count IS NOT NULL
          AND following_count IS NOT NULL
          AND username IS NOT NULL
          AND account_id NOT LIKE 'shadow:%'
        ORDER BY RANDOM()
        LIMIT :limit
    """)

    results = []
    with engine.begin() as conn:
        rows = conn.execute(query, {"limit": sample_size}).fetchall()

        print(f"Verifying {len(rows)} accounts...")
        print(f"Note: X API has rate limits (900 requests / 15 min)")
        print(f"This may take ~{len(rows) * 1.5:.0f} seconds if rate-limited\n")

        for idx, row in enumerate(rows, 1):
            username = row.username
            db_followers = row.followers_count
            db_following = row.following_count
            fetched_at = row.fetched_at
            source = row.source_channel

            print(f"[{idx}/{len(rows)}] Checking @{username}...", end=" ", flush=True)

            # Fetch current data from X API
            try:
                user_info = api.get_user_info_by_username(username)
                if not user_info:
                    print("⚠️ API lookup failed")
                    continue

                metrics = user_info.get("public_metrics", {})
                api_followers = metrics.get("followers_count")
                api_following = metrics.get("following_count")

                if api_followers is None or api_following is None:
                    print("⚠️ Incomplete API data")
                    continue

                # Calculate percentage difference
                followers_diff = abs(api_followers - db_followers)
                following_diff = abs(api_following - db_following)

                followers_pct = (followers_diff / max(db_followers, 1)) * 100
                following_pct = (following_diff / max(db_following, 1)) * 100

                is_stale = followers_pct > threshold or following_pct > threshold

                # Calculate staleness
                if isinstance(fetched_at, str):
                    fetched_dt = datetime.fromisoformat(fetched_at)
                else:
                    fetched_dt = fetched_at
                age_days = (datetime.now() - fetched_dt).days

                result = {
                    "username": username,
                    "db_followers": db_followers,
                    "api_followers": api_followers,
                    "followers_diff": followers_diff,
                    "followers_pct": followers_pct,
                    "db_following": db_following,
                    "api_following": api_following,
                    "following_diff": following_diff,
                    "following_pct": following_pct,
                    "age_days": age_days,
                    "source": source,
                    "is_stale": is_stale,
                }
                results.append(result)

                # Print based on filter
                if show_stale and not is_stale:
                    print("✅")
                    continue

                status = "🔴 STALE" if is_stale else "✅"
                print(status)

                if not show_stale or is_stale:
                    print(f"    {username} (age: {age_days}d, source: {source})")
                    print(f"    Followers: {db_followers:,} → {api_followers:,} (diff: {followers_diff:,}, {followers_pct:.1f}%)")
                    print(f"    Following: {db_following:,} → {api_following:,} (diff: {following_diff:,}, {following_pct:.1f}%)")

            except Exception as e:
                print(f"❌ Error - {e}")
                continue

    # Summary stats
    if results:
        stale_count = sum(1 for r in results if r["is_stale"])
        avg_followers_pct = sum(r["followers_pct"] for r in results) / len(results)
        avg_following_pct = sum(r["following_pct"] for r in results) / len(results)
        avg_age = sum(r["age_days"] for r in results) / len(results)

        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total verified: {len(results)}")
        print(f"Stale (>{threshold}% diff): {stale_count} ({stale_count/len(results)*100:.1f}%)")
        print(f"Fresh: {len(results) - stale_count} ({(len(results)-stale_count)/len(results)*100:.1f}%)")
        print(f"Avg followers drift: {avg_followers_pct:.2f}%")
        print(f"Avg following drift: {avg_following_pct:.2f}%")
        print(f"Avg data age: {avg_age:.1f} days")


def main():
    args = parse_args()

    # Load bearer token
    load_dotenv()
    bearer_token = os.getenv("X_BEARER_TOKEN")
    if not bearer_token:
        print("Error: X_BEARER_TOKEN not found in environment", file=sys.stderr)
        print("Add it to your .env file first", file=sys.stderr)
        sys.exit(1)

    # Initialize API client
    config = XAPIClientConfig(bearer_token=bearer_token)
    api = XAPIClient(config)

    # Verify accounts
    verify_accounts(
        api=api,
        db_path=args.db_path,
        sample_size=args.sample_size,
        threshold=args.threshold,
        show_stale=args.show_stale,
    )


if __name__ == "__main__":
    main()
