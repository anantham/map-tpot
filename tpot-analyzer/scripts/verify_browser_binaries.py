#!/usr/bin/env python3
"""
Verify browser-binary configuration and detect cached "Google Chrome for Testing" apps.

Checks:
  - Environment variables: TPOT_CHROME_BINARY, CHROME_BIN, PUPPETEER_EXECUTABLE_PATH
  - Known cache locations for "Google Chrome for Testing.app"
  - Summary of counts and approximate disk usage

This script is intentionally dependency-free (std-lib only).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable, Optional


ENV_VARS = ("TPOT_CHROME_BINARY", "CHROME_BIN", "PUPPETEER_EXECUTABLE_PATH")


def _format_bytes(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            return f"{value:.1f}{unit}"
        value /= 1024.0
    return f"{num_bytes}B"


def _is_macos_app_bundle(path: Path) -> bool:
    return path.suffix == ".app" and path.is_dir()


def _resolve_macos_app_binary(app_bundle: Path) -> Optional[Path]:
    macos_dir = app_bundle / "Contents" / "MacOS"
    if not macos_dir.is_dir():
        return None

    canonical = macos_dir / app_bundle.stem
    if canonical.is_file():
        return canonical

    for entry in macos_dir.iterdir():
        if entry.is_file():
            return entry

    return None


def _resolve_binary_path(raw: str) -> tuple[Optional[Path], Optional[str]]:
    """Return (resolved_path, error_reason)."""

    if not raw:
        return None, "not set"

    path = Path(raw).expanduser()
    if _is_macos_app_bundle(path):
        resolved = _resolve_macos_app_binary(path)
        if resolved is None:
            return None, f"app bundle missing Contents/MacOS: {path}"
        return resolved, None

    if path.is_file():
        return path, None

    return None, f"path not found: {path}"


def _walk_size_bytes(root: Path) -> int:
    total = 0
    try:
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                try:
                    total += (Path(dirpath) / name).stat().st_size
                except OSError:
                    continue
    except OSError:
        return 0
    return total


def _find_chrome_for_testing_apps(search_roots: Iterable[Path]) -> list[Path]:
    matches: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        try:
            for path in root.rglob("Google Chrome for Testing.app"):
                if path.is_dir():
                    matches.append(path)
        except OSError:
            continue
    return matches


def _status_line(ok: bool, label: str, detail: str = "") -> str:
    prefix = "✓" if ok else "✗"
    if detail:
        return f"{prefix} {label}: {detail}"
    return f"{prefix} {label}"


def main(argv: list[str]) -> int:
    home = Path.home()
    selenium_cache = home / ".cache" / "selenium" / "chrome"
    puppeteer_cache = home / ".cache" / "puppeteer"
    playwright_cache = home / "Library" / "Caches" / "ms-playwright"

    print("============================================================")
    print("BROWSER BINARY + CACHE VERIFICATION")
    print("============================================================")

    print("\nEnvironment variables:")
    any_browser_env = False
    for key in ENV_VARS:
        raw = os.getenv(key, "")
        resolved, error = _resolve_binary_path(raw)
        if resolved is not None:
            any_browser_env = True
            print(_status_line(True, key, str(resolved)))
        else:
            if raw:
                print(_status_line(False, key, error or "invalid"))
            else:
                print(_status_line(False, key, "not set"))

    if not any_browser_env:
        print(
            "\nNext step:\n"
            "  - Set `TPOT_CHROME_BINARY` (preferred) or `CHROME_BIN` to your system browser.\n"
            "    Example (Brave):\n"
            '      export TPOT_CHROME_BINARY="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"\n'
        )

    print("\nCache inventory (Google Chrome for Testing.app):")
    roots = [selenium_cache, puppeteer_cache, playwright_cache]
    matches = _find_chrome_for_testing_apps(roots)
    if matches:
        total_size = 0
        for app in matches:
            total_size += _walk_size_bytes(app)
        print(_status_line(False, "Found cached Chrome for Testing apps", f"{len(matches)} app(s), ~{_format_bytes(total_size)}"))
        for sample in matches[:12]:
            print(f"  - {sample}")
        if len(matches) > 12:
            print(f"  ... ({len(matches) - 12} more)")
    else:
        print(_status_line(True, "No cached Chrome for Testing apps found"))

    print("\nCache sizes (approx):")
    for root in roots:
        if root.exists():
            size = _walk_size_bytes(root)
            print(_status_line(True, str(root), _format_bytes(size)))
        else:
            print(_status_line(True, str(root), "missing"))

    print("\nNotes:")
    print("- Selenium in this repo respects `--chrome-binary` and also TPOT_CHROME_BINARY/CHROME_BIN.")
    print("- Puppeteer projects should prefer `puppeteer-core` + PUPPETEER_EXECUTABLE_PATH to avoid downloads.")
    print("- Playwright uses its own managed browsers; keep them unless you intentionally want to reinstall.")
    print("============================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

