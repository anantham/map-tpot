"""Diagnostic: map the three seed categories and surface community_account source breakdown.

Category 1 (strongest): archive exemplar AND in TPOT directory  → directory-confirmed archive account
Category 2 (directory-only): in TPOT directory, NOT in archive  → known TPOT, no graph data
Category 3 (archive-only): archive exemplar, NOT in directory   → graph-clustered, unconfirmed

Usage:
    .venv/bin/python3 -m scripts.verify_seed_ground_truth
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "archive_tweets.db"


def main() -> None:
    db = sqlite3.connect(str(DB_PATH))

    # ── 1. community_account source breakdown ────────────────────────────────
    print("=" * 70)
    print("COMMUNITY_ACCOUNT SOURCE BREAKDOWN")
    print("=" * 70)
    rows = db.execute("""
        SELECT source, COUNT(*) as rows, COUNT(DISTINCT account_id) as accounts
        FROM community_account
        GROUP BY source
        ORDER BY rows DESC
    """).fetchall()
    for source, n_rows, n_accts in rows:
        print(f"  source='{source}': {n_rows} rows, {n_accts} distinct accounts")

    # Show any human-sourced accounts specifically
    human_rows = db.execute("""
        SELECT ca.account_id, COALESCE(p.username, ra.username, ca.account_id) as handle,
               c.name as community, ca.weight
        FROM community_account ca
        JOIN community c ON c.id = ca.community_id
        LEFT JOIN profiles p ON p.account_id = ca.account_id
        LEFT JOIN resolved_accounts ra ON ra.account_id = ca.account_id
        WHERE ca.source = 'human'
        ORDER BY ca.weight DESC
    """).fetchall()
    if human_rows:
        print(f"\n  Human-sourced accounts ({len(human_rows)} rows):")
        for aid, handle, community, weight in human_rows:
            print(f"    @{handle:<28} → {community:<35} weight={weight:.3f}")
    else:
        print("\n  No source='human' rows found — all assignments are NMF-derived.")

    # ── 2. All exemplar accounts (NMF archive accounts) ──────────────────────
    exemplars = {row[0] for row in db.execute(
        "SELECT DISTINCT account_id FROM community_account"
    ).fetchall()}

    # ── 3. All directory accounts ─────────────────────────────────────────────
    dir_rows = db.execute("""
        SELECT handle, source, account_id
        FROM tpot_directory_holdout
    """).fetchall()
    dir_accounts = {row[2]: (row[0], row[1]) for row in dir_rows if row[2]}
    dir_handles_unresolved = [row[0] for row in dir_rows if not row[2]]

    print(f"\n{'=' * 70}")
    print("TPOT DIRECTORY HOLDOUT")
    print("=" * 70)
    dir_sources = {}
    for _, src, _ in dir_rows:
        dir_sources[src] = dir_sources.get(src, 0) + 1
    print(f"  Total: {len(dir_rows)}")
    print(f"  Resolved to account_id: {len(dir_accounts)}")
    print(f"  Unresolved (no account_id): {len(dir_handles_unresolved)}")
    for src, cnt in sorted(dir_sources.items()):
        print(f"  source='{src}': {cnt}")

    # ── 4. Three-way categorisation ───────────────────────────────────────────
    cat1 = exemplars & dir_accounts.keys()   # archive + directory
    cat2 = dir_accounts.keys() - exemplars   # directory-only
    cat3 = exemplars - dir_accounts.keys()   # archive-only

    print(f"\n{'=' * 70}")
    print("THREE-CATEGORY BREAKDOWN")
    print("=" * 70)
    print(f"  Category 1 (archive ∩ directory — USE AS SEEDS): {len(cat1)}")
    print(f"  Category 2 (directory only — ground truth, no assignments): {len(cat2)}")
    print(f"  Category 3 (archive only — NMF-confirmed, unverified TPOT): {len(cat3)}")
    print(f"  Directory unresolved (no account_id): {len(dir_handles_unresolved)}")

    # ── 5. Category 1: community distribution ────────────────────────────────
    if cat1:
        print(f"\n{'=' * 70}")
        print(f"CATEGORY 1 ACCOUNTS ({len(cat1)}) — COMMUNITY DISTRIBUTION")
        print("=" * 70)
        comm_counts = db.execute("""
            SELECT c.name, COUNT(DISTINCT ca.account_id) as n,
                   AVG(ca.weight) as avg_w, MIN(ca.weight) as min_w
            FROM community_account ca
            JOIN community c ON c.id = ca.community_id
            WHERE ca.account_id IN ({})
            GROUP BY c.name
            ORDER BY n DESC
        """.format(",".join("?" * len(cat1))), list(cat1)).fetchall()

        for comm, n, avg_w, min_w in comm_counts:
            print(f"  {comm:<40} {n:>3} accounts  avg_w={avg_w:.3f}  min_w={min_w:.3f}")

        # Show any communities with zero category-1 coverage
        all_comms = {r[0] for r in db.execute("SELECT name FROM community").fetchall()}
        covered = {r[0] for r in comm_counts}
        uncovered = all_comms - covered
        if uncovered:
            print(f"\n  Communities with NO category-1 seeds: {sorted(uncovered)}")

    # ── 6. Category 3: how many are seed_eligible? ───────────────────────────
    if cat3:
        eligible = db.execute("""
            SELECT COUNT(*) FROM seed_eligibility
            WHERE account_id IN ({}) AND concentration >= 0.3
        """.format(",".join("?" * len(cat3))), list(cat3)).fetchone()[0]
        print(f"\n{'=' * 70}")
        print(f"CATEGORY 3 — ARCHIVE-ONLY EXEMPLARS ({len(cat3)})")
        print("=" * 70)
        print(f"  seed_eligible (concentration >= 0.3): {eligible}")
        print(f"  Not in any directory: these are NMF-clustered but unconfirmed as TPOT")

    db.close()
    print(f"\n{'=' * 70}")
    print("RECOMMENDATION")
    print("=" * 70)
    print(f"  Use category 1 ({len(cat1)} accounts) as primary seeds.")
    print(f"  Category 3 ({len(cat3)}) can be secondary seeds weighted by concentration.")
    print(f"  Category 2 ({len(cat2)}) are holdout ground truth — do not use as seeds.")


if __name__ == "__main__":
    main()
