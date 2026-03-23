"""Resolve unmatched tpot_directory_holdout handles to account_ids.

Resolution order (cheapest first):
  1. Local: archive_tweets.db profiles + resolved_accounts
  2. Local: cache.db shadow_account + account tables (real numeric IDs only)
  3. Supabase: mentioned_users (screen_name → user_id)
  4. twitterapi.io: /twitter/user/info per handle (~$0.15/1000, ~165 calls)

Updates tpot_directory_holdout.account_id in place.

Usage:
    .venv/bin/python3 -m scripts.resolve_directory_handles           # dry-run
    .venv/bin/python3 -m scripts.resolve_directory_handles --write   # update DB
    .venv/bin/python3 -m scripts.resolve_directory_handles --skip-api  # local + Supabase only
"""
from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DB = ROOT / "data" / "archive_tweets.db"
CACHE_DB = ROOT / "data" / "cache.db"

TWITTERAPI_BASE = "https://api.twitterapi.io/twitter/user/info"
_SHADOW_ID_PREFIX = "shadow:"  # fake IDs used internally — filter these out


def load_unresolved(db: sqlite3.Connection) -> list[tuple[str, str]]:
    """Return [(handle_lower, source), ...] for rows missing account_id."""
    return [
        (row[0].lower().lstrip("@"), row[1])
        for row in db.execute(
            "SELECT handle, source FROM tpot_directory_holdout WHERE account_id IS NULL"
        ).fetchall()
    ]


def build_local_lookup(handles: set[str]) -> dict[str, tuple[str, str]]:
    """Check local DBs. Returns {handle_lower: (account_id, source_label)}."""
    found: dict[str, tuple[str, str]] = {}

    # archive_tweets.db: profiles (highest trust)
    adb = sqlite3.connect(str(ARCHIVE_DB))
    for h, aid in adb.execute("SELECT LOWER(username), account_id FROM profiles").fetchall():
        if h in handles and h not in found:
            found[h] = (aid, "profiles")
    for h, aid in adb.execute(
        "SELECT LOWER(username), account_id FROM resolved_accounts WHERE account_id IS NOT NULL"
    ).fetchall():
        if h in handles and h not in found:
            found[h] = (aid, "resolved_accounts")
    adb.close()

    if not CACHE_DB.exists():
        return found

    # cache.db: shadow_account, account — skip fake shadow IDs
    cdb = sqlite3.connect(str(CACHE_DB))
    for table in ("shadow_account", "account"):
        try:
            for h, aid in cdb.execute(
                f"SELECT LOWER(username), account_id FROM {table} WHERE username IS NOT NULL"
            ).fetchall():
                if h in handles and h not in found and aid and not str(aid).startswith(_SHADOW_ID_PREFIX):
                    found[h] = (aid, f"cache.{table}")
        except sqlite3.OperationalError:
            pass
    cdb.close()

    return found


def build_supabase_lookup(handles: set[str]) -> dict[str, tuple[str, str]]:
    """Query Supabase mentioned_users (screen_name → user_id)."""
    try:
        from src.config import get_supabase_config
        cfg = get_supabase_config()
    except Exception as e:
        logger.warning("Supabase config unavailable: %s", e)
        return {}

    found: dict[str, tuple[str, str]] = {}
    handle_list = sorted(handles)
    batch_size = 50

    for i in range(0, len(handle_list), batch_size):
        batch = handle_list[i : i + batch_size]
        in_clause = ",".join(batch)
        url = f"{cfg.url}/rest/v1/mentioned_users?select=screen_name,user_id&screen_name=in.({in_clause})"
        try:
            resp = httpx.get(url, headers=cfg.rest_headers, timeout=20)
            if resp.status_code == 200:
                for row in resp.json():
                    h = str(row.get("screen_name", "")).lower()
                    uid = str(row.get("user_id", "")).strip()
                    if h and uid and h in handles and h not in found:
                        found[h] = (uid, "supabase.mentioned_users")
        except Exception as e:
            logger.warning("Supabase batch %d error: %s", i // batch_size, e)

    return found


def build_twitterapi_lookup(handles: set[str]) -> dict[str, tuple[str, str]]:
    """Resolve via twitterapi.io /twitter/user/info (one call per handle).

    Cost: ~$0.15/1000 calls. For 165 handles ≈ $0.025.
    Suspended/deactivated accounts return unavailable=true — skipped cleanly.
    """
    api_key = (
        os.environ.get("TWITTERAPI_IO_API_KEY")
        or os.environ.get("TWITTERAPI_API_KEY")
        or os.environ.get("API_KEY", "")
    ).strip()
    if not api_key:
        logger.warning("No twitterapi.io key found — skipping API lookup")
        return {}

    headers = {"X-API-Key": api_key}
    found: dict[str, tuple[str, str]] = {}
    suspended: list[str] = []

    for i, handle in enumerate(sorted(handles)):
        try:
            resp = httpx.get(
                TWITTERAPI_BASE,
                params={"userName": handle},
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json().get("data") or {}
                if data.get("unavailable"):
                    suspended.append(handle)
                else:
                    uid = str(data.get("id") or data.get("user_id") or "").strip()
                    if uid:
                        found[handle] = (uid, "twitterapi.io")
            elif resp.status_code == 429:
                logger.warning("twitterapi.io rate limited at handle %d — sleeping 5s", i)
                time.sleep(5)
            else:
                logger.debug("twitterapi.io %d for @%s: %s", resp.status_code, handle, resp.text[:100])
        except Exception as e:
            logger.warning("twitterapi.io error for @%s: %s", handle, e)

        if i > 0 and i % 50 == 0:
            logger.info("  twitterapi.io progress: %d/%d resolved so far", len(found), i + 1)

    if suspended:
        logger.info("  Suspended/deactivated accounts (%d): %s", len(suspended), suspended[:10])

    return found


def build_graph_lookup(handles: set[str]) -> dict[str, tuple[str, str]]:
    """Layer 4: cross-reference local mention_graph + quote_graph via Supabase mentioned_users.

    Strategy:
      A) Collect all unique numeric IDs from local mention_graph + quote_graph.
      B) Batch-query Supabase mentioned_users by user_id → get screen_names.
      C) Match returned screen_names (case-insensitive) against unresolved handles.
      D) Also issue per-handle ilike queries to catch casing misses from Layer 2's
         case-sensitive in.() filter.
    """
    try:
        from src.config import get_supabase_config
        cfg = get_supabase_config()
    except Exception as e:
        logger.warning("Supabase config unavailable for graph lookup: %s", e)
        return {}

    found: dict[str, tuple[str, str]] = {}

    # ── A. Collect all IDs from local mention_graph + quote_graph ─────────────
    graph_ids: set[str] = set()
    adb = sqlite3.connect(str(ARCHIVE_DB))
    for table in ("mention_graph", "quote_graph"):
        try:
            for row in adb.execute(f"SELECT source_id, target_id FROM {table}").fetchall():
                for val in row:
                    if val and str(val).strip().lstrip("-").isdigit():
                        graph_ids.add(str(val).strip())
        except sqlite3.OperationalError:
            logger.debug("Table %s not found in archive DB — skipping", table)
    adb.close()

    logger.info("  Layer 4 — graph IDs collected: %d unique IDs", len(graph_ids))

    # ── B. Batch-query Supabase mentioned_users by user_id ────────────────────
    id_to_screen: dict[str, str] = {}
    id_list = sorted(graph_ids)
    batch_size = 50

    for i in range(0, len(id_list), batch_size):
        batch = id_list[i : i + batch_size]
        in_clause = ",".join(batch)
        url = f"{cfg.url}/rest/v1/mentioned_users?select=user_id,screen_name&user_id=in.({in_clause})"
        try:
            resp = httpx.get(url, headers=cfg.rest_headers, timeout=20)
            if resp.status_code == 200:
                for row in resp.json():
                    uid = str(row.get("user_id", "")).strip()
                    sn = str(row.get("screen_name", "")).lower().strip()
                    if uid and sn:
                        id_to_screen[uid] = sn
        except Exception as e:
            logger.warning("  Supabase graph batch %d error: %s", i // batch_size, e)

    logger.info("  Layer 4 — screen_names resolved from graph IDs: %d", len(id_to_screen))

    # ── C. Match screen_names against unresolved handles ─────────────────────
    for uid, sn in id_to_screen.items():
        if sn in handles and sn not in found:
            found[sn] = (uid, "graph.mentioned_users")

    if found:
        logger.info("  Layer 4 — matched via graph ID lookup: %d", len(found))

    # ── D. ilike per-handle queries for remaining (catches casing misses) ─────
    still_missing = handles - found.keys()
    if still_missing:
        logger.info("  Layer 4 — ilike fallback for %d remaining handles", len(still_missing))
        for handle in sorted(still_missing):
            try:
                resp = httpx.get(
                    f"{cfg.url}/rest/v1/mentioned_users",
                    params={"select": "user_id,screen_name", "screen_name": f"ilike.{handle}", "limit": "1"},
                    headers=cfg.rest_headers,
                    timeout=15,
                )
                if resp.status_code == 200:
                    rows = resp.json()
                    if rows:
                        row = rows[0]
                        uid = str(row.get("user_id", "")).strip()
                        sn = str(row.get("screen_name", "")).lower().strip()
                        if uid and sn == handle and handle not in found:
                            found[handle] = (uid, "ilike.mentioned_users")
            except Exception as e:
                logger.warning("  ilike error for @%s: %s", handle, e)

    return found


def write_resolutions(
    db: sqlite3.Connection,
    resolutions: dict[str, tuple[str, str]],
) -> int:
    """UPDATE tpot_directory_holdout for resolved handles. Returns rows updated."""
    updated = 0
    for handle_lower, (account_id, _source) in resolutions.items():
        result = db.execute(
            "UPDATE tpot_directory_holdout SET account_id = ? WHERE LOWER(handle) = ? AND account_id IS NULL",
            (account_id, handle_lower),
        )
        updated += result.rowcount
    db.commit()
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve tpot_directory_holdout handles to account_ids")
    parser.add_argument("--write", action="store_true", help="Write resolutions to DB (default: dry-run)")
    parser.add_argument("--skip-api", action="store_true", help="Skip twitterapi.io calls (local + Supabase only)")
    args = parser.parse_args()

    db = sqlite3.connect(str(ARCHIVE_DB))
    unresolved = load_unresolved(db)

    print(f"{'=' * 70}")
    print("DIRECTORY HANDLE RESOLUTION")
    print(f"{'=' * 70}")
    print(f"  Unresolved before: {len(unresolved)}")

    if not unresolved:
        print("  Nothing to resolve.")
        db.close()
        return

    handle_set = {h for h, _ in unresolved}

    # Layer 1: local
    local = build_local_lookup(handle_set)
    remaining = handle_set - local.keys()
    print(f"\n  Layer 1 — local DB:        +{len(local):>3}  ({len(remaining)} remaining)")

    # Layer 2: Supabase
    supa = build_supabase_lookup(remaining)
    remaining -= supa.keys()
    print(f"  Layer 2 — Supabase:        +{len(supa):>3}  ({len(remaining)} remaining)")

    # Layer 3: twitterapi.io
    tapi: dict[str, tuple[str, str]] = {}
    if not args.skip_api and remaining:
        print(f"  Layer 3 — twitterapi.io:   resolving {len(remaining)} handles (~${len(remaining)*0.00015:.3f})...")
        tapi = build_twitterapi_lookup(remaining)
        remaining -= tapi.keys()
        print(f"             result:        +{len(tapi):>3}  ({len(remaining)} remaining)")

    # Layer 4: graph cross-reference (mention_graph + quote_graph → Supabase mentioned_users)
    graph: dict[str, tuple[str, str]] = {}
    if remaining:
        print(f"  Layer 4 — graph lookup:    resolving {len(remaining)} handles via mention/quote graph...")
        graph = build_graph_lookup(remaining)
        remaining -= graph.keys()
        print(f"             result:        +{len(graph):>3}  ({len(remaining)} remaining)")

    all_found = {**local, **supa, **tapi, **graph}
    print(f"\n  Total resolved: {len(all_found)} / {len(unresolved)}")
    print(f"  Still unresolved: {len(remaining)}")

    # Source breakdown
    from collections import Counter
    src_counts = Counter(v[1] for v in all_found.values())
    for src, cnt in src_counts.most_common():
        print(f"    {src}: {cnt}")

    # Sample resolutions
    if all_found:
        print(f"\n  Sample resolutions:")
        for h, (aid, src) in list(all_found.items())[:15]:
            print(f"    @{h:<28} -> {aid:<22} [{src}]")

    # Unresolved remainder (likely suspended/deactivated)
    if remaining:
        print(f"\n  Still unresolved ({len(remaining)}) — likely suspended/deactivated:")
        for h in sorted(remaining)[:20]:
            print(f"    @{h}")
        if len(remaining) > 20:
            print(f"    ... and {len(remaining) - 20} more")

    if args.write:
        n = write_resolutions(db, all_found)
        print(f"\n  Wrote {n} account_id values to tpot_directory_holdout.")
    else:
        print(f"\n  DRY RUN — pass --write to update DB.")

    db.close()


if __name__ == "__main__":
    main()
