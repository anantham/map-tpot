#!/usr/bin/env python3
"""Verify a local Community Archive snapshot and print human-readable evidence."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.archive.snapshot_contract import DATA_FILENAME, MANIFEST_FILENAME  # noqa: E402
from src.archive.snapshot_manifest import (  # noqa: E402
    inspect_enriched_tweets_parquet,
    verify_local_snapshot,
)


def _print_metrics(metrics: dict[str, object]) -> None:
    print("\nMetrics")
    if not metrics:
        print("- unavailable")
        return
    for name, value in metrics.items():
        rendered = f"{value:,}" if isinstance(value, int) else value
        print(f"- {name}: {rendered}")


def _inspect_dataset(snapshot_dir: Path) -> tuple[bool, str]:
    manifest_path = snapshot_dir / MANIFEST_FILENAME
    data_path = snapshot_dir / DATA_FILENAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = manifest["dataset"]
        observed = inspect_enriched_tweets_parquet(data_path)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    differing = {
        key: (expected.get(key), value)
        for key, value in observed.items()
        if expected.get(key) != value
    }
    if differing:
        return False, f"manifest differs from Parquet inspection: {differing}"
    return True, (
        f"rows={observed['row_count']:,}, accounts={observed['account_count']:,}, "
        f"latest={observed['created_at_max']}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="skip SHA-256 recomputation",
    )
    parser.add_argument(
        "--inspect-parquet",
        action="store_true",
        help="rescan Parquet rows, accounts, cutoffs, and upload linkage",
    )
    args = parser.parse_args(argv)

    snapshot_dir = args.snapshot_dir.resolve()
    print("Community Archive Snapshot Verification")
    print("=" * 39)
    checks, metrics = verify_local_snapshot(snapshot_dir, deep=not args.quick)
    failed = False
    for check in checks:
        marker = "✓" if check.passed else "✗"
        print(f"{marker} {check.name}: {check.detail}")
        failed = failed or not check.passed

    if args.inspect_parquet and not failed:
        passed, detail = _inspect_dataset(snapshot_dir)
        marker = "✓" if passed else "✗"
        print(f"{marker} Parquet dataset inspection: {detail}")
        failed = failed or not passed

    _print_metrics(metrics)
    print("\nNext steps")
    if failed:
        print("1. Do not use this snapshot as research evidence.")
        print("2. Resolve the failed check or acquire a new immutable snapshot.")
    else:
        if args.quick:
            print("1. Re-run without --quick before evidence-grade use.")
        elif not args.inspect_parquet:
            print("1. Add --inspect-parquet to recheck dataset-level metrics.")
        else:
            print("1. Snapshot is ready to bind to a downstream artifact manifest.")
        print("2. Preserve the snapshot ID and SHA-256 in the experiment log.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
