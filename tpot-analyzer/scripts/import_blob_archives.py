#!/usr/bin/env python3
"""Import Community Archive data from Supabase blob storage.

This script supplements the REST API fetcher by pulling complete archive data
directly from blob storage URLs, which bypasses pagination limits.

Usage:
    # Dry run to preview imports
    python -m scripts.import_blob_archives --dry-run

    # Import specific user
    python -m scripts.import_blob_archives --username adityaarpitha

    # Import all archives (careful!)
    python -m scripts.import_blob_archives --all

    # Import first 10 archives (for testing)
    python -m scripts.import_blob_archives --all --max 10
"""
import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine

from src.config import get_cache_settings
from src.data.blob_importer import BlobStorageImporter


def parse_args():
    parser = argparse.ArgumentParser(
        description="Import Community Archive data from blob storage"
    )
    parser.add_argument(
        "--username",
        type=str,
        help="Import specific username only"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Import all available archives"
    )
    parser.add_argument(
        "--max",
        type=int,
        help="Maximum number of archives to import (for testing)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview imports without writing to database"
    )
    parser.add_argument(
        "--merge-strategy",
        choices=["timestamp", "archive_only", "shadow_only"],
        default="timestamp",
        help="How to handle conflicts with existing data (default: timestamp)"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        help="Path to cache database (default: from config)"
    )
    parser.add_argument(
        "--force-reimport",
        action="store_true",
        help="Re-import archives even if already imported"
    )

    args = parser.parse_args()

    if not args.username and not args.all:
        parser.error("Must specify either --username or --all")

    return args


def main():
    args = parse_args()

    # Get database path
    if args.db_path:
        db_path = Path(args.db_path)
    else:
        cache_settings = get_cache_settings()
        db_path = Path(cache_settings.path)

    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        print("Please run the data fetcher first to create the cache")
        sys.exit(1)

    engine = create_engine(f"sqlite:///{db_path}", future=True)

    print("=" * 60)
    print("IMPORTING ARCHIVES FROM BLOB STORAGE")
    print("=" * 60)
    print(f"Database: {db_path}")
    print(f"Merge strategy: {args.merge_strategy}")
    print(f"Dry run: {args.dry_run}")
    print()

    with BlobStorageImporter(engine) as importer:
        if args.username:
            # Import single user
            print(f"Importing archive for '{args.username}'...")
            metadata = importer.import_archive(
                args.username,
                merge_strategy=args.merge_strategy,
                dry_run=args.dry_run
            )

            if metadata:
                print("\n✅ Import successful!")
                print(f"   Account ID: {metadata.account_id}")
                print(f"   Following: {metadata.following_count}")
                print(f"   Followers: {metadata.follower_count}")
                print(f"   Tweets: {metadata.tweet_count}")
                print(f"   Likes: {metadata.like_count}")
            else:
                print(f"\n❌ Archive not found for '{args.username}'")
                sys.exit(1)

        else:
            # Import all archives
            print("Fetching list of available archives...")
            results = importer.import_all_archives(
                merge_strategy=args.merge_strategy,
                dry_run=args.dry_run,
                max_archives=args.max,
                force_reimport=args.force_reimport
            )

            print("\n" + "=" * 60)
            print("IMPORT SUMMARY")
            print("=" * 60)
            print(f"Successfully imported: {len(results)} archives")

            if results:
                total_following = sum(m.following_count for m in results)
                total_followers = sum(m.follower_count for m in results)
                print(f"Total following edges: {total_following:,}")
                print(f"Total follower edges: {total_followers:,}")

                print("\nTop 10 by following count:")
                sorted_results = sorted(results, key=lambda m: m.following_count, reverse=True)
                for i, metadata in enumerate(sorted_results[:10], 1):
                    print(f"  {i}. {metadata.username}: {metadata.following_count:,} following")

    print("\n" + "=" * 60)
    if args.dry_run:
        print("DRY RUN COMPLETE - No changes made")
    else:
        print("IMPORT COMPLETE")
        print("\nNext steps:")
        print("  1. Run: python -m scripts.refresh_graph_snapshot")
        print("  2. Restart the API server")
    print("=" * 60)


if __name__ == "__main__":
    main()
