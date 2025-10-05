"""Integration tests for Supabase connectivity and cache behavior."""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from src.config import get_supabase_config
from src.data.fetcher import CachedDataFetcher

# Conditional skip marker for tests requiring Supabase
REQUIRES_SUPABASE = pytest.mark.skipif(
    not os.getenv("SUPABASE_KEY"),
    reason="SUPABASE_KEY environment variable not configured",
)


@pytest.mark.integration
@REQUIRES_SUPABASE
def test_supabase_connection() -> None:
    cfg = get_supabase_config()
    with httpx.Client(base_url=cfg.url, headers=cfg.rest_headers, timeout=15.0) as client:
        response = client.get(
            "/rest/v1/profile",
            params={"select": "account_id", "limit": 1},
            headers={"Range": "0-0"},
        )
    assert response.status_code in (200, 206), f"Supabase responded with {response.status_code}"
    assert response.json(), "Supabase response did not include data"


@pytest.mark.integration
@REQUIRES_SUPABASE
def test_profile_count(tmp_path: Path) -> None:
    expected_min_profiles = 275
    with CachedDataFetcher(cache_db=tmp_path / "cache.db", max_age_days=7) as fetcher:
        profiles = fetcher.fetch_profiles(force_refresh=True)
    assert len(profiles) >= expected_min_profiles, (
        f"Expected at least {expected_min_profiles} profiles"
    )


@pytest.mark.integration
@REQUIRES_SUPABASE
def test_cache_persistence(tmp_path: Path) -> None:
    cache_db = tmp_path / "cache.db"
    expected_min_profiles = 275
    with CachedDataFetcher(cache_db=cache_db, max_age_days=7) as fetcher:
        profiles_first = fetcher.fetch_profiles(force_refresh=True)
        assert len(profiles_first) >= expected_min_profiles
        status_after_first = fetcher.cache_status()["profile"]

        profiles_cached = fetcher.fetch_profiles()
        assert len(profiles_cached) >= expected_min_profiles
        status_after_second = fetcher.cache_status()["profile"]

    assert status_after_second["fetched_at"] == status_after_first["fetched_at"], "Cache should not refresh on second access"
