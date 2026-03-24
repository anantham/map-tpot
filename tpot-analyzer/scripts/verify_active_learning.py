#!/usr/bin/env python3
"""Verify active learning pipeline state.

Prints human-friendly status of all pipeline components with ✓/✗ markers.
Surfaces concrete metrics and proposes next steps.

Usage:
    .venv/bin/python3 -m scripts.verify_active_learning
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "archive_tweets.db"


def check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "✓" if ok else "✗"
    line = f"  {mark} {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def main():
    if not DB_PATH.exists():
        print(f"✗ Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    print("=" * 60)
    print("  ACTIVE LEARNING PIPELINE STATUS")
    print("=" * 60)
    all_ok = True

    # 1. Tables exist?
    print("\n--- Tables ---")
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    all_ok &= check("enriched_tweets table", "enriched_tweets" in tables)
    all_ok &= check("enrichment_log table", "enrichment_log" in tables)

    # 2. Enriched tweets count
    print("\n--- Enrichment ---")
    if "enriched_tweets" in tables:
        et_count = conn.execute("SELECT COUNT(*) FROM enriched_tweets").fetchone()[0]
        et_accounts = conn.execute("SELECT COUNT(DISTINCT account_id) FROM enriched_tweets").fetchone()[0]
        check("Enriched tweets", et_count > 0, f"{et_count} tweets across {et_accounts} accounts")
    else:
        check("Enriched tweets", False, "table missing")

    # 3. Budget
    print("\n--- Budget ---")
    if "enrichment_log" in tables:
        spent = conn.execute("SELECT COALESCE(SUM(estimated_cost), 0) FROM enrichment_log").fetchone()[0]
        calls = conn.execute("SELECT COUNT(*) FROM enrichment_log").fetchone()[0]
        check("Budget", spent < 5.0, f"${spent:.2f} spent of $5.00 ({calls} API calls)")
    else:
        check("Budget", False, "enrichment_log table missing")

    # 4. Labels
    print("\n--- Labeling ---")
    label_sets = conn.execute(
        "SELECT COUNT(*) FROM tweet_label_set WHERE axis='active_learning'"
    ).fetchone()[0] if "tweet_label_set" in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()] else 0
    check("Label sets (active_learning)", label_sets > 0, f"{label_sets} rows")

    bits_tags = conn.execute(
        "SELECT COUNT(*) FROM tweet_tags WHERE category='bits' AND added_by NOT IN ('human', 'aditya')"
    ).fetchone()[0] if "tweet_tags" in tables else 0
    check("LLM-generated bits tags", bits_tags > 0, f"{bits_tags} tags")

    # Per-model breakdown
    if label_sets > 0:
        reviewers = conn.execute(
            "SELECT reviewer, COUNT(*) FROM tweet_label_set WHERE axis='active_learning' GROUP BY reviewer ORDER BY COUNT(*) DESC"
        ).fetchall()
        for reviewer, count in reviewers:
            print(f"    {reviewer}: {count} label sets")

    # 5. New community signals
    print("\n--- New Community Signals ---")
    nc_tags = conn.execute(
        "SELECT tag, COUNT(*) FROM tweet_tags WHERE category='new-community' GROUP BY tag ORDER BY COUNT(*) DESC"
    ).fetchall() if "tweet_tags" in tables else []
    if nc_tags:
        for tag, count in nc_tags:
            print(f"    {tag}: {count} occurrences")
    else:
        print("    (none detected)")

    # 6. Seeds inserted
    print("\n--- Seed Insertion ---")
    llm_seeds = conn.execute(
        "SELECT COUNT(DISTINCT account_id) FROM community_account WHERE source='llm_ensemble'"
    ).fetchone()[0]
    check("LLM ensemble seeds", llm_seeds > 0, f"{llm_seeds} accounts")

    # 7. Propagation metrics (if available)
    print("\n--- Propagation ---")
    npz_path = DB_PATH.parent / "community_propagation.npz"
    check("Propagation NPZ exists", npz_path.exists())

    # 8. Model agreement diagnostic
    if label_sets > 0:
        print("\n--- Model Agreement ---")
        # Count tweets where we have labels from all 3 models
        tweet_model_counts = conn.execute("""
            SELECT tweet_id, COUNT(DISTINCT reviewer) as model_count
            FROM tweet_label_set
            WHERE axis='active_learning' AND reviewer != 'llm_ensemble_consensus'
            GROUP BY tweet_id
        """).fetchall()
        full_coverage = sum(1 for _, c in tweet_model_counts if c >= 3)
        total_labeled = len(tweet_model_counts)
        if total_labeled > 0:
            check("Full 3-model coverage", full_coverage > 0,
                  f"{full_coverage}/{total_labeled} tweets ({100*full_coverage/total_labeled:.0f}%)")

    # Summary
    print("\n" + "=" * 60)
    if all_ok:
        print("  Pipeline is operational.")
    else:
        print("  Pipeline has issues — see ✗ marks above.")

    # Next steps
    print("\n--- Next Steps ---")
    if "enriched_tweets" not in tables:
        print("  1. Run: .venv/bin/python3 -m scripts.active_learning --round 1 --top 3 --dry-run")
    elif et_count == 0:
        print("  1. Run: .venv/bin/python3 -m scripts.active_learning --round 1 --top 3 --budget 1.0")
    elif llm_seeds == 0:
        print("  1. Run: .venv/bin/python3 -m scripts.active_learning --measure")
    else:
        print("  1. Run: .venv/bin/python3 -m scripts.verify_holdout_recall")
        print("  2. Review labels and decide on Round 2")
    print()

    conn.close()


if __name__ == "__main__":
    main()
