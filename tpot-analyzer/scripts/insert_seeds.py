"""Insert LLM-labeled accounts as propagation seeds.

After the active learning rollup, newly classified accounts must be inserted
into community_account so harmonic label propagation can use them as seeds.
Also inserts into seed_eligibility with concentration=0.5 (reduced authority
compared to NMF seeds at 1.0).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def insert_llm_seeds(conn: sqlite3.Connection, account_ids: list[str]) -> int:
    """Insert rollup results into community_account for propagation.

    Skips accounts already present with source='nmf' (don't overwrite NMF seeds).
    Inserts with source='llm_ensemble' and weight = pct/100.
    Also inserts into seed_eligibility with concentration=0.5.

    Returns count of community_account rows inserted.
    """
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0

    for account_id in account_ids:
        # Check if already an NMF seed
        existing = conn.execute(
            "SELECT source FROM community_account WHERE account_id = ? AND source = 'nmf' LIMIT 1",
            (account_id,),
        ).fetchone()
        if existing:
            continue  # don't overwrite NMF seeds

        # Load bits rollup for this account
        bits_rows = conn.execute(
            "SELECT community_id, pct FROM account_community_bits WHERE account_id = ? AND pct > 5.0",
            (account_id,),
        ).fetchall()

        if not bits_rows:
            continue

        for community_id, pct in bits_rows:
            weight = pct / 100.0
            assert 0.0 <= weight <= 1.0, f"Invalid weight {weight} for {account_id}/{community_id}"
            conn.execute(
                "INSERT OR REPLACE INTO community_account "
                "(community_id, account_id, weight, source, updated_at) "
                "VALUES (?, ?, ?, 'llm_ensemble', ?)",
                (community_id, account_id, weight, now),
            )
            inserted += 1

        # Insert into seed_eligibility with reduced concentration (0.5)
        # NMF seeds default to 1.0; LLM seeds propagate with half strength
        # Compute required fields from the bits data
        max_pct = max(pct for _, pct in bits_rows)
        max_weight = max_pct / 100.0
        dominant_community = max(bits_rows, key=lambda r: r[1])[0]

        # Entropy: measure how spread the bits are across communities
        import math
        total_pct = sum(pct for _, pct in bits_rows)
        if total_pct > 0:
            probs = [pct / total_pct for _, pct in bits_rows]
            entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        else:
            entropy = 0.0

        conn.execute(
            """INSERT OR REPLACE INTO seed_eligibility
               (account_id, max_weight, dominant_community, entropy,
                concentration, content_agrees, eligible, created_at)
               VALUES (?, ?, ?, ?, 0.5, NULL, 1, ?)""",
            (account_id, max_weight, dominant_community, entropy, now),
        )

    conn.commit()
    return inserted


def _ensure_seed_eligibility_table(conn: sqlite3.Connection) -> None:
    """Create seed_eligibility table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seed_eligibility (
            account_id TEXT PRIMARY KEY,
            concentration REAL NOT NULL DEFAULT 1.0
        )
    """)
