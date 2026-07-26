#!/usr/bin/env python3
"""Verify that code and optional working data are ready for assumption tests.

The verifier is deliberately read-only: SQLite databases are opened with
``mode=ro&immutable=1`` and it never creates artifacts. Use ``--require-data``
after copying an immutable source baseline into this checkout.

Test intent: this recurring CLI contract has regression coverage for invalid
certification options, required artifact sets, and empty archive handling in
``tests/test_verify_assumption_baseline.py``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts._assumption_baseline_checks import (  # noqa: E402
    Report,
    inspect_git,
    inspect_toolchain,
)
from scripts._assumption_baseline_data import inspect_data  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--source-data-dir", type=Path)
    parser.add_argument("--require-data", action="store_true")
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument("--hash-data", action="store_true")
    parser.add_argument(
        "--deep",
        action="store_true",
        help="run SQLite quick_check in addition to schema/count probes",
    )
    args = parser.parse_args()
    if args.hash_data and args.source_data_dir is None:
        parser.error("--hash-data requires --source-data-dir")
    if (args.source_data_dir is not None or args.deep) and not args.require_data:
        parser.error("--source-data-dir and --deep require --require-data")

    report = Report()
    print("Assumption-Test Baseline Verification")
    print("=" * 37)
    inspect_git(PROJECT_ROOT, report, args.require_clean)
    inspect_toolchain(PROJECT_ROOT, report)
    inspect_data(
        args.data_dir.resolve(),
        args.source_data_dir.resolve() if args.source_data_dir else None,
        report,
        args.require_data,
        args.hash_data,
        args.deep,
    )

    print("\nMetrics")
    print(f"- checks_passed: {report.passed}")
    print(f"- checks_failed: {report.failed}")
    print(f"- warnings: {report.warnings}")
    for metric in report.metrics:
        print(f"- {metric}")

    print("\nNext steps")
    if report.failed:
        print("1. Resolve failed checks before treating an experiment as reproducible.")
    elif report.warnings:
        print("1. Review runtime/data freshness warnings and record accepted drift.")
    else:
        print("1. Record the command and metrics with the experiment.")
    print("2. Run `make verify-baseline` and `make test-ci` before method changes.")
    print(
        "3. Certify with `--require-data --source-data-dir PATH "
        "--hash-data --deep`."
    )
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
