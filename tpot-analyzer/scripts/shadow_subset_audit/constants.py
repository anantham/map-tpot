"""Constants and shared utilities for twitterapi.io shadow audit."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


CHECK = "✓"
CROSS = "✗"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "cache.db"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "outputs" / "twitterapiio_shadow_audit" / "latest.json"
DEFAULT_BASE = "https://api.twitterapi.io/twitter/user"
KEY_ENV_CANDIDATES = (
    "TWITTERAPI_IO_API_KEY",
    "TWITTERAPI_API_KEY",
    "TWITTERAPIIO_API_KEY",
    "TWITTERAPI_KEY",
    "API_KEY",
    "X_API_KEY",
)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
