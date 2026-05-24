"""Rollup bits for newly labeled accounts + insert as propagation seeds."""
from __future__ import annotations

import datetime
import logging
import sqlite3

from scripts.insert_seeds import insert_llm_seeds
from scripts.rollup_bits import (
    aggregate_bits,
    compute_discount,
    load_bits_tags,
    load_short_to_id,
    scoped_delete_bits,
)

logger = logging.getLogger(__name__)


def run_measure(conn: sqlite3.Connection) -> dict:
    """Rollup bits for newly labeled accounts, insert as propagation seeds.

    Steps:
      1. Find accounts with enriched tweets not yet in community_account
         with source='llm_ensemble'
      2. Run scoped rollup for those accounts
      3. Insert as seeds via insert_llm_seeds

    Returns metrics dict with account counts and rows inserted.
    """
    # 1. Find newly labeled accounts (have enriched_tweets + tweet_tags bits,
    #    but NOT in community_account with source='llm_ensemble')
    new_accounts_rows = conn.execute(
        """
        SELECT DISTINCT e.account_id
        FROM enriched_tweets e
        JOIN tweet_tags tt ON tt.tweet_id = e.tweet_id AND tt.category = 'bits'
        WHERE e.account_id NOT IN (
            SELECT account_id FROM community_account WHERE source = 'llm_ensemble'
        )
        """
    ).fetchall()
    new_account_ids = [r[0] for r in new_accounts_rows]

    if not new_account_ids:
        logger.info("No newly labeled accounts to measure")
        return {"new_accounts": 0, "rollup_rows": 0, "seeds_inserted": 0}

    logger.info("Found %d newly labeled accounts for measurement", len(new_account_ids))

    # 2. Run rollup — load tags, aggregate, write scoped
    short_to_id = load_short_to_id(conn)
    tags = load_bits_tags(conn)

    # Filter tags to only new accounts
    account_set = set(new_account_ids)
    filtered_tags = [(a, t, tag) for a, t, tag in tags if a in account_set]

    rollup = aggregate_bits(filtered_tags, short_to_id)

    # Apply informativeness discount
    for (account_id, community_id), data in rollup.items():
        discount = compute_discount(conn, account_id)
        data["total_bits"] = int(data["total_bits"] * discount)
        data["weighted_bits"] = data["weighted_bits"] * discount

    # Scoped delete + insert (don't wipe existing rollup for archive accounts)
    # NOTE: Do NOT call write_rollup here — it does a global DELETE that wipes
    # all accounts, not just the ones being measured. Use scoped_delete + manual insert.
    scoped_delete_bits(conn, new_account_ids)
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    rollup_rows = 0
    for (account_id, community_id), data in sorted(rollup.items()):
        conn.execute(
            """INSERT OR REPLACE INTO account_community_bits
               (account_id, community_id, total_bits, tweet_count, pct, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (account_id, community_id, data["total_bits"],
             data["tweet_count"], data["pct"], now_str),
        )
        rollup_rows += 1
    conn.commit()

    # 3. Insert as seeds
    seeds_inserted = insert_llm_seeds(conn, new_account_ids)

    print(
        "NOTE: Recall measured WITHOUT TF-IDF context — "
        "may underestimate pipeline potential"
    )

    metrics = {
        "new_accounts": len(new_account_ids),
        "rollup_rows": rollup_rows,
        "seeds_inserted": seeds_inserted,
    }
    logger.info("Measure complete: %s", metrics)
    return metrics
