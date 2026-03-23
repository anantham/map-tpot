"""Validate seed accounts for propagation eligibility.

Three independent checks determine if an archive account should be used
as a seed (propagates labels outward) or demoted to shadow (propagated TO):

1. Max NMF weight — concentrated accounts are better seeds
2. Content agreement — NMF community matches content topic (CT1)
3. Entropy-based concentration — continuous weighting for propagation

Output: seed_eligibility table with per-account scores and a composite
'concentration' weight that propagation uses to scale boundary conditions.

Usage:
    .venv/bin/python3 -m scripts.validate_seeds
    .venv/bin/python3 -m scripts.validate_seeds --min-weight 0.25
"""
from __future__ import annotations

import argparse
import sqlite3
import numpy as np
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "archive_tweets.db"

# Rough mapping: community short_name → content topic index
# (from CT3 analysis this session)
COMMUNITY_TO_TOP_TOPIC = {
    "highbies": 0,             # T0 = highbies/vibecamp
    "AI-Safety": 1,            # T1 = EA/rationalist
    "Contemplative-Practitioners": 22,  # T22 = jhana/metta
    "TfT-Coordination": 15,   # T15 = indiehackers/builders
    "Qualia-Research": 22,     # T22 (closest — weak content signal)
    "LLM-Whisperers": 6,      # T6 = LLM tinkering
    "Core-TPOT": 0,            # T0 (general, overlaps highbies)
    "Collective-Intelligence": 7,  # T7 = regen/web3
    "Relational-Explorers": 22,    # T22 (contemplative-adjacent)
    "NYC-Institution-Builders": 0,  # T0 (weak — uses general TPOT signal)
    "AI-Creativity": 6,       # T6 (overlaps LLM)
    "Quiet-Creatives": 2,     # T2 = personal growth
    "Internet-Intellectuals": 8,   # T8 = essayists
    "Tech-Intellectuals": 1,  # T1 (EA-adjacent)
    "Queer-TPOT": 5,          # T5 = queer/sexuality
}


def compute_seed_eligibility(db_path: Path, min_weight: float = 0.25):
    conn = sqlite3.connect(str(db_path))
    now = datetime.now(timezone.utc).isoformat()

    # Get communities
    communities = conn.execute(
        "SELECT id, short_name FROM community ORDER BY name"
    ).fetchall()
    cid_to_short = {cid: short for cid, short in communities}
    cid_to_idx = {cid: i for i, (cid, _) in enumerate(communities)}
    K = len(communities)

    # Get all seed accounts and their community weights
    seeds = {}
    for cid, aid, weight in conn.execute(
        "SELECT community_id, account_id, weight FROM community_account"
    ).fetchall():
        if aid not in seeds:
            seeds[aid] = np.zeros(K)
        col = cid_to_idx.get(cid)
        if col is not None:
            seeds[aid][col] = max(seeds[aid][col], weight)

    # Get content profiles (CT1)
    content_profiles = {}
    for aid, tidx, weight in conn.execute(
        "SELECT account_id, topic_idx, weight FROM account_content_profile"
    ).fetchall():
        if aid not in content_profiles:
            content_profiles[aid] = {}
        content_profiles[aid][tidx] = weight

    # Compute per-account eligibility
    results = []
    for aid, weights in seeds.items():
        # 1. Max NMF weight
        max_w = float(np.max(weights))
        dominant_col = int(np.argmax(weights))
        dominant_cid = communities[dominant_col][0]
        dominant_short = cid_to_short[dominant_cid]

        # 2. Normalized entropy (0 = pure specialist, 1 = uniform)
        p = weights / (weights.sum() + 1e-10)
        entropy = -np.sum(p * np.log(p + 1e-10))
        max_entropy = np.log(K)
        norm_entropy = entropy / max_entropy if max_entropy > 0 else 0

        # 3. Concentration (inverse of entropy)
        concentration = 1.0 - norm_entropy

        # 4. Content agreement
        content_agrees = None
        ct1_profile = content_profiles.get(aid)
        if ct1_profile:
            top_topic = max(ct1_profile, key=ct1_profile.get)
            expected_topic = COMMUNITY_TO_TOP_TOPIC.get(dominant_short)
            if expected_topic is not None:
                content_agrees = (top_topic == expected_topic)

        # 5. Composite eligibility
        # concentration is the primary weight for propagation
        # content agreement boosts or penalizes
        eligible = max_w >= min_weight
        if content_agrees is False and max_w < 0.40:
            eligible = False  # disagree + weak = demote

        # Get username
        uname = conn.execute(
            "SELECT username FROM profiles WHERE account_id = ?", (aid,)
        ).fetchone()
        username = uname[0] if uname else aid[:12]

        results.append({
            "account_id": aid,
            "username": username,
            "max_weight": max_w,
            "dominant_community": dominant_short,
            "entropy": norm_entropy,
            "concentration": concentration,
            "content_agrees": content_agrees,
            "eligible": eligible,
        })

    # Save to DB
    conn.execute("DROP TABLE IF EXISTS seed_eligibility")
    conn.execute("""
        CREATE TABLE seed_eligibility (
            account_id      TEXT PRIMARY KEY,
            max_weight      REAL NOT NULL,
            dominant_community TEXT NOT NULL,
            entropy         REAL NOT NULL,
            concentration   REAL NOT NULL,
            content_agrees  INTEGER,
            eligible        INTEGER NOT NULL,
            created_at      TEXT NOT NULL
        )
    """)
    conn.executemany(
        "INSERT INTO seed_eligibility VALUES (?,?,?,?,?,?,?,?)",
        [(r["account_id"], r["max_weight"], r["dominant_community"],
          r["entropy"], r["concentration"],
          1 if r["content_agrees"] else (0 if r["content_agrees"] is False else None),
          1 if r["eligible"] else 0, now)
         for r in results]
    )
    conn.commit()

    # Print report
    eligible = [r for r in results if r["eligible"]]
    demoted = [r for r in results if not r["eligible"]]

    print(f"Seed Eligibility Report")
    print(f"  Total seeds: {len(results)}")
    print(f"  Eligible:    {len(eligible)} ({len(eligible)/len(results)*100:.0f}%)")
    print(f"  Demoted:     {len(demoted)} ({len(demoted)/len(results)*100:.0f}%)")

    print(f"\n  DEMOTED ACCOUNTS (would be shadow nodes, not seeds):")
    for r in sorted(demoted, key=lambda x: x["max_weight"]):
        agree_str = "✓" if r["content_agrees"] else ("✗" if r["content_agrees"] is False else "?")
        print(f"    @{r['username']:<24} max_w={r['max_weight']:.2f} "
              f"ent={r['entropy']:.2f} conc={r['concentration']:.2f} "
              f"content={agree_str} dom={r['dominant_community']}")

    print(f"\n  CONCENTRATION DISTRIBUTION (all seeds):")
    concentrations = [r["concentration"] for r in results]
    for thresh in [0.9, 0.7, 0.5, 0.3, 0.1]:
        count = sum(1 for c in concentrations if c >= thresh)
        print(f"    >= {thresh:.1f}: {count} seeds")

    print(f"\n  CONTENT AGREEMENT:")
    agrees = sum(1 for r in results if r["content_agrees"] is True)
    disagrees = sum(1 for r in results if r["content_agrees"] is False)
    unknown = sum(1 for r in results if r["content_agrees"] is None)
    print(f"    Agree: {agrees}, Disagree: {disagrees}, No CT1 data: {unknown}")

    conn.close()
    return results


def main():
    parser = argparse.ArgumentParser(description="Validate seed eligibility")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--min-weight", type=float, default=0.25,
                        help="Minimum max NMF weight for eligibility (default 0.25)")
    args = parser.parse_args()
    compute_seed_eligibility(args.db_path, args.min_weight)


if __name__ == "__main__":
    main()
