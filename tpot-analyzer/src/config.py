"""Configuration helpers for the TPOT Community Graph Analyzer."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

# Load environment variables early so downstream modules can rely on them.
load_dotenv(ENV_PATH, override=False)

SUPABASE_URL_KEY = "SUPABASE_URL"
SUPABASE_KEY_KEY = "SUPABASE_KEY"
CACHE_DB_ENV = "CACHE_DB_PATH"
CACHE_MAX_AGE_ENV = "CACHE_MAX_AGE_DAYS"
SNAPSHOT_DIR_ENV = "SNAPSHOT_DIR"

DEFAULT_SUPABASE_URL = "https://fabxmporizzqflnftavs.supabase.co"
DEFAULT_CACHE_DB = PROJECT_ROOT / "data" / "cache.db"
DEFAULT_CACHE_MAX_AGE_DAYS = 7
DEFAULT_SNAPSHOT_DIR = PROJECT_ROOT / "data"


@dataclass(frozen=True)
class SupabaseConfig:
    """Connection settings required to query the Supabase REST endpoint."""

    url: str
    key: str

    @property
    def rest_headers(self) -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "count=exact",
        }


@dataclass(frozen=True)
class CacheSettings:
    """Runtime configuration for the SQLite caching layer."""

    path: Path
    max_age_days: int


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def get_supabase_config() -> SupabaseConfig:
    """Return Supabase REST configuration or raise a descriptive error."""

    url = _get_env(SUPABASE_URL_KEY, DEFAULT_SUPABASE_URL)
    key = _get_env(SUPABASE_KEY_KEY)
    if not url:
        raise RuntimeError("SUPABASE_URL is not configured; check your .env or environment")
    if not key:
        raise RuntimeError(
            "SUPABASE_KEY is not configured. Set it in .env or export the variable before running."
        )
    return SupabaseConfig(url=url, key=key)


def get_cache_settings() -> CacheSettings:
    """Resolve cache configuration from environment with sensible defaults."""

    raw_path = _get_env(CACHE_DB_ENV, str(DEFAULT_CACHE_DB))
    cache_path = Path(raw_path).expanduser().resolve()
    raw_max_age = _get_env(CACHE_MAX_AGE_ENV)
    try:
        max_age = int(raw_max_age) if raw_max_age is not None else DEFAULT_CACHE_MAX_AGE_DAYS
    except ValueError as exc:
        raise RuntimeError(
            f"CACHE_MAX_AGE_DAYS must be an integer; received '{raw_max_age}'."
        ) from exc
    return CacheSettings(path=cache_path, max_age_days=max_age)


def get_snapshot_dir() -> Path:
    """Resolve the snapshot directory (shared by refresh scripts and API)."""

    raw_path = _get_env(SNAPSHOT_DIR_ENV, str(DEFAULT_SNAPSHOT_DIR))
    snapshot_dir = Path(raw_path).expanduser().resolve()
    return snapshot_dir
