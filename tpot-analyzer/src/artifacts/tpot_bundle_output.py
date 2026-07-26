"""Persist sidecars for one reserved, unpublished TPOT artifact bundle."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def save_tpot_bundle_sidecars(
    output_prefix,
    full_nodes,
    full_edges,
    selected_node_ids,
    mapping,
):
    """Write mapping and exact induced Parquet subsets for a new bundle."""
    output_prefix = Path(output_prefix)
    selected_ids = np.asarray([str(value) for value in selected_node_ids])
    selected_set = set(selected_ids)
    if len(selected_set) != len(selected_ids):
        raise ValueError("selected TPOT node IDs must be unique")

    nodes_tpot = full_nodes[
        full_nodes["node_id"].astype(str).isin(selected_set)
    ]
    observed_ids = nodes_tpot["node_id"].astype(str).to_numpy()
    if not np.array_equal(observed_ids, selected_ids):
        raise ValueError(
            "filtered TPOT nodes do not preserve the selected ordered IDs"
        )
    edges_tpot = full_edges[
        full_edges["source"].astype(str).isin(selected_set)
        & full_edges["target"].astype(str).isin(selected_set)
    ]

    mapping_path = Path(str(output_prefix) + ".mapping.json")
    nodes_path = Path(str(output_prefix) + ".nodes.parquet")
    edges_path = Path(str(output_prefix) + ".edges.parquet")
    mapping_path.write_text(json.dumps(mapping, indent=2))
    nodes_tpot.to_parquet(nodes_path, index=False)
    edges_tpot.to_parquet(edges_path, index=False)
    return {"nodes": len(nodes_tpot), "edges": len(edges_tpot)}
