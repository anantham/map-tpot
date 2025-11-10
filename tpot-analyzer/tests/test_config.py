"""Unit tests for configuration module.

Tests configuration loading, environment variable handling, and dataclasses.
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
    CacheSettings,
    SupabaseConfig,
    get_cache_settings,
    get_supabase_config,
)


# ==============================================================================
# SupabaseConfig Tests
# ==============================================================================

@pytest.mark.unit
def test_supabase_config_creation():
    """SupabaseConfig should store url and key."""
    config = SupabaseConfig(url="https://example.supabase.co", key="test-key-123")

    assert config.url == "https://example.supabase.co"
    assert config.key == "test-key-123"


@pytest.mark.unit
def test_supabase_config_frozen():
    """SupabaseConfig should be immutable (frozen dataclass)."""
    config = SupabaseConfig(url="https://example.supabase.co", key="test-key")

    with pytest.raises(AttributeError):
        config.url = "https://different.supabase.co"  # type: ignore


@pytest.mark.unit
def test_supabase_config_rest_headers():
    """SupabaseConfig.rest_headers should return proper headers."""
    config = SupabaseConfig(url="https://example.supabase.co", key="test-key-123")

    headers = config.rest_headers

    assert headers["apikey"] == "test-key-123"
    assert headers["Authorization"] == "Bearer test-key-123"
    assert headers["Content-Type"] == "application/json"
    assert headers["Accept"] == "application/json"
    assert headers["Prefer"] == "count=exact"


@pytest.mark.unit
def test_supabase_config_rest_headers_multiple_calls():
    """rest_headers should return consistent results across calls."""
    config = SupabaseConfig(url="https://example.supabase.co", key="test-key")

    headers1 = config.rest_headers
    headers2 = config.rest_headers

    assert headers1 == headers2


# ==============================================================================
# CacheSettings Tests
# ==============================================================================

@pytest.mark.unit
def test_cache_settings_creation():
    """CacheSettings should store path and max_age_days."""
    settings = CacheSettings(path=Path("/tmp/cache.db"), max_age_days=14)

    assert settings.path == Path("/tmp/cache.db")
    assert settings.max_age_days == 14


@pytest.mark.unit
def test_cache_settings_frozen():
    """CacheSettings should be immutable (frozen dataclass)."""
    settings = CacheSettings(path=Path("/tmp/cache.db"), max_age_days=7)

    with pytest.raises(AttributeError):
        settings.max_age_days = 30  # type: ignore


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
    """Should read cache settings from environment variables."""
    with patch.dict(
        os.environ,
        {CACHE_DB_ENV: "/custom/path/cache.db", CACHE_MAX_AGE_ENV: "30"},
        clear=True,
    ):
        settings = get_cache_settings()

        assert settings.path == Path("/custom/path/cache.db")
        assert settings.max_age_days == 30


@pytest.mark.unit
def test_get_cache_settings_uses_defaults():
    """Should use default cache settings if env vars not set."""
    with patch.dict(os.environ, {}, clear=True):
        settings = get_cache_settings()

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
# Module Constants Tests
# ==============================================================================

@pytest.mark.unit
def test_project_root_is_absolute():
    """PROJECT_ROOT should be an absolute path."""
    assert PROJECT_ROOT.is_absolute()


@pytest.mark.unit
def test_project_root_points_to_tpot_analyzer():
    """PROJECT_ROOT should point to tpot-analyzer directory."""
    # PROJECT_ROOT is src/../ so it should be the tpot-analyzer dir
    assert PROJECT_ROOT.name == "tpot-analyzer"


@pytest.mark.unit
def test_default_cache_db_under_project_root():
    """DEFAULT_CACHE_DB should be under PROJECT_ROOT."""
    assert DEFAULT_CACHE_DB.is_relative_to(PROJECT_ROOT)


@pytest.mark.unit
def test_default_supabase_url_is_valid():
    """DEFAULT_SUPABASE_URL should be a valid HTTPS URL."""
    assert DEFAULT_SUPABASE_URL.startswith("https://")
    assert ".supabase.co" in DEFAULT_SUPABASE_URL


@pytest.mark.unit
def test_default_cache_max_age_positive():
    """DEFAULT_CACHE_MAX_AGE_DAYS should be positive."""
    assert DEFAULT_CACHE_MAX_AGE_DAYS > 0


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
