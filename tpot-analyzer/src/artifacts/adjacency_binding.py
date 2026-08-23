"""Bind a cached adjacency matrix to node order and edge-table content."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import scipy.sparse as sp

from src.artifacts.digests import csr_digests, ordered_node_digest


class AdjacencyBindingError(ValueError):
    """Raised when a cache cannot be proven to match its node/edge sources."""


@dataclass(frozen=True)
class AdjacencyBinding:
    node_count: int
    edge_row_count: int
    ignored_edge_count: int
    adjacency_nnz: int
    ordered_node_sha256: str
    structure_sha256: str
    values_sha256: str
    construction_method: str = "directed_edge_rows"


def validate_adjacency_binding(
    adjacency: sp.spmatrix,
    node_ids,
    edges: pd.DataFrame,
    *,
    add_mutual_reverse: bool = False,
) -> AdjacencyBinding:
    raw_ids = np.asarray(node_ids)
    if raw_ids.ndim != 1:
        raise AdjacencyBindingError(
            f"node_ids must be one-dimensional; got shape={raw_ids.shape}"
        )
    if pd.isna(raw_ids).any() or any(not str(value).strip() for value in raw_ids):
        raise AdjacencyBindingError("graph node IDs contain null or empty values")
    normalized_ids = np.asarray([str(value) for value in raw_ids])
    seen: set[str] = set()
    duplicates: list[str] = []
    for node_id in normalized_ids:
        if node_id in seen and node_id not in duplicates:
            duplicates.append(node_id)
        seen.add(node_id)
    if duplicates:
        raise AdjacencyBindingError(
            f"duplicate graph node IDs: sample={duplicates[:5]}"
        )
    n_nodes = len(normalized_ids)
    if adjacency.shape != (n_nodes, n_nodes):
        raise AdjacencyBindingError(
            "adjacency shape must match ordered node IDs: "
            f"adjacency={adjacency.shape}, nodes={n_nodes}"
        )
    missing_columns = {"source", "target"} - set(edges.columns)
    if missing_columns:
        raise AdjacencyBindingError(
            f"edge table is missing columns: {sorted(missing_columns)}"
        )

    index = {node_id: position for position, node_id in enumerate(normalized_ids)}
    source_indices = edges["source"].astype(str).map(index)
    target_indices = edges["target"].astype(str).map(index)
    valid = source_indices.notna() & target_indices.notna()
    ignored_count = int((~valid).sum())
    if ignored_count:
        sample = edges.loc[~valid, ["source", "target"]].head(5).to_dict("records")
        raise AdjacencyBindingError(
            f"{ignored_count} edges fall outside the authoritative node domain: "
            f"sample={sample}"
        )
    rows = source_indices[valid].astype(np.int64).to_numpy()
    columns = target_indices[valid].astype(np.int64).to_numpy()
    if add_mutual_reverse:
        if "mutual" not in edges.columns:
            raise AdjacencyBindingError(
                "mutual-reverse construction requires edge column mutual"
            )
        mutual = edges.loc[valid, "mutual"].fillna(False).astype(bool).to_numpy()
        rows, columns = (
            np.concatenate((rows, columns[mutual])),
            np.concatenate((columns, rows[mutual])),
        )
    expected = sp.csr_matrix(
        (np.ones(len(rows), dtype=np.float64), (rows, columns)),
        shape=(n_nodes, n_nodes),
    )
    expected.sum_duplicates()
    expected.sort_indices()

    cached = adjacency.tocsr(copy=True).astype(np.float64)
    cached.sum_duplicates()
    cached.sort_indices()
    difference = cached - expected
    difference.eliminate_zeros()
    if difference.nnz:
        max_difference = float(np.max(np.abs(difference.data)))
        raise AdjacencyBindingError(
            "adjacency content mismatch under supplied node order: "
            f"differing_cells={difference.nnz}, "
            f"cached_nnz={cached.nnz}, expected_nnz={expected.nnz}, "
            f"max_abs_difference={max_difference}"
        )

    structure_digest, values_digest = csr_digests(cached)
    return AdjacencyBinding(
        node_count=n_nodes,
        edge_row_count=len(edges),
        ignored_edge_count=ignored_count,
        adjacency_nnz=cached.nnz,
        ordered_node_sha256=ordered_node_digest(normalized_ids),
        structure_sha256=structure_digest,
        values_sha256=values_digest,
        construction_method=(
            "directed_plus_mutual_reverse"
            if add_mutual_reverse
            else "directed_edge_rows"
        ),
    )
