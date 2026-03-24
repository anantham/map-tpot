"""Batch fetch user profile data (followers/following counts) from twitterapi.io.

Stores results in user_profile_cache table in archive_tweets.db.
Uses the Batch Get User Info By UserIds endpoint (up to 100 IDs per call).

Note: numpy is used to load propagation .npz files (our own precomputed data,
not untrusted external content).

Usage:
    .venv/bin/python3 -m scripts.fetch_user_profiles --min-inbound 50
    .venv/bin/python3 -m scripts.fetch_user_profiles --accounts eigenrobot,elonmusk
    .venv/bin/python3 -m scripts.fetch_user_profiles --min-inbound 50 --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
from dotenv import load_dotenv

from scripts.fetch_tweets_for_account import get_api_key
from src.config import DEFAULT_ARCHIVE_DB

load_dotenv()

logger = logging.getLogger(__name__)

BATCH_URL = "https://api.twitterapi.io/twitter/user/batch_info_by_ids"
BATCH_SIZE = 100  # API limit per call


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_profile_cache (
            account_id   TEXT PRIMARY KEY,
            username     TEXT,
            followers    INTEGER,
            following    INTEGER,
            statuses     INTEGER,
            favourites   INTEGER,
            is_verified  INTEGER DEFAULT 0,
            is_blue      INTEGER DEFAULT 0,
            description  TEXT,
            location     TEXT,
            created_at   TEXT,
            raw_json     TEXT,
            fetched_at   TEXT
        )
    """)
    conn.commit()


def fetch_batch(api_key: str, user_ids: list[str]) -> list[dict]:
    """Fetch user profiles for up to 100 user IDs in one call."""
    resp = httpx.get(
        BATCH_URL,
        params={"userIds": ",".join(user_ids)},
        headers={"X-API-Key": api_key},
        timeout=30,
    )

    if resp.status_code == 429:
        logger.warning("Rate limited, waiting 60s...")
        time.sleep(60)
        resp = httpx.get(
            BATCH_URL,
            params={"userIds": ",".join(user_ids)},
            headers={"X-API-Key": api_key},
            timeout=30,
        )

    resp.raise_for_status()
    data = resp.json()

    users = data.get("users", [])
    if not users and "data" in data:
        users = data["data"] if isinstance(data["data"], list) else []

    return users


def store_profiles(conn: sqlite3.Connection, users: list[dict]) -> int:
    """Store fetched profiles into user_profile_cache. Returns count stored."""
    now = datetime.now(timezone.utc).isoformat()
    stored = 0
    for u in users:
        uid = u.get("id")
        if not uid:
            continue
        conn.execute("""
            INSERT OR REPLACE INTO user_profile_cache
            (account_id, username, followers, following, statuses, favourites,
             is_verified, is_blue, description, location, created_at, raw_json, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uid),
            u.get("userName"),
            u.get("followers"),
            u.get("following"),
            u.get("statusesCount"),
            u.get("favouritesCount"),
            1 if u.get("isVerified") else 0,
            1 if u.get("isBlueVerified") else 0,
            u.get("description"),
            u.get("location"),
            u.get("createdAt"),
            json.dumps(u),
            now,
        ))
        stored += 1
    conn.commit()
    return stored


def get_tier1_account_ids(
    conn: sqlite3.Connection, min_inbound: int = 50,
) -> list[str]:
    """Get account IDs for placed accounts needing profile data.

    Returns accounts that have >= min_inbound followers in our graph,
    are NOT already cached, and have seed_neighbor_counts >= 1.
    """
    npz_path = Path("data/community_propagation.npz")
    if not npz_path.exists():
        logger.error("No propagation data at %s", npz_path)
        return []

    npz = np.load(str(npz_path), allow_pickle=True)
    node_ids = npz["node_ids"]
    seed_neighbor_counts = npz["seed_neighbor_counts"]
    labeled_mask = npz["labeled_mask"]

    placed = set()
    for i in range(len(node_ids)):
        if labeled_mask[i]:
            continue
        if seed_neighbor_counts[i].max() >= 1:
            placed.add(node_ids[i])

    inbound = {}
    for aid, cnt in conn.execute(
        "SELECT following_account_id, COUNT(*) FROM account_following GROUP BY following_account_id"
    ).fetchall():
        inbound[aid] = cnt

    _ensure_table(conn)
    cached = set(
        r[0] for r in conn.execute("SELECT account_id FROM user_profile_cache").fetchall()
    )

    candidates = []
    for aid in placed:
        if inbound.get(aid, 0) >= min_inbound and aid not in cached:
            candidates.append((aid, inbound[aid]))

    candidates.sort(key=lambda x: -x[1])
    return [aid for aid, _ in candidates]


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Batch fetch user profiles")
    parser.add_argument("--min-inbound", type=int, default=50,
                        help="Min inbound edges in our graph (default: 50)")
    parser.add_argument("--accounts", type=str, default=None,
                        help="Comma-separated usernames to fetch")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_ARCHIVE_DB)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max accounts to fetch")
    args = parser.parse_args()

    conn = sqlite3.connect(str(args.db_path))
    _ensure_table(conn)

    if args.accounts:
        handles = [h.strip().lstrip("@") for h in args.accounts.split(",")]
        account_ids = []
        for h in handles:
            row = conn.execute(
                "SELECT account_id FROM resolved_accounts WHERE lower(username) = lower(?)", (h,)
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT account_id FROM profiles WHERE lower(username) = lower(?)", (h,)
                ).fetchone()
            if row:
                account_ids.append(row[0])
            else:
                logger.warning("Could not resolve: @%s", h)
    else:
        account_ids = get_tier1_account_ids(conn, min_inbound=args.min_inbound)

    if args.limit:
        account_ids = account_ids[:args.limit]

    logger.info("Accounts to fetch: %d", len(account_ids))

    if args.dry_run:
        for aid in account_ids[:20]:
            row = conn.execute(
                "SELECT username FROM resolved_accounts WHERE account_id = ?", (aid,)
            ).fetchone()
            uname = row[0] if row else aid
            print(f"  @{uname}")
        if len(account_ids) > 20:
            print(f"  ... and {len(account_ids) - 20} more")
        conn.close()
        return

    api_key = get_api_key()
    total_stored = 0
    n_batches = (len(account_ids) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(n_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(account_ids))
        batch_ids = account_ids[start:end]

        logger.info(
            "Batch %d/%d: fetching %d profiles...",
            batch_idx + 1, n_batches, len(batch_ids),
        )
        try:
            users = fetch_batch(api_key, batch_ids)
            stored = store_profiles(conn, users)
            total_stored += stored
            logger.info("  Stored %d profiles (total: %d)", stored, total_stored)

            if batch_idx < n_batches - 1:
                time.sleep(1)
        except Exception as e:
            logger.error("Batch %d failed: %s", batch_idx + 1, e)

    logger.info("Done: %d profiles fetched and stored", total_stored)
    conn.close()


if __name__ == "__main__":
    main()
