"""Thin X API v2 client with local rate-limit awareness."""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


LOGGER = logging.getLogger(__name__)


@dataclass
class RateLimit:
    requests_per_window: int
    window_seconds: int
    request_times: List[datetime]

    def __init__(self, requests_per_window: int, window_seconds: int) -> None:
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.request_times = []

    def can_make_request(self) -> bool:
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=self.window_seconds)
        self.request_times = [ts for ts in self.request_times if ts > cutoff]
        return len(self.request_times) < self.requests_per_window

    def wait_time(self) -> int:
        if self.can_make_request():
            return 0
        oldest = min(self.request_times)
        wait_until = oldest + timedelta(seconds=self.window_seconds)
        return max(int((wait_until - datetime.utcnow()).total_seconds()) + 1, 0)

    def record_request(self) -> None:
        self.request_times.append(datetime.utcnow())


@dataclass
class XAPIClientConfig:
    bearer_token: str
    rate_state_path: Path = Path("data/x_api_rate_state.json")


class XAPIClient:
    """Minimal wrapper around X API endpoints used for enrichment."""

    def __init__(self, config: XAPIClientConfig) -> None:
        self._config = config
        self._rate_state_path = config.rate_state_path
        self._owned_lists_limit = RateLimit(100, 24 * 60 * 60)
        self._user_lookup_limit = RateLimit(900, 15 * 60)
        self._load_rate_limit_state()

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {config.bearer_token}",
                "User-Agent": "TPOTShadowEnricher/1.0",
            }
        )

    # ------------------------------------------------------------------
    # Rate limit persistence
    # ------------------------------------------------------------------
    def _load_rate_limit_state(self) -> None:
        if not self._rate_state_path.exists():
            self._last_reset_ts = 0
            return
        try:
            data = json.loads(self._rate_state_path.read_text())
        except json.JSONDecodeError:
            self._last_reset_ts = 0
            return
        self._last_reset_ts = int(data.get("reset_timestamp", 0))

    def _save_rate_limit_state(self, reset_timestamp: int) -> None:
        payload = {
            "reset_timestamp": reset_timestamp,
            "persisted_at": int(time.time()),
        }
        self._rate_state_path.parent.mkdir(parents=True, exist_ok=True)
        self._rate_state_path.write_text(json.dumps(payload, indent=2))
        self._last_reset_ts = reset_timestamp

    def _respect_persistent_limit(self) -> None:
        if not self._last_reset_ts:
            return
        now = int(time.time())
        if now < self._last_reset_ts:
            wait_seconds = self._last_reset_ts - now + 5
            LOGGER.info("Waiting %s seconds for persisted rate limit reset", wait_seconds)
            time.sleep(wait_seconds)

    # ------------------------------------------------------------------
    # Request plumbing
    # ------------------------------------------------------------------
    def _make_request(self, url: str, limiter: RateLimit) -> Optional[Dict[str, Any]]:
        self._respect_persistent_limit()
        wait = limiter.wait_time()
        if wait > 0:
            LOGGER.info("Rate limiter sleeping %s seconds", wait)
            time.sleep(wait)

        try:
            response = self._session.get(url, timeout=30)
        except requests.RequestException as exc:
            LOGGER.error("X API request failed: %s", exc)
            return None

        limiter.record_request()
        if response.status_code == 200:
            return response.json()

        if response.status_code == 429:
            reset_header = response.headers.get("x-rate-limit-reset")
            retry_after = response.headers.get("retry-after")
            if reset_header:
                reset_ts = int(reset_header)
                self._save_rate_limit_state(reset_ts)
                sleep_for = max(reset_ts - int(time.time()) + 5, 60)
            elif retry_after:
                sleep_for = int(retry_after)
                self._save_rate_limit_state(int(time.time()) + sleep_for)
            else:
                sleep_for = 900
            LOGGER.warning("X API rate-limited; sleeping %s seconds", sleep_for)
            time.sleep(sleep_for)
            return self._make_request(url, limiter)

        LOGGER.error("X API returned %s: %s", response.status_code, response.text)
        return None

    # ------------------------------------------------------------------
    # Public lookups
    # ------------------------------------------------------------------
    def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        url = f"https://api.twitter.com/2/users/{user_id}?user.fields=id,username,name,public_metrics,description,location"
        payload = self._make_request(url, self._user_lookup_limit)
        if payload and "data" in payload:
            return payload["data"]
        return None

    def get_user_info_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        url = (
            "https://api.twitter.com/2/users/by/username/"
            f"{username}?user.fields=id,username,name,public_metrics,description,location"
        )
        payload = self._make_request(url, self._user_lookup_limit)
        if payload and "data" in payload:
            return payload["data"]
        return None

    def get_list_members(self, list_id: str) -> List[Dict[str, Any]]:
        url = f"https://api.twitter.com/2/lists/{list_id}/members?user.fields=id,username,name"
        payload = self._make_request(url, self._owned_lists_limit)
        if payload and "data" in payload:
            return payload["data"]
        return []
