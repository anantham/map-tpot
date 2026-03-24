#!/usr/bin/env python3
"""Automate bits rollup: parse tweet_tags → aggregate to account_community_bits.

Reads bits-category tags from tweet_tags, aggregates per (account, community),
and writes the rollup to account_community_bits.

Optionally weights bits by the tweet's dominant simulacrum level:
    L1 (sincere proposition)  → 1.5x
    L2 (strategic)            → 1.0x
    L3 (performative/in-group)→ 2.0x
    L4 (pure simulacrum)      → 0.5x

Usage:
    python scripts/rollup_bits.py                          # live run (unweighted)
    python scripts/rollup_bits.py --simulacrum-weighted    # weighted by simulacrum level
    python scripts/rollup_bits.py --dry-run                # preview without writing
    python scripts/rollup_bits.py --db-path other.db       # custom DB path
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

# Simulacrum level weights: how strongly each level signals community membership.
# L3 (performative/in-group) IS community membership → 2x.
# L1 (sincere proposition) reveals intellectual commitments → 1.5x.
# L2 (strategic) is baseline → 1.0x.
# L4 (pure simulacrum/shitpost) is weak for community assignment → 0.5x.
SIMULACRUM_WEIGHTS: Dict[str, float] = {
    "l1": 1.5,
    "l2": 1.0,
    "l3": 2.0,
    "l4": 0.5,
}

# Default weight when simulacrum data is unavailable (all-zero probs, missing).
DEFAULT_SIMULACRUM_WEIGHT = 1.0


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


def get_dominant_simulacrum(distribution: Dict[str, float]) -> Optional[str]:
    """Return the dominant simulacrum level (highest probability) from a distribution.

    Returns None if the distribution is empty or all-zero (no signal).
    Ties are broken alphabetically (l1 < l2 < l3 < l4) for determinism.
    """
    if not distribution:
        return None

    total = sum(distribution.values())
    if total <= 0.0:
        return None

    # Normalize to handle non-normalized distributions (sums != 1.0)
    normalized = {k: v / total for k, v in distribution.items()}

    # argmax with deterministic tie-breaking (sorted keys)
    return max(sorted(normalized.keys()), key=lambda k: normalized[k])


def simulacrum_weight_for_tweet(
    distribution: Dict[str, float],
) -> float:
    """Compute the simulacrum weight multiplier for a tweet.

    Uses the dominant (highest-probability) simulacrum level to look up the weight.
    Returns DEFAULT_SIMULACRUM_WEIGHT if the distribution has no signal.
    """
    dominant = get_dominant_simulacrum(distribution)
    if dominant is None:
        return DEFAULT_SIMULACRUM_WEIGHT
    return SIMULACRUM_WEIGHTS.get(dominant, DEFAULT_SIMULACRUM_WEIGHT)


def load_simulacrum_weights(conn: sqlite3.Connection) -> Dict[str, float]:
    """Load tweet_id → simulacrum weight multiplier for all labeled tweets.

    Queries tweet_label_set (active) + tweet_label_prob to build the distribution
    per tweet, then computes the weight from the dominant level.

    Returns {tweet_id: weight_multiplier}. Tweets with all-zero probs get 1.0.
    """
    rows = conn.execute(
        """
        SELECT tls.tweet_id, tlp.label, tlp.probability
        FROM tweet_label_set tls
        JOIN tweet_label_prob tlp ON tlp.label_set_id = tls.id
        WHERE tls.is_active = 1
        ORDER BY tls.tweet_id, tlp.label
        """
    ).fetchall()

    # Group by tweet_id
    tweet_dists: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for tweet_id, label, probability in rows:
        tweet_dists[tweet_id][label] += probability

    # Convert distributions to weights
    result: Dict[str, float] = {}
    for tweet_id, dist in tweet_dists.items():
        result[tweet_id] = simulacrum_weight_for_tweet(dict(dist))

    return result


def aggregate_bits(
    tags: List[Tuple[str, str, str]],
    short_to_id: Dict[str, str],
    tweet_weights: Optional[Dict[str, float]] = None,
) -> Dict[Tuple[str, str], dict]:
    """Aggregate (account_id, tweet_id, tag) triples into rollup dict.

    Returns {(account_id, community_id): {total_bits, weighted_bits, tweet_count, pct}}.

    total_bits = unweighted integer sum (always computed, backwards compatible).
    weighted_bits = simulacrum-weighted float sum (only meaningful when tweet_weights
                    is provided; equals total_bits as float when tweet_weights is None).
    tweet_count = distinct tweets per (account, community) pair.
    pct = abs(total_bits) / sum(abs(total_bits)) per account * 100.

    When tweet_weights is provided, each tag's value is multiplied by the tweet's
    simulacrum weight. Tweets not in tweet_weights get DEFAULT_SIMULACRUM_WEIGHT (1.0).

    Unknown communities (short_name not in short_to_id) are skipped.
    Malformed tags are skipped.
    """
    # Build case-insensitive lookup: lowercase(short_name) → community_id
    lower_to_id = {k.lower(): v for k, v in short_to_id.items()}

    # Phase 1: accumulate bits and track tweet sets
    bits_acc: Dict[Tuple[str, str], int] = defaultdict(int)  # (acct, comm_id) → unweighted total
    weighted_acc: Dict[Tuple[str, str], float] = defaultdict(float)  # (acct, comm_id) → weighted total
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

        # Apply simulacrum weight if available
        if tweet_weights is not None:
            weight = tweet_weights.get(tweet_id, DEFAULT_SIMULACRUM_WEIGHT)
            weighted_acc[key] += value * weight
        else:
            weighted_acc[key] += float(value)

        tweet_sets[key].add(tweet_id)

    # Phase 2: compute pct per account (from unweighted bits, for backwards compat)
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
            "weighted_bits": weighted_acc[key],
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

    Joins tweet_tags with both tweets (archive) and enriched_tweets (API-fetched)
    to resolve account_id from tweet_id.
    """
    # Check if enriched_tweets table exists
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    if "enriched_tweets" in tables:
        query = """
            SELECT t.account_id, tt.tweet_id, tt.tag
            FROM tweet_tags tt
            JOIN tweets t ON t.tweet_id = tt.tweet_id
            WHERE tt.category = 'bits'
            UNION ALL
            SELECT e.account_id, tt.tweet_id, tt.tag
            FROM tweet_tags tt
            JOIN enriched_tweets e ON tt.tweet_id = e.tweet_id
            WHERE tt.category = 'bits'
        """
    else:
        query = """
            SELECT t.account_id, tt.tweet_id, tt.tag
            FROM tweet_tags tt
            JOIN tweets t ON t.tweet_id = tt.tweet_id
            WHERE tt.category = 'bits'
        """

    rows = conn.execute(query).fetchall()
    return [(row[0], row[1], row[2]) for row in rows]


def scoped_delete_bits(
    conn: sqlite3.Connection, account_ids: List[str]
) -> int:
    """Delete account_community_bits rows for specific accounts only.

    Unlike the global DELETE in write_rollup, this preserves rows for
    accounts not in the list.
    """
    if not account_ids:
        return 0
    placeholders = ",".join("?" for _ in account_ids)
    cur = conn.execute(
        f"DELETE FROM account_community_bits WHERE account_id IN ({placeholders})",
        account_ids,
    )
    conn.commit()
    return cur.rowcount


def compute_discount(conn: sqlite3.Connection, account_id: str) -> float:
    """Compute informativeness discount for an account.

    Archive accounts (tweets in `tweets` table) get no discount (1.0).
    Enriched accounts (tweets in `enriched_tweets` table) get sqrt(N/50)
    discount where N is the number of enriched tweets.

    This prevents 20 viral API-fetched tweets from generating the same
    confidence as 50+ deeply-labeled archive tweets.
    """
    import math

    # Check if enriched_tweets table exists
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    if "enriched_tweets" not in tables:
        return 1.0

    # Count enriched tweets for this account
    enriched_count = conn.execute(
        "SELECT COUNT(*) FROM enriched_tweets WHERE account_id = ?",
        (account_id,),
    ).fetchone()[0]

    if enriched_count == 0:
        # No enriched tweets — this is an archive account
        return 1.0

    # Check if account also has archive tweets
    archive_count = conn.execute(
        "SELECT COUNT(*) FROM tweets WHERE account_id = ?",
        (account_id,),
    ).fetchone()[0]

    if archive_count > 0:
        # Has archive tweets — no discount (archive is primary)
        return 1.0

    # Pure enriched account — apply discount
    return min(1.0, math.sqrt(enriched_count / 50))


def ensure_weighted_bits_column(conn: sqlite3.Connection) -> None:
    """Add weighted_bits column to account_community_bits if it doesn't exist.

    Idempotent — safe to call multiple times.
    """
    cols = conn.execute("PRAGMA table_info(account_community_bits)").fetchall()
    col_names = {row[1] for row in cols}
    if "weighted_bits" not in col_names:
        conn.execute(
            "ALTER TABLE account_community_bits ADD COLUMN weighted_bits REAL"
        )
        conn.commit()
        logger.info("Added weighted_bits column to account_community_bits")


def write_rollup(
    conn: sqlite3.Connection,
    rollup: Dict[Tuple[str, str], dict],
    dry_run: bool = False,
    simulacrum_weighted: bool = False,
) -> int:
    """Write rollup to account_community_bits table.

    Deletes all existing rows and inserts computed ones.
    When simulacrum_weighted=True, also writes the weighted_bits column.
    Returns the number of rows written (or that would be written in dry-run).
    """
    now = datetime.now(timezone.utc).isoformat()

    if simulacrum_weighted:
        rows = [
            (
                account_id, community_id,
                data["total_bits"], data["tweet_count"], data["pct"],
                data.get("weighted_bits"), now,
            )
            for (account_id, community_id), data in sorted(rollup.items())
        ]
    else:
        rows = [
            (account_id, community_id, data["total_bits"], data["tweet_count"], data["pct"], now)
            for (account_id, community_id), data in sorted(rollup.items())
        ]

    if dry_run:
        logger.info("[DRY RUN] Would write %d rows to account_community_bits", len(rows))
        return len(rows)

    if simulacrum_weighted:
        ensure_weighted_bits_column(conn)

    conn.execute("DELETE FROM account_community_bits")

    if simulacrum_weighted:
        conn.executemany(
            """INSERT INTO account_community_bits
               (account_id, community_id, total_bits, tweet_count, pct, weighted_bits, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
    else:
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
    parser.add_argument(
        "--simulacrum-weighted", action="store_true",
        help="Weight bits by dominant simulacrum level (L3=2x, L1=1.5x, L2=1x, L4=0.5x)",
    )
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

    # Optionally load simulacrum weights
    tweet_weights = None
    if args.simulacrum_weighted:
        tweet_weights = load_simulacrum_weights(conn)
        logger.info("Loaded simulacrum weights for %d tweets", len(tweet_weights))

        # Report coverage
        bits_tweet_ids = {t[1] for t in tags}
        covered = bits_tweet_ids & set(tweet_weights.keys())
        logger.info(
            "Simulacrum coverage: %d/%d bits-tagged tweets (%.1f%%)",
            len(covered), len(bits_tweet_ids),
            (len(covered) / len(bits_tweet_ids) * 100) if bits_tweet_ids else 0,
        )

    # Aggregate
    rollup = aggregate_bits(tags, short_to_id, tweet_weights=tweet_weights)
    logger.info("Aggregated to %d (account, community) pairs", len(rollup))

    # Summarize per account
    accounts = defaultdict(list)
    for (acct, comm_id), data in rollup.items():
        # Reverse-lookup short_name for display
        sn = next((k for k, v in short_to_id.items() if v == comm_id), comm_id[:8])
        accounts[acct].append((sn, data["total_bits"], data["tweet_count"], data["pct"],
                               data.get("weighted_bits")))

    for acct, entries in sorted(accounts.items()):
        entries.sort(key=lambda x: -abs(x[1]))
        if args.simulacrum_weighted:
            parts = [
                f"{sn}={bits:+d}(w={wb:+.1f},{tc}t,{pct:.1f}%)"
                for sn, bits, tc, pct, wb in entries
            ]
        else:
            parts = [f"{sn}={bits:+d}({tc}t,{pct:.1f}%)" for sn, bits, tc, pct, _ in entries]
        logger.info("  %s: %s", acct, " | ".join(parts))

    # Write
    count = write_rollup(conn, rollup, dry_run=args.dry_run,
                         simulacrum_weighted=args.simulacrum_weighted)
    action = "Would write" if args.dry_run else "Wrote"
    weighted_label = " (simulacrum-weighted)" if args.simulacrum_weighted else ""
    print(f"\n{action} {count} rows to account_community_bits{weighted_label}")

    conn.close()


if __name__ == "__main__":
    main()
