"""Validate a persisted TPOT selection against recomputed ordered IDs."""
from __future__ import annotations

import math

import numpy as np

from src.artifacts.digests import ordered_node_digest


class SelectionBindingError(ValueError):
    """Raised when a saved TPOT mapping contradicts recomputation."""


def validate_selection_mapping(
    mapping,
    graph_node_ids,
    selected_node_ids,
    tau,
    counts,
):
    """Validate a saved mapping and return its ordered selection digest."""
    if not isinstance(mapping, dict):
        raise SelectionBindingError(
            f"selection mapping root must be an object; got {type(mapping).__name__}"
        )
    required = {
        "tau",
        "n_total_graph",
        "n_tpot_subgraph",
        "n_core",
        "n_halo",
        "tpot_node_ids",
    }
    missing = sorted(required - set(mapping))
    if missing:
        raise SelectionBindingError(f"selection mapping is missing fields: {missing}")

    graph_ids = np.asarray(graph_node_ids)
    selected_ids = np.asarray(selected_node_ids)
    if graph_ids.ndim != 1 or selected_ids.ndim != 1:
        raise SelectionBindingError("graph and selected node IDs must be one-dimensional")
    graph_ids = np.asarray([str(value) for value in graph_ids])
    selected_ids = np.asarray([str(value) for value in selected_ids])
    mapping_values = mapping["tpot_node_ids"]
    if not isinstance(mapping_values, list):
        raise SelectionBindingError("mapping tpot_node_ids must be a list")
    mapping_ids = np.asarray([str(value) for value in mapping_values])

    saved_tau = mapping["tau"]
    if (
        isinstance(saved_tau, bool)
        or not isinstance(saved_tau, (int, float))
        or not math.isfinite(float(saved_tau))
        or float(saved_tau) != float(tau)
    ):
        raise SelectionBindingError(
            f"mapping tau={saved_tau!r}, expected {float(tau)!r}"
        )
    expected_fields = {
        "n_total_graph": len(graph_ids),
        "n_tpot_subgraph": len(selected_ids),
        "n_core": counts["n_core"],
        "n_halo": counts["n_halo"],
    }
    for field, expected in expected_fields.items():
        if mapping[field] != expected:
            raise SelectionBindingError(
                f"mapping {field}={mapping[field]!r}, expected {expected!r}"
            )
    if counts["n_total"] != len(selected_ids):
        raise SelectionBindingError(
            f"observed n_total={counts['n_total']!r}, "
            f"but selected IDs contain {len(selected_ids)}"
        )
    if not np.array_equal(mapping_ids, selected_ids):
        raise SelectionBindingError(
            "mapping ordered node IDs do not match recomputed selection"
        )
    return ordered_node_digest(selected_ids)
