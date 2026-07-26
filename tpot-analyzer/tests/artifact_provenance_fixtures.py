from __future__ import annotations

import numpy as np

from src.artifacts.adjacency_binding import AdjacencyBinding
from src.artifacts.propagation_alignment import (
    AlignedPropagation,
    CandidateEvaluation,
)
from src.artifacts.provenance import build_artifact_provenance


def calibration_method_record():
    return {
        "name": "recall_compactness_harmonic_utility",
        "objective": (
            "harmonic_mean(holdout_positive_recall,"
            "one_minus_selected_graph_fraction)"
        ),
        "recall_floor": 0.85,
        "tau_min": 0.001,
        "tau_max": 0.5,
        "tau_steps": 100,
        "holdout_file": "tpot_holdout_seeds.json",
        "holdout_file_sha256": "a" * 64,
        "holdout_fraction": 0.2,
        "holdout_seed": 42,
        "n_holdout": 55,
        "n_train": 243,
        "code_files": {
            "relevance_scorer": {
                "file": "tpot_relevance.py",
                "sha256": "b" * 64,
            },
            "threshold_selector": {
                "file": "calibration_method.py",
                "sha256": "c" * 64,
            },
            "calibrator": {
                "file": "calibrate_tpot_threshold.py",
                "sha256": "d" * 64,
            },
        },
    }


def build_test_provenance(tmp_path):
    propagation_path = tmp_path / "propagation.npz"
    propagation_path.write_bytes(b"stable artifact bytes")
    source_files = {}
    for label in ("nodes", "edges", "adjacency_cache"):
        path = tmp_path / label
        path.write_bytes(label.encode())
        source_files[label] = path
    binding = AdjacencyBinding(
        node_count=2,
        edge_row_count=1,
        ignored_edge_count=0,
        adjacency_nnz=1,
        ordered_node_sha256="n" * 64,
        structure_sha256="s" * 64,
        values_sha256="v" * 64,
    )
    evaluation = CandidateEvaluation(
        path=propagation_path,
        source_node_count=2,
        matched_node_count=2,
        missing_node_count=0,
        exact_order=True,
        reason="exact graph order",
    )
    propagation = AlignedPropagation(
        path=propagation_path,
        graph_node_ids=np.array(["a", "b"]),
        arrays={
            "memberships": np.tile(
                np.array([[0.6, 0.3, 0.1]]),
                (2, 1),
            ),
            "community_ids": np.array(["c1", "c2"]),
            "community_names": np.array(["one", "two"]),
            "community_colors": np.array(["#111111", "#222222"]),
        },
        source_node_count=2,
        exact_order=True,
        graph_node_sha256="n" * 64,
        source_node_sha256="n" * 64,
        evaluations=(evaluation,),
    )
    return (
        build_artifact_provenance(
            binding,
            propagation,
            source_files=source_files,
        ),
        propagation_path,
    )
