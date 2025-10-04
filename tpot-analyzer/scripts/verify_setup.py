"""Phase 1.1 verification script for the TPOT Community Graph Analyzer."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from textwrap import indent

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_cache_settings, get_supabase_config  # noqa: E402
from src.data.fetcher import CachedDataFetcher  # noqa: E402

CHECK_MARK = "\u2713"
CROSS_MARK = "\u2717"


def _fmt_status(ok: bool, message: str) -> str:
    symbol = CHECK_MARK if ok else CROSS_MARK
    return f"{symbol} {message}"


def _format_sample_rows(df, limit: int = 5) -> str:
    cols = [c for c in ("username", "account_id") if c in df.columns]
    items = []
    for _, row in df.head(limit).iterrows():
        if len(cols) == 2:
            items.append(f"- @{row[cols[0]]} ({row[cols[1]]})")
        elif cols:
            items.append(f"- {row[cols[0]]}")
        else:
            items.append(f"- {row.iloc[0]}")
    return "Sample accounts:\n" + indent("\n".join(items), "  ")


def main() -> int:
    cache_settings = get_cache_settings()
    supabase_cfg = get_supabase_config()
    success = True

    # 1. Supabase connectivity
    try:
        with httpx.Client(base_url=supabase_cfg.url, headers=supabase_cfg.rest_headers, timeout=15.0) as client:
            ping = client.get(
                "/rest/v1/profile",
                params={"select": "account_id", "limit": 1},
                headers={"Range": "0-0"},
            )
        if ping.status_code not in (200, 206):
            print(_fmt_status(False, f"Supabase returned {ping.status_code}: {ping.text}"))
            return 1
        print(_fmt_status(True, "Supabase connection successful"))
    except Exception as exc:  # pragma: no cover - network edge cases
        print(_fmt_status(False, f"Supabase connection failed: {exc}"))
        return 1

    # 2. Profiles fetch + cache write
    try:
        with CachedDataFetcher(cache_db=cache_settings.path) as fetcher:
            profiles = fetcher.fetch_profiles()
            status = fetcher.cache_status().get("profile")
    except Exception as exc:
        print(_fmt_status(False, f"Profile fetch failed: {exc}"))
        return 1

    row_count = len(profiles)
    ok = row_count == 275
    message = f"Found {row_count} profiles in Community Archive"
    print(_fmt_status(ok, message))
    if not ok:
        success = False

    cache_file = cache_settings.path
    if cache_file.exists():
        size_kb = cache_file.stat().st_size / 1024
        print(_fmt_status(True, f"Cache initialized at: {cache_file} ({size_kb:.1f} KB)"))
        if status:
            fetched_at = status["fetched_at"].astimezone(timezone.utc)
            age_minutes = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 60
            freshness = "FRESH" if age_minutes <= (cache_settings.max_age_days * 1440) else "STALE"
            print(_fmt_status(True, f"Cache status: {freshness} (fetched {age_minutes:.1f} minutes ago)"))
        else:
            print(_fmt_status(True, "Cache status: UNKNOWN (metadata missing)"))
    else:
        print(_fmt_status(True, "Cache status: MISSING (cache file not created)"))

    print()
    print(_format_sample_rows(profiles))
    print()
    print("Next steps:")
    print("  - Run 'pytest tests/ -v' to execute automated checks")
    print("  - Proceed to Phase 1.2: Build engagement graph")

    if not success:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
