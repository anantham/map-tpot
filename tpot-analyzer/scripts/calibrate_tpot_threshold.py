"""Calibrate TPOT relevance threshold τ on holdout seeds.

Loads train-only propagation + holdout seed IDs, computes the per-node
relevance score r_i, and sweeps τ to maximize TPOT-vs-none F1 with a
recall floor (default ≥85%).

Usage:
    # Step 1: Run propagation with holdout
    .venv/bin/python3 -m scripts.propagate_community_labels --save --holdout-fraction 0.2

    # Step 2: Calibrate threshold
    .venv/bin/python3 -m scripts.calibrate_tpot_threshold
"""
from __future__ import annotations

import argparse
import json
import pickle  # NOTE: only used to load our own cached adjacency matrix, not untrusted data
from pathlib import Path

import numpy as np
import scipy.sparse as sp

from src.graph.tpot_relevance import build_core_halo_mask, compute_relevance

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def load_adjacency(path: Path) -> sp.csr_matrix:
    """Load cached adjacency matrix (our own precomputed data, not untrusted)."""
    with open(path, "rb") as f:
        cached = pickle.load(f)
    if isinstance(cached, dict) and "adjacency" in cached:
        return cached["adjacency"].tocsr()
    return cached.tocsr()


def compute_degrees(adjacency: sp.csr_matrix) -> np.ndarray:
    """Compute symmetrized degree per node."""
    sym = adjacency.maximum(adjacency.T).tocsr()
    return np.asarray(sym.sum(axis=1)).flatten()


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate TPOT relevance threshold τ")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--recall-floor", type=float, default=0.85,
                        help="Minimum recall on holdout TPOT seeds (default: 0.85)")
    parser.add_argument("--tau-min", type=float, default=0.001)
    parser.add_argument("--tau-max", type=float, default=0.5)
    parser.add_argument("--tau-steps", type=int, default=100)
    args = parser.parse_args()

    data_dir = args.data_dir

    # --- Load train-only propagation ---
    train_path = data_dir / "community_propagation_train.npz"
    if not train_path.exists():
        # Fall back to production propagation (no holdout)
        train_path = data_dir / "community_propagation.npz"
        print(f"WARNING: No train-only propagation found, using {train_path}")
        print("         Run with --holdout-fraction 0.2 first for proper calibration")

    print(f"Loading propagation: {train_path}")
    prop = np.load(str(train_path), allow_pickle=True)
    memberships = prop["memberships"]
    uncertainty = prop["uncertainty"]
    converged = prop["converged"]
    node_ids = prop["node_ids"]
    n_nodes = len(node_ids)
    node_id_to_idx = {str(nid): i for i, nid in enumerate(node_ids)}

    K = memberships.shape[1] - 1
    print(f"Nodes: {n_nodes:,}, Communities: {K}")

    # --- Load adjacency for degree computation ---
    adj_path = data_dir / "adjacency_matrix_cache.pkl"
    print(f"Loading adjacency: {adj_path}")
    adjacency = load_adjacency(adj_path)
    degrees = compute_degrees(adjacency)
    median_deg = float(np.median(degrees[degrees > 0]))
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
        print("\nWARNING: No holdout seeds found. Cannot calibrate threshold.")
        print("Run: .venv/bin/python3 -m scripts.propagate_community_labels --save --holdout-fraction 0.2")
        # Still save uncalibrated results with a default threshold
        _save_calibration(data_dir, r, adjacency, n_nodes, default_tau=0.05, calibrated=False)
        return

    holdout = json.loads(holdout_path.read_text())
    holdout_accounts = holdout["accounts"]
    n_holdout = holdout["n_holdout"]
    print(f"\nHoldout: {n_holdout} seeds from {holdout_path}")

    # Resolve holdout seeds to indices + ground truth
    holdout_indices = []
    for aid in holdout_accounts:
        idx = node_id_to_idx.get(str(aid))
        if idx is not None:
            holdout_indices.append(idx)

    n_resolved = len(holdout_indices)
    print(f"Holdout resolved to graph: {n_resolved}/{n_holdout}")

    if n_resolved == 0:
        print("ERROR: No holdout seeds found in graph. Aborting.")
        return

    # --- Threshold sweep ---
    print(f"\n=== Threshold Calibration (recall floor >= {args.recall_floor:.0%}) ===")
    print(f"{'tau':>8s} {'core':>8s} {'halo':>8s} {'total':>8s} {'holdout_recall':>15s} {'F1':>8s}")
    print("-" * 65)

    taus = np.linspace(args.tau_min, args.tau_max, args.tau_steps)
    best_tau = taus[0]
    best_f1 = 0.0
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

        # F-score using recall and compactness (1 - fraction_of_graph)
        # This rewards both high recall and small subgraph size
        compactness = 1.0 - (n_total / n_nodes)
        if recall + compactness > 0:
            f1 = 2.0 * (compactness * recall) / (compactness + recall)
        else:
            f1 = 0.0

        results.append({
            "tau": float(tau),
            "n_core": int(n_core),
            "n_halo": int(n_halo),
            "n_total": int(n_total),
            "recall": float(recall),
            "compactness": float(compactness),
            "f1": float(f1),
        })

        # Check if this meets recall floor and improves F1
        if recall >= args.recall_floor and f1 > best_f1:
            best_f1 = f1
            best_tau = tau

        # Print selected rows (every 5th step)
        if tau in taus[::max(1, len(taus) // 20)] or abs(tau - best_tau) < 1e-6:
            print(f"{tau:8.4f} {n_core:8,} {n_halo:8,} {n_total:8,} {recall:15.3f} {f1:8.4f}")

    print("-" * 65)
    print(f"\n** Best tau = {best_tau:.4f} (F1={best_f1:.4f}) **")

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
    _save_calibration(data_dir, r, adjacency, n_nodes, default_tau=best_tau, calibrated=True, results=results)


def _save_calibration(
    data_dir: Path,
    r: np.ndarray,
    adjacency: sp.csr_matrix,
    n_nodes: int,
    default_tau: float,
    calibrated: bool,
    results: list | None = None,
) -> None:
    """Save calibration output."""
    # Save relevance scores
    r_path = data_dir / "tpot_relevance_scores.npy"
    np.save(str(r_path), r.astype(np.float32))
    print(f"\nSaved relevance scores: {r_path}")

    # Save calibration JSON
    mask = build_core_halo_mask(r, adjacency, default_tau)
    cal = {
        "tau": float(default_tau),
        "calibrated": calibrated,
        "n_nodes_total": int(n_nodes),
        "n_core": int((r >= default_tau).sum()),
        "n_halo": int(mask.sum() - (r >= default_tau).sum()),
        "n_total": int(mask.sum()),
    }
    if results:
        cal["sweep"] = results

    cal_path = data_dir / "tpot_calibration.json"
    cal_path.write_text(json.dumps(cal, indent=2))
    print(f"Saved calibration: {cal_path}")


if __name__ == "__main__":
    main()
