#!/usr/bin/env python3
"""Import reviewed Phase 1 judgments into account-community gold labels."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from scripts.phase1_community_audit.config import DEFAULT_DB_PATH, DEFAULT_REVIEW_CSV_PATH
    from scripts.phase1_community_audit.db import connect_db, list_active_label_breakdown, load_community_lookup
    from scripts.phase1_community_audit.io import load_review_csv
except ImportError:  # pragma: no cover
    from phase1_community_audit.config import DEFAULT_DB_PATH, DEFAULT_REVIEW_CSV_PATH
    from phase1_community_audit.db import connect_db, list_active_label_breakdown, load_community_lookup
    from phase1_community_audit.io import load_review_csv

from src.data.community_gold import CommunityGoldStore
from src.data.community_gold.schema import validate_confidence, validate_judgment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import human-reviewed Phase 1 labels")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="Path to archive_tweets.db")
    parser.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW_CSV_PATH, help="Review-sheet CSV path")
    parser.add_argument("--reviewer", default="human_phase1", help="Reviewer namespace to write")
    parser.add_argument("--assigned-by", default="phase1_import", help="Split assignment provenance label")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be imported without writing")
    return parser.parse_args()


def validate_pending_rows(
    rows: list[dict[str, str]],
    *,
    communities: dict[str, dict[str, str]],
    community_id_to_short: dict[str, str],
) -> list[dict[str, object]]:
    validated: list[dict[str, object]] = []
    for row in rows:
        target_id = (row.get("target_community_id") or "").strip()
        target_short = (row.get("target_community_short_name") or "").strip()
        if not target_id:
            if target_short not in communities:
                raise ValueError(f"Unknown target community for {row.get('review_id')}: {target_short}")
            target_id = str(communities[target_short]["id"])
        elif target_id not in community_id_to_short:
            raise ValueError(f"Unknown target community id for {row.get('review_id')}: {target_id}")

        validated.append(
            {
                "row": row,
                "target_id": target_id,
                "target_short": community_id_to_short.get(target_id, target_short),
                "judgment": validate_judgment((row.get("human_judgment") or "").strip()),
                "confidence": validate_confidence((row.get("human_confidence") or "").strip() or None),
            }
        )
    return validated


def main() -> int:
    args = parse_args()
    if not args.review_csv.exists():
        print(f"Review CSV not found: {args.review_csv}")
        return 2

    rows = load_review_csv(args.review_csv)
    pending = [row for row in rows if (row.get("human_judgment") or "").strip()]
    if not pending:
        print("No human_judgment rows found. Fill the review CSV before importing.")
        return 2

    conn = connect_db(args.db_path)
    try:
        communities = load_community_lookup(conn)
    finally:
        conn.close()
    community_id_to_short = {row["id"]: short for short, row in communities.items()}

    try:
        validated_rows = validate_pending_rows(
            pending,
            communities=communities,
            community_id_to_short=community_id_to_short,
        )
    except ValueError as exc:
        print(f"Validation failed before import: {exc}")
        return 2

    store = CommunityGoldStore(args.db_path)
    bucket_counts = Counter()
    judgment_counts = Counter()
    imported = 0

    for entry in validated_rows:
        row = entry["row"]
        target_id = str(entry["target_id"])
        target_short = str(entry["target_short"])
        judgment = str(entry["judgment"])
        confidence = entry["confidence"]
        evidence = {
            "source": "phase1_membership_audit",
            "review_id": row.get("review_id"),
            "bucket": row.get("bucket"),
            "grok_tpot_status": row.get("grok_tpot_status"),
            "grok_top_communities": row.get("grok_top_communities"),
            "grok_confidence": row.get("grok_confidence"),
            "expected_judgment": row.get("expected_judgment"),
        }
        note = (row.get("human_note") or "").strip() or None
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "account_id": row["account_id"],
                        "username": row["username"],
                        "community_id": target_id,
                        "community_short_name": target_short,
                        "judgment": judgment,
                        "confidence": confidence,
                        "reviewer": args.reviewer,
                    }
                )
            )
        else:
            store.upsert_label(
                account_id=row["account_id"],
                community_id=target_id,
                reviewer=args.reviewer,
                judgment=judgment,
                confidence=confidence,
                note=note,
                evidence=evidence,
                assigned_by=args.assigned_by,
            )
        bucket_counts[row["bucket"]] += 1
        judgment_counts[judgment] += 1
        imported += 1

    print("Phase 1 Gold Import")
    print("===================")
    print(f"rows_processed: {imported}")
    print(f"bucket_counts: {dict(bucket_counts)}")
    print(f"judgment_counts: {dict(judgment_counts)}")
    print(f"reviewer: {args.reviewer}")
    if args.dry_run:
        print("dry_run: true")
        return 0

    conn = connect_db(args.db_path)
    try:
        breakdown = list_active_label_breakdown(conn, reviewer=args.reviewer)
    finally:
        conn.close()
    print("active_label_breakdown:")
    for row in breakdown:
        print(f"- {row['short_name']} / {row['judgment']} = {row['n']}")
    print("next_steps:")
    print("- Run scripts/verify_phase1_community_audit.py to check label counts and evaluator readiness.")
    print("- Once dev/test splits have enough labels, run the account-community evaluator scoreboard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
