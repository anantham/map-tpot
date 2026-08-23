#!/usr/bin/env python3
"""Verify the final Map TPOT repository consolidation and recovery boundary."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts._repository_consolidation_checks import (  # noqa: E402
    Report,
    verify_integration,
    verify_legacy,
    verify_recovery,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-pushed",
        action="store_true",
        help="require HEAD to equal the local origin/main tracking ref",
    )
    args = parser.parse_args()
    legacy = REPOSITORY_ROOT.with_name("Project 2 - Map TPOT")
    bundle = legacy.with_name(f"{legacy.name} - preservation") / (
        "2026-08-23/map-tpot-pre-integration-20260823.bundle"
    )

    report = Report()
    print("Repository Consolidation Verification")
    print("=" * 37)
    verify_integration(REPOSITORY_ROOT, report, args.require_pushed)
    verify_recovery(REPOSITORY_ROOT, legacy, bundle, report)
    verify_legacy(REPOSITORY_ROOT, legacy, report)

    print("\nMetrics")
    print(f"- checks_passed: {report.passed}")
    print(f"- checks_failed: {report.failed}")
    print(f"- warnings: {report.warnings}")
    for metric in report.metrics:
        print(f"- {metric}")
    print("\nNext steps")
    if report.failed:
        print("1. Stop: inspect the first failed invariant before pushing or pruning.")
    elif args.require_pushed:
        print("1. Consolidation is pushed; retain recovery refs until explicitly retired.")
    else:
        print("1. Fast-forward local main to this verified HEAD and push main.")
        print("2. Re-run with --require-pushed after refreshing origin/main.")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
