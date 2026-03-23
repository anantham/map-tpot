#!/usr/bin/env python3
"""
Verification script for CT1 content vectors.

Checks:
  1. content_topic table has expected number of topics with words
  2. account_content_profile table has rows for each account
  3. Weights per account sum to ~1.0
  4. Shows each topic with top words
  5. Shows known accounts' top 3 topics
  6. Compares content profile vs NMF community membership — correlation check

Usage:
    .venv/bin/python3 -m scripts.verify_content_vectors
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DB = ROOT / "data" / "archive_tweets.db"

KNOWN_ACCOUNTS = [
    "RomeoStevens76",
    "repligate",
    "visakanv",
    "eshear",
    "dschorno",
    "QiaochuYuan",
    "adityaarpitha",
    "pee_zombie",
]

PASS = "\u2713"
FAIL = "\u2717"


def check(label: str, ok: bool, detail: str = "") -> bool:
    mark = PASS if ok else FAIL
    suffix = f"  ({detail})" if detail else ""
    print(f"  {mark} {label}{suffix}")
    return ok


def main() -> None:
    if not ARCHIVE_DB.exists():
        print(f"  {FAIL} Database not found: {ARCHIVE_DB}")
        sys.exit(1)

    conn = sqlite3.connect(str(ARCHIVE_DB))
    all_ok = True

    # ── 1. content_topic table ───────────────────────────────────────────
    print("\n=== Content Topic Table ===")

    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('content_topic', 'account_content_profile')"
        ).fetchall()
    ]
    all_ok &= check("content_topic table exists", "content_topic" in tables)
    all_ok &= check(
        "account_content_profile table exists",
        "account_content_profile" in tables,
    )

    if "content_topic" not in tables:
        print(f"\n  {FAIL} Cannot proceed — run build_content_vectors.py first")
        sys.exit(1)

    topic_count = conn.execute(
        "SELECT COUNT(*) FROM content_topic"
    ).fetchone()[0]
    all_ok &= check(
        f"Topic count = {topic_count}",
        topic_count > 0,
        "expected 25 by default",
    )

    # Check all topics have words
    empty_topics = conn.execute(
        "SELECT COUNT(*) FROM content_topic WHERE top_words IS NULL OR top_words = ''"
    ).fetchone()[0]
    all_ok &= check(
        "All topics have top_words",
        empty_topics == 0,
        f"{empty_topics} empty" if empty_topics else "",
    )

    # ── 2. account_content_profile table ─────────────────────────────────
    print("\n=== Account Content Profiles ===")

    profile_count = conn.execute(
        "SELECT COUNT(*) FROM account_content_profile"
    ).fetchone()[0]
    all_ok &= check(
        f"Profile rows = {profile_count}",
        profile_count > 0,
    )

    distinct_accounts = conn.execute(
        "SELECT COUNT(DISTINCT account_id) FROM account_content_profile"
    ).fetchone()[0]
    all_ok &= check(
        f"Distinct accounts = {distinct_accounts}",
        distinct_accounts > 200,
        "expected ~257",
    )

    # ── 3. Weight normalization check ────────────────────────────────────
    print("\n=== Weight Normalization ===")

    weight_sums = conn.execute(
        "SELECT account_id, SUM(weight) AS total "
        "FROM account_content_profile "
        "GROUP BY account_id"
    ).fetchall()

    totals = [r[1] for r in weight_sums]
    min_total = min(totals) if totals else 0
    max_total = max(totals) if totals else 0
    mean_total = np.mean(totals) if totals else 0

    all_ok &= check(
        f"Weight sums range: [{min_total:.4f}, {max_total:.4f}], mean={mean_total:.4f}",
        all(abs(t - 1.0) < 0.05 for t in totals),
        "should all be ~1.0",
    )

    # ── 4. Topic display ─────────────────────────────────────────────────
    print("\n=== Topics ===")

    topics = conn.execute(
        "SELECT topic_idx, top_words FROM content_topic ORDER BY topic_idx"
    ).fetchall()

    for idx, words in topics:
        short = ", ".join(words.split(", ")[:8])
        print(f"  T{idx:2d}: {short}")

    # ── 5. Known account profiles ────────────────────────────────────────
    print("\n=== Known Account Profiles (top 3 topics) ===")

    # Resolve usernames to account_ids via likes table
    username_to_id = {}
    for uname in KNOWN_ACCOUNTS:
        row = conn.execute(
            "SELECT DISTINCT liker_account_id FROM likes "
            "WHERE liker_username = ? LIMIT 1",
            (uname,),
        ).fetchone()
        if row:
            username_to_id[uname] = row[0]

    found = len(username_to_id)
    print(f"\n  Resolved {found}/{len(KNOWN_ACCOUNTS)} known accounts")

    for uname in KNOWN_ACCOUNTS:
        aid = username_to_id.get(uname)
        if not aid:
            print(f"\n  @{uname}: NOT FOUND in likes table")
            continue

        rows = conn.execute(
            "SELECT p.topic_idx, p.weight, t.top_words "
            "FROM account_content_profile p "
            "JOIN content_topic t ON t.topic_idx = p.topic_idx "
            "WHERE p.account_id = ? "
            "ORDER BY p.weight DESC "
            "LIMIT 3",
            (aid,),
        ).fetchall()

        if not rows:
            print(f"\n  @{uname}: NO PROFILE DATA")
            continue

        print(f"\n  @{uname} ({aid}):")
        for tidx, weight, words in rows:
            short = ", ".join(words.split(", ")[:5])
            print(f"    T{tidx:2d} = {weight:.1%}  [{short}]")

    # ── 6. Cross-reference with NMF communities ─────────────────────────
    print("\n=== Content vs Graph Community Correlation ===")

    # Check if community tables exist
    has_communities = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master "
        "WHERE type='table' AND name='community_account'"
    ).fetchone()[0]

    if not has_communities:
        print(f"  {FAIL} No community_account table — skipping correlation check")
    else:
        # Get community memberships for accounts that also have content profiles
        community_data = conn.execute(
            "SELECT ca.account_id, ca.community_id, ca.weight "
            "FROM community_account ca "
            "WHERE ca.account_id IN "
            "  (SELECT DISTINCT account_id FROM account_content_profile)"
        ).fetchall()

        if community_data:
            n_community_accounts = len(set(r[0] for r in community_data))
            n_communities = len(set(r[1] for r in community_data))
            print(
                f"  Found {n_community_accounts} accounts with both "
                f"content and community profiles ({n_communities} communities)"
            )

            # Build a simple comparison: for each account, find their
            # top content topic and top community — see if there's structure
            content_tops = {}
            for uname, aid in username_to_id.items():
                row = conn.execute(
                    "SELECT topic_idx FROM account_content_profile "
                    "WHERE account_id = ? ORDER BY weight DESC LIMIT 1",
                    (aid,),
                ).fetchone()
                if row:
                    content_tops[uname] = row[0]

            comm_tops = {}
            for uname, aid in username_to_id.items():
                row = conn.execute(
                    "SELECT community_id FROM community_account "
                    "WHERE account_id = ? ORDER BY weight DESC LIMIT 1",
                    (aid,),
                ).fetchone()
                if row:
                    comm_tops[uname] = row[0]

            print("\n  Account         | Top Content Topic | Top Community")
            print("  " + "-" * 55)
            for uname in KNOWN_ACCOUNTS:
                ct = content_tops.get(uname, "?")
                cc = comm_tops.get(uname, "?")
                print(f"  @{uname:<16s} | T{str(ct):<17s} | C{cc}")

            print(
                "\n  Note: Content topics and graph communities are orthogonal"
                "\n  signals. Divergence is expected and informative — it reveals"
                "\n  interests that cut across social clusters."
            )
        else:
            print("  No overlapping accounts between content and community data")

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n=== Summary ===")
    print(f"  Topics:   {topic_count}")
    print(f"  Accounts: {distinct_accounts}")
    print(f"  Rows:     {profile_count}")

    conn.close()

    if all_ok:
        print(f"\n  {PASS} All checks passed")
    else:
        print(f"\n  {FAIL} Some checks failed — see above")

    print("\n  Next steps:")
    print("  - Inspect topic coherence — are top words semantically grouped?")
    print("  - Label topics manually (e.g., T1=rationalism, T3=philosophy)")
    print("  - Compare content vectors against tweet labeling bits")
    print("  - Use content profiles as features in community prediction")


if __name__ == "__main__":
    main()
