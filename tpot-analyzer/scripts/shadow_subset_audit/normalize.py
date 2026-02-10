"""Normalization helpers for twitterapi.io shadow audit."""
from __future__ import annotations

from typing import Optional


def normalize_username(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = value.strip().lstrip("@").lower()
    return cleaned or None
