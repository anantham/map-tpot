"""Property-based tests for configuration module using Hypothesis.

These tests use property-based testing to generate thousands of random inputs
and verify that invariants hold for all of them. This catches edge cases that
example-based tests miss.

To run: pytest tests/test_config_properties.py -v
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, strategies as st

from src.config import (
    CACHE_DB_ENV,
    CACHE_MAX_AGE_ENV,
    SUPABASE_KEY_KEY,
    SUPABASE_URL_KEY,
    get_cache_settings,
    get_supabase_config,
)


# ==============================================================================
# Hypothesis Strategies
# ==============================================================================

# Strategy for valid absolute paths
valid_absolute_paths = st.one_of(
    st.just("/tmp/cache.db"),
    st.just("/var/cache/app.db"),
    st.just("/home/user/.cache/data.db"),
    st.builds(
        lambda x: f"/tmp/{x}.db",
        st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")), min_size=1, max_size=20)
    )
)

# Strategy for positive integers (cache max age)
positive_integers = st.integers(min_value=1, max_value=365)

# Strategy for any integers (including edge cases)
any_integers = st.integers(min_value=-1000, max_value=1000)

# Strategy for valid URLs
valid_urls = st.one_of(
    st.just("https://example.supabase.co"),
    st.just("https://test.supabase.co"),
    st.builds(
        lambda x: f"https://{x}.supabase.co",
        st.text(alphabet=st.characters(whitelist_categories=("Ll", "Nd")), min_size=3, max_size=20)
    )
)

# Strategy for API keys
api_keys = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=20,
    max_size=100
)


# ==============================================================================
# Property-Based Tests for get_cache_settings()
# ==============================================================================

@pytest.mark.property
@given(path=valid_absolute_paths, max_age=positive_integers)
def test_cache_settings_path_always_absolute(path, max_age):
    """Property: Cache path is always absolute regardless of input."""
    with patch.dict(
        os.environ,
        {CACHE_DB_ENV: path, CACHE_MAX_AGE_ENV: str(max_age)},
        clear=True,
    ):
        settings = get_cache_settings()

        # PROPERTY: Output path is always absolute
        assert settings.path.is_absolute(), \
            f"Path {settings.path} should be absolute for input {path}"


@pytest.mark.property
@given(path=valid_absolute_paths, max_age=positive_integers)
def test_cache_settings_max_age_is_integer(path, max_age):
    """Property: max_age_days is always an integer type."""
    with patch.dict(
        os.environ,
        {CACHE_DB_ENV: path, CACHE_MAX_AGE_ENV: str(max_age)},
        clear=True,
    ):
        settings = get_cache_settings()

        # PROPERTY: max_age_days is always int type
        assert isinstance(settings.max_age_days, int), \
            f"max_age_days should be int, got {type(settings.max_age_days)}"


@pytest.mark.property
@given(path=valid_absolute_paths, max_age=positive_integers)
def test_cache_settings_preserves_input_values(path, max_age):
    """Property: Output matches input for valid values."""
    with patch.dict(
        os.environ,
        {CACHE_DB_ENV: path, CACHE_MAX_AGE_ENV: str(max_age)},
        clear=True,
    ):
        settings = get_cache_settings()

        # PROPERTY: Input values are preserved
        assert settings.path == Path(path)
        assert settings.max_age_days == max_age


@pytest.mark.property
@given(max_age=any_integers)
def test_cache_settings_accepts_any_integer_max_age(max_age):
    """Property: Any integer max_age is accepted (no validation enforced)."""
    with patch.dict(
        os.environ,
        {CACHE_DB_ENV: "/tmp/test.db", CACHE_MAX_AGE_ENV: str(max_age)},
        clear=True,
    ):
        settings = get_cache_settings()

        # PROPERTY: Any integer is accepted (even negative, zero)
        assert settings.max_age_days == max_age
        assert isinstance(settings.max_age_days, int)


@pytest.mark.property
@given(invalid_max_age=st.text(
    alphabet=st.characters(
        blacklist_characters="0123456789-",
        blacklist_categories=("Cc",)  # Exclude control characters (including null bytes)
    ),
    min_size=1
))
def test_cache_settings_rejects_non_numeric_max_age(invalid_max_age):
    """Property: Non-numeric max_age raises RuntimeError."""
    # Skip if the text happens to be convertible to int
    try:
        int(invalid_max_age)
        pytest.skip("Generated text is convertible to int")
    except ValueError:
        pass

    with patch.dict(
        os.environ,
        {CACHE_DB_ENV: "/tmp/test.db", CACHE_MAX_AGE_ENV: invalid_max_age},
        clear=True,
    ):
        # PROPERTY: Non-numeric values raise RuntimeError
        with pytest.raises(RuntimeError, match="must be an integer"):
            get_cache_settings()


# ==============================================================================
# Property-Based Tests for get_supabase_config()
# ==============================================================================

@pytest.mark.property
@given(url=valid_urls, key=api_keys)
def test_supabase_config_creates_valid_config(url, key):
    """Property: Valid inputs always create valid config."""
    with patch.dict(
        os.environ,
        {SUPABASE_URL_KEY: url, SUPABASE_KEY_KEY: key},
        clear=True,
    ):
        config = get_supabase_config()

        # PROPERTY: Config has correct structure
        assert config.url == url
        assert config.key == key
        assert hasattr(config, 'rest_headers')


@pytest.mark.property
@given(url=valid_urls, key=api_keys)
def test_supabase_config_rest_headers_always_dict(url, key):
    """Property: rest_headers always returns a dict."""
    with patch.dict(
        os.environ,
        {SUPABASE_URL_KEY: url, SUPABASE_KEY_KEY: key},
        clear=True,
    ):
        config = get_supabase_config()

        # PROPERTY: rest_headers is always a dict
        headers = config.rest_headers
        assert isinstance(headers, dict)
        assert len(headers) > 0


@pytest.mark.property
@given(url=valid_urls, key=api_keys)
def test_supabase_config_rest_headers_contains_key(url, key):
    """Property: rest_headers always contains the API key."""
    with patch.dict(
        os.environ,
        {SUPABASE_URL_KEY: url, SUPABASE_KEY_KEY: key},
        clear=True,
    ):
        config = get_supabase_config()

        # PROPERTY: API key appears in headers
        headers = config.rest_headers
        assert "apikey" in headers
        assert headers["apikey"] == key
        assert "Authorization" in headers
        assert key in headers["Authorization"]


@pytest.mark.property
@given(url=valid_urls, key=api_keys)
def test_supabase_config_rest_headers_idempotent(url, key):
    """Property: Calling rest_headers multiple times returns same result."""
    with patch.dict(
        os.environ,
        {SUPABASE_URL_KEY: url, SUPABASE_KEY_KEY: key},
        clear=True,
    ):
        config = get_supabase_config()

        # PROPERTY: Multiple calls are idempotent
        headers1 = config.rest_headers
        headers2 = config.rest_headers
        assert headers1 == headers2


@pytest.mark.property
@given(url=valid_urls)
def test_supabase_config_missing_key_always_raises(url):
    """Property: Missing API key always raises RuntimeError."""
    with patch.dict(
        os.environ,
        {SUPABASE_URL_KEY: url},
        clear=True,
    ):
        # PROPERTY: Missing key always raises
        with pytest.raises(RuntimeError, match="SUPABASE_KEY"):
            get_supabase_config()


@pytest.mark.property
@given(key=api_keys)
def test_supabase_config_uses_default_url_when_missing(key):
    """Property: Missing URL uses default."""
    with patch.dict(
        os.environ,
        {SUPABASE_KEY_KEY: key},
        clear=True,
    ):
        config = get_supabase_config()

        # PROPERTY: Default URL is used when not specified
        assert config.url is not None
        assert len(config.url) > 0
        assert config.key == key


# ==============================================================================
# Property-Based Tests for Path Handling
# ==============================================================================

@pytest.mark.property
@given(
    path=st.one_of(
        st.just("~/cache.db"),
        st.just("~/.cache/app.db"),
        st.just("~/data/test.db")
    )
)
def test_cache_settings_expands_tilde_in_all_paths(path):
    """Property: Tilde is always expanded in paths."""
    with patch.dict(
        os.environ,
        {CACHE_DB_ENV: path, CACHE_MAX_AGE_ENV: "7"},
        clear=True,
    ):
        settings = get_cache_settings()

        # PROPERTY: Tilde is expanded (path doesn't start with ~)
        assert not str(settings.path).startswith("~"), \
            f"Tilde should be expanded in {settings.path}"
        assert settings.path.is_absolute()


@pytest.mark.property
@given(
    path=st.one_of(
        st.just("./relative/cache.db"),
        st.just("relative/cache.db"),
        st.just("../cache.db")
    )
)
def test_cache_settings_resolves_relative_paths(path):
    """Property: Relative paths are resolved to absolute."""
    with patch.dict(
        os.environ,
        {CACHE_DB_ENV: path, CACHE_MAX_AGE_ENV: "7"},
        clear=True,
    ):
        settings = get_cache_settings()

        # PROPERTY: Relative paths become absolute
        assert settings.path.is_absolute(), \
            f"Path {settings.path} should be absolute for input {path}"


# ==============================================================================
# Integration Property Tests
# ==============================================================================

@pytest.mark.property
@given(
    supabase_url=valid_urls,
    supabase_key=api_keys,
    cache_path=valid_absolute_paths,
    cache_max_age=positive_integers
)
def test_complete_config_loading(supabase_url, supabase_key, cache_path, cache_max_age):
    """Property: All config can be loaded together without conflicts."""
    with patch.dict(
        os.environ,
        {
            SUPABASE_URL_KEY: supabase_url,
            SUPABASE_KEY_KEY: supabase_key,
            CACHE_DB_ENV: cache_path,
            CACHE_MAX_AGE_ENV: str(cache_max_age),
        },
        clear=True,
    ):
        # PROPERTY: Both configs load successfully
        supabase_config = get_supabase_config()
        cache_settings = get_cache_settings()

        # Both should be valid
        assert supabase_config.url == supabase_url
        assert supabase_config.key == supabase_key
        assert cache_settings.path == Path(cache_path)
        assert cache_settings.max_age_days == cache_max_age
