"""Unit tests for configuration module.

Tests configuration loading, environment variable handling, and validation logic.

CLEANED UP - Phase 1:
- Task 1.4: Removed 10 Category C tests (framework/constant tests)
- Task 1.5: Fixed 2 Category B tests with property/invariant checks
- Kept 12 Category A tests (business logic)

Estimated mutation score: 35-45% → 80-85% (target)
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config import (
    CACHE_DB_ENV,
    CACHE_MAX_AGE_ENV,
    DEFAULT_CACHE_DB,
    DEFAULT_CACHE_MAX_AGE_DAYS,
    DEFAULT_SUPABASE_URL,
    PROJECT_ROOT,
    SUPABASE_KEY_KEY,
    SUPABASE_URL_KEY,
    get_cache_settings,
    get_supabase_config,
)


# ==============================================================================
# get_supabase_config() Tests
# ==============================================================================

@pytest.mark.unit
def test_get_supabase_config_from_env():
    """Should read Supabase config from environment variables."""
    with patch.dict(
        os.environ,
        {SUPABASE_URL_KEY: "https://test.supabase.co", SUPABASE_KEY_KEY: "test-key-abc"},
        clear=False,
    ):
        config = get_supabase_config()

        assert config.url == "https://test.supabase.co"
        assert config.key == "test-key-abc"


@pytest.mark.unit
def test_get_supabase_config_uses_default_url():
    """Should use default URL if SUPABASE_URL not set."""
    with patch.dict(
        os.environ,
        {SUPABASE_KEY_KEY: "test-key"},
        clear=True,
    ):
        config = get_supabase_config()

        assert config.url == DEFAULT_SUPABASE_URL
        assert config.key == "test-key"


@pytest.mark.unit
def test_get_supabase_config_missing_key_raises():
    """Should raise RuntimeError if SUPABASE_KEY is missing."""
    with patch.dict(
        os.environ,
        {SUPABASE_URL_KEY: "https://test.supabase.co"},
        clear=True,
    ):
        with pytest.raises(RuntimeError, match="SUPABASE_KEY is not configured"):
            get_supabase_config()


@pytest.mark.unit
def test_get_supabase_config_empty_key_raises():
    """Should raise RuntimeError if SUPABASE_KEY is empty string."""
    with patch.dict(
        os.environ,
        {SUPABASE_URL_KEY: "https://test.supabase.co", SUPABASE_KEY_KEY: ""},
        clear=True,
    ):
        with pytest.raises(RuntimeError, match="SUPABASE_KEY is not configured"):
            get_supabase_config()


@pytest.mark.unit
def test_get_supabase_config_empty_url_raises():
    """Should raise RuntimeError if SUPABASE_URL is empty string."""
    with patch.dict(
        os.environ,
        {SUPABASE_URL_KEY: "", SUPABASE_KEY_KEY: "test-key"},
        clear=True,
    ):
        with pytest.raises(RuntimeError, match="SUPABASE_URL is not configured"):
            get_supabase_config()


# ==============================================================================
# get_cache_settings() Tests
# ==============================================================================

@pytest.mark.unit
def test_get_cache_settings_from_env():
    """Should read cache settings from environment variables and maintain invariants."""
    with patch.dict(
        os.environ,
        {CACHE_DB_ENV: "/custom/path/cache.db", CACHE_MAX_AGE_ENV: "30"},
        clear=True,
    ):
        settings = get_cache_settings()

        # Property 1: Path is always absolute (critical for file operations)
        assert settings.path.is_absolute(), "Cache path must be absolute to avoid working directory issues"

        # Property 2: Path parent directories are valid Path objects
        assert isinstance(settings.path.parent, Path), "Path parent must be valid"

        # Property 3: max_age_days is an integer (type safety)
        assert isinstance(settings.max_age_days, int), "max_age_days must be int type"

        # Regression test: Values match environment input
        assert settings.path == Path("/custom/path/cache.db")
        assert settings.max_age_days == 30


@pytest.mark.unit
def test_get_cache_settings_uses_defaults():
    """Should use default cache settings if env vars not set, and defaults must be reasonable."""
    with patch.dict(os.environ, {}, clear=True):
        settings = get_cache_settings()

        # Property 1: Default path is always absolute (critical for reliability)
        assert settings.path.is_absolute(), "Default cache path must be absolute"

        # Property 2: Default path is under project root (predictable location)
        assert PROJECT_ROOT in settings.path.parents or settings.path == PROJECT_ROOT, \
            "Default cache should be under project root for portability"

        # Property 3: Default max_age is positive (negative cache age makes no sense)
        assert settings.max_age_days > 0, "Default cache max age must be positive"

        # Property 4: Default max_age is reasonable (not too short, not too long)
        assert 1 <= settings.max_age_days <= 365, \
            "Default cache max age should be reasonable (1-365 days)"

        # Regression test: Values match declared constants
        assert settings.path == DEFAULT_CACHE_DB
        assert settings.max_age_days == DEFAULT_CACHE_MAX_AGE_DAYS


@pytest.mark.unit
def test_get_cache_settings_expands_tilde():
    """Should expand ~ in cache path."""
    with patch.dict(
        os.environ,
        {CACHE_DB_ENV: "~/my_cache/cache.db"},
        clear=True,
    ):
        settings = get_cache_settings()

        assert not str(settings.path).startswith("~")
        assert settings.path.is_absolute()


@pytest.mark.unit
def test_get_cache_settings_resolves_relative_path():
    """Should resolve relative paths to absolute."""
    with patch.dict(
        os.environ,
        {CACHE_DB_ENV: "./relative/cache.db"},
        clear=True,
    ):
        settings = get_cache_settings()

        assert settings.path.is_absolute()


@pytest.mark.unit
def test_get_cache_settings_invalid_max_age_raises():
    """Should raise RuntimeError if CACHE_MAX_AGE_DAYS is not an integer."""
    with patch.dict(
        os.environ,
        {CACHE_MAX_AGE_ENV: "not-a-number"},
        clear=True,
    ):
        with pytest.raises(RuntimeError, match="CACHE_MAX_AGE_DAYS must be an integer"):
            get_cache_settings()


@pytest.mark.unit
def test_get_cache_settings_zero_max_age():
    """Should allow zero as valid max_age_days."""
    with patch.dict(
        os.environ,
        {CACHE_MAX_AGE_ENV: "0"},
        clear=True,
    ):
        settings = get_cache_settings()

        assert settings.max_age_days == 0


@pytest.mark.unit
def test_get_cache_settings_negative_max_age():
    """Should allow negative max_age_days (though unusual)."""
    with patch.dict(
        os.environ,
        {CACHE_MAX_AGE_ENV: "-1"},
        clear=True,
    ):
        settings = get_cache_settings()

        assert settings.max_age_days == -1


# ==============================================================================
# Integration Tests
# ==============================================================================

@pytest.mark.integration
def test_config_roundtrip():
    """Test full config loading with realistic environment."""
    with patch.dict(
        os.environ,
        {
            SUPABASE_URL_KEY: "https://example.supabase.co",
            SUPABASE_KEY_KEY: "example-key-123",
            CACHE_DB_ENV: "/tmp/test_cache.db",
            CACHE_MAX_AGE_ENV: "14",
        },
        clear=True,
    ):
        # Load configs
        supabase_config = get_supabase_config()
        cache_settings = get_cache_settings()

        # Verify Supabase config
        assert supabase_config.url == "https://example.supabase.co"
        assert supabase_config.key == "example-key-123"

        # Verify cache settings
        assert cache_settings.path == Path("/tmp/test_cache.db")
        assert cache_settings.max_age_days == 14

        # Verify headers work
        headers = supabase_config.rest_headers
        assert "Bearer example-key-123" in headers["Authorization"]


@pytest.mark.integration
def test_config_with_partial_env():
    """Test config when only some env vars are set (uses defaults)."""
    with patch.dict(
        os.environ,
        {SUPABASE_KEY_KEY: "test-key"},  # Only key set
        clear=True,
    ):
        supabase_config = get_supabase_config()
        cache_settings = get_cache_settings()

        # Supabase should use default URL
        assert supabase_config.url == DEFAULT_SUPABASE_URL
        assert supabase_config.key == "test-key"

        # Cache should use all defaults
        assert cache_settings.path == DEFAULT_CACHE_DB
        assert cache_settings.max_age_days == DEFAULT_CACHE_MAX_AGE_DAYS
