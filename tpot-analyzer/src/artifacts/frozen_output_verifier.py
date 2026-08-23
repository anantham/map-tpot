"""Verify persisted TPOT outputs against a recomputed frozen control."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.artifacts.digests import file_sha256
from src.artifacts.provenance import validate_artifact_provenance_identity
from src.artifacts.selection_binding import validate_selection_mapping
from src.artifacts.spectral_binding import validate_spectral_binding
from src.artifacts.adjacency_binding import validate_adjacency_binding
from src.data.adjacency import load_adjacency_cache


def _require_equal(label: str, expected, observed) -> None:
    if expected != observed:
        raise ValueError(f"{label}: expected={expected!r}, observed={observed!r}")


def verify_frozen_outputs(data_dir: Path, control) -> None:
    """Verify mapping, Parquet subsets, spectral rows, and runtime cache."""
    mapping_path = data_dir / "graph_snapshot_tpot.mapping.json"
    if not mapping_path.exists():
        raise FileNotFoundError(
            "frozen calibration requires frozen output mapping: "
            f"{mapping_path}"
        )
    mapping = json.loads(mapping_path.read_text())
    saved_provenance = mapping.get("artifact_provenance")
    if saved_provenance is None:
        if control.calibration_status != "legacy-runtime-validation-required":
            raise ValueError(
                "mapping lacks artifact_provenance but calibration is not legacy"
            )
        print(
            "· Frozen mapping predates compatibility provenance; exact runtime "
            "output reproduction is required"
        )
    else:
        validate_artifact_provenance_identity(
            saved_provenance,
            control.provenance,
            label="mapping",
        )
        _verify_mapping_calibration(mapping, control)

    selected_digest = validate_selection_mapping(
        mapping,
        control.node_ids,
        control.selected_ids,
        control.tau,
        control.observed_counts,
    )
    print(
        "✓ Frozen TPOT mapping is byte-order equivalent to recomputation: "
        f"ordered_selected_sha256={selected_digest}"
    )

    tpot_nodes_path = data_dir / "graph_snapshot_tpot.nodes.parquet"
    tpot_edges_path = data_dir / "graph_snapshot_tpot.edges.parquet"
    tpot_nodes = pd.read_parquet(tpot_nodes_path)
    tpot_edges = pd.read_parquet(tpot_edges_path)
    selected_set = set(control.selected_ids)
    expected_nodes = control.nodes[
        control.nodes["node_id"].astype(str).isin(selected_set)
    ].reset_index(drop=True)
    if not tpot_nodes.reset_index(drop=True).equals(expected_nodes):
        raise ValueError(
            "TPOT node parquet is not the exact selected subset of full nodes"
        )
    expected_edges = control.edges[
        control.edges["source"].astype(str).isin(selected_set)
        & control.edges["target"].astype(str).isin(selected_set)
    ].reset_index(drop=True)
    if not tpot_edges.reset_index(drop=True).equals(expected_edges):
        raise ValueError(
            "TPOT edge parquet is not the exact induced full-graph subset"
        )
    print(
        "✓ TPOT parquet subset is exact: "
        f"nodes={len(tpot_nodes):,}, edges={len(tpot_edges):,}"
    )

    tpot_spectral = validate_spectral_binding(
        data_dir / "graph_snapshot_tpot.spectral.npz",
        data_dir / "graph_snapshot_tpot.spectral_meta.json",
        control.selected_ids,
    )
    print(
        "✓ TPOT spectral rows match recomputed selected order: "
        f"nodes={tpot_spectral.node_count:,}, "
        f"dims={tpot_spectral.embedding_dims}"
    )
    tpot_adjacency = load_adjacency_cache(
        data_dir / "adjacency_matrix_cache.tpot.pkl"
    )
    tpot_binding = validate_adjacency_binding(
        tpot_adjacency,
        control.selected_ids,
        tpot_edges,
        add_mutual_reverse=True,
    )
    print(
        "✓ TPOT runtime adjacency matches mutual-edge semantics: "
        f"nnz={tpot_binding.adjacency_nnz:,}, "
        f"construction={tpot_binding.construction_method}, "
        f"structure_sha256={tpot_binding.structure_sha256}"
    )


def _verify_mapping_calibration(mapping, control) -> None:
    mapping_calibration = mapping.get("calibration")
    if not isinstance(mapping_calibration, dict):
        raise ValueError("provenance-bound mapping lacks calibration record")
    _require_equal(
        "mapping calibration status",
        control.calibration_status,
        mapping_calibration.get("status"),
    )
    _require_equal(
        "mapping calibration tau",
        control.tau,
        mapping_calibration.get("tau"),
    )
    saved_hash = mapping_calibration.get("file_sha256")
    if saved_hash is not None:
        _require_equal(
            "mapping calibration file_sha256",
            file_sha256(control.calibration_path),
            saved_hash,
        )
