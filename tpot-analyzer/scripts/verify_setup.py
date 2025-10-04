"""Phase 1.1 verification script for the TPOT Community Graph Analyzer."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from textwrap import indent

from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_cache_settings, get_supabase_client  # noqa: E402
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
    fetcher = CachedDataFetcher(cache_db=cache_settings.path)
    success = True

    # 1. Supabase connectivity
    try:
        client = get_supabase_client()
        ping = client.table("profiles").select("account_id").limit(1).execute()
        ok = getattr(ping, "error", None) in (None, "")
        print(_fmt_status(ok, "Supabase connection successful" if ok else f"Supabase error: {ping.error}"))
        if not ok:
            return 1
    except Exception as exc:
        print(_fmt_status(False, f"Supabase connection failed: {exc}"))
        return 1

    # 2. Profiles fetch + cache write
    try:
        profiles = fetcher.fetch_profiles()
        row_count = len(profiles)
        ok = row_count == 275
        message = f"Found {row_count} profiles in Community Archive"
        print(_fmt_status(ok, message))
        if not ok:
            success = False
    except Exception as exc:
        print(_fmt_status(False, f"Profile fetch failed: {exc}"))
        return 1

    cache_file = cache_settings.path
    if cache_file.exists():
        size_kb = cache_file.stat().st_size / 1024
        status = fetcher.cache_status().get("profiles")
        if status:
            fetched_at = status["fetched_at"].astimezone(timezone.utc)
            age_minutes = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 60
            freshness = "FRESH" if age_minutes <= (cache_settings.max_age_days * 1440) else "STALE"
            freshness_msg = f"Cache status: {freshness} (fetched {age_minutes:.1f} minutes ago)"
        else:
            freshness_msg = "Cache status: UNKNOWN (metadata missing)"
    else:
        size_kb = 0.0
        freshness_msg = "Cache status: MISSING (cache file not created)"

    print(_fmt_status(True, f"Cache initialized at: {cache_file} ({size_kb:.1f} KB)"))
    print(_fmt_status(True, freshness_msg))

    if 'profiles' in locals():
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
