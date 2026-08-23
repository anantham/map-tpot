"""Evaluate frozen soft-membership assumptions with explicit falsifiers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.config import DEFAULT_DATA_DIR
from src.evaluation.frozen_membership import (
    evaluate_frozen_membership,
    strict_failures,
)


def write_json_no_clobber(path: Path, report: dict) -> None:
    """Write a result once so later experiments cannot overwrite evidence."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(payload)


def _print_report(report: dict) -> None:
    heldout = report["heldout"]
    core = report["core_halo"]
    taxonomy = report["taxonomy_split_all"]
    print(
        "✓ Propagation-heldout discrimination measured: "
        f"top-1={heldout['top1_correct']}/{heldout['n_holdout']} "
        f"({heldout['top1_accuracy']:.3f}), "
        f"top-3={heldout['top3_correct']}/{heldout['n_holdout']} "
        f"({heldout['top3_accuracy']:.3f}), "
        f"zero-community rows={heldout['zero_community_rows']}"
    )
    model = heldout["model"]
    prior = heldout["empirical_prior"]
    uniform = heldout["uniform"]
    print(
        "✓ Soft-label probability scores measured: "
        f"model Brier={model['brier']:.6f}, "
        f"prior Brier={prior['brier']:.6f}, "
        f"uniform Brier={uniform['brier']:.6f}, "
        f"model log loss={model['soft_log_loss']:.6f}, "
        f"prior log loss={prior['soft_log_loss']:.6f}, "
        f"uniform log loss={uniform['soft_log_loss']:.6f}, "
        f"ECE-5={heldout['ece_5_equal_width']:.6f}"
    )
    print(
        "✓ Calibration-set core/halo behavior measured: "
        f"core={core['core']:,}, halo={core['halo']:,}, "
        f"selected={core['total']:,}; holdout core={core['holdout_core']}, "
        f"halo-only={core['holdout_halo_only']}, "
        f"missed={core['holdout_missed']}"
    )
    print(
        "✓ Taxonomy split-all sensitivity measured: "
        f"core={taxonomy['baseline_core']:,}→{taxonomy['split_core']:,}, "
        f"core Jaccard={taxonomy['core_jaccard']:.6f}, "
        f"selected={taxonomy['baseline_selected']:,}→"
        f"{taxonomy['split_selected']:,}, "
        f"selected Jaccard={taxonomy['selected_jaccard']:.6f}"
    )
    for row in report["edge_loss"].values():
        print(
            f"✓ Edge-loss {row['fraction']:.0%}: "
            f"minimum selected Jaccard={row['min_selected_jaccard']:.6f} "
            f"(floor={row['jaccard_floor']:.2f}), "
            f"selected range={row['selected_count_range']}"
        )
    for name, hypothesis in report["hypotheses"].items():
        mark = "✓" if hypothesis["passed"] else "✗"
        verdict = "SUPPORTED" if hypothesis["passed"] else "FALSIFIED"
        print(f"{mark} {name}: {verdict}")
        print(f"  Falsifier: {hypothesis['falsifier']}")


def evaluate(
    data_dir: Path,
    *,
    json_output: Path | None = None,
    strict: bool = False,
    edge_repetitions: int = 10,
) -> int:
    """Complete the experiment; strict mode additionally enforces hypotheses."""
    print("Frozen soft-membership evaluation")
    print(f"Data directory: {Path(data_dir).resolve()}")
    try:
        report = evaluate_frozen_membership(
            data_dir, edge_repetitions=edge_repetitions
        )
        if json_output is not None:
            write_json_no_clobber(json_output, report)
            print(f"✓ Wrote no-clobber JSON result: {json_output.resolve()}")
    except Exception as exc:
        print(f"✗ Evaluation failed: {type(exc).__name__}: {exc}")
        print(
            "Next step: inspect the named frozen input or validation error; "
            "do not weaken the identity or leakage gates."
        )
        return 1

    _print_report(report)
    failures = strict_failures(report)
    print("✓ Experiment completed; falsification is evidence, not a run failure.")
    if strict and failures:
        print("✗ Strict mode rejected: " + ", ".join(failures))
        return 2
    if failures:
        print("Next step: investigate the falsified assumptions before redesign.")
    else:
        print("Next step: replicate on a fresh temporal snapshot.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate frozen soft-membership assumptions"
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--edge-repetitions", type=int, default=10)
    args = parser.parse_args()
    raise SystemExit(
        evaluate(
            args.data_dir,
            json_output=args.json_output,
            strict=args.strict,
            edge_repetitions=args.edge_repetitions,
        )
    )


if __name__ == "__main__":
    main()
