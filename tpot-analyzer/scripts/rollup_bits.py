#!/usr/bin/env python3
"""Automate bits rollup: parse tweet_tags → aggregate to account_community_bits.

Reads bits-category tags from tweet_tags, aggregates per (account, community),
and writes the rollup to account_community_bits.

Usage:
    python scripts/rollup_bits.py                    # live run
    python scripts/rollup_bits.py --dry-run          # preview without writing
    python scripts/rollup_bits.py --db-path other.db # custom DB path
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "archive_tweets.db"


def parse_bits_tag(tag: str) -> Optional[Tuple[str, int]]:
    """Parse a bits tag like 'bits:SHORT_NAME:+N' → (short_name, value).

    Returns None for malformed tags:
    - Wrong prefix (not 'bits')
    - Missing value part
    - Non-numeric value
    - Extra colons (more than 3 parts)
    """
    if not tag:
        return None

    parts = tag.split(":")
    if len(parts) != 3:
        return None

    prefix, short_name, value_str = parts
    if prefix.lower() != "bits":
        return None

    if not short_name:
        return None

    try:
        value = int(value_str)
    except ValueError:
        return None

    return (short_name, value)


def aggregate_bits(
    tags: List[Tuple[str, str, str]],
    short_to_id: Dict[str, str],
) -> Dict[Tuple[str, str], dict]:
    """Aggregate (account_id, tweet_id, tag) triples into rollup dict.

    Returns {(account_id, community_id): {total_bits, tweet_count, pct}}.

    tweet_count = distinct tweets per (account, community) pair.
    pct = abs(total_bits) / sum(abs(total_bits)) per account * 100.

    Unknown communities (short_name not in short_to_id) are skipped.
    Malformed tags are skipped.
    """
    # Build case-insensitive lookup: lowercase(short_name) → community_id
    lower_to_id = {k.lower(): v for k, v in short_to_id.items()}

    # Phase 1: accumulate bits and track tweet sets
    bits_acc: Dict[Tuple[str, str], int] = defaultdict(int)  # (acct, comm_id) → total
    tweet_sets: Dict[Tuple[str, str], set] = defaultdict(set)  # (acct, comm_id) → {tweet_ids}

    for account_id, tweet_id, tag in tags:
        parsed = parse_bits_tag(tag)
        if parsed is None:
            continue

        short_name, value = parsed
        community_id = lower_to_id.get(short_name.lower())
        if community_id is None:
            continue

        key = (account_id, community_id)
        bits_acc[key] += value
        tweet_sets[key].add(tweet_id)

    # Phase 2: compute pct per account
    # Group by account to get sum of abs(total_bits)
    account_abs_sum: Dict[str, int] = defaultdict(int)
    for (account_id, _), total in bits_acc.items():
        account_abs_sum[account_id] += abs(total)

    # Phase 3: build result
    result: Dict[Tuple[str, str], dict] = {}
    for key, total in bits_acc.items():
        account_id = key[0]
        abs_sum = account_abs_sum[account_id]
        pct = (abs(total) / abs_sum * 100) if abs_sum > 0 else 0.0

        result[key] = {
            "total_bits": total,
            "tweet_count": len(tweet_sets[key]),
            "pct": pct,
        }

    return result


def load_short_to_id(conn: sqlite3.Connection) -> Dict[str, str]:
    """Map community.short_name → community.id for all communities with short_name."""
    rows = conn.execute(
        "SELECT id, short_name FROM community WHERE short_name IS NOT NULL"
    ).fetchall()
    return {row[1]: row[0] for row in rows}


def load_bits_tags(conn: sqlite3.Connection) -> List[Tuple[str, str, str]]:
    """Load (account_id, tweet_id, tag) triples for all bits-category tags.

    Joins tweet_tags with tweets to resolve account_id from tweet_id.
    """
    rows = conn.execute(
        """
        SELECT t.account_id, tt.tweet_id, tt.tag
        FROM tweet_tags tt
        JOIN tweets t ON t.tweet_id = tt.tweet_id
        WHERE tt.category = 'bits'
        """
    ).fetchall()
    return [(row[0], row[1], row[2]) for row in rows]


def write_rollup(
    conn: sqlite3.Connection,
    rollup: Dict[Tuple[str, str], dict],
    dry_run: bool = False,
) -> int:
    """Write rollup to account_community_bits table.

    Deletes all existing rows and inserts computed ones.
    Returns the number of rows written (or that would be written in dry-run).
    """
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        (account_id, community_id, data["total_bits"], data["tweet_count"], data["pct"], now)
        for (account_id, community_id), data in sorted(rollup.items())
    ]

    if dry_run:
        logger.info("[DRY RUN] Would write %d rows to account_community_bits", len(rows))
        return len(rows)

    conn.execute("DELETE FROM account_community_bits")
    conn.executemany(
        """INSERT INTO account_community_bits
           (account_id, community_id, total_bits, tweet_count, pct, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    logger.info("Wrote %d rows to account_community_bits", len(rows))
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Rollup bits tags to account_community_bits")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="Path to archive_tweets.db")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if not args.db_path.exists():
        logger.error("Database not found: %s", args.db_path)
        sys.exit(1)

    conn = sqlite3.connect(str(args.db_path))

    # Load community mapping
    short_to_id = load_short_to_id(conn)
    logger.info("Loaded %d community short_name mappings", len(short_to_id))
    if not short_to_id:
        logger.error("No communities with short_name found — nothing to roll up")
        sys.exit(1)

    # Load bits tags
    tags = load_bits_tags(conn)
    logger.info("Loaded %d bits tags from tweet_tags", len(tags))
    if not tags:
        logger.warning("No bits tags found — table will be empty after rollup")

    # Aggregate
    rollup = aggregate_bits(tags, short_to_id)
    logger.info("Aggregated to %d (account, community) pairs", len(rollup))

    # Summarize per account
    accounts = defaultdict(list)
    for (acct, comm_id), data in rollup.items():
        # Reverse-lookup short_name for display
        sn = next((k for k, v in short_to_id.items() if v == comm_id), comm_id[:8])
        accounts[acct].append((sn, data["total_bits"], data["tweet_count"], data["pct"]))

    for acct, entries in sorted(accounts.items()):
        entries.sort(key=lambda x: -abs(x[1]))
        parts = [f"{sn}={bits:+d}({tc}t,{pct:.1f}%)" for sn, bits, tc, pct in entries]
        logger.info("  %s: %s", acct, " | ".join(parts))

    # Write
    count = write_rollup(conn, rollup, dry_run=args.dry_run)
    action = "Would write" if args.dry_run else "Wrote"
    print(f"\n{action} {count} rows to account_community_bits")

    conn.close()


if __name__ == "__main__":
    main()
