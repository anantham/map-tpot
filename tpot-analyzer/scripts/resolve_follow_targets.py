#!/usr/bin/env python3
"""
Build a resolved_accounts lookup table in archive_tweets.db.

Maps numeric Twitter accountIds → usernames using local sources only:
  1. profiles table in archive_tweets.db (seed accounts with full archive)
  2. account table in cache.db (seed list with IDs)

Any ID not resolved locally is marked 'unknown'. Empirically, 10/10 of the
top-200 unresolved following targets tested against twitterapi.io were
suspended accounts — so 'unknown' effectively means suspended/deplatformed.

Usage:
    python scripts/resolve_follow_targets.py              # resolve top 1000
    python scripts/resolve_follow_targets.py --all        # resolve all 171K
    python scripts/resolve_follow_targets.py --dry-run    # stats only
"""

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT       = Path(__file__).resolve().parents[1]
ARCHIVE_DB = ROOT / "data" / "archive_tweets.db"
CACHE_DB   = ROOT / "data" / "cache.db"

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS resolved_accounts (
    account_id   TEXT PRIMARY KEY,
    username     TEXT,
    display_name TEXT,
    status       TEXT NOT NULL DEFAULT 'active',
    resolved_at  TEXT NOT NULL
)
"""


def load_local_id_map() -> dict:
    """Return {account_id: (username, display_name)} from all local sources."""
    id_map: dict[str, tuple[str, str]] = {}

    # Source 1: profiles in archive_tweets.db (seed accounts, has username column)
    try:
        arc = sqlite3.connect(str(ARCHIVE_DB))
        for aid, username in arc.execute(
            "SELECT account_id, username FROM profiles"
        ).fetchall():
            if aid and username:
                id_map[aid] = (username, "")
        arc.close()
    except Exception as e:
        print(f"  [warn] Could not read archive profiles: {e}")

    # Source 2: account table in cache.db (seed list with numeric IDs)
    try:
        cache = sqlite3.connect(str(CACHE_DB))
        for aid, username in cache.execute(
            "SELECT account_id, username FROM account WHERE username IS NOT NULL"
        ).fetchall():
            if aid and username and aid not in id_map:
                id_map[aid] = (username, "")
        cache.close()
    except Exception as e:
        print(f"  [warn] Could not read cache accounts: {e}")

    return id_map


def get_follow_targets(top: Optional[int]) -> list:
    """Return [(account_id, follow_count)] sorted by follow_count desc."""
    arc = sqlite3.connect(str(ARCHIVE_DB))
    query = """
        SELECT following_account_id, COUNT(*) as n
        FROM account_following
        GROUP BY following_account_id
        ORDER BY n DESC
    """
    if top:
        query += f" LIMIT {top}"
    rows = arc.execute(query).fetchall()
    arc.close()
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all",     action="store_true", help="Resolve all following targets (171K)")
    parser.add_argument("--top",     type=int, default=1000, help="Resolve top-N by follow count (default 1000)")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing to DB")
    args = parser.parse_args()

    top = None if args.all else args.top

    print("Loading local ID → username mappings...")
    id_map = load_local_id_map()
    print(f"  Local map: {len(id_map):,} account IDs resolved")

    print(f"\nLoading {'all' if top is None else f'top {top}'} following targets...")
    targets = get_follow_targets(top)
    print(f"  Targets to process: {len(targets):,}")

    now = datetime.now(timezone.utc).isoformat()

    resolved = []    # (account_id, username, display_name, 'active', now)
    unknown  = []    # (account_id, None, None, 'unknown', now)

    for aid, n in targets:
        if aid in id_map:
            username, display_name = id_map[aid]
            resolved.append((aid, username, display_name, "active", now))
        else:
            unknown.append((aid, None, None, "unknown", now))

    print(f"\nResolution results:")
    print(f"  ✓ Resolved (active):  {len(resolved):,}")
    print(f"  ? Unknown/suspended:  {len(unknown):,}")
    print(f"  Coverage: {100 * len(resolved) / max(1, len(targets)):.1f}%")

    if resolved:
        print(f"\nSample resolved accounts:")
        for aid, username, _, status, _ in resolved[:10]:
            n = next(cnt for a, cnt in targets if a == aid)
            print(f"  {n:3d}x  {aid:<22}  @{username}")

    if unknown[:5]:
        print(f"\nSample unknown (likely suspended):")
        for aid, *_ in unknown[:5]:
            n = next(cnt for a, cnt in targets if a == aid)
            print(f"  {n:3d}x  {aid}")

    if args.dry_run:
        print("\n[dry-run] No changes written.")
        return

    # Write to DB
    arc = sqlite3.connect(str(ARCHIVE_DB))
    arc.execute(CREATE_TABLE)
    arc.commit()

    arc.executemany(
        "INSERT OR REPLACE INTO resolved_accounts VALUES (?,?,?,?,?)",
        resolved + unknown,
    )
    arc.commit()

    total = arc.execute("SELECT COUNT(*) FROM resolved_accounts").fetchone()[0]
    active = arc.execute(
        "SELECT COUNT(*) FROM resolved_accounts WHERE status='active'"
    ).fetchone()[0]
    arc.close()

    print(f"\n✓ resolved_accounts table updated:")
    print(f"  Total rows:  {total:,}")
    print(f"  Active:      {active:,}")
    print(f"  Unknown:     {total - active:,}")


if __name__ == "__main__":
    main()
