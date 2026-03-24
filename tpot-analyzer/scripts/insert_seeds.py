"""Insert LLM-labeled accounts as propagation seeds.

After the active learning rollup, newly classified accounts must be inserted
into community_account so harmonic label propagation can use them as seeds.

Weight is based on ABSOLUTE evidence (bits) not percentages, so bridge accounts
with strong evidence in multiple communities propagate at full strength in each.

Accounts dominated by bits:None are blocked from seed insertion (not TPOT).
"""
from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone

# Reference: 30 absolute bits = full weight (1.0). Fewer = proportionally less.
BITS_REFERENCE = 30
# Minimum absolute bits to be considered a seed for a community
MIN_BITS_THRESHOLD = 3


def insert_llm_seeds(conn: sqlite3.Connection, account_ids: list[str]) -> int:
    """Insert rollup results into community_account for propagation.

    Skips accounts already present with source='nmf' (don't overwrite NMF seeds).
    Uses absolute bits for weight: weight = min(1.0, abs(bits) / BITS_REFERENCE).
    Blocks accounts where None bits dominate (not TPOT — adjacent ecosystem).

    Resolves short_name community IDs to UUIDs before inserting, since
    account_community_bits stores short_names but community_account needs UUIDs.

    Returns count of community_account rows inserted.
    """
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0

    # Build short_name → UUID lookup (account_community_bits uses short_names,
    # but community_account needs UUIDs to match NMF seeds)
    short_to_uuid = {}
    for row in conn.execute("SELECT id, short_name FROM community WHERE short_name IS NOT NULL").fetchall():
        short_to_uuid[row[1]] = row[0]
        short_to_uuid[row[0]] = row[0]  # also map UUID → UUID for safety

    for account_id in account_ids:
        # Check if already an NMF seed
        existing = conn.execute(
            "SELECT source FROM community_account WHERE account_id = ? AND source = 'nmf' LIMIT 1",
            (account_id,),
        ).fetchone()
        if existing:
            continue  # don't overwrite NMF seeds

        # Load ALL bits rollup for this account (including None)
        all_bits_rows = conn.execute(
            "SELECT community_id, total_bits, pct FROM account_community_bits WHERE account_id = ?",
            (account_id,),
        ).fetchall()

        if not all_bits_rows:
            continue

        # --- None community gate (#5) ---
        # Check if this account is dominated by None bits (not TPOT)
        none_bits = 0
        real_bits_rows = []
        for community_id, total_bits, pct in all_bits_rows:
            if community_id == 'None' or community_id == short_to_uuid.get('None'):
                none_bits = abs(total_bits)
            else:
                real_bits_rows.append((community_id, total_bits, pct))

        total_real_bits = sum(abs(tb) for _, tb, _ in real_bits_rows)

        # If None dominates (more than real bits), mark ineligible and skip
        if none_bits > total_real_bits and none_bits >= 5:
            _ensure_seed_eligibility_table(conn)
            conn.execute(
                """INSERT OR REPLACE INTO seed_eligibility
                   (account_id, max_weight, dominant_community, entropy,
                    concentration, content_agrees, eligible, created_at)
                   VALUES (?, 0, 'None', 0, 0, NULL, 0, ?)""",
                (account_id, now),
            )
            continue

        # Filter to communities with enough absolute evidence
        seed_rows = [(cid, tb, pct) for cid, tb, pct in real_bits_rows if abs(tb) >= MIN_BITS_THRESHOLD]

        if not seed_rows:
            continue

        # --- Absolute-bits weight (#4) ---
        # Weight per community based on absolute evidence, NOT percentage
        # Resolve short_name → UUID for community_account compatibility
        for community_id, total_bits, _pct in seed_rows:
            resolved_cid = short_to_uuid.get(community_id, community_id)
            if resolved_cid == community_id and not community_id.count('-') >= 4:
                # Unresolved short_name with no UUID match — skip
                continue
            weight = min(1.0, abs(total_bits) / BITS_REFERENCE)
            conn.execute(
                "INSERT OR REPLACE INTO community_account "
                "(community_id, account_id, weight, source, updated_at) "
                "VALUES (?, ?, ?, 'llm_ensemble', ?)",
                (resolved_cid, account_id, round(weight, 4), now),
            )
            inserted += 1

        # Compute concentration from evidence quality
        # Now concentration only controls the "none" column strength in propagation,
        # NOT the individual community weights (those are set by absolute bits above)
        max_abs_bits = max(abs(tb) for _, tb, _ in seed_rows)
        max_weight = min(1.0, max_abs_bits / BITS_REFERENCE)
        dominant_community = max(seed_rows, key=lambda r: abs(r[1]))[0]

        total_bits = sum(abs(tb) for _, tb, _ in seed_rows)

        # Entropy over absolute bits distribution
        if total_bits > 0 and len(seed_rows) > 1:
            probs = [abs(tb) / total_bits for _, tb, _ in seed_rows]
            entropy = -sum(p * math.log2(p) for p in probs if p > 0)
            max_entropy = math.log2(len(seed_rows))
            normalized_entropy = entropy / max_entropy if max_entropy > 0 else 1.0
        else:
            entropy = 0.0
            normalized_entropy = 0.0

        # evidence_mass from total absolute bits
        evidence_mass = min(1.0, math.sqrt(total_bits / 50))
        focus = 1.0 - normalized_entropy
        concentration = round(max(0.05, evidence_mass * focus), 3)

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
