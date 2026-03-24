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

        # Compute principled concentration from evidence quality
        import math

        max_pct = max(pct for _, pct in bits_rows)
        max_weight = max_pct / 100.0
        dominant_community = max(bits_rows, key=lambda r: r[1])[0]

        # Total bits across all communities for this account
        total_bits_row = conn.execute(
            "SELECT SUM(total_bits), MAX(tweet_count) FROM account_community_bits WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        total_bits = total_bits_row[0] or 0
        tweet_count = total_bits_row[1] or 0

        # Entropy: how spread the bits are (0 = all in one community, high = diffuse)
        total_pct = sum(pct for _, pct in bits_rows)
        if total_pct > 0:
            probs = [pct / total_pct for _, pct in bits_rows]
            entropy = -sum(p * math.log2(p) for p in probs if p > 0)
            # Normalize: max entropy for N communities = log2(N)
            max_entropy = math.log2(len(bits_rows)) if len(bits_rows) > 1 else 1.0
            normalized_entropy = entropy / max_entropy
        else:
            entropy = 0.0
            normalized_entropy = 1.0

        # Principled concentration:
        #   evidence_mass = sqrt(total_bits / 50) capped at 1.0
        #     → 50+ bits = full mass, 10 bits = 0.45, 5 bits = 0.32
        #   focus = 1 - normalized_entropy
        #     → all bits in one community = 1.0, evenly spread = 0.0
        #   concentration = evidence_mass × focus
        #     → repligate (213 bits, concentrated) → ~0.8
        #     → bryan_johnson (17 bits, diffuse) → ~0.15
        #     → NMF seeds stay at 1.0 (not affected by this code)
        evidence_mass = min(1.0, math.sqrt(total_bits / 50))
        focus = 1.0 - normalized_entropy
        concentration = round(evidence_mass * focus, 3)

        # Floor: minimum 0.05 so even weak seeds contribute something
        concentration = max(0.05, concentration)

        _ensure_seed_eligibility_table(conn)
        conn.execute(
            """INSERT OR REPLACE INTO seed_eligibility
               (account_id, max_weight, dominant_community, entropy,
                concentration, content_agrees, eligible, created_at)
               VALUES (?, ?, ?, ?, ?, NULL, 1, ?)""",
            (account_id, max_weight, dominant_community, entropy, concentration, now),
        )

    conn.commit()
    return inserted


def _ensure_seed_eligibility_table(conn: sqlite3.Connection) -> None:
    """Create seed_eligibility table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seed_eligibility (
            account_id      TEXT PRIMARY KEY,
            max_weight      REAL NOT NULL DEFAULT 0.0,
            dominant_community TEXT NOT NULL DEFAULT '',
            entropy         REAL NOT NULL DEFAULT 0.0,
            concentration   REAL NOT NULL DEFAULT 1.0,
            content_agrees  INTEGER,
            eligible        INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT NOT NULL DEFAULT ''
        )
    """)
