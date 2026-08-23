"""Build spectral embedding for the TPOT-focused subgraph.

Loads propagation + calibrated threshold, computes relevance scores,
builds core+halo subgraph with reweighted adjacency W' = D_r^{1/2} W D_r^{1/2},
then runs spectral embedding on the filtered+reweighted graph.

Usage:
    # After calibration:
    .venv/bin/python3 -m scripts.build_tpot_spectral \
        --output-prefix data/generations/graph_snapshot_tpot-EXPERIMENT_ID

Existing bundles are never overwritten; atomic publication remains a separate
required step.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path

import numpy as np

from src.artifacts.output_reservation import reserve_new_outputs
from src.artifacts.frozen_manifest import (
    MANIFEST_RELATIVE_PATH,
    expected_frozen_file_sha256,
)
from src.artifacts.provenance import (
    CalibrationCompatibilityError,
)
from src.artifacts.relevance_binding import validate_saved_relevance
from src.artifacts.selection_binding import validate_selection_mapping
from src.artifacts.tpot_bundle_output import save_tpot_bundle_sidecars
from src.artifacts.tpot_calibration import load_bound_threshold
from src.artifacts.tpot_inputs import load_bound_tpot_inputs
from src.config import DEFAULT_DATA_DIR
from src.graph.spectral import SpectralConfig, compute_spectral_embedding, save_spectral_result
from src.graph.tpot_relevance import (
    build_core_halo_mask,
    compute_relevance,
    compute_symmetrized_degree_stats,
    reweight_adjacency,
)

DATA_DIR = DEFAULT_DATA_DIR
PROJECT_ROOT = Path(__file__).resolve().parents[1]

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build TPOT-focused spectral embedding")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--tau", type=float, default=None,
                        help="Relevance threshold (default: from tpot_calibration.json)")
    parser.add_argument(
        "--calibration-path",
        type=Path,
        default=None,
        help="Calibration JSON to use instead of DATA_DIR/tpot_calibration.json",
    )
    parser.add_argument("--n-dims", type=int, default=30)
    parser.add_argument("--maxiter", type=int, default=5000)
    parser.add_argument("--tol", type=float, default=1e-10)
    parser.add_argument("--birch-threshold", type=float, default=0.3)
    parser.add_argument("--max-linkage-nodes", type=int, default=12000)
    parser.add_argument("--output-prefix", type=Path, default=None,
                        help="New, non-existing output prefix")
    args = parser.parse_args()
    if args.tau is not None and args.calibration_path is not None:
        raise ValueError("Use either --tau or --calibration-path, not both")
    if args.tau is not None and (
        not math.isfinite(args.tau) or not 0.0 <= args.tau <= 1.0
    ):
        raise ValueError(f"--tau must be finite and in [0, 1]; got {args.tau!r}")

    data_dir = args.data_dir
    out_prefix = args.output_prefix or (data_dir / "graph_snapshot_tpot")
    output_paths = [
        Path(out_prefix).with_suffix(".spectral.npz"),
        Path(out_prefix).with_suffix(".spectral_meta.json"),
        Path(str(out_prefix) + ".mapping.json"),
        Path(str(out_prefix) + ".nodes.parquet"),
        Path(str(out_prefix) + ".edges.parquet"),
    ]
    lock_path = Path(str(out_prefix) + ".build.lock")
    with reserve_new_outputs(output_paths, lock_path):
        _build(args, data_dir, out_prefix)


def _build(args, data_dir: Path, out_prefix: Path) -> None:
    """Build one new, reserved but not atomically published TPOT bundle."""

    # --- Load and bind the authoritative graph + propagation ---
    frozen_manifest_path = data_dir / MANIFEST_RELATIVE_PATH
    legacy_mode_hash = (
        expected_frozen_file_sha256(
            data_dir,
            "community_propagation_train.npz",
        )
        if frozen_manifest_path.exists()
        else None
    )
    inputs = load_bound_tpot_inputs(
        data_dir,
        [
            "community_propagation.npz",
            "community_propagation_train.npz",
        ],
        legacy_undeclared_mode_sha256=legacy_mode_hash,
    )
    nodes_full = inputs.nodes
    edges_full = inputs.edges
    adjacency = inputs.adjacency
    binding = inputs.binding
    logger.info(
        "Verified adjacency binding: nodes=%d edges=%d nnz=%d ignored=%d",
        binding.node_count,
        binding.edge_row_count,
        binding.adjacency_nnz,
        binding.ignored_edge_count,
    )

    propagation = inputs.propagation
    for evaluation in propagation.evaluations:
        logger.info("Propagation candidate %s: %s", evaluation.path, evaluation.reason)
    logger.info(
        "Selected propagation: %s (source_nodes=%d, exact_order=%s)",
        propagation.path,
        propagation.source_node_count,
        propagation.exact_order,
    )
    artifact_provenance = inputs.provenance
    memberships = propagation.arrays["memberships"]
    uncertainty = propagation.arrays["uncertainty"]
    converged = propagation.arrays["converged"]
    node_ids = propagation.graph_node_ids
    n_total = len(node_ids)

    # --- Load and bind threshold calibration ---
    threshold = load_bound_threshold(
        data_dir,
        explicit_tau=args.tau,
        calibration_path=args.calibration_path,
        provenance=artifact_provenance,
        relevance_scorer_path=PROJECT_ROOT / "src/graph/tpot_relevance.py",
    )
    tau = threshold.tau
    calibration = threshold.calibration
    calibration_record = threshold.record
    logger.info(
        "Using tau=%.4f (%s)",
        tau,
        calibration_record["status"],
    )

    # Symmetrize for spectral (needs undirected)
    adjacency_sym, degrees, median_deg = compute_symmetrized_degree_stats(
        adjacency
    )
    logger.info("Median degree (nonzero): %.1f", median_deg)

    r = compute_relevance(memberships, uncertainty, converged, degrees, median_deg)
    if calibration_record["status"] == "legacy-runtime-validation-required":
        relevance_path = data_dir / "tpot_relevance_scores.npy"
        calibration_record["relevance_file_sha256"] = validate_saved_relevance(
            relevance_path,
            r,
        )
        calibration_record["relevance_status"] = (
            "exact-saved-float32-vector-reproduced"
        )

    # --- Build core+halo mask ---
    mask = build_core_halo_mask(r, adjacency_sym, tau)
    n_selected = mask.sum()
    n_core = (r >= tau).sum()
    n_halo = n_selected - n_core
    if calibration is not None:
        observed_counts = {
            "n_core": int(n_core),
            "n_halo": int(n_halo),
            "n_total": int(n_selected),
        }
        for field, observed in observed_counts.items():
            expected = calibration.get(field)
            if expected is not None and expected != observed:
                raise CalibrationCompatibilityError(
                    f"calibration {field}={expected}, but current artifacts "
                    f"produce {observed} at tau={tau}"
                )
        calibration_record["runtime_count_validation"] = observed_counts
    logger.info("TPOT subgraph: %d core + %d halo = %d total (%.1f%% of %d)",
                n_core, n_halo, n_selected,
                100.0 * n_selected / n_total, n_total)

    # --- Extract subgraph ---
    selected_indices = np.flatnonzero(mask)
    sub_adjacency = adjacency_sym[np.ix_(selected_indices, selected_indices)].tocsr()
    sub_node_ids = node_ids[selected_indices]
    sub_r = r[selected_indices]
    if calibration_record["status"] == "legacy-runtime-validation-required":
        prior_mapping_path = data_dir / "graph_snapshot_tpot.mapping.json"
        if not prior_mapping_path.exists():
            raise FileNotFoundError(
                "legacy calibration requires exact prior-output validation, "
                f"but mapping is absent: {prior_mapping_path}"
            )
        prior_mapping = json.loads(prior_mapping_path.read_text())
        calibration_record["prior_selection_sha256"] = validate_selection_mapping(
            prior_mapping,
            node_ids,
            sub_node_ids,
            tau,
            observed_counts,
        )

    # --- Reweight adjacency: W' = D_r^{1/2} W D_r^{1/2} ---
    # For halo nodes with r=0, set a small floor so they still contribute weakly
    sub_r_floored = np.maximum(sub_r, 0.01)
    reweighted = reweight_adjacency(sub_adjacency, sub_r_floored)
    logger.info("Reweighted adjacency: %d nodes, %d nonzeros", reweighted.shape[0], reweighted.nnz)

    # --- Run spectral embedding ---
    cfg = SpectralConfig(
        n_dims=args.n_dims,
        eigensolver_tol=args.tol,
        eigensolver_maxiter=args.maxiter,
        birch_threshold=args.birch_threshold,
        max_linkage_nodes=args.max_linkage_nodes,
    )
    logger.info("Computing spectral embedding (%d dims)...", cfg.n_dims)
    result = compute_spectral_embedding(reweighted, sub_node_ids, cfg)

    # --- Save ---
    save_spectral_result(result, Path(out_prefix))
    logger.info("Saved TPOT spectral to %s.*", out_prefix)

    # Save node mapping (for backend to look up original metadata)
    mapping = {
        "tau": float(tau),
        "n_total_graph": int(n_total),
        "n_tpot_subgraph": int(n_selected),
        "n_core": int(n_core),
        "n_halo": int(n_halo),
        "tpot_node_ids": [str(nid) for nid in sub_node_ids],
        "artifact_provenance": artifact_provenance,
        "calibration": calibration_record,
    }
    sidecar_counts = save_tpot_bundle_sidecars(
        out_prefix,
        nodes_full,
        edges_full,
        sub_node_ids,
        mapping,
    )
    logger.info(
        "Saved TPOT mapping and Parquet sidecars: nodes=%d edges=%d",
        sidecar_counts["nodes"],
        sidecar_counts["edges"],
    )


if __name__ == "__main__":
    main()
