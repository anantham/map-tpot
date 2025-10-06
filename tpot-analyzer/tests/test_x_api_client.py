"""Unit tests for X API client (rate limiting, HTTP errors, state persistence)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from src.shadow.x_api_client import RateLimit, XAPIClient, XAPIClientConfig


# ==============================================================================
# RateLimit Unit Tests
# ==============================================================================
class TestRateLimit:
    """Unit tests for sliding window rate limiter."""

    def test_can_make_request_when_empty(self):
        """Should allow requests when no requests have been made."""
        limiter = RateLimit(requests_per_window=10, window_seconds=60)
        assert limiter.can_make_request() is True

    def test_can_make_request_when_under_limit(self):
        """Should allow requests when under the rate limit."""
        limiter = RateLimit(requests_per_window=10, window_seconds=60)
        limiter.record_request()
        limiter.record_request()
        assert limiter.can_make_request() is True

    def test_cannot_make_request_when_at_limit(self):
        """Should block requests when at the rate limit."""
        limiter = RateLimit(requests_per_window=3, window_seconds=60)
        limiter.record_request()
        limiter.record_request()
        limiter.record_request()
        assert limiter.can_make_request() is False

    def test_sliding_window_evicts_old_requests(self):
        """Should evict requests outside the time window."""
        limiter = RateLimit(requests_per_window=2, window_seconds=10)

        # Add old request (11 seconds ago, outside window)
        old_time = datetime.utcnow() - timedelta(seconds=11)
        limiter.request_times.append(old_time)

        # Should be evicted, so new request allowed
        assert limiter.can_make_request() is True
        assert len(limiter.request_times) == 0  # Old request evicted

    def test_wait_time_when_can_request(self):
        """Should return 0 wait time when requests are allowed."""
        limiter = RateLimit(requests_per_window=10, window_seconds=60)
        assert limiter.wait_time() == 0

    def test_wait_time_when_rate_limited(self):
        """Should calculate wait time based on oldest request."""
        limiter = RateLimit(requests_per_window=2, window_seconds=60)

        # Fill the limit with requests 30 seconds ago
        old_time = datetime.utcnow() - timedelta(seconds=30)
        limiter.request_times = [old_time, old_time]

        # Should wait ~31 seconds (60 - 30 + 1)
        wait = limiter.wait_time()
        assert 29 <= wait <= 32  # Allow for timing variance

    def test_record_request_adds_timestamp(self):
        """Should add current timestamp when recording request."""
        limiter = RateLimit(requests_per_window=10, window_seconds=60)
        before = datetime.utcnow()
        limiter.record_request()
        after = datetime.utcnow()

        assert len(limiter.request_times) == 1
        assert before <= limiter.request_times[0] <= after


# ==============================================================================
# XAPIClient State Persistence Tests
# ==============================================================================
class TestXAPIClientStatePersistence:
    """Tests for rate limit state file persistence."""

    def test_load_state_when_file_missing(self, tmp_path):
        """Should initialize with no reset timestamp when state file missing."""
        config = XAPIClientConfig(
            bearer_token="test_token",
            rate_state_path=tmp_path / "missing.json"
        )

        with patch('requests.Session'):
            client = XAPIClient(config)
            assert client._last_reset_ts == 0

    def test_load_state_from_valid_file(self, tmp_path):
        """Should load reset timestamp from valid state file."""
        state_file = tmp_path / "rate_state.json"
        state_file.write_text(json.dumps({
            "reset_timestamp": 1234567890,
            "persisted_at": 1234567800
        }))

        config = XAPIClientConfig(
            bearer_token="test_token",
            rate_state_path=state_file
        )

        with patch('requests.Session'):
            client = XAPIClient(config)
            assert client._last_reset_ts == 1234567890

    def test_load_state_from_corrupted_file(self, tmp_path):
        """Should handle corrupted JSON gracefully."""
        state_file = tmp_path / "rate_state.json"
        state_file.write_text("not valid json {{{")

        config = XAPIClientConfig(
            bearer_token="test_token",
            rate_state_path=state_file
        )

        with patch('requests.Session'):
            client = XAPIClient(config)
            assert client._last_reset_ts == 0

    def test_save_state_creates_directory(self, tmp_path):
        """Should create parent directories when saving state."""
        state_file = tmp_path / "nested" / "dir" / "rate_state.json"
        config = XAPIClientConfig(
            bearer_token="test_token",
            rate_state_path=state_file
        )

        with patch('requests.Session'):
            client = XAPIClient(config)
            client._save_rate_limit_state(1234567890)

        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert data["reset_timestamp"] == 1234567890
        assert "persisted_at" in data

    def test_respect_persistent_limit_waits(self, tmp_path):
        """Should wait when current time is before reset timestamp."""
        config = XAPIClientConfig(
            bearer_token="test_token",
            rate_state_path=tmp_path / "rate_state.json"
        )

        with patch('requests.Session'), patch('time.sleep') as mock_sleep:
            client = XAPIClient(config)

            # Set reset time to 10 seconds in the future
            future_reset = int(time.time()) + 10
            client._last_reset_ts = future_reset

            client._respect_persistent_limit()

            # Should have slept for ~15 seconds (10 + 5 buffer)
            assert mock_sleep.called
            sleep_duration = mock_sleep.call_args[0][0]
            assert 13 <= sleep_duration <= 17

    def test_respect_persistent_limit_no_wait_when_expired(self, tmp_path):
        """Should not wait when reset timestamp has passed."""
        config = XAPIClientConfig(
            bearer_token="test_token",
            rate_state_path=tmp_path / "rate_state.json"
        )

        with patch('requests.Session'), patch('time.sleep') as mock_sleep:
            client = XAPIClient(config)

            # Set reset time to the past
            client._last_reset_ts = int(time.time()) - 100

            client._respect_persistent_limit()

            # Should not sleep
            assert not mock_sleep.called


# ==============================================================================
# XAPIClient HTTP Request Tests
# ==============================================================================
class TestXAPIClientHTTP:
    """Tests for HTTP request handling and error codes."""

    def test_successful_request_200(self, tmp_path):
        """Should parse JSON response on 200 OK."""
        config = XAPIClientConfig(
            bearer_token="test_token",
            rate_state_path=tmp_path / "rate_state.json"
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"id": "123", "username": "testuser"}}

        with patch('requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session.get.return_value = mock_response
            mock_session_class.return_value = mock_session

            client = XAPIClient(config)
            result = client._make_request(
                "https://api.twitter.com/2/users/123",
                client._user_lookup_limit
            )

        assert result == {"data": {"id": "123", "username": "testuser"}}
        assert mock_session.get.called

    def test_rate_limit_429_with_reset_header(self, tmp_path):
        """Should save reset timestamp and retry on 429."""
        config = XAPIClientConfig(
            bearer_token="test_token",
            rate_state_path=tmp_path / "rate_state.json"
        )

        # First response: 429 with reset header
        mock_429_response = Mock()
        mock_429_response.status_code = 429
        mock_429_response.headers = {"x-rate-limit-reset": str(int(time.time()) + 10)}

        # Second response: 200 OK
        mock_200_response = Mock()
        mock_200_response.status_code = 200
        mock_200_response.json.return_value = {"data": {"id": "123"}}

        with patch('requests.Session') as mock_session_class, \
             patch('time.sleep') as mock_sleep:
            mock_session = Mock()
            mock_session.get.side_effect = [mock_429_response, mock_200_response]
            mock_session_class.return_value = mock_session

            client = XAPIClient(config)
            result = client._make_request(
                "https://api.twitter.com/2/users/123",
                client._user_lookup_limit
            )

        # Should have retried and succeeded
        assert result == {"data": {"id": "123"}}
        assert mock_sleep.called

        # Should have saved reset timestamp
        assert tmp_path.joinpath("rate_state.json").exists()

    def test_rate_limit_429_with_retry_after(self, tmp_path):
        """Should respect retry-after header on 429 and save state."""
        config = XAPIClientConfig(
            bearer_token="test_token",
            rate_state_path=tmp_path / "rate_state.json"
        )

        mock_429_response = Mock()
        mock_429_response.status_code = 429
        mock_429_response.headers = {"retry-after": "60"}

        mock_200_response = Mock()
        mock_200_response.status_code = 200
        mock_200_response.json.return_value = {"data": {}}

        with patch('requests.Session') as mock_session_class, \
             patch('time.sleep') as mock_sleep:
            mock_session = Mock()
            mock_session.get.side_effect = [mock_429_response, mock_200_response]
            mock_session_class.return_value = mock_session

            client = XAPIClient(config)
            client._make_request(
                "https://api.twitter.com/2/users/123",
                client._user_lookup_limit
            )

        # Should have slept for retry-after duration
        # Note: First sleep is the initial 60s, then _respect_persistent_limit adds 5s buffer
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert 60 in sleep_calls or 65 in sleep_calls  # Depending on execution order

    def test_http_error_non_200(self, tmp_path):
        """Should return None on HTTP errors (401, 500, etc)."""
        config = XAPIClientConfig(
            bearer_token="test_token",
            rate_state_path=tmp_path / "rate_state.json"
        )

        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch('requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session.get.return_value = mock_response
            mock_session_class.return_value = mock_session

            client = XAPIClient(config)
            result = client._make_request(
                "https://api.twitter.com/2/users/123",
                client._user_lookup_limit
            )

        assert result is None

    def test_network_exception(self, tmp_path):
        """Should return None on network exceptions."""
        config = XAPIClientConfig(
            bearer_token="test_token",
            rate_state_path=tmp_path / "rate_state.json"
        )

        with patch('requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session.get.side_effect = requests.RequestException("Network error")
            mock_session_class.return_value = mock_session

            client = XAPIClient(config)
            result = client._make_request(
                "https://api.twitter.com/2/users/123",
                client._user_lookup_limit
            )

        assert result is None


# ==============================================================================
# XAPIClient Public API Tests
# ==============================================================================
class TestXAPIClientPublicAPI:
    """Tests for public lookup methods."""

    def test_get_user_info_success(self, tmp_path):
        """Should fetch user info by ID."""
        config = XAPIClientConfig(
            bearer_token="test_token",
            rate_state_path=tmp_path / "rate_state.json"
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "id": "123",
                "username": "testuser",
                "name": "Test User"
            }
        }

        with patch('requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session.get.return_value = mock_response
            mock_session_class.return_value = mock_session

            client = XAPIClient(config)
            result = client.get_user_info("123")

        assert result == {"id": "123", "username": "testuser", "name": "Test User"}

    def test_get_user_info_by_username_success(self, tmp_path):
        """Should fetch user info by username."""
        config = XAPIClientConfig(
            bearer_token="test_token",
            rate_state_path=tmp_path / "rate_state.json"
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "id": "456",
                "username": "anotheruser",
                "name": "Another User"
            }
        }

        with patch('requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session.get.return_value = mock_response
            mock_session_class.return_value = mock_session

            client = XAPIClient(config)
            result = client.get_user_info_by_username("anotheruser")

        assert result == {"id": "456", "username": "anotheruser", "name": "Another User"}

    def test_get_list_members_success(self, tmp_path):
        """Should fetch list members."""
        config = XAPIClientConfig(
            bearer_token="test_token",
            rate_state_path=tmp_path / "rate_state.json"
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "1", "username": "user1"},
                {"id": "2", "username": "user2"}
            ]
        }

        with patch('requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session.get.return_value = mock_response
            mock_session_class.return_value = mock_session

            client = XAPIClient(config)
            result = client.get_list_members("list123")

        assert len(result) == 2
        assert result[0]["username"] == "user1"

    def test_get_user_info_returns_none_on_error(self, tmp_path):
        """Should return None when API returns error."""
        config = XAPIClientConfig(
            bearer_token="test_token",
            rate_state_path=tmp_path / "rate_state.json"
        )

        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not found"

        with patch('requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session.get.return_value = mock_response
            mock_session_class.return_value = mock_session

            client = XAPIClient(config)
            result = client.get_user_info("999")

        assert result is None

    def test_get_list_members_returns_empty_on_error(self, tmp_path):
        """Should return empty list when API returns error."""
        config = XAPIClientConfig(
            bearer_token="test_token",
            rate_state_path=tmp_path / "rate_state.json"
        )

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal error"

        with patch('requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session.get.return_value = mock_response
            mock_session_class.return_value = mock_session

            client = XAPIClient(config)
            result = client.get_list_members("badlist")

        assert result == []
