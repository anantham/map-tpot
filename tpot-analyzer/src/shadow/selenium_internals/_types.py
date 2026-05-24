"""Dataclasses + module-level helpers used across the SeleniumWorker mixins.

Kept private (`selenium_internals`) — these are re-exported from
`src.shadow.selenium_worker` for backward compat with existing imports.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set


LOGGER = logging.getLogger("src.shadow.selenium_worker")

_BROWSER_BINARY_ENV_VARS = ("TPOT_CHROME_BINARY", "CHROME_BIN")


def _shorten_text(value: Optional[str], limit: int) -> str:
    """Return a trimmed, single-line representation for logging."""

    if value is None:
        return "-"

    text = str(value).strip()
    if not text:
        return "-"

    if len(text) <= limit:
        return text

    return text[: max(0, limit - 3)] + "..."


def _resolve_chrome_binary_from_env() -> Optional[Path]:
    for key in _BROWSER_BINARY_ENV_VARS:
        raw = os.getenv(key)
        if not raw:
            continue

        candidate = Path(raw).expanduser()
        if candidate.suffix == ".app" and candidate.is_dir():
            macos_binary = candidate / "Contents" / "MacOS" / candidate.stem
            if macos_binary.is_file():
                return macos_binary

            macos_dir = candidate / "Contents" / "MacOS"
            if macos_dir.is_dir():
                for entry in macos_dir.iterdir():
                    if entry.is_file():
                        return entry

        if candidate.is_file():
            return candidate

    return None


@dataclass(frozen=True)
class SeleniumConfig:
    cookies_path: Path
    headless: bool = False
    scroll_delay_min: float = 5.0
    scroll_delay_max: float = 40.0
    max_no_change_scrolls: int = 6
    window_size: str = "1080,1280"
    action_delay_min: float = 5.0
    action_delay_max: float = 40.0
    chrome_binary: Optional[Path] = None
    require_confirmation: bool = True
    retry_delays: List[float] = field(default_factory=lambda: [5.0, 15.0, 60.0])


@dataclass
class CapturedUser:
    username: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    profile_url: Optional[str] = None
    website: Optional[str] = None
    profile_image_url: Optional[str] = None
    list_types: Set[str] = field(default_factory=set)


@dataclass
class UserListCapture:
    list_type: str
    entries: List[CapturedUser]
    claimed_total: Optional[int]
    page_url: str
    profile_overview: Optional["ProfileOverview"] = None
    list_overview: Optional["ListOverview"] = None


@dataclass
class ListOverview:
    list_id: str
    name: Optional[str]
    description: Optional[str]
    owner_username: Optional[str]
    owner_display_name: Optional[str]
    owner_profile_url: Optional[str]
    members_total: Optional[int]
    followers_total: Optional[int]

    headless: bool = False


@dataclass
class AccountStatusInfo:
    """Result of account existence check.

    Attributes:
        status: One of "active", "deleted", "suspended", "protected"
        detected_at: Timestamp when status was detected
        message: Optional error message (e.g., "These posts are protected")
    """
    status: str
    detected_at: datetime
    message: Optional[str] = None


@dataclass(frozen=True)
class ProfileOverview:
    username: str
    display_name: Optional[str]
    bio: Optional[str]
    location: Optional[str]
    website: Optional[str]
    followers_total: Optional[int]
    following_total: Optional[int]
    joined_date: Optional[str] = None
    profile_image_url: Optional[str] = None
