"""Tests for CachedDataFetcher - cache behavior, expiry, and HTTP error handling.

This test module covers:
- Cache hit/miss behavior
- Cache expiry logic (max_age_days)
- Force refresh functionality
- HTTP error handling (timeouts, 404s, 500s, network errors)
- Cache status reporting
- Context manager lifecycle
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import httpx
import pandas as pd
import pytest
from sqlalchemy import create_engine, select

from src.data.fetcher import CachedDataFetcher


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def mock_http_client():
    """Create a mock httpx.Client for testing without network calls."""
    client = Mock(spec=httpx.Client)
    client.close = Mock()
    return client


@pytest.fixture
def sample_accounts_response():
    """Sample Supabase response for accounts table."""
    return [
        {"account_id": "123", "username": "alice", "followers_count": 1000},
        {"account_id": "456", "username": "bob", "followers_count": 500},
    ]


@pytest.fixture
def fetcher_with_mock_client(temp_cache_db, mock_http_client):
    """Create a CachedDataFetcher with mocked HTTP client for testing."""
    fetcher = CachedDataFetcher(cache_db=temp_cache_db, http_client=mock_http_client, max_age_days=7)
    return fetcher


# ==============================================================================
# Cache Hit/Miss Tests
# ==============================================================================

@pytest.mark.unit
def test_cache_miss_fetches_from_supabase(fetcher_with_mock_client, mock_http_client, sample_accounts_response):
    """When cache is empty, should fetch from Supabase and cache the result."""
    # Setup mock response
    mock_response = Mock()
    mock_response.json.return_value = sample_accounts_response
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response

    # Fetch data (cache miss)
    df = fetcher_with_mock_client.fetch_accounts(use_cache=True)

    # Verify HTTP call was made
    mock_http_client.get.assert_called_once()
    assert mock_http_client.get.call_args[0][0] == "/rest/v1/account"

    # Verify data was returned correctly
    assert len(df) == 2
    assert list(df["username"]) == ["alice", "bob"]


@pytest.mark.unit
def test_cache_hit_skips_supabase(fetcher_with_mock_client, mock_http_client, sample_accounts_response):
    """When cache is fresh, should return cached data without calling Supabase."""
    # Setup mock response
    mock_response = Mock()
    mock_response.json.return_value = sample_accounts_response
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response

    # First fetch (cache miss)
    df1 = fetcher_with_mock_client.fetch_accounts(use_cache=True)
    assert len(df1) == 2

    # Reset mock to verify second call doesn't happen
    mock_http_client.get.reset_mock()

    # Second fetch (cache hit)
    df2 = fetcher_with_mock_client.fetch_accounts(use_cache=True)

    # Verify no HTTP call was made
    mock_http_client.get.assert_not_called()

    # Verify data matches
    assert len(df2) == 2
    pd.testing.assert_frame_equal(df1, df2)


@pytest.mark.unit
def test_use_cache_false_always_fetches(fetcher_with_mock_client, mock_http_client, sample_accounts_response):
    """When use_cache=False, should always fetch from Supabase even if cache exists."""
    # Setup mock response
    mock_response = Mock()
    mock_response.json.return_value = sample_accounts_response
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response

    # First fetch with caching
    fetcher_with_mock_client.fetch_accounts(use_cache=True)
    mock_http_client.get.reset_mock()

    # Second fetch with use_cache=False (should fetch from Supabase)
    df = fetcher_with_mock_client.fetch_accounts(use_cache=False)

    # Verify HTTP call was made
    mock_http_client.get.assert_called_once()
    assert len(df) == 2


@pytest.mark.unit
def test_force_refresh_bypasses_cache(fetcher_with_mock_client, mock_http_client, sample_accounts_response):
    """When force_refresh=True, should fetch from Supabase and update cache."""
    # Setup mock response
    mock_response = Mock()
    mock_response.json.return_value = sample_accounts_response
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response

    # First fetch (populate cache)
    fetcher_with_mock_client.fetch_accounts(use_cache=True)
    mock_http_client.get.reset_mock()

    # Change mock response for second fetch
    updated_response = sample_accounts_response + [{"account_id": "789", "username": "charlie", "followers_count": 2000}]
    mock_response.json.return_value = updated_response

    # Force refresh (should fetch new data)
    df = fetcher_with_mock_client.fetch_accounts(use_cache=True, force_refresh=True)

    # Verify HTTP call was made
    mock_http_client.get.assert_called_once()
    assert len(df) == 3  # Should have new data


# ==============================================================================
# Cache Expiry Tests
# ==============================================================================

@pytest.mark.integration
def test_expired_cache_triggers_refresh(temp_cache_db, mock_http_client, sample_accounts_response):
    """When cache is older than max_age_days, should fetch from Supabase."""
    # Create fetcher with 1-day expiry
    fetcher = CachedDataFetcher(cache_db=temp_cache_db, http_client=mock_http_client, max_age_days=1)

    # Setup mock response
    mock_response = Mock()
    mock_response.json.return_value = sample_accounts_response
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response

    # First fetch (populate cache)
    fetcher.fetch_accounts(use_cache=True)
    mock_http_client.get.reset_mock()

    # Manually set cache timestamp to 2 days ago (expired)
    with fetcher.engine.begin() as conn:
        two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
        conn.execute(
            fetcher._meta_table.update()
            .where(fetcher._meta_table.c.table_name == "account")
            .values(fetched_at=two_days_ago)
        )

    # Fetch again (should detect expiry and refresh)
    df = fetcher.fetch_accounts(use_cache=True)

    # Verify HTTP call was made due to expiry
    mock_http_client.get.assert_called_once()
    assert len(df) == 2


@pytest.mark.integration
def test_fresh_cache_not_expired(temp_cache_db, mock_http_client, sample_accounts_response):
    """When cache is fresher than max_age_days, should use cached data."""
    # Create fetcher with 7-day expiry
    fetcher = CachedDataFetcher(cache_db=temp_cache_db, http_client=mock_http_client, max_age_days=7)

    # Setup mock response
    mock_response = Mock()
    mock_response.json.return_value = sample_accounts_response
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response

    # First fetch (populate cache)
    fetcher.fetch_accounts(use_cache=True)
    mock_http_client.get.reset_mock()

    # Manually set cache timestamp to 3 days ago (still fresh)
    with fetcher.engine.begin() as conn:
        three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
        conn.execute(
            fetcher._meta_table.update()
            .where(fetcher._meta_table.c.table_name == "account")
            .values(fetched_at=three_days_ago)
        )

    # Fetch again (should use cache)
    df = fetcher.fetch_accounts(use_cache=True)

    # Verify no HTTP call was made
    mock_http_client.get.assert_not_called()
    assert len(df) == 2


# ==============================================================================
# HTTP Error Handling Tests
# ==============================================================================

@pytest.mark.unit
def test_http_404_error_raises_runtime_error(fetcher_with_mock_client, mock_http_client):
    """When Supabase returns 404, should raise RuntimeError with clear message."""
    # Setup mock to raise 404
    mock_http_client.get.side_effect = httpx.HTTPStatusError(
        "404 Not Found",
        request=Mock(url="http://test.com"),
        response=Mock(status_code=404)
    )

    # Verify error is raised and wrapped
    with pytest.raises(RuntimeError, match="Supabase REST query for 'account' failed"):
        fetcher_with_mock_client.fetch_accounts(use_cache=False)


@pytest.mark.unit
def test_http_500_error_raises_runtime_error(fetcher_with_mock_client, mock_http_client):
    """When Supabase returns 500, should raise RuntimeError."""
    # Setup mock to raise 500
    mock_http_client.get.side_effect = httpx.HTTPStatusError(
        "500 Internal Server Error",
        request=Mock(url="http://test.com"),
        response=Mock(status_code=500)
    )

    # Verify error is raised
    with pytest.raises(RuntimeError, match="Supabase REST query for 'account' failed"):
        fetcher_with_mock_client.fetch_accounts(use_cache=False)


@pytest.mark.unit
def test_network_timeout_raises_runtime_error(fetcher_with_mock_client, mock_http_client):
    """When network times out, should raise RuntimeError."""
    # Setup mock to raise timeout
    mock_http_client.get.side_effect = httpx.TimeoutException("Request timed out")

    # Verify error is raised
    with pytest.raises(RuntimeError, match="Supabase REST query for 'account' failed"):
        fetcher_with_mock_client.fetch_accounts(use_cache=False)


@pytest.mark.unit
def test_connection_error_raises_runtime_error(fetcher_with_mock_client, mock_http_client):
    """When network is unreachable, should raise RuntimeError."""
    # Setup mock to raise connection error
    mock_http_client.get.side_effect = httpx.ConnectError("Connection refused")

    # Verify error is raised
    with pytest.raises(RuntimeError, match="Supabase REST query for 'account' failed"):
        fetcher_with_mock_client.fetch_accounts(use_cache=False)


@pytest.mark.unit
def test_malformed_json_response_raises_runtime_error(fetcher_with_mock_client, mock_http_client):
    """When Supabase returns non-list JSON, should raise RuntimeError."""
    # Setup mock to return invalid JSON (dict instead of list)
    mock_response = Mock()
    mock_response.json.return_value = {"error": "unexpected format"}
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response

    # Verify error is raised
    with pytest.raises(RuntimeError, match="Supabase returned unexpected payload"):
        fetcher_with_mock_client.fetch_accounts(use_cache=False)


# ==============================================================================
# Cache Status Tests
# ==============================================================================

@pytest.mark.integration
def test_cache_status_empty_db(temp_cache_db):
    """When cache is empty, cache_status() should return empty dict."""
    fetcher = CachedDataFetcher(cache_db=temp_cache_db)
    status = fetcher.cache_status()
    assert status == {}


@pytest.mark.integration
def test_cache_status_after_fetch(fetcher_with_mock_client, mock_http_client, sample_accounts_response):
    """After fetching data, cache_status() should report metadata."""
    # Setup mock response
    mock_response = Mock()
    mock_response.json.return_value = sample_accounts_response
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response

    # Fetch data
    fetcher_with_mock_client.fetch_accounts(use_cache=True)

    # Check cache status
    status = fetcher_with_mock_client.cache_status()
    assert "account" in status
    assert status["account"]["row_count"] == 2
    assert status["account"]["age_days"] < 1  # Just fetched
    assert isinstance(status["account"]["fetched_at"], datetime)


@pytest.mark.integration
def test_cache_status_multiple_tables(fetcher_with_mock_client, mock_http_client):
    """Cache status should track multiple tables independently."""
    # Setup mock responses for different tables
    def mock_get_response(url, **kwargs):
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        if "account" in url:
            mock_response.json.return_value = [{"account_id": "123"}]
        elif "profile" in url:
            mock_response.json.return_value = [{"user_id": "123"}, {"user_id": "456"}]
        return mock_response

    mock_http_client.get.side_effect = mock_get_response

    # Fetch from multiple tables
    fetcher_with_mock_client.fetch_accounts(use_cache=True)
    fetcher_with_mock_client.fetch_profiles(use_cache=True)

    # Check cache status
    status = fetcher_with_mock_client.cache_status()
    assert "account" in status
    assert "profile" in status
    assert status["account"]["row_count"] == 1
    assert status["profile"]["row_count"] == 2


# ==============================================================================
# Context Manager Tests
# ==============================================================================

@pytest.mark.unit
def test_context_manager_closes_http_client(temp_cache_db):
    """When using context manager, should close HTTP client on exit."""
    mock_client = Mock(spec=httpx.Client)
    mock_client.close = Mock()

    with CachedDataFetcher(cache_db=temp_cache_db, http_client=mock_client):
        pass

    # Verify client was closed
    mock_client.close.assert_called_once()


@pytest.mark.unit
def test_context_manager_does_not_close_external_client(temp_cache_db):
    """When external client is provided, should NOT close it."""
    mock_client = Mock(spec=httpx.Client)
    mock_client.close = Mock()

    # Create fetcher without context manager (external client)
    fetcher = CachedDataFetcher(cache_db=temp_cache_db, http_client=mock_client)
    fetcher.close()

    # Verify client was NOT closed (fetcher doesn't own it)
    mock_client.close.assert_not_called()


@pytest.mark.unit
def test_manual_close(temp_cache_db):
    """Calling close() manually should close owned HTTP client."""
    mock_client = Mock(spec=httpx.Client)
    mock_client.close = Mock()

    # Create fetcher with NO external client (owns the client)
    fetcher = CachedDataFetcher(cache_db=temp_cache_db)

    # Manually inject a mock client and mark as owned
    fetcher._http_client = mock_client
    fetcher._owns_client = True

    fetcher.close()

    # Verify client was closed
    mock_client.close.assert_called_once()


# ==============================================================================
# Generic fetch_table Tests
# ==============================================================================

@pytest.mark.unit
def test_fetch_table_generic(fetcher_with_mock_client, mock_http_client):
    """fetch_table() should work with any table name."""
    # Setup mock response
    mock_response = Mock()
    mock_response.json.return_value = [{"custom_id": "xyz", "value": 42}]
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response

    # Fetch custom table
    df = fetcher_with_mock_client.fetch_table("custom_table", use_cache=False)

    # Verify correct endpoint was called
    assert mock_http_client.get.call_args[0][0] == "/rest/v1/custom_table"
    assert len(df) == 1
    assert df.iloc[0]["value"] == 42


@pytest.mark.unit
def test_fetch_table_with_custom_params(fetcher_with_mock_client, mock_http_client):
    """fetch_table() should support custom query parameters."""
    # Setup mock response
    mock_response = Mock()
    mock_response.json.return_value = [{"id": "1"}]
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response

    # Fetch with custom params
    custom_params = {"select": "id,name", "limit": "10"}
    fetcher_with_mock_client.fetch_table("test_table", use_cache=False, params=custom_params)

    # Verify params were passed
    call_kwargs = mock_http_client.get.call_args[1]
    assert call_kwargs["params"] == custom_params


# ==============================================================================
# Lazy HTTP Client Initialization Tests
# ==============================================================================

@pytest.mark.unit
@patch("src.data.fetcher.get_supabase_config")
def test_http_client_lazy_initialization(mock_get_config, temp_cache_db, sample_accounts_response):
    """HTTP client should only be created when first network call is made."""
    # Setup mock config
    mock_config = Mock()
    mock_config.url = "https://test.supabase.co"
    mock_config.rest_headers = {"Authorization": "Bearer test-key"}
    mock_get_config.return_value = mock_config

    # Create fetcher without providing http_client
    fetcher = CachedDataFetcher(cache_db=temp_cache_db)

    # At this point, HTTP client should NOT be initialized
    assert fetcher._http_client is None

    # Setup mock for httpx.Client
    with patch("src.data.fetcher.httpx.Client") as mock_client_class:
        mock_instance = Mock()
        mock_response = Mock()
        mock_response.json.return_value = sample_accounts_response
        mock_response.raise_for_status = Mock()
        mock_instance.get.return_value = mock_response
        mock_client_class.return_value = mock_instance

        # Trigger network call (should initialize client)
        fetcher.fetch_accounts(use_cache=False)

        # Verify client was created with correct config
        mock_client_class.assert_called_once()
        assert mock_client_class.call_args[1]["base_url"] == "https://test.supabase.co"
        assert "Authorization" in mock_client_class.call_args[1]["headers"]


# ==============================================================================
# Edge Cases
# ==============================================================================

@pytest.mark.integration
def test_empty_table_response(fetcher_with_mock_client, mock_http_client):
    """Fetching an empty table should return empty DataFrame."""
    # Setup mock response with empty list
    mock_response = Mock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response

    # Fetch empty table
    df = fetcher_with_mock_client.fetch_accounts(use_cache=False)

    # Verify empty DataFrame
    assert len(df) == 0
    assert isinstance(df, pd.DataFrame)


@pytest.mark.integration
def test_cache_replacement_on_refresh(fetcher_with_mock_client, mock_http_client):
    """When cache is refreshed, old data should be completely replaced."""
    # First fetch
    mock_response = Mock()
    mock_response.json.return_value = [{"id": "1", "name": "Alice"}]
    mock_response.raise_for_status = Mock()
    mock_http_client.get.return_value = mock_response

    df1 = fetcher_with_mock_client.fetch_table("test_table", use_cache=True)
    assert len(df1) == 1
    assert df1.iloc[0]["name"] == "Alice"

    # Second fetch with different data (force refresh)
    mock_response.json.return_value = [{"id": "2", "name": "Bob"}, {"id": "3", "name": "Charlie"}]
    df2 = fetcher_with_mock_client.fetch_table("test_table", use_cache=True, force_refresh=True)

    # Verify new data replaced old data
    assert len(df2) == 2
    assert "Alice" not in df2["name"].values
    assert "Bob" in df2["name"].values

    # Verify cache now contains only new data
    df3 = fetcher_with_mock_client.fetch_table("test_table", use_cache=True)
    assert len(df3) == 2
    pd.testing.assert_frame_equal(df2, df3)
