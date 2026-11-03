"""Validated JSON cookies stored atomically with owner-only permissions.

Legacy pickle cookies must be recaptured using setup_cookies. They are never
loaded or automatically converted, even when a file uses a misleading suffix.
"""
from __future__ import annotations

import json
import os
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path

MAX_COOKIE_BYTES = 128 * 1024
MAX_COOKIES = 128
_FIELDS = {"name", "value", "domain", "path", "expiry", "httpOnly", "secure", "sameSite"}
_DOMAINS = {"twitter.com", ".twitter.com", "x.com", ".x.com"}


def validate_cookies(cookies: list) -> list[dict]:
    if not isinstance(cookies, list) or not 1 <= len(cookies) <= MAX_COOKIES:
        raise ValueError("cookies must be a nonempty bounded array")
    for cookie in cookies:
        if not isinstance(cookie, dict) or set(cookie) - _FIELDS:
            raise ValueError("cookie contains unsupported fields")
        for key in ("name", "value"):
            value = cookie.get(key)
            if not isinstance(value, str) or not value or len(value) > 16384:
                raise ValueError(f"cookie {key} must be a bounded nonempty string")
        if "domain" in cookie and cookie["domain"] not in _DOMAINS:
            raise ValueError("cookie domain must be twitter.com or x.com")
        if "path" in cookie and (not isinstance(cookie["path"], str) or
                                 not cookie["path"].startswith("/") or len(cookie["path"]) > 2048):
            raise ValueError("cookie path must be a bounded absolute path")
        for key in ("httpOnly", "secure"):
            if key in cookie and not isinstance(cookie[key], bool):
                raise ValueError(f"cookie {key} must be boolean")
        if "expiry" in cookie and (type(cookie["expiry"]) is not int or not 0 <= cookie["expiry"] <= 2**53):
            raise ValueError("cookie expiry must be a nonnegative integer")
        if "sameSite" in cookie and cookie["sameSite"] not in {"Strict", "Lax", "None"}:
            raise ValueError("cookie sameSite is invalid")
    return cookies


@contextmanager
def _parent_directory(path: Path, *, create: bool = False):
    """Walk with dirfd + O_NOFOLLOW so ancestor replacement cannot redirect I/O."""
    absolute = Path(os.path.abspath(path.expanduser()))
    if absolute.suffix.lower() != ".json":
        raise ValueError("cookie files must use JSON; recapture legacy pickle cookies")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parent.parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor, absolute.name
    finally:
        os.close(descriptor)


def save_cookies(path: Path, cookies: list[dict]) -> Path:
    """Create a new 0600 JSON file; existing files and symlinks are not overwritten."""
    body = json.dumps(validate_cookies(cookies), ensure_ascii=True, allow_nan=False).encode()
    if len(body) > MAX_COOKIE_BYTES:
        raise ValueError("cookie JSON exceeds byte limit")
    with _parent_directory(Path(path), create=True) as (directory, name):
        temporary = f".{name}.{secrets.token_hex(12)}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            # Atomic, no-clobber publication. A raced symlink/existing target fails.
            os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            os.fsync(directory)
        finally:
            os.unlink(temporary, dir_fd=directory)
    return Path(path)


def load_cookies(path: Path) -> list[dict]:
    with _parent_directory(Path(path)) as (directory, name):
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise ValueError("cookie file must be a regular file owned by this user with mode 0600")
            body = handle.read(MAX_COOKIE_BYTES + 1)
    if len(body) > MAX_COOKIE_BYTES:
        raise ValueError("cookie JSON exceeds byte limit")
    try:
        return validate_cookies(json.loads(body))
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError("cookie file must be valid JSON; recapture legacy pickle cookies") from exc
