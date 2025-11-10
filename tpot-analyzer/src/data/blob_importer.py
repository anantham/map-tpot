"""Import Community Archive data from Supabase blob storage.

This module handles importing complete archive data from blob storage URLs,
which is more comprehensive than the REST API (which has pagination limits).

Architecture:
    - Community Archive: Complete but potentially stale (user upload date)
    - Shadow enrichment: Incomplete but fresh (recent scrapes)
    - Merge strategy: Use timestamps to prefer newer data while keeping complete coverage
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import httpx
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# Configuration
MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds
BATCH_COMMIT_SIZE = 500  # rows per commit batch


@dataclass
class ArchiveMetadata:
    """Metadata about an imported archive."""
    username: str
    account_id: str
    blob_url: str
    imported_at: datetime
    follower_count: int
    following_count: int
    tweet_count: int
    like_count: int


class BlobStorageImporter:
    """Import archives from Supabase blob storage into local cache.

    Example usage:
        importer = BlobStorageImporter(engine, base_url=SUPABASE_STORAGE_URL)
        usernames = await importer.list_archives()
        for username in usernames:
            await importer.import_archive(username)
    """

    def __init__(
        self,
        engine: Engine,
        base_url: str = "https://fabxmporizzqflnftavs.supabase.co",
        timeout: float = 30.0
    ):
        self.engine = engine
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None

    def __enter__(self) -> "BlobStorageImporter":
        self._client = httpx.Client(timeout=self.timeout)

        # Enable WAL mode for better concurrency
        with self.engine.connect() as conn:
            try:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.commit()
                logger.info("Enabled SQLite WAL mode for better concurrency")
            except Exception as e:
                logger.warning(f"Failed to enable WAL mode: {e}")

        return self

    def __exit__(self, exc_type, exc, tb):
        if self._client:
            self._client.close()

    def list_archives(self) -> List[str]:
        """List all available archive usernames from blob storage.

        Strategy: Since bucket listing isn't public, we try all usernames
        from the account table. The import process will skip archives that
        don't exist (404).

        Returns:
            List of lowercase usernames to attempt importing
        """
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT DISTINCT username FROM account WHERE username IS NOT NULL"))
            usernames = [row[0].lower() for row in result if row[0]]

        logger.info(f"Found {len(usernames)} usernames in account table (will attempt import for each)")
        return usernames

    def fetch_archive(self, username: str) -> Optional[Dict]:
        """Fetch archive JSON from blob storage.

        Args:
            username: Twitter handle (will be lowercased)

        Returns:
            Archive dict or None if not found
        """
        username_lower = username.lower()
        url = f"{self.base_url}/storage/v1/object/public/archives/{username_lower}/archive.json"

        logger.info(f"Fetching archive for '{username}' from blob storage")

        if not self._client:
            raise RuntimeError("BlobStorageImporter must be used as context manager")

        try:
            response = self._client.get(url)
            if response.status_code == 404:
                logger.warning(f"Archive not found for '{username}' at {url}")
                return None
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch archive for '{username}': {e}")
            return None

    def import_archive(
        self,
        username: str,
        *,
        merge_strategy: str = "timestamp",
        dry_run: bool = False
    ) -> Optional[ArchiveMetadata]:
        """Import a single archive into the database.

        Args:
            username: Twitter handle
            merge_strategy: How to handle conflicts ("timestamp", "archive_only", "shadow_only")
            dry_run: If True, don't write to database

        Returns:
            Metadata about the import, or None if archive not found
        """
        archive = self.fetch_archive(username)
        if not archive:
            return None

        # Extract account info
        account_data = archive.get("account", [])
        if not account_data or len(account_data) == 0:
            logger.warning(f"No account data in archive for '{username}'")
            return None

        account = account_data[0].get("account", {})
        account_id = account.get("accountId")
        if not account_id:
            logger.warning(f"No account ID in archive for '{username}'")
            return None

        # Extract edges
        following_data = archive.get("following", [])
        follower_data = archive.get("follower", [])

        following_ids = [
            entry.get("following", {}).get("accountId")
            for entry in following_data
            if entry.get("following", {}).get("accountId")
        ]

        follower_ids = [
            entry.get("follower", {}).get("accountId")
            for entry in follower_data
            if entry.get("follower", {}).get("accountId")
        ]

        logger.info(
            f"Archive for '{username}' ({account_id}): "
            f"{len(following_ids)} following, {len(follower_ids)} followers"
        )

        if dry_run:
            logger.info("Dry run mode - skipping database writes")
            return ArchiveMetadata(
                username=username,
                account_id=account_id,
                blob_url=f"{self.base_url}/storage/v1/object/public/archives/{username.lower()}/archive.json",
                imported_at=datetime.utcnow(),
                follower_count=len(follower_ids),
                following_count=len(following_ids),
                tweet_count=len(archive.get("tweets", [])),
                like_count=len(archive.get("like", []))
            )

        # Import profile data (bio, website, location)
        self._import_profile_data(account_id, archive, merge_strategy)

        # Import tweets (high priority: top liked + recent)
        self._import_tweets(account_id, archive, merge_strategy)

        # Import likes data (medium priority)
        self._import_likes(account_id, archive, merge_strategy)

        # Import following edges with timestamp-based merge
        self._import_edges(
            source_account_id=account_id,
            target_account_ids=following_ids,
            edge_type="following",
            merge_strategy=merge_strategy
        )

        # Import follower edges
        self._import_edges(
            source_account_id=account_id,
            target_account_ids=follower_ids,
            edge_type="follower",
            merge_strategy=merge_strategy
        )

        return ArchiveMetadata(
            username=username,
            account_id=account_id,
            blob_url=f"{self.base_url}/storage/v1/object/public/archives/{username.lower()}/archive.json",
            imported_at=datetime.utcnow(),
            follower_count=len(follower_ids),
            following_count=len(following_ids),
            tweet_count=len(archive.get("tweets", [])),
            like_count=len(archive.get("like", []))
        )

    def _import_edges(
        self,
        source_account_id: str,
        target_account_ids: List[str],
        edge_type: str,  # "following" or "follower"
        merge_strategy: str
    ):
        """Import edges into archive staging tables.

        Args:
            source_account_id: The account whose archive is being imported
            target_account_ids: List of account IDs in the relationship
            edge_type: "following" (accounts source follows) or "follower" (accounts following source)
            merge_strategy: Reserved for future use (currently always imports to staging)

        Directionality:
            - "following": source_account → target_account (source follows target)
            - "follower": target_account → source_account (target follows source)
        """
        if merge_strategy == "shadow_only":
            logger.debug(f"Skipping {edge_type} import (shadow_only mode)")
            return

        now = datetime.utcnow().isoformat()

        # Choose target table based on edge type
        if edge_type == "following":
            table_name = "archive_following"
            account_col = "account_id"
            target_col = "following_account_id"
        else:  # "follower"
            table_name = "archive_followers"
            account_col = "account_id"
            target_col = "follower_account_id"

        with self.engine.connect() as conn:
            for i, target_id in enumerate(target_account_ids):
                # For "following": source follows target
                # For "follower": source is followed by target
                if edge_type == "following":
                    account_id = source_account_id
                    related_id = target_id
                else:  # follower
                    account_id = source_account_id
                    related_id = target_id

                # Insert into archive staging table with UNIQUE constraint handling
                conn.execute(text(f"""
                    INSERT OR REPLACE INTO {table_name}
                    ({account_col}, {target_col}, uploaded_at, imported_at)
                    VALUES (:account_id, :related_id, :uploaded_at, :imported_at)
                """), {
                    "account_id": account_id,
                    "related_id": related_id,
                    "uploaded_at": now,  # TODO: Get actual upload timestamp from archive metadata
                    "imported_at": now
                })

                # Batch commits every BATCH_COMMIT_SIZE rows to reduce lock duration
                if (i + 1) % BATCH_COMMIT_SIZE == 0:
                    conn.commit()
                    logger.debug(f"Batch commit at {i + 1}/{len(target_account_ids)} edges")

            # Final commit for remaining rows
            conn.commit()

        logger.debug(f"Imported {len(target_account_ids)} {edge_type} edges to {table_name}")

    def _is_already_imported(self, account_id: str) -> bool:
        """Check if an archive has already been imported.

        Args:
            account_id: The account ID to check

        Returns:
            True if archive already has edges in the database
        """
        with self.engine.connect() as conn:
            # Check both following and followers tables
            following_count = conn.execute(text("""
                SELECT COUNT(*) FROM archive_following
                WHERE account_id = :account_id
            """), {"account_id": account_id}).scalar()

            followers_count = conn.execute(text("""
                SELECT COUNT(*) FROM archive_followers
                WHERE account_id = :account_id
            """), {"account_id": account_id}).scalar()

            return (following_count or 0) > 0 or (followers_count or 0) > 0

    def import_all_archives(
        self,
        *,
        merge_strategy: str = "timestamp",
        dry_run: bool = False,
        max_archives: Optional[int] = None,
        force_reimport: bool = False
    ) -> List[ArchiveMetadata]:
        """Import all available archives with skip logic and retry.

        Args:
            merge_strategy: How to handle conflicts
            dry_run: If True, don't write to database
            max_archives: Limit number of archives to import (for testing)
            force_reimport: If True, re-import even if already exists

        Returns:
            List of imported archive metadata
        """
        usernames = self.list_archives()
        if max_archives:
            usernames = usernames[:max_archives]

        logger.info(f"Importing {len(usernames)} archives (dry_run={dry_run}, force_reimport={force_reimport})")

        results = []
        skipped = []
        permanent_failures = []  # 400 errors - archives don't exist

        for i, username in enumerate(usernames, 1):
            logger.info(f"[{i}/{len(usernames)}] Processing '{username}'...")

            # Get account_id first to check if already imported
            archive = None
            try:
                archive = self.fetch_archive(username)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400:
                    logger.warning(f"Archive not found for '{username}' (400 Bad Request)")
                    permanent_failures.append(username)
                    continue
                else:
                    logger.error(f"HTTP error fetching '{username}': {e}")
                    continue
            except Exception as e:
                logger.error(f"Failed to fetch '{username}': {e}")
                continue

            if not archive:
                logger.warning(f"No archive data for '{username}'")
                continue

            # Extract account_id for skip check
            account_data = archive.get("account", [])
            if not account_data or len(account_data) == 0:
                logger.warning(f"No account data in archive for '{username}'")
                continue

            account = account_data[0].get("account", {})
            account_id = account.get("accountId")
            if not account_id:
                logger.warning(f"No account ID in archive for '{username}'")
                continue

            # Skip if already imported (unless force_reimport) - with retry
            skip = False
            if not force_reimport and not dry_run:
                for attempt in range(MAX_RETRIES):
                    try:
                        if self._is_already_imported(account_id):
                            logger.info(f"Skipping '{username}' ({account_id}) - already imported")
                            skipped.append(username)
                            skip = True
                        break  # Success checking
                    except sqlite3.OperationalError as e:
                        if "disk I/O error" in str(e) and attempt < MAX_RETRIES - 1:
                            sleep_time = BACKOFF_BASE ** attempt
                            logger.warning(
                                f"Disk I/O error checking '{username}' - "
                                f"retry {attempt + 1}/{MAX_RETRIES} after {sleep_time}s"
                            )
                            time.sleep(sleep_time)
                        else:
                            logger.error(f"Failed to check '{username}' after {attempt + 1} attempts: {e}")
                            skip = True  # Skip on persistent error
                            break

                if skip:
                    continue

            # Retry logic for transient failures during import
            success = False
            for attempt in range(MAX_RETRIES):
                try:
                    metadata = self.import_archive(
                        username,
                        merge_strategy=merge_strategy,
                        dry_run=dry_run
                    )
                    if metadata:
                        results.append(metadata)
                        success = True
                        break  # Success!
                except sqlite3.OperationalError as e:
                    if "disk I/O error" in str(e) and attempt < MAX_RETRIES - 1:
                        sleep_time = BACKOFF_BASE ** attempt
                        logger.warning(
                            f"Disk I/O error for '{username}' - "
                            f"retry {attempt + 1}/{MAX_RETRIES} after {sleep_time}s"
                        )
                        time.sleep(sleep_time)
                    else:
                        logger.error(f"Failed to import '{username}' after {attempt + 1} attempts: {e}")
                        raise
                except Exception as e:
                    logger.error(f"Failed to import '{username}': {e}", exc_info=True)
                    break  # Don't retry non-I/O errors

            if not success:
                logger.error(f"Giving up on '{username}' after {MAX_RETRIES} attempts")

        logger.info(
            f"Import complete: {len(results)} imported, "
            f"{len(skipped)} skipped, "
            f"{len(permanent_failures)} not found"
        )
        return results

    def _import_profile_data(
        self,
        account_id: str,
        archive: Dict,
        merge_strategy: str
    ):
        """Import profile data (bio, website, location, avatar, header)."""
        if merge_strategy == "shadow_only":
            logger.debug("Skipping profile import (shadow_only mode)")
            return

        profile_data = archive.get("profile", [])
        if not profile_data or len(profile_data) == 0:
            logger.debug(f"No profile data for account {account_id}")
            return

        profile = profile_data[0].get("profile", {})
        description = profile.get("description", {})

        now = datetime.utcnow().isoformat()

        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS archive_profiles (
                    account_id TEXT PRIMARY KEY,
                    bio TEXT,
                    website TEXT,
                    location TEXT,
                    avatar_media_url TEXT,
                    header_media_url TEXT,
                    uploaded_at TEXT,
                    imported_at TEXT
                )
            """))

            conn.execute(text("""
                INSERT OR REPLACE INTO archive_profiles
                (account_id, bio, website, location, avatar_media_url, header_media_url, uploaded_at, imported_at)
                VALUES (:account_id, :bio, :website, :location, :avatar_url, :header_url, :uploaded_at, :imported_at)
            """), {
                "account_id": account_id,
                "bio": description.get("bio"),
                "website": description.get("website"),
                "location": description.get("location"),
                "avatar_url": profile.get("avatarMediaUrl"),
                "header_url": profile.get("headerMediaUrl"),
                "uploaded_at": now,
                "imported_at": now
            })
            conn.commit()

        logger.debug(f"Imported profile data for account {account_id}")

    def _import_tweets(
        self,
        account_id: str,
        archive: Dict,
        merge_strategy: str
    ):
        """Import tweets (top 20 most liked + 10 most recent)."""
        if merge_strategy == "shadow_only":
            logger.debug("Skipping tweets import (shadow_only mode)")
            return

        tweets_data = archive.get("tweets", [])
        if not tweets_data:
            logger.debug(f"No tweets for account {account_id}")
            return

        # Parse and sort tweets
        parsed_tweets = []
        for entry in tweets_data:
            tweet = entry.get("tweet", {})
            try:
                parsed_tweets.append({
                    "tweet_id": tweet.get("id_str"),
                    "full_text": tweet.get("full_text"),
                    "created_at": tweet.get("created_at"),
                    "favorite_count": int(tweet.get("favorite_count", 0)),
                    "retweet_count": int(tweet.get("retweet_count", 0)),
                    "lang": tweet.get("lang")
                })
            except (ValueError, TypeError):
                continue

        # Get top 20 by likes
        top_liked = sorted(parsed_tweets, key=lambda t: t["favorite_count"], reverse=True)[:20]

        # Get 10 most recent (by creation date - would need proper parsing, for now just take last 10)
        recent = parsed_tweets[-10:] if len(parsed_tweets) >= 10 else parsed_tweets

        # Combine and deduplicate
        tweets_to_import = {t["tweet_id"]: t for t in (top_liked + recent) if t["tweet_id"]}

        now = datetime.utcnow().isoformat()

        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS archive_tweets (
                    account_id TEXT NOT NULL,
                    tweet_id TEXT NOT NULL,
                    full_text TEXT,
                    created_at TEXT,
                    favorite_count INTEGER,
                    retweet_count INTEGER,
                    lang TEXT,
                    uploaded_at TEXT,
                    imported_at TEXT,
                    UNIQUE(account_id, tweet_id)
                )
            """))

            for tweet in tweets_to_import.values():
                conn.execute(text("""
                    INSERT OR REPLACE INTO archive_tweets
                    (account_id, tweet_id, full_text, created_at, favorite_count, retweet_count, lang, uploaded_at, imported_at)
                    VALUES (:account_id, :tweet_id, :full_text, :created_at, :favorite_count, :retweet_count, :lang, :uploaded_at, :imported_at)
                """), {
                    "account_id": account_id,
                    "tweet_id": tweet["tweet_id"],
                    "full_text": tweet["full_text"],
                    "created_at": tweet["created_at"],
                    "favorite_count": tweet["favorite_count"],
                    "retweet_count": tweet["retweet_count"],
                    "lang": tweet["lang"],
                    "uploaded_at": now,
                    "imported_at": now
                })

            conn.commit()

        logger.debug(f"Imported {len(tweets_to_import)} tweets for account {account_id}")

    def _import_likes(
        self,
        account_id: str,
        archive: Dict,
        merge_strategy: str
    ):
        """Import likes data (all liked tweets)."""
        if merge_strategy == "shadow_only":
            logger.debug("Skipping likes import (shadow_only mode)")
            return

        likes_data = archive.get("like", [])
        if not likes_data:
            logger.debug(f"No likes for account {account_id}")
            return

        now = datetime.utcnow().isoformat()

        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS archive_likes (
                    account_id TEXT NOT NULL,
                    tweet_id TEXT NOT NULL,
                    full_text TEXT,
                    expanded_url TEXT,
                    uploaded_at TEXT,
                    imported_at TEXT,
                    UNIQUE(account_id, tweet_id)
                )
            """))

            for entry in likes_data:
                like = entry.get("like", {})
                tweet_id = like.get("tweetId")
                if not tweet_id:
                    continue

                conn.execute(text("""
                    INSERT OR REPLACE INTO archive_likes
                    (account_id, tweet_id, full_text, expanded_url, uploaded_at, imported_at)
                    VALUES (:account_id, :tweet_id, :full_text, :expanded_url, :uploaded_at, :imported_at)
                """), {
                    "account_id": account_id,
                    "tweet_id": tweet_id,
                    "full_text": like.get("fullText"),
                    "expanded_url": like.get("expandedUrl"),
                    "uploaded_at": now,
                    "imported_at": now
                })

            conn.commit()

        logger.debug(f"Imported {len(likes_data)} likes for account {account_id}")
