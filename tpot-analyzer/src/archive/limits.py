"""Resource and shape limits for untrusted Community Archive JSON."""
from __future__ import annotations

import json
import math
import re
import os
import time
from pathlib import Path

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_RECORDS = 500_000
MAX_SECTION_RECORDS = 250_000
MAX_JSON_DEPTH = 32
MAX_JSON_VALUES = 4_000_000
MAX_STRING_CHARS = 1_000_000
MAX_DOWNLOAD_SECONDS = 120
_SECTIONS = {"tweets": "tweet", "community-tweet": "tweet", "note-tweet": "noteTweet",
             "like": "like", "following": "following", "follower": "follower",
             "account": "account", "profile": "profile"}


def validate_username(username: str) -> str:
    if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,15}", username):
        raise ValueError("archive username must be a Twitter handle (1–15 letters, digits or underscores)")
    return username.lower()


def _check_json_depth(raw: bytes) -> None:
    depth = 0
    quoted = escaped = False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (91, 123):
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError("archive JSON exceeds nesting depth limit")
        elif char in (93, 125):
            depth -= 1


def validate_archive(archive: dict) -> dict:
    """Validate before parsers allocate rows or open a database."""
    if not isinstance(archive, dict):
        raise ValueError("archive root must be an object")
    records = 0
    for section, wrapper in _SECTIONS.items():
        items = archive.get(section, [])
        if not isinstance(items, list):
            raise ValueError(f"archive section {section} must be an array")
        records += len(items)
        if len(items) > MAX_SECTION_RECORDS or records > MAX_ARCHIVE_RECORDS:
            raise ValueError("archive exceeds record limit")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get(wrapper, {}), dict):
                raise ValueError(f"archive {section} record must contain an object")
    for section in ("tweets", "community-tweet"):
        for item in archive.get(section, []):
            tweet = item.get("tweet", {})
            if not isinstance(tweet.get("full_text", ""), str):
                raise ValueError("archive tweet full_text must be a string")
            for field in ("favorite_count", "retweet_count"):
                value = tweet.get(field)
                if value is not None and (isinstance(value, bool) or
                        not isinstance(value, (str, int)) or len(str(value)) > 20):
                    raise ValueError("archive engagement counts must be bounded integers")
                if value not in (None, ""):
                    try:
                        int(value)
                    except ValueError as exc:
                        raise ValueError("archive engagement counts must be integers") from exc
    for item in archive.get("note-tweet", []):
        core = item.get("noteTweet", {}).get("core", {})
        if not isinstance(core, dict) or not isinstance(core.get("text", ""), str):
            raise ValueError("archive note-tweet core/text shape is invalid")
    for item in archive.get("profile", []):
        if not isinstance(item.get("profile", {}).get("description", {}), dict):
            raise ValueError("archive profile description must be an object")
    pending = [iter((archive,))]
    count = 0
    while pending:
        try:
            value = next(pending[-1])
        except StopIteration:
            pending.pop()
            continue
        count += 1
        if count > MAX_JSON_VALUES or len(pending) > MAX_JSON_DEPTH + 1:
            raise ValueError("archive exceeds parser value/depth limit")
        if isinstance(value, dict):
            if len(value) > 1024 or any(not isinstance(k, str) or len(k) > 256 for k in value):
                raise ValueError("archive object keys must be bounded strings")
            pending.append(iter(value.values()))
        elif isinstance(value, list):
            if len(value) > MAX_ARCHIVE_RECORDS:
                raise ValueError("archive exceeds record limit")
            pending.append(iter(value))
        elif isinstance(value, str):
            if len(value) > MAX_STRING_CHARS:
                raise ValueError("archive string exceeds character limit")
        elif value is not None and not isinstance(value, (int, float, bool)):
            raise ValueError("archive contains unsupported value type")
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("archive numeric values must be finite")
    return archive


def parse_archive(raw: bytes, *, max_bytes: int = MAX_ARCHIVE_BYTES) -> dict:
    if len(raw) > max_bytes:
        raise ValueError("archive exceeds byte limit")
    _check_json_depth(raw)
    try:
        return validate_archive(json.loads(raw))
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("archive JSON cannot be decoded safely") from exc


def read_archive(path: Path, *, max_bytes: int = MAX_ARCHIVE_BYTES) -> dict:
    if path.is_symlink():
        raise ValueError("archive cache must not be a symlink")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        return parse_archive(handle.read(max_bytes + 1), max_bytes=max_bytes)


def bounded_response_bytes(response, *, max_bytes: int = MAX_ARCHIVE_BYTES) -> bytes:
    """Bound decoded bytes even with absent/dishonest Content-Length."""
    length = response.headers.get("Content-Length")
    if length is not None:
        try:
            declared = int(length)
        except ValueError as exc:
            raise ValueError("archive Content-Length must be numeric") from exc
        if declared < 0 or declared > max_bytes:
            raise ValueError("archive exceeds declared byte limit")
    body = bytearray()
    started = time.monotonic()
    for chunk in response.iter_bytes(chunk_size=65536):
        if len(body) + len(chunk) > max_bytes:
            raise ValueError("archive exceeds decoded byte limit")
        if time.monotonic() - started > MAX_DOWNLOAD_SECONDS:
            raise ValueError("archive exceeds download duration limit")
        body.extend(chunk)
    return bytes(body)
