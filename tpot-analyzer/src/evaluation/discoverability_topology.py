"""Sparse graph primitives used by discoverability measurements."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.csgraph import breadth_first_order, connected_components


def build_graph_views(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
) -> tuple[np.ndarray, sparse.csr_matrix, sparse.csr_matrix, sparse.csr_matrix]:
    """Build binary directed, any-direction, and reciprocal-only graph views."""
    node_columns = {"node_id", "shadow"}
    edge_columns = {"source", "target", "shadow", "direction_label"}
    if not node_columns.issubset(nodes.columns):
        raise ValueError(f"nodes missing columns: {sorted(node_columns - set(nodes))}")
    if not edge_columns.issubset(edges.columns):
        raise ValueError(f"edges missing columns: {sorted(edge_columns - set(edges))}")
    node_ids = nodes["node_id"].astype(str).to_numpy()
    if len(node_ids) == 0 or len(set(node_ids)) != len(node_ids):
        raise ValueError("frozen graph node IDs must be nonempty and unique")
    index = pd.Index(node_ids)
    rows = index.get_indexer(edges["source"].astype(str))
    columns = index.get_indexer(edges["target"].astype(str))
    missing = int(np.count_nonzero((rows < 0) | (columns < 0)))
    if missing:
        raise ValueError(f"frozen graph has {missing} edges with unknown endpoints")
    directed = sparse.csr_matrix(
        (np.ones(len(edges), dtype=np.uint8), (rows, columns)),
        shape=(len(node_ids), len(node_ids)),
    )
    directed.sum_duplicates()
    directed.data[:] = 1
    undirected = directed.maximum(directed.T).tocsr()
    mutual = directed.multiply(directed.T).tocsr()
    mutual.data[:] = 1
    return node_ids, directed, undirected, mutual


def component_summary(
    matrix: sparse.csr_matrix,
    *,
    directed: bool,
    connection: str = "weak",
) -> dict[str, float | int]:
    """Count components and the largest-component share."""
    count, labels = connected_components(
        matrix,
        directed=directed,
        connection=connection,
    )
    giant = int(np.bincount(labels, minlength=count).max())
    return {
        "components": int(count),
        "giant_nodes": giant,
        "giant_pct": 100.0 * giant / matrix.shape[0],
    }


def reachability_summary(
    matrix: sparse.csr_matrix,
    seeds: np.ndarray,
    *,
    directed: bool,
) -> dict[str, float | int]:
    """Measure the union reachable from a fixed seed panel."""
    reached = np.zeros(matrix.shape[0], dtype=bool)
    for seed in seeds:
        order = breadth_first_order(
            matrix,
            int(seed),
            directed=directed,
            return_predecessors=False,
        )
        reached[np.asarray(order, dtype=np.int64)] = True
    return {"nodes": int(reached.sum()), "pct": 100.0 * reached.mean()}
