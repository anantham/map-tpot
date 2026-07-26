"""Verify the full-graph inputs and selection of the frozen TPOT control."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.artifacts.adjacency_binding import validate_adjacency_binding
from src.artifacts.calibration_record import validate_calibration_code_files
from src.artifacts.propagation_alignment import AlignedPropagation
from src.artifacts.propagation_alignment import select_aligned_propagation
from src.artifacts.provenance import (
    build_artifact_provenance,
    validate_calibration_compatibility,
)
from src.artifacts.propagation_schema import propagation_score_semantics
from src.artifacts.relevance_binding import validate_saved_relevance
from src.artifacts.spectral_binding import validate_spectral_binding
from src.data.adjacency import load_adjacency_cache
from src.graph.tpot_relevance import (
    build_core_halo_mask,
    compute_relevance,
    compute_symmetrized_degree_stats,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class FrozenControlEvidence:
    nodes: pd.DataFrame
    edges: pd.DataFrame
    node_ids: np.ndarray
    adjacency: object
    propagation: AlignedPropagation
    provenance: dict
    calibration_path: Path
    calibration: dict
    calibration_status: str
    tau: float
    observed_counts: dict
    selected_ids: np.ndarray


def verify_frozen_control(
    data_dir: Path,
    *,
    selected_propagation: str,
) -> FrozenControlEvidence:
    """Verify full graph through exact relevance-based node selection."""
    nodes_path = data_dir / "graph_snapshot.nodes.parquet"
    edges_path = data_dir / "graph_snapshot.edges.parquet"
    nodes = pd.read_parquet(nodes_path)
    edges = pd.read_parquet(edges_path)
    if "node_id" not in nodes.columns:
        raise ValueError(f"{nodes_path} is missing required column node_id")
    node_ids = nodes["node_id"].astype(str).to_numpy()
    print(
        f"✓ Graph tables loaded: nodes={len(nodes):,}, "
        f"edge_rows={len(edges):,}"
    )

    adjacency_path = data_dir / "adjacency_matrix_cache.pkl"
    adjacency = load_adjacency_cache(adjacency_path)
    binding = validate_adjacency_binding(adjacency, node_ids, edges)
    print(
        "✓ Adjacency exactly reconstructs from ordered nodes + edges: "
        f"shape={adjacency.shape}, nnz={binding.adjacency_nnz:,}, "
        f"ignored_edges={binding.ignored_edge_count:,}, "
        f"construction={binding.construction_method}"
    )
    print(f"  ordered_node_sha256={binding.ordered_node_sha256}")
    print(f"  adjacency_structure_sha256={binding.structure_sha256}")
    print(f"  adjacency_values_sha256={binding.values_sha256}")
    full_spectral = validate_spectral_binding(
        data_dir / "graph_snapshot.spectral.npz",
        data_dir / "graph_snapshot.spectral_meta.json",
        node_ids,
    )
    print(
        "✓ Full spectral rows match authoritative graph order: "
        f"nodes={full_spectral.node_count:,}, "
        f"dims={full_spectral.embedding_dims}, "
        f"approximate={full_spectral.approximate}"
    )

    pinned_path = data_dir / selected_propagation
    diagnostics = select_aligned_propagation(
        node_ids,
        adjacency,
        [
            data_dir / "community_propagation.npz",
            pinned_path,
        ],
    )
    for evaluation in diagnostics.evaluations:
        symbol = "✓" if evaluation.missing_node_count == 0 else "·"
        print(
            f"{symbol} Propagation candidate {evaluation.path.name}: "
            f"{evaluation.reason}"
        )
    propagation = select_aligned_propagation(
        node_ids,
        adjacency,
        [pinned_path],
    )
    print(
        f"✓ Manifest-selected {propagation.path.name}: "
        f"source_nodes={propagation.source_node_count:,}, "
        f"exact_order={propagation.exact_order}"
    )
    _report_propagation_health(propagation)
    provenance = build_artifact_provenance(
        binding,
        propagation,
        source_files={
            "nodes": nodes_path,
            "edges": edges_path,
            "adjacency_cache": adjacency_path,
        },
    )
    print(
        "✓ Compatibility provenance generated: "
        f"memberships={provenance['propagation']['membership_shape']}, "
        f"communities="
        f"{len(provenance['propagation']['community_schema']['ids'])}"
    )

    calibration_path = data_dir / "tpot_calibration.json"
    calibration = json.loads(calibration_path.read_text())
    calibration_status = validate_calibration_compatibility(
        calibration,
        provenance,
    )
    if calibration_status == "compatibility-record-bound":
        validate_calibration_code_files(
            calibration["calibration_method"],
            {
                "relevance_scorer": (
                    PROJECT_ROOT / "src/graph/tpot_relevance.py"
                )
            },
        )
    tau = float(calibration["tau"])
    print(
        f"✓ Calibration identity accepted: tau={tau:.12g}, "
        f"status={calibration_status}"
    )

    _, degrees, median_degree = compute_symmetrized_degree_stats(adjacency)
    relevance = compute_relevance(
        propagation.arrays["memberships"],
        propagation.arrays["uncertainty"],
        propagation.arrays["converged"],
        degrees,
        median_degree,
    )
    if calibration_status == "legacy-runtime-validation-required":
        relevance_digest = validate_saved_relevance(
            data_dir / "tpot_relevance_scores.npy",
            relevance,
        )
        print(
            "✓ Legacy relevance vector reproduces exactly at float32: "
            f"sha256={relevance_digest}"
        )
    mask = build_core_halo_mask(relevance, adjacency, tau)
    n_core = int((relevance >= tau).sum())
    observed = {
        "n_core": n_core,
        "n_halo": int(mask.sum() - n_core),
        "n_total": int(mask.sum()),
    }
    for field, value in observed.items():
        if calibration.get(field) != value:
            raise ValueError(
                f"calibration {field}: expected={calibration.get(field)!r}, "
                f"observed={value!r}"
            )
    print(
        "✓ Saved calibration reproduces exactly: "
        f"core={observed['n_core']:,}, halo={observed['n_halo']:,}, "
        f"total={observed['n_total']:,}, median_degree={median_degree:.3f}"
    )
    return FrozenControlEvidence(
        nodes=nodes,
        edges=edges,
        node_ids=node_ids,
        adjacency=adjacency,
        propagation=propagation,
        provenance=provenance,
        calibration_path=calibration_path,
        calibration=calibration,
        calibration_status=calibration_status,
        tau=tau,
        observed_counts=observed,
        selected_ids=node_ids[mask],
    )


def _report_propagation_health(propagation: AlignedPropagation) -> None:
    memberships = propagation.arrays["memberships"]
    converged = propagation.arrays["converged"]
    mode, score_semantics, mode_declared = propagation_score_semantics(
        propagation.arrays
    )
    n_converged = int(np.count_nonzero(converged))
    n_classes = len(converged)
    print(
        "✓ Propagation schema is numerically valid: "
        f"communities={memberships.shape[1] - 1}, "
        f"membership_rows={memberships.shape[0]:,}, "
        f"mode={mode} ({'declared' if mode_declared else 'legacy-inferred'}), "
        f"score_semantics={score_semantics}, "
        f"converged_classes={n_converged}/{n_classes}"
    )
    if n_converged != n_classes:
        iterations = propagation.arrays.get("cg_iterations")
        detail = (
            f", iteration_sample={iterations[:5].tolist()}"
            if iterations is not None
            else ""
        )
        print(
            "⚠ Legacy propagation is reproducible but not solver-validated: "
            f"{n_classes - n_converged}/{n_classes} classes did not "
            f"converge{detail}"
        )
