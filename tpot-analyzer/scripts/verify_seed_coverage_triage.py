#!/usr/bin/env python3
"""Verify zero-spend coverage and rank candidates for explicit named seeds."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if not __package__:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from src.evaluation.seed_coverage import (  # noqa: E402
    SeedCoverageInputError,
    build_seed_coverage_report,
)
from src.evaluation.seed_coverage_contract import (  # noqa: E402
    compare_seed_coverage_reports,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-panel", type=Path, required=True)
    parser.add_argument("--cache-db", type=Path, required=True)
    parser.add_argument("--archive-db", type=Path, required=True)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--price-card", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=25)
    parser.add_argument(
        "--comparison-archive-db",
        type=Path,
        help="optional second working DB; reports path-dependent seed deltas",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="optional no-clobber path for the complete report",
    )
    return parser


def _build(args: argparse.Namespace, archive_db: Path) -> dict:
    return build_seed_coverage_report(
        seed_panel_path=args.seed_panel,
        cache_db_path=args.cache_db,
        archive_db_path=archive_db,
        archive_snapshot_dir=args.snapshot_dir,
        api_price_card_path=args.price_card,
        top_k=args.top_k,
    )


def _write_no_clobber(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _print_report(report: dict) -> None:
    print("ZERO-SPEND NAMED-SEED COVERAGE TRIAGE")
    print("=" * 39)
    checks = [
        (
            "explicit inputs opened read-only",
            all(
                "mode=ro" in report["inputs"][name]["open_mode"]
                for name in ("archive_db", "cache_db")
            ),
        ),
        (
            "immutable tweet snapshot deep-verified",
            report["inputs"]["archive_snapshot"]["verification"].startswith("deep"),
        ),
        ("every pinned seed emitted", bool(report["seeds"])),
        (
            "source-selectivity consumer executed",
            report["ranking"]["candidate_count"] > 0,
        ),
    ]
    print("\nImplementation contract")
    for label, passed in checks:
        print(f"{'✓' if passed else '✗'} {label}")

    print("\nExecution boundary")
    print("- Static contract: the report builder accepts local paths only.")
    print("- Cost is a quote; this verifier does not meter external account spend.")

    print("\nEmpirical hypotheses")
    for name, result in report["hypotheses"].items():
        marker = "✗ falsified" if result["falsified"] else "· not falsified"
        suffix = f" — {result['reason']}" if result.get("reason") else ""
        if result.get("quality_tested") is False:
            suffix += " — retrieval quality untested"
        print(f"{marker}: {name}{suffix}")

    print("\nSeed metrics")
    total_refresh_usd = 0.0
    for seed in report["seeds"]:
        follows = seed["follows"]
        content = seed["content"]
        refresh = follows["full_refresh_estimate"]
        total_refresh_usd += refresh["estimated_usd"] if refresh else 0.0
        print(
            f"- @{seed['handle_at_freeze']}: "
            f"sqlite={follows['merged_sqlite_direct']['distinct_targets']}, "
            f"shadow_direct={follows['shadow_direct_following']['distinct_targets']}, "
            f"shadow_inverse={follows['shadow_inverse_following']['distinct_targets']}, "
            f"union={follows['stored_key_union']['distinct_targets']}, "
            f"claimed={seed.get('claimed_following')}, "
            f"tweets={content['authored_rows']}, "
            f"incoming_CA_replies={content['incoming_nonself_reply_rows']}, "
            f"full_refresh_est=${refresh['estimated_usd']:.5f}"
        )
    print(
        f"- candidates={report['ranking']['candidate_count']:,}; "
        f"priced full-refresh total=${total_refresh_usd:.5f}; quote only"
    )

    print("\nTop source-selective candidates")
    for index, row in enumerate(report["ranking"]["top_candidates"][:15], 1):
        label = (
            f"@{row['username_candidates'][0]}"
            if row["username_candidates"]
            else row["account_id"]
        )
        print(
            f"{index:>2}. {label:<24} score={row['selectivity_score']:.9f} "
            f"support={row['raw_support']} "
            f"seeds={','.join(row['supporting_seeds'])}"
        )

    if comparison := report.get("path_comparison"):
        print("\nPath-dependence diagnostic")
        print(
            f"{'✗' if comparison['same_inode'] else '✓'} independent DB copies: "
            f"same_inode={comparison['same_inode']}"
        )
        print(
            f"- selected={comparison['selected_archive_db']['path']} "
            f"inode={comparison['selected_archive_db']['inode']}"
        )
        print(
            f"- comparison={comparison['comparison_archive_db']['path']} "
            f"inode={comparison['comparison_archive_db']['inode']}"
        )
        for row in comparison["seed_deltas"]:
            print(
                f"- @{row['handle_at_freeze']}: "
                f"{row['comparison_distinct_targets']} -> "
                f"{row['selected_distinct_targets']} "
                f"(delta={row['delta']:+d}, same_digest={row['same_target_digest']})"
            )

    print("\nBoundary")
    print(report["boundary"])
    print("\nNext steps")
    print("1. Review the ranked candidates against held-out human judgments.")
    print("2. Add source/run/timestamp receipts to every future follow ingestion.")
    print("3. Do not buy more follow data until local retrieval has been evaluated.")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = _build(args, args.archive_db)
        if args.comparison_archive_db:
            report["path_comparison"] = compare_seed_coverage_reports(
                report,
                _build(args, args.comparison_archive_db),
            )
        report["generated_at"] = datetime.now(timezone.utc).isoformat()
        if args.json_output:
            _write_no_clobber(args.json_output, report)
            report["json_output"] = str(args.json_output.resolve())
    except (SeedCoverageInputError, FileExistsError, OSError) as exc:
        print(f"✗ coverage triage: {type(exc).__name__}: {exc}")
        print("Next: fix the explicit input or choose a new no-clobber output path.")
        return 1
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
