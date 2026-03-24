"""CF1: Build co-followed similarity matrix among seed accounts.

For each pair of seed accounts (A, B), computes how many of the 317
source accounts follow both A and B, then normalises to Jaccard similarity.

High Jaccard = the community "agrees" these two belong together.
Compares within-community vs between-community averages to validate
the NMF ontology from pure topology.

Usage:
    .venv/bin/python3 -m scripts.build_cofollowed_matrix
    .venv/bin/python3 -m scripts.build_cofollowed_matrix --dry-run
    .venv/bin/python3 -m scripts.build_cofollowed_matrix --min-jaccard 0.05
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from src.config import DEFAULT_ARCHIVE_DB

DB_PATH = DEFAULT_ARCHIVE_DB
MIN_JACCARD_DEFAULT = 0.1


# ── data loading ────────────────────────────────────────────────────────


def load_seed_accounts(conn: sqlite3.Connection) -> Set[str]:
    """Return set of account_ids from the profiles table (seed accounts)."""
    cur = conn.execute("SELECT account_id FROM profiles")
    return {row[0] for row in cur.fetchall()}


def load_follow_edges(conn: sqlite3.Connection) -> List[Tuple[str, str]]:
    """Return (follower, target) edges from account_following."""
    cur = conn.execute("SELECT account_id, following_account_id FROM account_following")
    return cur.fetchall()


def load_community_assignments(conn: sqlite3.Connection) -> Dict[str, str]:
    """Return account_id → primary community short_name (max NMF weight)."""
    cur = conn.execute(
        """
        SELECT ca.account_id, c.short_name, ca.weight
        FROM community_account ca
        JOIN community c ON ca.community_id = c.id
        ORDER BY ca.account_id, ca.weight DESC
        """
    )
    assignments: Dict[str, str] = {}
    for account_id, short_name, _weight in cur.fetchall():
        if account_id not in assignments:  # first row = highest weight
            assignments[account_id] = short_name
    return assignments


# ── matrix construction ─────────────────────────────────────────────────


def build_follower_sets(
    edges: List[Tuple[str, str]], seed_ids: Set[str]
) -> Dict[str, Set[str]]:
    """Build target → {set of followers} mapping, filtered to seed targets.

    Only counts followers who are themselves seed accounts (so we have a
    consistent basis for comparison).
    """
    followers_of: Dict[str, Set[str]] = defaultdict(set)
    for follower, target in edges:
        if target in seed_ids and follower in seed_ids:
            followers_of[target].add(follower)
    return dict(followers_of)


def compute_cofollowed_pairs(
    follower_sets: Dict[str, Set[str]], min_jaccard: float
) -> List[Tuple[str, str, int, float]]:
    """Compute pairwise Jaccard similarity for all target pairs.

    Returns list of (account_a, account_b, shared_followers, jaccard)
    with jaccard >= min_jaccard.  Only stores upper triangle (a < b).
    """
    targets = sorted(follower_sets.keys())
    n = len(targets)
    logger.info("Computing pairwise Jaccard for %d targets...", n)

    pairs: List[Tuple[str, str, int, float]] = []
    checked = 0
    total = n * (n - 1) // 2

    for i in range(n):
        set_i = follower_sets[targets[i]]
        if not set_i:
            continue
        for j in range(i + 1, n):
            set_j = follower_sets[targets[j]]
            if not set_j:
                continue
            shared = len(set_i & set_j)
            if shared == 0:
                continue
            union = len(set_i | set_j)
            jaccard = shared / union
            if jaccard >= min_jaccard:
                pairs.append((targets[i], targets[j], shared, jaccard))
        checked += n - i - 1
        if (i + 1) % 50 == 0:
            logger.info(
                "  progress: %d/%d targets (%.0f%%), %d pairs so far",
                i + 1,
                n,
                100 * checked / max(total, 1),
                len(pairs),
            )

    logger.info(
        "Done. %d pairs above Jaccard threshold %.2f (out of %d checked).",
        len(pairs),
        min_jaccard,
        total,
    )
    return pairs


# ── persistence ─────────────────────────────────────────────────────────


def save_pairs(
    conn: sqlite3.Connection,
    pairs: List[Tuple[str, str, int, float]],
    dry_run: bool,
) -> None:
    """Write pairs to cofollowed_similarity table."""
    if dry_run:
        logger.info("[DRY RUN] Would write %d pairs. Skipping DB writes.", len(pairs))
        return

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cofollowed_similarity (
            account_a        TEXT NOT NULL,
            account_b        TEXT NOT NULL,
            shared_followers INTEGER NOT NULL,
            jaccard          REAL NOT NULL,
            created_at       TEXT NOT NULL,
            PRIMARY KEY (account_a, account_b)
        )
        """
    )
    conn.execute("DELETE FROM cofollowed_similarity")
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        """
        INSERT INTO cofollowed_similarity (account_a, account_b, shared_followers, jaccard, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [(a, b, s, j, now) for a, b, s, j in pairs],
    )
    conn.commit()
    logger.info("Saved %d pairs to cofollowed_similarity.", len(pairs))


# ── community cohesion analysis ─────────────────────────────────────────


def analyze_community_cohesion(
    pairs: List[Tuple[str, str, int, float]],
    assignments: Dict[str, str],
) -> None:
    """Compare within-community vs between-community co-followed Jaccard."""
    # Build lookup: (account_a, account_b) → jaccard
    pair_jaccard: Dict[Tuple[str, str], float] = {}
    for a, b, _s, j in pairs:
        pair_jaccard[(a, b)] = j
        pair_jaccard[(b, a)] = j  # symmetric

    # Group accounts by community
    community_members: Dict[str, List[str]] = defaultdict(list)
    for account_id, comm in assignments.items():
        community_members[comm].append(account_id)

    print("\n" + "=" * 80)
    print("COMMUNITY COHESION ANALYSIS: Co-Followed Jaccard")
    print("=" * 80)
    print(
        f"{'Community':<30} {'N':>4} {'Within':>8} {'Between':>8} "
        f"{'Ratio':>7} {'Cohesive?':>10}"
    )
    print("-" * 80)

    all_within: List[float] = []
    all_between: List[float] = []

    communities_sorted = sorted(
        community_members.keys(), key=lambda c: len(community_members[c]), reverse=True
    )

    for comm in communities_sorted:
        members = community_members[comm]
        n = len(members)

        # Within-community pairs
        within_jaccards: List[float] = []
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                key = (members[i], members[j])
                rev = (members[j], members[i])
                jac = pair_jaccard.get(key, pair_jaccard.get(rev, 0.0))
                within_jaccards.append(jac)

        # Between-community pairs: this community vs all others
        other_accounts = [
            aid for aid, c in assignments.items() if c != comm
        ]
        between_jaccards: List[float] = []
        for m in members:
            for o in other_accounts:
                key = (m, o)
                rev = (o, m)
                jac = pair_jaccard.get(key, pair_jaccard.get(rev, 0.0))
                between_jaccards.append(jac)

        avg_within = np.mean(within_jaccards) if within_jaccards else 0.0
        avg_between = np.mean(between_jaccards) if between_jaccards else 0.0
        ratio = avg_within / avg_between if avg_between > 0 else float("inf")
        cohesive = ratio > 1.5

        all_within.extend(within_jaccards)
        all_between.extend(between_jaccards)

        print(
            f"{comm:<30} {n:>4} {avg_within:>8.4f} {avg_between:>8.4f} "
            f"{ratio:>7.1f}x {'YES' if cohesive else 'no':>10}"
        )

    print("-" * 80)
    global_within = np.mean(all_within) if all_within else 0.0
    global_between = np.mean(all_between) if all_between else 0.0
    global_ratio = global_within / global_between if global_between > 0 else float("inf")
    print(
        f"{'GLOBAL':<30} {'':>4} {global_within:>8.4f} {global_between:>8.4f} "
        f"{global_ratio:>7.1f}x"
    )

    print(f"\nTotal within-community pairs:  {len(all_within):,}")
    print(f"Total between-community pairs: {len(all_between):,}")
    print(
        f"\nInterpretation: ratio > 1.5x means members of that community "
        f"are followed by the same people\nmore often than they are co-followed "
        f"with outsiders. Higher = more topologically distinct."
    )


def print_top_pairs(
    pairs: List[Tuple[str, str, int, float]],
    conn: sqlite3.Connection,
    top_n: int = 20,
) -> None:
    """Print the top co-followed pairs with usernames."""
    # Load username lookup
    cur = conn.execute("SELECT account_id, username FROM profiles")
    id_to_name: Dict[str, str] = {row[0]: row[1] for row in cur.fetchall()}

    sorted_pairs = sorted(pairs, key=lambda p: p[3], reverse=True)

    print(f"\nTOP {top_n} CO-FOLLOWED PAIRS (by Jaccard similarity):")
    print("-" * 70)
    print(f"{'Account A':<22} {'Account B':<22} {'Shared':>7} {'Jaccard':>8}")
    print("-" * 70)
    for a, b, shared, jac in sorted_pairs[:top_n]:
        name_a = id_to_name.get(a, a[:15])
        name_b = id_to_name.get(b, b[:15])
        print(f"{name_a:<22} {name_b:<22} {shared:>7} {jac:>8.4f}")


# ── main ────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CF1: Build co-followed similarity matrix among seed accounts."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and print results without writing to DB.",
    )
    parser.add_argument(
        "--min-jaccard",
        type=float,
        default=MIN_JACCARD_DEFAULT,
        help=f"Minimum Jaccard threshold to store (default: {MIN_JACCARD_DEFAULT}).",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(DB_PATH),
        help="Path to archive_tweets.db.",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        logger.error("Database not found: %s", db_path)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    try:
        # 1. Load data
        logger.info("Loading seed accounts from profiles...")
        seed_ids = load_seed_accounts(conn)
        logger.info("  %d seed accounts.", len(seed_ids))

        logger.info("Loading follow edges...")
        edges = load_follow_edges(conn)
        logger.info("  %d follow edges.", len(edges))

        # 2. Build follower sets (filtered to seed-to-seed edges)
        logger.info("Building follower sets (seed-to-seed only)...")
        follower_sets = build_follower_sets(edges, seed_ids)
        logger.info(
            "  %d targets with at least one seed follower.", len(follower_sets)
        )

        # Stats
        follower_counts = [len(v) for v in follower_sets.values()]
        logger.info(
            "  Follower count stats: min=%d, median=%d, mean=%.1f, max=%d",
            min(follower_counts),
            int(np.median(follower_counts)),
            np.mean(follower_counts),
            max(follower_counts),
        )

        # 3. Compute pairwise Jaccard
        pairs = compute_cofollowed_pairs(follower_sets, args.min_jaccard)

        # 4. Save
        save_pairs(conn, pairs, args.dry_run)

        # 5. Print top pairs
        print_top_pairs(pairs, conn)

        # 6. Community cohesion analysis
        assignments = load_community_assignments(conn)
        logger.info("  %d accounts with community assignments.", len(assignments))
        analyze_community_cohesion(pairs, assignments)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
