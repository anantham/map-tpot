"""Headless Selenium helper for extracting follower/following handles.

Public surface (unchanged): SeleniumWorker, SeleniumConfig, CapturedUser,
UserListCapture, ListOverview, AccountStatusInfo, ProfileOverview.

This file is the COORDINATOR. Behavior lives in mixins under
`src/shadow/selenium_internals/` and pure parsers in `src/shadow/selenium_parsing.py`.
The class binds them together and owns the runtime state.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable, Dict, Optional

from selenium import webdriver

# Re-export public dataclasses + helpers for back-compat with existing imports
from src.shadow.selenium_internals._types import (
    AccountStatusInfo,
    CapturedUser,
    ListOverview,
    ProfileOverview,
    SeleniumConfig,
    UserListCapture,
    LOGGER,
    _BROWSER_BINARY_ENV_VARS,
    _resolve_chrome_binary_from_env,
    _shorten_text,
)
from src.shadow.selenium_internals._driver_mixin import DriverLifecycleMixin
from src.shadow.selenium_internals._list_capture_mixin import ListCaptureMixin
from src.shadow.selenium_internals._profile_mixin import ProfileMixin
from src.shadow.selenium_internals._counters_mixin import CounterExtractionMixin

# Backward-compat: parser functions are re-exported as @staticmethod wrappers on the class
from src.shadow.selenium_parsing import (
    clean_bio_text,
    counter_priority,
    extract_handle,
    extract_profile_image_url,
    extract_website,
    handle_from_href,
    normalize_href_path,
    parse_compact_count,
    parse_profile_schema_payload,
)

__all__ = [
    "SeleniumWorker",
    "SeleniumConfig",
    "CapturedUser",
    "UserListCapture",
    "ListOverview",
    "AccountStatusInfo",
    "ProfileOverview",
]


class SeleniumWorker(
    DriverLifecycleMixin,
    ListCaptureMixin,
    ProfileMixin,
    CounterExtractionMixin,
):
    """Minimal Selenium-based scroller for Twitter lists.

    Composes four behavior mixins; this class owns the runtime state.
    """

    # Backward-compat wrappers — real implementation in src/shadow/selenium_parsing.py
    _handle_from_href = staticmethod(handle_from_href)
    _clean_bio_text = staticmethod(clean_bio_text)
    _counter_priority = staticmethod(counter_priority)
    _normalize_href_path = staticmethod(normalize_href_path)
    _parse_compact_count = staticmethod(parse_compact_count)
    _parse_profile_schema_payload = staticmethod(parse_profile_schema_payload)
    _extract_handle = staticmethod(extract_handle)
    _extract_website = staticmethod(extract_website)
    _extract_profile_image_url = staticmethod(extract_profile_image_url)

    def __init__(self, config: SeleniumConfig) -> None:
        self._config = config
        self._driver: webdriver.Chrome | None = None
        self._profile_overviews: Dict[str, ProfileOverview] = {}
        self._snapshot_dir = Path("logs")
        self._snapshot_dir.mkdir(exist_ok=True)
        self._pause_callback: Optional[Callable[[], bool]] = None
        self._shutdown_callback: Optional[Callable[[], bool]] = None

    def _save_page_snapshot(self, username: str, label: str) -> None:
        assert self._driver is not None
        timestamp = int(time.time())
        safe_user = re.sub(r"[^A-Za-z0-9_-]+", "-", username) or "user"
        filename = self._snapshot_dir / f"snapshot_{safe_user}_{label}_{timestamp}.html"
        try:
            source = self._driver.page_source
            filename.write_text(source)
            LOGGER.warning("Saved page snapshot to %s", filename)
        except Exception as exc:
            LOGGER.error("Failed to save snapshot for @%s: %s", username, exc)
