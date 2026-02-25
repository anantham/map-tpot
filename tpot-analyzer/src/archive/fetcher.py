"""
Fetches Twitter archive JSON from the Community Archive Supabase blob storage.

Each archive lives at:
  https://fabxmporizzqflnftavs.supabase.co/storage/v1/object/public/archives/<username>/archive.json

Features:
- Streams large archives to a temp file, atomically renamed on success
  (so interrupted downloads leave no corrupt cache files)
- Retries with exponential backoff on network errors
- 400/404 both treated as "no archive" (not an error)
- JSON cache in cache_dir avoids re-downloading on resume
"""

import json
import logging
import time
import tempfile
from pathlib import Path
from typing import Optional

import httpx

SUPABASE_URL = "https://fabxmporizzqflnftavs.supabase.co"
ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZhYnhtcG9yaXp6cWZsbmZ0YXZzIiwicm9sZSI6"
    "ImFub24iLCJpYXQiOjE3MjIyNDQ5MTIsImV4cCI6MjAzNzgyMDkxMn0"
    ".UIEJiUNkLsW28tBHmG-RQDW-I5JNlJLt62CSk9D_qG8"
)

# Statuses that mean "no archive exists" — not worth retrying
_NOT_FOUND_CODES = {400, 404}

# Max retries and base delay for exponential backoff
_MAX_RETRIES = 4
_BASE_DELAY  = 2.0   # seconds; doubles each attempt: 2, 4, 8, 16

log = logging.getLogger(__name__)


def fetch_archive(
    username: str,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
) -> Optional[dict]:
    """
    Fetch the community archive JSON for a given username.

    Returns the parsed archive dict, or None if the account has no archive.
    Raises on unrecoverable errors after all retries are exhausted.

    Download is streamed to a temp file and atomically renamed on success,
    so an interrupted download never leaves a corrupt cache file.
    """
    username_lower = username.lower()

    # Return from cache if available
    if cache_dir and not force_refresh:
        cache_file = cache_dir / f"{username_lower}.json"
        if cache_file.exists():
            log.debug("Cache hit for %s", username)
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)

    url = (
        f"{SUPABASE_URL}/storage/v1/object/public/archives"
        f"/{username_lower}/archive.json"
    )
    headers = {"apikey": ANON_KEY, "Authorization": f"Bearer {ANON_KEY}"}

    last_exc = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            data = _download(url, headers, username, cache_dir)
            return data  # None means not-found, dict means success
        except _NotFound:
            return None  # No point retrying a 400/404
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                delay = _BASE_DELAY * (2 ** (attempt - 1))
                log.warning(
                    "Attempt %d/%d failed for %s (%s) — retrying in %.0fs",
                    attempt, _MAX_RETRIES, username, exc, delay,
                )
                time.sleep(delay)
            else:
                log.error(
                    "All %d attempts failed for %s: %s", _MAX_RETRIES, username, exc
                )

    raise last_exc


# ── internals ────────────────────────────────────────────────────────────────

class _NotFound(Exception):
    pass


def _download(url: str, headers: dict, username: str, cache_dir: Optional[Path]) -> Optional[dict]:
    """
    Stream the archive to a temp file, parse JSON, atomically save to cache.
    Raises _NotFound for 400/404. Raises other exceptions for transient errors.
    """
    with httpx.Client(timeout=httpx.Timeout(connect=30, read=300, write=30, pool=30)) as client:
        with client.stream("GET", url, headers=headers) as response:
            if response.status_code in _NOT_FOUND_CODES:
                log.info("No archive for %s (HTTP %d)", username, response.status_code)
                raise _NotFound(username)

            response.raise_for_status()

            # Stream into a temp file to avoid holding 50MB+ in RAM
            # and to ensure atomic write (temp → final path)
            if cache_dir:
                cache_dir.mkdir(parents=True, exist_ok=True)
                final_path = cache_dir / f"{username.lower()}.json"
                tmp_fd, tmp_path = tempfile.mkstemp(dir=cache_dir, suffix=".tmp")
                try:
                    with open(tmp_fd, "wb") as f:
                        for chunk in response.iter_bytes(chunk_size=65536):
                            f.write(chunk)
                    # Atomic rename: only reaches final path if fully written
                    Path(tmp_path).rename(final_path)
                    log.debug("Cached archive for %s -> %s", username, final_path)
                    with open(final_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    # Clean up temp file on any failure
                    try:
                        Path(tmp_path).unlink(missing_ok=True)
                    except Exception:
                        pass
                    raise
            else:
                # No cache: stream into memory
                chunks = []
                for chunk in response.iter_bytes(chunk_size=65536):
                    chunks.append(chunk)
                return json.loads(b"".join(chunks))
