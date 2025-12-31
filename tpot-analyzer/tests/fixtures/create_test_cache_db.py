"""Create a deterministic cache.db for tests that rely on CachedDataFetcher."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict

import pandas as pd

from src.data.fetcher import CachedDataFetcher


@dataclass(frozen=True)
class CacheTableCounts:
    accounts: int
    profiles: int
    followers: int
    following: int

    def as_dict(self) -> Dict[str, int]:
        return {
            "account": self.accounts,
            "profile": self.profiles,
            "followers": self.followers,
            "following": self.following,
        }


def create_test_cache_db(cache_path: Path) -> CacheTableCounts:
    """Create a minimal cache.db with deterministic data and fresh metadata."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.utcnow().isoformat()
    accounts = pd.DataFrame(
        [
            {
                "account_id": "a",
                "username": "user_a",
                "account_display_name": "User A",
                "created_at": now,
                "created_via": "web",
                "num_followers": 3,
                "num_following": 2,
                "num_tweets": 10,
                "num_likes": 5,
            },
            {
                "account_id": "b",
                "username": "user_b",
                "account_display_name": "User B",
                "created_at": now,
                "created_via": "web",
                "num_followers": 2,
                "num_following": 2,
                "num_tweets": 7,
                "num_likes": 3,
            },
            {
                "account_id": "c",
                "username": "user_c",
                "account_display_name": "User C",
                "created_at": now,
                "created_via": "web",
                "num_followers": 1,
                "num_following": 1,
                "num_tweets": 2,
                "num_likes": 1,
            },
            {
                "account_id": "d",
                "username": "user_d",
                "account_display_name": "User D",
                "created_at": now,
                "created_via": "web",
                "num_followers": 0,
                "num_following": 1,
                "num_tweets": 1,
                "num_likes": 0,
            },
        ]
    )

    profiles = pd.DataFrame(
        [
            {
                "account_id": "a",
                "bio": "Bio A",
                "website": "https://example.com/a",
                "location": "Test City",
                "avatar_media_url": None,
                "header_media_url": None,
            },
            {
                "account_id": "b",
                "bio": "Bio B",
                "website": None,
                "location": None,
                "avatar_media_url": None,
                "header_media_url": None,
            },
        ]
    )

    followers = pd.DataFrame(
        [
            {"follower_account_id": "b", "account_id": "a"},
            {"follower_account_id": "c", "account_id": "a"},
            {"follower_account_id": "a", "account_id": "b"},
        ]
    )

    following = pd.DataFrame(
        [
            {"account_id": "a", "following_account_id": "b"},
            {"account_id": "b", "following_account_id": "a"},
            {"account_id": "c", "following_account_id": "a"},
            {"account_id": "d", "following_account_id": "a"},
        ]
    )

    fetcher = CachedDataFetcher(cache_db=cache_path, max_age_days=3650)
    try:
        fetcher._write_cache("account", accounts)
        fetcher._write_cache("profile", profiles)
        fetcher._write_cache("followers", followers)
        fetcher._write_cache("following", following)
    finally:
        fetcher.close()

    return CacheTableCounts(
        accounts=len(accounts),
        profiles=len(profiles),
        followers=len(followers),
        following=len(following),
    )
