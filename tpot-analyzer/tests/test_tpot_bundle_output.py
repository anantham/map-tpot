from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.artifacts.tpot_bundle_output import save_tpot_bundle_sidecars


def test_saves_ordered_selected_nodes_edges_and_mapping(tmp_path):
    prefix = tmp_path / "generation" / "tpot"
    prefix.parent.mkdir()
    nodes = pd.DataFrame(
        {"node_id": ["a", "b", "c"], "username": ["A", "B", "C"]}
    )
    edges = pd.DataFrame(
        {
            "source": ["a", "a", "b"],
            "target": ["b", "c", "c"],
        }
    )
    mapping = {"tau": 0.5, "tpot_node_ids": ["a", "b"]}

    counts = save_tpot_bundle_sidecars(
        prefix,
        nodes,
        edges,
        np.array(["a", "b"]),
        mapping,
    )

    assert counts == {"nodes": 2, "edges": 1}
    assert json.loads((prefix.parent / "tpot.mapping.json").read_text()) == mapping
    saved_nodes = pd.read_parquet(prefix.parent / "tpot.nodes.parquet")
    assert saved_nodes["node_id"].tolist() == ["a", "b"]
    saved_edges = pd.read_parquet(prefix.parent / "tpot.edges.parquet")
    assert saved_edges[["source", "target"]].values.tolist() == [["a", "b"]]
