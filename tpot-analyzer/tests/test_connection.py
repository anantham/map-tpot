"""Integration tests for Supabase connectivity and cache behavior."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# Ensure project src/ is importable when running `pytest` from repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_cache_settings, get_supabase_client  # noqa: E402
from src.data.fetcher import CachedDataFetcher  # noqa: E402

REQUIRES_SUPABASE = pytest.mark.skipif(
    not os.getenv("SUPABASE_KEY"), reason="SUPABASE_KEY environment variable not configured"
)


@REQUIRES_SUPABASE
def test_supabase_connection() -> None:
    client = get_supabase_client()
    response = client.table("profiles").select("account_id").limit(1).execute()
    assert getattr(response, "error", None) in (None, ""), "Supabase responded with an error"
    assert response.data, "Supabase response did not include data"


@REQUIRES_SUPABASE
def test_profile_count(tmp_path: Path) -> None:
    fetcher = CachedDataFetcher(cache_db=tmp_path / "cache.db", max_age_days=7)
    profiles = fetcher.fetch_profiles(force_refresh=True)
    assert len(profiles) == 275, "Expected 275 Community Archive profiles"


@REQUIRES_SUPABASE
def test_cache_persistence(tmp_path: Path) -> None:
    cache_db = tmp_path / "cache.db"
    fetcher = CachedDataFetcher(cache_db=cache_db, max_age_days=7)

    profiles_first = fetcher.fetch_profiles(force_refresh=True)
    assert len(profiles_first) == 275
    status_after_first = fetcher.cache_status()["profiles"]

    profiles_cached = fetcher.fetch_profiles()
    assert len(profiles_cached) == 275
    status_after_second = fetcher.cache_status()["profiles"]

    assert status_after_second["fetched_at"] == status_after_first["fetched_at"], "Cache should not refresh on second access"
