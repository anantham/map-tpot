#!/usr/bin/env python3
"""Verify communities persistence: schema, data integrity, override behavior."""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
ARCHIVE_DB = ROOT / "data" / "archive_tweets.db"


def check(label, ok, detail=""):
    status = "\u2713" if ok else "\u2717"
    print(f"  {status}  {label}" + (f"  ({detail})" if detail else ""))
    return ok


def main():
    if not ARCHIVE_DB.exists():
        print(f"\u2717  Database not found: {ARCHIVE_DB}")
        sys.exit(1)

    conn = sqlite3.connect(str(ARCHIVE_DB))
    all_ok = True

    print("Schema checks:")
    for table in ["community_run", "community_membership", "community_definition",
                  "community", "community_account"]:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        all_ok &= check(f"Table {table} exists", exists is not None)

    print("\nData checks:")
    runs = conn.execute("SELECT COUNT(*) FROM community_run").fetchone()[0]
    all_ok &= check("At least one saved run", runs > 0, f"{runs} runs")

    comms = conn.execute("SELECT COUNT(*) FROM community").fetchone()[0]
    all_ok &= check("Communities exist", comms > 0, f"{comms} communities")

    memberships = conn.execute("SELECT COUNT(*) FROM community_account").fetchone()[0]
    all_ok &= check("Community memberships exist", memberships > 0, f"{memberships} total")

    nmf_count = conn.execute(
        "SELECT COUNT(*) FROM community_account WHERE source='nmf'"
    ).fetchone()[0]
    human_count = conn.execute(
        "SELECT COUNT(*) FROM community_account WHERE source='human'"
    ).fetchone()[0]
    check("NMF memberships", True, f"{nmf_count}")
    check("Human memberships", True, f"{human_count}")

    print("\nReferential integrity:")
    orphan_ca = conn.execute("""
        SELECT COUNT(*) FROM community_account ca
        WHERE NOT EXISTS (SELECT 1 FROM community c WHERE c.id = ca.community_id)
    """).fetchone()[0]
    all_ok &= check("community_account -> community FK", orphan_ca == 0,
                     f"{orphan_ca} orphans" if orphan_ca else "clean")

    orphan_cm = conn.execute("""
        SELECT COUNT(*) FROM community_membership cm
        WHERE NOT EXISTS (SELECT 1 FROM community_run cr WHERE cr.run_id = cm.run_id)
    """).fetchone()[0]
    all_ok &= check("community_membership -> community_run FK", orphan_cm == 0,
                     f"{orphan_cm} orphans" if orphan_cm else "clean")

    orphan_cd = conn.execute("""
        SELECT COUNT(*) FROM community_definition cd
        WHERE NOT EXISTS (SELECT 1 FROM community_run cr WHERE cr.run_id = cd.run_id)
    """).fetchone()[0]
    all_ok &= check("community_definition -> community_run FK", orphan_cd == 0,
                     f"{orphan_cd} orphans" if orphan_cd else "clean")

    print("\nBehavioral checks:")

    # B1: No duplicate community seeds for the same (run, idx) — Finding #2 regression guard
    dup_seeds = conn.execute("""
        SELECT seeded_from_run, seeded_from_idx, COUNT(*) as cnt
        FROM community
        WHERE seeded_from_run IS NOT NULL AND seeded_from_idx IS NOT NULL
        GROUP BY seeded_from_run, seeded_from_idx
        HAVING cnt > 1
    """).fetchall()
    all_ok &= check(
        "No duplicate community seeds (run+idx unique)",
        len(dup_seeds) == 0,
        f"{len(dup_seeds)} duplicate (run,idx) pairs" if dup_seeds else "clean",
    )

    # B2: All source values are valid
    invalid_source = conn.execute(
        "SELECT COUNT(*) FROM community_account WHERE source NOT IN ('nmf', 'human')"
    ).fetchone()[0]
    all_ok &= check(
        "All membership sources valid ('nmf' or 'human')",
        invalid_source == 0,
        f"{invalid_source} invalid" if invalid_source else "clean",
    )

    # B3: account_note table present (required by curator notes feature)
    note_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_note'"
    ).fetchone()
    all_ok &= check("Table account_note exists", note_table is not None)

    # B4: Human-override integrity — no (community_id, account_id) has duplicate rows
    # (enforced by PK; this catches corrupted DBs)
    dupe_ca = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT community_id, account_id, COUNT(*) as cnt
            FROM community_account
            GROUP BY community_id, account_id
            HAVING cnt > 1
        )
    """).fetchone()[0]
    all_ok &= check(
        "No duplicate (community, account) membership rows",
        dupe_ca == 0,
        f"{dupe_ca} duplicates" if dupe_ca else "clean",
    )

    print("\nRuns:")
    for run_id, k, signal, thresh, acct_count, notes, created in conn.execute(
        "SELECT * FROM community_run ORDER BY created_at DESC"
    ).fetchall():
        print(f"  {run_id}  k={k}  accounts={acct_count}  notes={notes}")

    print(f"\nCommunities ({comms}):")
    for cid, name, color, desc, sfrun, sfidx, count, created, updated in conn.execute(
        """SELECT c.id, c.name, c.color, c.description,
                  c.seeded_from_run, c.seeded_from_idx,
                  COUNT(ca.account_id) as member_count,
                  c.created_at, c.updated_at
           FROM community c
           LEFT JOIN community_account ca ON ca.community_id = c.id
           GROUP BY c.id ORDER BY member_count DESC"""
    ).fetchall():
        print(f"  {color or '---'}  {name:<35} {count:>3} members")

    print(f"\nSummary:")
    print(f"  Communities: {comms}")
    print(f"  Memberships: {memberships} ({nmf_count} nmf, {human_count} human)")

    l1_memberships = conn.execute("SELECT COUNT(*) FROM community_membership").fetchone()[0]
    l1_definitions = conn.execute("SELECT COUNT(*) FROM community_definition").fetchone()[0]
    print(f"  Layer 1: {l1_memberships} membership rows, {l1_definitions} definition rows")

    print(f"\n{'ALL CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED'}")

    print("\nNext steps:")
    if human_count == 0:
        print("  1. Start backend: .venv/bin/python3 -m src.api.server")
        print("  2. Start frontend: cd graph-explorer && npm run dev")
        print("  3. Open Communities tab and start curating memberships")
        print("  4. Re-run this script to verify human edits are persisted")
    else:
        print(f"  - {human_count} human-curated memberships preserved")
        print("  - Communities tab ready for further curation")
        print("  - Run 'pytest tests/test_communities_store.py -v' to verify store invariants")

    conn.close()
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
