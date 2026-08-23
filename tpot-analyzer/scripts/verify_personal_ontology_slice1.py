#!/usr/bin/env python3
"""Verify Slice 1 integrity on synthetic local data only."""
from __future__ import annotations

import tempfile
import sys
from pathlib import Path

if not __package__:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

if __package__:
    from scripts._personal_ontology_slice1_checks import run_verification
else:
    from _personal_ontology_slice1_checks import run_verification


def main() -> int:
    print("Personal-Ontology Slice 1 Verification")
    print("=" * 46)
    try:
        with tempfile.TemporaryDirectory(
            prefix="tpot-personal-ontology-slice1-"
        ) as temp_dir:
            checks, metrics = run_verification(
                Path(temp_dir) / "synthetic.db"
            )
    except Exception as exc:
        print(f"✗ Verifier execution: {type(exc).__name__}: {exc}")
        print("Next steps:")
        print("1. Inspect the named schema or integrity failure.")
        print("2. Re-run before using any real labels or paid data.")
        return 1

    for check in checks:
        print(f"{'✓' if check.passed else '✗'} {check.name}: {check.detail}")
    failures = [check for check in checks if not check.passed]
    print("-" * 46)
    print(
        f"Checks: {len(checks)} | "
        f"Passed: {len(checks) - len(failures)} | Failed: {len(failures)}"
    )
    print(
        "Metrics: "
        f"roles={metrics['roleCounts']}, "
        "min_nominal_terminal_pi="
        f"{metrics['minimumNominalTerminalInclusionProbability']:.6f}"
    )
    print(
        "Digests: "
        f"frame={metrics['frameDigest'][:12]}…, "
        f"roles={metrics['roleDigest'][:12]}…, "
        f"release={metrics['releaseManifestHash'][:12]}…"
    )
    print("Next steps:")
    if failures:
        print("1. Repair the failed synthetic integrity contract.")
        print("2. Do not migrate real labels or open a terminal test.")
        return 1
    print("1. Review the frozen role quotas before creating a real frame.")
    print("2. Keep network/API/model spend blocked until later slice gates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
