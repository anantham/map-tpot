"""Choose TPOT relevance threshold τ on held-out positive seeds.

Loads train-only propagation + holdout seed IDs, computes the per-node
relevance score r_i, and sweeps τ to maximize the harmonic mean of holdout
recall and graph compactness with a recall floor (default ≥85%). This is not a
positive-vs-negative classification F1 because the split has no negatives.

Usage:
    # Calibrate an already versioned train-only propagation + holdout pair:
    .venv/bin/python3 -m scripts.calibrate_tpot_threshold \
        --output-dir data/generations/calibration-EXPERIMENT_ID

The legacy propagation CLI overwrites flat artifacts. Upgrade it to versioned
output before using it to regenerate calibration inputs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from src.artifacts.calibration_method import (
    select_best_feasible_result,
    validate_holdout_split,
)
from src.artifacts.calibration_output import save_calibration_outputs
from src.artifacts.calibration_record import build_calibration_method_record
from src.artifacts.tpot_inputs import load_bound_tpot_inputs
from src.config import DEFAULT_DATA_DIR
from src.graph.tpot_relevance import (
    build_core_halo_mask,
    compute_relevance,
    compute_symmetrized_degree_stats,
)

DATA_DIR = DEFAULT_DATA_DIR
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate TPOT relevance threshold τ")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--recall-floor", type=float, default=0.85,
                        help="Minimum recall on holdout TPOT seeds (default: 0.85)")
    parser.add_argument("--tau-min", type=float, default=0.001)
    parser.add_argument("--tau-max", type=float, default=0.5)
    parser.add_argument("--tau-steps", type=int, default=100)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="New output directory (defaults to --data-dir; never overwrites)",
    )
    args = parser.parse_args()

    data_dir = args.data_dir
    output_dir = args.output_dir or data_dir
    existing_outputs = [
        output_dir / name
        for name in ("tpot_relevance_scores.npy", "tpot_calibration.json")
        if (output_dir / name).exists()
    ]
    if existing_outputs:
        raise FileExistsError(
            "Refusing to replace existing calibration outputs; choose a new "
            f"--output-dir. Existing={existing_outputs}"
        )

    # --- Load train-only propagation ---
    train_path = data_dir / "community_propagation_train.npz"
    if not train_path.exists():
        raise FileNotFoundError(
            f"Train-only propagation is required: {train_path}. Generate it "
            "from this exact spectral graph with a held-out split in a new "
            "versioned workspace; production propagation would leak labels."
        )

    print(f"Loading graph, adjacency, and propagation: {data_dir}")
    inputs = load_bound_tpot_inputs(
        data_dir,
        ["community_propagation_train.npz"],
    )
    adjacency = inputs.adjacency
    binding = inputs.binding
    propagation = inputs.propagation
    print(
        "Verified adjacency binding: "
        f"nodes={binding.node_count:,}, edges={binding.edge_row_count:,}, "
        f"nnz={binding.adjacency_nnz:,}, ignored={binding.ignored_edge_count:,}"
    )
    for evaluation in propagation.evaluations:
        print(f"Propagation candidate {evaluation.path}: {evaluation.reason}")
    artifact_provenance = inputs.provenance
    memberships = propagation.arrays["memberships"]
    uncertainty = propagation.arrays["uncertainty"]
    converged = propagation.arrays["converged"]
    if "labeled_mask" not in propagation.arrays:
        raise ValueError(
            f"train propagation lacks labeled_mask required for leakage checks: "
            f"{train_path}"
        )
    labeled_mask = propagation.arrays["labeled_mask"]
    node_ids = propagation.graph_node_ids
    n_nodes = len(node_ids)
    node_id_to_idx = {str(nid): i for i, nid in enumerate(node_ids)}

    K = memberships.shape[1] - 1
    print(f"Nodes: {n_nodes:,}, Communities: {K}")

    # --- Load adjacency for degree computation ---
    _, degrees, median_deg = compute_symmetrized_degree_stats(adjacency)
    print(f"Median degree (nonzero): {median_deg:.1f}")

    # --- Compute relevance scores ---
    print("\nComputing relevance scores...")
    r = compute_relevance(memberships, uncertainty, converged, degrees, median_deg)

    # --- Distribution histogram (sanity check) ---
    print("\n=== Relevance Score Distribution ===")
    thresholds_for_hist = [0.001, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5]
    for t in thresholds_for_hist:
        count = (r >= t).sum()
        pct = 100.0 * count / n_nodes
        print(f"  r >= {t:.3f}: {count:6,} nodes ({pct:5.1f}%)")

    # Percentile distribution
    print("\n  Percentiles (nonzero r only):")
    r_nonzero = r[r > 0]
    if len(r_nonzero) > 0:
        for p in [10, 25, 50, 75, 90, 95, 99]:
            val = np.percentile(r_nonzero, p)
            print(f"    P{p:2d}: {val:.4f}")
    print(f"  Zero-r nodes: {(r == 0).sum():,} ({100.0 * (r == 0).sum() / n_nodes:.1f}%)")

    # --- Load holdout seeds ---
    holdout_path = data_dir / "tpot_holdout_seeds.json"
    if not holdout_path.exists():
        raise FileNotFoundError(
            f"Holdout split is required: {holdout_path}. Generate it together "
            "with the train-only propagation from this exact spectral graph "
            "in a new versioned workspace."
        )

    holdout = json.loads(holdout_path.read_text())
    n_holdout = holdout["n_holdout"]
    print(f"\nHoldout: {n_holdout} seeds from {holdout_path}")

    holdout_indices = validate_holdout_split(
        holdout,
        node_id_to_idx,
        labeled_mask,
    )
    n_resolved = len(holdout_indices)
    print(f"Holdout resolved to graph: {n_resolved}/{n_holdout}")

    # --- Threshold sweep ---
    print(f"\n=== Threshold Calibration (recall floor >= {args.recall_floor:.0%}) ===")
    print(f"{'tau':>8s} {'core':>8s} {'halo':>8s} {'total':>8s} {'holdout_recall':>15s} {'utility':>8s}")
    print("-" * 65)

    taus = np.linspace(args.tau_min, args.tau_max, args.tau_steps)
    results = []

    for tau in taus:
        # Core + halo
        mask = build_core_halo_mask(r, adjacency, tau)
        n_total = mask.sum()
        n_core = (r >= tau).sum()
        n_halo = n_total - n_core

        # Holdout recall: what fraction of holdout TPOT seeds are in the mask?
        holdout_in_mask = sum(1 for idx in holdout_indices if mask[idx])
        recall = holdout_in_mask / n_resolved if n_resolved > 0 else 0.0

        # Harmonic utility using recall and compactness (1 - graph fraction).
        # This is not classification F1 because there are no held-out negatives.
        compactness = 1.0 - (n_total / n_nodes)
        if recall + compactness > 0:
            objective_score = (
                2.0 * (compactness * recall) / (compactness + recall)
            )
        else:
            objective_score = 0.0

        results.append({
            "tau": float(tau),
            "n_core": int(n_core),
            "n_halo": int(n_halo),
            "n_total": int(n_total),
            "recall": float(recall),
            "compactness": float(compactness),
            "objective_score": float(objective_score),
        })

        # Print selected rows (every 5th step)
        if tau in taus[::max(1, len(taus) // 20)]:
            print(f"{tau:8.4f} {n_core:8,} {n_halo:8,} {n_total:8,} {recall:15.3f} {objective_score:8.4f}")

    best = select_best_feasible_result(results, args.recall_floor)
    best_tau = best["tau"]
    best_score = best["objective_score"]
    print("-" * 65)
    print(f"\n** Best tau = {best_tau:.4f} (utility={best_score:.4f}) **")

    # Print stats for best threshold
    best_mask = build_core_halo_mask(r, adjacency, best_tau)
    best_core = (r >= best_tau).sum()
    best_total = best_mask.sum()
    best_recall = sum(1 for idx in holdout_indices if best_mask[idx]) / n_resolved

    print(f"   Core:    {best_core:,} nodes")
    print(f"   Halo:    {best_total - best_core:,} nodes")
    print(f"   Total:   {best_total:,} nodes ({100.0 * best_total / n_nodes:.1f}% of graph)")
    print(f"   Recall:  {best_recall:.3f} ({sum(1 for idx in holdout_indices if best_mask[idx])}/{n_resolved} holdout seeds)")

    # --- Save calibration ---
    record = save_calibration_outputs(
        output_dir,
        r,
        adjacency,
        tau=best_tau,
        artifact_provenance=artifact_provenance,
        calibration_method=build_calibration_method_record(
            recall_floor=args.recall_floor,
            tau_min=args.tau_min,
            tau_max=args.tau_max,
            tau_steps=args.tau_steps,
            holdout=holdout,
            holdout_path=holdout_path,
            code_files={
                "relevance_scorer": PROJECT_ROOT / "src/graph/tpot_relevance.py",
                "threshold_selector": (
                    PROJECT_ROOT / "src/artifacts/calibration_method.py"
                ),
                "calibrator": Path(__file__).resolve(),
            },
        ),
        results=results,
    )
    print(f"\nSaved relevance scores: {output_dir / 'tpot_relevance_scores.npy'}")
    print(f"Saved calibration: {output_dir / 'tpot_calibration.json'}")
    print(
        "Saved counts: "
        f"core={record['n_core']:,}, halo={record['n_halo']:,}, "
        f"total={record['n_total']:,}"
    )


if __name__ == "__main__":
    main()
