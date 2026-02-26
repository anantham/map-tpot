#!/usr/bin/env python3
"""
Seed Layer 2 (curator's canonical map) from a saved NMF run.

Reads community_membership + community_definition for a given run_id,
creates named community entries and populates community_account rows.

Communities are auto-named from their top RT targets (e.g. "dwarkesh_sp /
davidad"). You rename them in the UI or directly in the DB. Re-running with
the same --run-id clears and re-seeds that run's communities cleanly.

Usage:
    python scripts/seed_communities.py --list
    python scripts/seed_communities.py --run-id nmf-k14-20260225-abc123
    python scripts/seed_communities.py --run-id nmf-k14-20260225-abc123 --threshold 0.15
"""

import argparse
import sqlite3
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from communities.store import (
    init_db,
    list_runs,
    get_memberships,
    get_definitions,
    upsert_community,
    upsert_community_account,
    reseed_nmf_memberships,
    list_communities,
)

ARCHIVE_DB = ROOT / "data" / "archive_tweets.db"

# 16-color palette for UI — cycles if k > 16
PALETTE = [
    "#4a90e2",  # blue
    "#e67e22",  # orange
    "#2ecc71",  # green
    "#9b59b6",  # purple
    "#e74c3c",  # red
    "#1abc9c",  # teal
    "#f39c12",  # yellow
    "#3498db",  # light blue
    "#e91e63",  # pink
    "#00bcd4",  # cyan
    "#8bc34a",  # light green
    "#ff5722",  # deep orange
    "#607d8b",  # blue grey
    "#9c27b0",  # deep purple
    "#795548",  # brown
    "#ff9800",  # amber
]


def auto_name(community_idx: int, rt_targets: list[str], follow_targets: list[str]) -> str:
    """Generate a human-readable name from top RT targets, falling back to follows."""
    sources = rt_targets[:2] if rt_targets else follow_targets[:2]
    if sources:
        return " / ".join(sources)
    return f"Community {community_idx + 1}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id",    type=str,   help="NMF run to seed from")
    parser.add_argument("--list",      action="store_true", help="List available runs")
    parser.add_argument("--threshold", type=float, default=0.10,
                        help="Min NMF weight to include in community_account (default 0.10)")
    args = parser.parse_args()

    conn = sqlite3.connect(str(ARCHIVE_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    init_db(conn)

    if args.list:
        runs = list_runs(conn)
        if not runs:
            print("No saved NMF runs found. Run cluster_soft.py --save first.")
        else:
            print(f"{'run_id':<35} {'k':>3}  {'accounts':>8}  {'notes'}")
            print("-" * 65)
            for run_id, k, signal, threshold, acct_count, notes, created_at in runs:
                label = notes or ""
                print(f"{run_id:<35} {k:>3}  {acct_count:>8}  {label}")
        conn.close()
        return

    if not args.run_id:
        parser.error("--run-id is required (or use --list to see available runs)")

    run_id = args.run_id

    # Verify run exists
    row = conn.execute(
        "SELECT k, account_count, notes FROM community_run WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if not row:
        print(f"ERROR: run '{run_id}' not found. Use --list to see available runs.")
        conn.close()
        sys.exit(1)

    k, account_count, notes = row
    print(f"Seeding from run: {run_id}  (k={k}, {account_count} accounts, notes={notes!r})")

    # Clear only NMF-seeded memberships (preserves human edits and community metadata)
    deleted = reseed_nmf_memberships(conn, run_id)
    if deleted:
        print(f"  Cleared {deleted} NMF memberships (human edits preserved).")

    # Load definitions and memberships
    definitions = get_definitions(conn, run_id)
    memberships = get_memberships(conn, run_id)

    # Group definitions by community index
    rt_by_community: dict[int, list[str]] = {}
    follow_by_community: dict[int, list[str]] = {}
    for cidx, ftype, target, score, rank in definitions:
        if ftype == "rt":
            rt_by_community.setdefault(cidx, []).append(target)
        else:
            follow_by_community.setdefault(cidx, []).append(target)

    # Group memberships by community index
    accounts_by_community: dict[int, list[tuple[str, float]]] = {}
    for account_id, cidx, weight in memberships:
        if weight >= args.threshold:
            accounts_by_community.setdefault(cidx, []).append((account_id, weight))

    # Create community + account rows
    community_ids: dict[int, str] = {}
    total_accounts = 0

    for cidx in range(k):
        members = accounts_by_community.get(cidx, [])
        if not members:
            continue  # skip empty communities

        rt_targets = rt_by_community.get(cidx, [])
        follow_targets = follow_by_community.get(cidx, [])
        name = auto_name(cidx, rt_targets, follow_targets)
        color = PALETTE[cidx % len(PALETTE)]
        existing = conn.execute(
            "SELECT id FROM community WHERE seeded_from_run = ? AND seeded_from_idx = ?",
            (run_id, cidx),
        ).fetchone()
        community_id = existing[0] if existing else str(uuid.uuid4())
        community_ids[cidx] = community_id

        upsert_community(
            conn,
            community_id=community_id,
            name=name,
            color=color,
            seeded_from_run=run_id,
            seeded_from_idx=cidx,
        )

        for account_id, weight in members:
            upsert_community_account(
                conn,
                community_id=community_id,
                account_id=account_id,
                weight=weight,
                source="nmf",
            )
        total_accounts += len(members)

    conn.commit()

    # Summary
    communities = list_communities(conn)
    seeded = [c for c in communities if c[4] == run_id]  # seeded_from_run == run_id

    print(f"\n✓ Seeded {len(seeded)} communities ({total_accounts} account memberships)\n")
    print(f"  {'Name':<35} {'Members':>7}  {'Color'}")
    print("  " + "-" * 55)
    for cid, name, color, desc, sfrun, sfidx, member_count, created_at, updated_at in seeded:
        print(f"  {name:<35} {member_count:>7}  {color}")

    print(f"\n  Tip: rename communities via the UI or:")
    print(f"    UPDATE community SET name='EA / forecasting' WHERE id='<uuid>';")

    conn.close()


if __name__ == "__main__":
    main()
