#!/usr/bin/env python3
"""Bulk-resolve usernames for band-classified accounts via Supabase.

The export pipeline skips accounts without usernames. This script fills
the gap by querying Supabase mentioned_users (screen_name by user_id)
for all account_band accounts that lack a username in profiles or
resolved_accounts.

Zero API cost — queries our own Supabase instance.

Usage:
    .venv/bin/python3 -m scripts.resolve_band_usernames           # dry-run
    .venv/bin/python3 -m scripts.resolve_band_usernames --write   # update DB
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "archive_tweets.db"

BATCH_SIZE = 50


def load_unresolved_ids(db: sqlite3.Connection) -> list[str]:
    """Return account_ids from account_band that have no username anywhere."""
    already = set()
    for r in db.execute(
        "SELECT account_id FROM profiles WHERE username IS NOT NULL"
    ).fetchall():
        already.add(r[0])
    for r in db.execute(
        "SELECT account_id FROM resolved_accounts WHERE username IS NOT NULL AND username != ''"
    ).fetchall():
        already.add(r[0])

    band_ids = [
        r[0]
        for r in db.execute(
            "SELECT account_id FROM account_band WHERE band != 'unknown'"
        ).fetchall()
    ]

    return [aid for aid in band_ids if aid not in already]


def resolve_via_supabase(account_ids: list[str]) -> dict[str, str]:
    """Batch-query Supabase mentioned_users by user_id.

    Returns {account_id: screen_name}.
    """
    try:
        from src.config import get_supabase_config
        cfg = get_supabase_config()
    except Exception as e:
        logger.error("Supabase config unavailable: %s", e)
        return {}

    found: dict[str, str] = {}
    total = len(account_ids)
    n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, total, BATCH_SIZE):
        batch = account_ids[i : i + BATCH_SIZE]
        in_clause = ",".join(batch)
        url = (
            f"{cfg.url}/rest/v1/mentioned_users"
            f"?select=user_id,screen_name&user_id=in.({in_clause})"
        )
        try:
            resp = httpx.get(url, headers=cfg.rest_headers, timeout=20)
            if resp.status_code == 200:
                for row in resp.json():
                    uid = str(row.get("user_id", "")).strip()
                    sn = str(row.get("screen_name", "")).strip()
                    if uid and sn and uid not in found:
                        found[uid] = sn
            elif resp.status_code == 429:
                logger.warning("Rate limited at batch %d — sleeping 3s", i // BATCH_SIZE)
                time.sleep(3)
            else:
                logger.debug("Batch %d: HTTP %d", i // BATCH_SIZE, resp.status_code)
        except Exception as e:
            logger.warning("Batch %d error: %s", i // BATCH_SIZE, e)

        batch_num = i // BATCH_SIZE + 1
        if batch_num % 50 == 0 or batch_num == n_batches:
            logger.info(
                "  Progress: %d/%d batches, %d resolved so far",
                batch_num, n_batches, len(found),
            )

    return found


def write_resolved(
    db: sqlite3.Connection, resolved: dict[str, str]
) -> int:
    """Insert resolved usernames into resolved_accounts. Returns rows inserted."""
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for aid, username in resolved.items():
        try:
            db.execute(
                "INSERT OR IGNORE INTO resolved_accounts "
                "(account_id, username, display_name, status, resolved_at) "
                "VALUES (?, ?, '', 'active', ?)",
                (aid, username, now),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass
    db.commit()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk-resolve usernames for band accounts via Supabase"
    )
    parser.add_argument("--write", action="store_true", help="Write to DB (default: dry-run)")
    args = parser.parse_args()

    db = sqlite3.connect(str(DB_PATH))

    print("=" * 70)
    print("BAND USERNAME RESOLUTION")
    print("=" * 70)

    unresolved = load_unresolved_ids(db)
    print(f"  Band accounts without username: {len(unresolved)}")

    if not unresolved:
        print("  Nothing to resolve.")
        db.close()
        return

    print(f"  Querying Supabase mentioned_users ({len(unresolved)} IDs, "
          f"{(len(unresolved) + BATCH_SIZE - 1) // BATCH_SIZE} batches)...")
    t0 = time.perf_counter()
    resolved = resolve_via_supabase(unresolved)
    elapsed = time.perf_counter() - t0

    print(f"\n  Resolved: {len(resolved)} / {len(unresolved)} "
          f"({len(resolved) / len(unresolved) * 100:.1f}%) in {elapsed:.1f}s")
    still_missing = len(unresolved) - len(resolved)
    print(f"  Still missing: {still_missing}")

    if resolved:
        print(f"\n  Sample resolutions:")
        for aid, sn in list(resolved.items())[:15]:
            print(f"    {aid:<22} -> @{sn}")

    if args.write:
        n = write_resolved(db, resolved)
        print(f"\n  Wrote {n} rows to resolved_accounts.")

        # Verify new export coverage
        total_with_name = db.execute("""
            SELECT COUNT(DISTINCT ab.account_id)
            FROM account_band ab
            WHERE ab.band != 'unknown'
              AND (
                EXISTS (SELECT 1 FROM profiles p WHERE p.account_id = ab.account_id AND p.username IS NOT NULL)
                OR EXISTS (SELECT 1 FROM resolved_accounts ra WHERE ra.account_id = ab.account_id AND ra.username IS NOT NULL AND ra.username != '')
              )
        """).fetchone()[0]
        print(f"  Band accounts with username now: {total_with_name}")
    else:
        print(f"\n  DRY RUN — pass --write to update DB.")

    db.close()


if __name__ == "__main__":
    main()
