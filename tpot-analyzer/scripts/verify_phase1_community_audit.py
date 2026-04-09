#!/usr/bin/env python3
"""Human-friendly verifier for the Phase 1 community-correctness audit."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Dict
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from scripts.phase1_community_audit.config import (
        DEFAULT_DB_PATH,
        DEFAULT_MANIFEST_PATH,
        DEFAULT_MEMBERSHIP_PROMPT_PATH,
        DEFAULT_RESULTS_JSONL_PATH,
        DEFAULT_REVIEW_CSV_PATH,
        EXPECTED_BUCKET_COUNTS,
        PROJECT_ROOT,
    )
    from scripts.phase1_community_audit.db import connect_db, count_active_labels, list_active_label_breakdown
    from scripts.phase1_community_audit.io import load_manifest, load_review_csv
except ImportError:  # pragma: no cover
    from phase1_community_audit.config import (
        DEFAULT_DB_PATH,
        DEFAULT_MANIFEST_PATH,
        DEFAULT_MEMBERSHIP_PROMPT_PATH,
        DEFAULT_RESULTS_JSONL_PATH,
        DEFAULT_REVIEW_CSV_PATH,
        EXPECTED_BUCKET_COUNTS,
        PROJECT_ROOT,
    )
    from phase1_community_audit.db import connect_db, count_active_labels, list_active_label_breakdown
    from phase1_community_audit.io import load_manifest, load_review_csv

from src.data.community_gold import CommunityGoldStore


CHECK = "✓"
CROSS = "✗"


def status_line(ok: bool, message: str) -> str:
    return f"{CHECK if ok else CROSS} {message}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Phase 1 community-correctness audit artifacts")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="Path to archive_tweets.db")
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH, help="Manifest JSON path")
    parser.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW_CSV_PATH, help="Review-sheet CSV path")
    parser.add_argument("--results-jsonl", type=Path, default=DEFAULT_RESULTS_JSONL_PATH, help="Membership results JSONL path")
    parser.add_argument("--reviewer", default="human_phase1", help="Reviewer namespace for imported labels")
    parser.add_argument("--require-imported", action="store_true", help="Fail if no imported labels exist yet")
    parser.add_argument("--require-scoreboard", action="store_true", help="Fail if evaluator cannot score communities yet")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checks = []
    failures = 0

    docs_ok = all(
        path.exists()
        for path in [
            PROJECT_ROOT / "docs" / "reference" / "evals" / "phase1-community-correctness.md",
            DEFAULT_MEMBERSHIP_PROMPT_PATH,
            PROJECT_ROOT / "docs" / "reference" / "evals" / "prompts" / "grok-420-hard-negatives.md",
        ]
    )
    checks.append(status_line(docs_ok, "Phase 1 docs + prompt templates exist"))
    if not docs_ok:
        failures += 1

    manifest_exists = args.manifest_path.exists()
    checks.append(status_line(manifest_exists, f"manifest exists ({args.manifest_path})"))
    if not manifest_exists:
        failures += 1
        print("\n".join(checks))
        return 1

    manifest = load_manifest(args.manifest_path)
    bucket_counts: Dict[str, int] = dict(Counter(item["bucket"] for item in manifest))
    buckets_ok = bucket_counts == EXPECTED_BUCKET_COUNTS
    checks.append(status_line(buckets_ok, f"manifest bucket counts match expected ({bucket_counts})"))
    if not buckets_ok:
        failures += 1

    missing_posts = sum(1 for item in manifest if item.get("missing_local_posts"))
    checks.append(status_line(True, f"manifest rows with no local posts are tracked (count={missing_posts})"))

    review_exists = args.review_csv.exists()
    checks.append(status_line(review_exists, f"review sheet exists ({args.review_csv})"))
    if not review_exists:
        failures += 1
        print("\n".join(checks))
        return 1

    review_rows = load_review_csv(args.review_csv)
    row_count_ok = len(review_rows) == len(manifest)
    checks.append(status_line(row_count_ok, f"review sheet row count matches manifest ({len(review_rows)})"))
    if not row_count_ok:
        failures += 1

    results_count = 0
    if args.results_jsonl.exists():
        results_count = sum(1 for _ in args.results_jsonl.open("r", encoding="utf-8"))
    checks.append(status_line(True, f"membership audit result rows present (count={results_count})"))

    conn = connect_db(args.db_path)
    try:
        active_count = count_active_labels(conn, reviewer=args.reviewer)
        breakdown = list_active_label_breakdown(conn, reviewer=args.reviewer)
    finally:
        conn.close()

    imported_ok = active_count > 0
    checks.append(status_line(imported_ok or not args.require_imported, f"imported active labels for reviewer {args.reviewer} (count={active_count})"))
    if args.require_imported and not imported_ok:
        failures += 1

    store = CommunityGoldStore(args.db_path)
    try:
        scoreboard = store.evaluate_scoreboard(split="dev", reviewer=args.reviewer, train_split="train")
        summary = scoreboard.get("summary") or {}
        scored_methods = sum(1 for row in summary.values() if row.get("scoredCommunities", 0) > 0)
        scoreboard_ok = scored_methods > 0
    except Exception:
        summary = {}
        scored_methods = 0
        scoreboard_ok = False

    checks.append(status_line(scoreboard_ok or not args.require_scoreboard, f"scoreboard has scored communities (methods={scored_methods})"))
    if args.require_scoreboard and not scoreboard_ok:
        failures += 1

    print("Phase 1 Community Audit Verification")
    print("====================================")
    for line in checks:
        print(line)

    print("\nMetrics")
    print(f"- manifest_rows: {len(manifest)}")
    print(f"- bucket_counts: {bucket_counts}")
    print(f"- rows_missing_local_posts: {missing_posts}")
    print(f"- review_rows: {len(review_rows)}")
    print(f"- grok_result_rows: {results_count}")
    print(f"- active_labels[{args.reviewer}]: {active_count}")
    if breakdown:
        print("- active_label_breakdown:")
        for row in breakdown:
            print(f"  - {row['short_name']} / {row['judgment']} = {row['n']}")
    print(f"- scored_methods: {scored_methods}")
    print(f"- method_summary: {summary}")

    print("\nNext steps")
    if active_count == 0:
        print("- Run scripts/run_phase1_membership_audit.py --prepare-only to refresh the slate if needed.")
        print("- Run the Grok audit or review the CSV manually, then fill human_judgment in the review sheet.")
        print("- Import the reviewed judgments with scripts/import_phase1_gold_labels.py.")
    elif not scoreboard_ok:
        print("- Add more in/out labels per community before treating the evaluator as a real benchmark.")
        print("- Re-run this verifier with --require-scoreboard once coverage improves.")
    else:
        print("- The Phase 1 substrate is live: use the evaluator output to nominate Phase 2 merge/split/birth pressure candidates.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
