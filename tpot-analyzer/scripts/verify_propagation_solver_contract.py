"""Print bounded, falsifiable propagation solver-contract measurements."""
from __future__ import annotations

import argparse
from pathlib import Path

from src.config import DEFAULT_DATA_DIR
from src.evaluation.solver_contract import measure_solver_contract


def _format_metrics(metrics: dict[str, object]) -> str:
    return ", ".join(f"{key}={value}" for key, value in metrics.items())


def verify(data_dir: Path, *, require_valid_contract: bool = False) -> int:
    """Measure the contract; optionally require every hypothesis to survive."""
    print("Propagation solver contract verification")
    print(f"Data directory: {Path(data_dir).resolve()}")
    print(
        "Exit policy: measurement failures always fail; rejected scientific "
        "hypotheses fail only with --require-valid-contract."
    )
    try:
        report = measure_solver_contract(data_dir)
    except Exception as exc:
        print(
            "✗ Solver-contract measurement failed: "
            f"{type(exc).__name__}: {exc}"
        )
        print(
            "Next step: restore the hash-pinned inputs or inspect the named "
            "probe before interpreting solver validity."
        )
        return 1

    for check in report.checks:
        mark = "✓" if check.accepted else "✗"
        verdict = "survived" if check.accepted else "rejected"
        print(f"\n{mark} {check.name}: hypothesis {verdict}")
        print(f"  Hypothesis: {check.hypothesis}")
        print(f"  Falsifier: {check.falsifier}")
        print(f"  Observed: {_format_metrics(check.metrics)}")

    print(
        f"\n✓ Measurement completed: bundle_id={report.bundle_id}, "
        f"checks={len(report.checks)}"
    )
    if report.valid_contract:
        print("✓ Solver validity contract survived every bounded falsifier.")
        print(
            "Next step: run the versioned full per-class convergence "
            "experiment before treating memberships as calibrated."
        )
        return 0

    print(
        "✗ Solver validity contract rejected by one or more bounded probes. "
        "Reproducibility does not establish valid soft memberships."
    )
    if require_valid_contract:
        print("Strict validity mode requested; returning scientific rejection.")
        return 2
    print(
        "Measurement-only mode: returning success because all diagnostics "
        "completed and rejection is the recorded scientific result."
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure propagation solver assumptions and falsifiers"
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--require-valid-contract",
        action="store_true",
        help="Fail when any measured solver-validity hypothesis is rejected",
    )
    args = parser.parse_args()
    raise SystemExit(
        verify(
            args.data_dir,
            require_valid_contract=args.require_valid_contract,
        )
    )


if __name__ == "__main__":
    main()
