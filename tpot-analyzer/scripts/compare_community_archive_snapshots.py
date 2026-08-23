#!/usr/bin/env python3
"""Compare two immutable Community Archive snapshots."""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from src.archive.snapshot_comparison import (
    compare_snapshot_directories,
    write_json_no_clobber,
)


def _integer_delta(value: int) -> str:
    return f"{value:+,}"


def _print_summary(label: str, summary: dict[str, object]) -> None:
    print(
        f"✓ {label}: {summary['snapshot_id']} | "
        f"rows={summary['row_count']:,} | accounts={summary['account_count']:,} | "
        f"latest={summary['created_at_max']}"
    )
    samples = summary["sample_rows"]
    if samples:
        rendered = ", ".join(
            f"tweet={row.get('tweet_id')} account={row.get('account_id')}"
            for row in samples
        )
        print(f"  Samples: {rendered}")


def compare(
    baseline_dir: Path,
    candidate_dir: Path,
    *,
    quick: bool = False,
    strict: bool = False,
    json_output: Path | None = None,
) -> int:
    print("Community Archive Snapshot Comparison")
    print("=" * 37)
    try:
        result = compare_snapshot_directories(
            baseline_dir,
            candidate_dir,
            deep=not quick,
        )
        if json_output is not None:
            write_json_no_clobber(json_output, result)
            print(f"✓ result JSON: {json_output.resolve()}")
    except Exception as exc:
        print(f"✗ comparison failed: {type(exc).__name__}: {exc}")
        print("\nNext steps")
        print("1. Repair or reacquire the failed immutable snapshot.")
        print("2. Do not weaken its manifest or hash checks.")
        return 1

    _print_summary("baseline verified", result["baseline"])
    _print_summary("candidate verified", result["candidate"])
    delta = result["deltas"]
    print("\nMetrics")
    print(f"- rows: {_integer_delta(delta['row_count'])}")
    print(f"- accounts: {_integer_delta(delta['account_count'])}")
    print(
        "- archive-linked rows: "
        f"{_integer_delta(delta['archive_upload_linked_rows'])}"
    )
    print(
        "- missing archive-upload IDs: "
        f"{_integer_delta(delta['archive_upload_id_missing_rows'])}"
    )
    print(f"- bytes: {_integer_delta(delta['size_bytes'])}")
    print(f"- newest-tweet advance: {delta['created_at_max_seconds']:+.0f}s")
    print(
        "- archive-linked fraction: "
        f"{delta['archive_linked_fraction']:+.6f}"
    )

    print("\nHypotheses")
    failures = []
    for name, hypothesis in result["hypotheses"].items():
        passed = hypothesis["passed"]
        marker = "✓" if passed else "✗"
        verdict = "supported" if passed else "falsified"
        print(f"{marker} {name}: {verdict}")
        print(f"  Falsifier: {hypothesis['falsifier']}")
        if not passed:
            failures.append(name)

    print("\n✓ Measurement completed; falsification is evidence, not script failure.")
    print("\nNext steps")
    print("1. Bind the candidate snapshot ID and SHA-256 to downstream experiments.")
    if failures:
        print("2. Preserve falsified hypotheses in docs/EXPERIMENT_LOG.md.")
    else:
        print("2. Re-probe before the next downstream corpus build.")
    if quick:
        print("3. Re-run without --quick before evidence-grade use.")
    if strict and failures:
        print(f"✗ strict mode: {len(failures)} hypothesis check(s) failed.")
        return 2
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline_dir", type=Path)
    parser.add_argument("candidate_dir", type=Path)
    parser.add_argument("--quick", action="store_true", help="skip SHA-256 rescans")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args(argv)
    return compare(
        args.baseline_dir,
        args.candidate_dir,
        quick=args.quick,
        strict=args.strict,
        json_output=args.json_output,
    )


if __name__ == "__main__":
    raise SystemExit(main())
