"""CLI parsing and API key resolution for twitterapi.io shadow audit."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional, Tuple

from .constants import DEFAULT_BASE, DEFAULT_DB_PATH, DEFAULT_OUTPUT_PATH, KEY_ENV_CANDIDATES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare local shadow edges with twitterapi.io relationship data."
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="Path to sqlite cache DB.")
    parser.add_argument("--usernames", nargs="*", default=[], help="Explicit usernames to audit.")
    parser.add_argument(
        "--sample-size",
        type=int,
        default=3,
        help="If usernames not provided, sample top N shadow accounts.",
    )
    parser.add_argument("--page-size", type=int, default=200, help="twitterapi.io page size.")
    parser.add_argument("--max-pages", type=int, default=3, help="Max pages per relation per account.")
    parser.add_argument(
        "--identifier-mode",
        choices=("auto", "username", "id"),
        default="auto",
        help="Remote lookup strategy.",
    )
    parser.add_argument(
        "--wait-on-rate-limit",
        action="store_true",
        default=False,
        help="Wait and retry when 429 is returned.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=30, help="HTTP timeout.")
    parser.add_argument(
        "--sample-output-count",
        type=int,
        default=8,
        help="How many sample mismatches to print.",
    )
    parser.add_argument("--api-key", type=str, default=None, help="twitterapi.io key (fallback: env vars).")
    parser.add_argument(
        "--base-url",
        type=str,
        default=DEFAULT_BASE,
        help="Base URL for twitterapi.io user endpoints.",
    )
    parser.add_argument(
        "--checkpoint-every-requests",
        type=int,
        default=25,
        help="Write a progress checkpoint at least every N remote requests.",
    )
    parser.add_argument(
        "--checkpoint-min-seconds",
        type=int,
        default=30,
        help="Write a progress checkpoint if this many seconds elapsed since the last checkpoint.",
    )
    parser.add_argument(
        "--max-event-history",
        type=int,
        default=250,
        help="Maximum number of recent remote events persisted in runtime metadata.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="Verbosity for audit logs.",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Optional log file path (defaults to <output>.log).",
    )
    parser.add_argument(
        "--resume-from-output",
        action="store_true",
        default=False,
        help="Resume from existing output JSON by skipping already-completed usernames.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="JSON report output path.")
    return parser.parse_args()


def resolve_api_key(explicit_key: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if explicit_key:
        return explicit_key, "--api-key"
    for env_name in KEY_ENV_CANDIDATES:
        value = os.getenv(env_name)
        if value:
            return value, env_name
    return None, None
