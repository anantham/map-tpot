from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from src.artifacts.adjacency_binding import (
    AdjacencyBindingError,
    validate_adjacency_binding,
)
from src.artifacts.digests import csr_digests, json_sha256, ordered_node_digest


def _edges():
    return pd.DataFrame(
        {
            "source": ["a", "b"],
            "target": ["b", "c"],
        }
    )


def test_validates_cache_against_ordered_nodes_and_edges():
    adjacency = sparse.csr_matrix(
        (
            np.ones(2),
            ([0, 1], [1, 2]),
        ),
        shape=(3, 3),
    )

    result = validate_adjacency_binding(
        adjacency,
        np.array(["a", "b", "c"]),
        _edges(),
    )

    assert result.node_count == 3
    assert result.edge_row_count == 2
    assert result.ignored_edge_count == 0
    assert result.adjacency_nnz == 2
    assert result.construction_method == "directed_edge_rows"
    assert len(result.ordered_node_sha256) == 64
    assert len(result.structure_sha256) == 64
    assert len(result.values_sha256) == 64


def test_rejects_same_shape_cache_under_different_node_order():
    old_order_cache = sparse.csr_matrix(
        (
            np.ones(2),
            ([0, 1], [1, 2]),
        ),
        shape=(3, 3),
    )

    with pytest.raises(AdjacencyBindingError, match="content mismatch"):
        validate_adjacency_binding(
            old_order_cache,
            np.array(["b", "a", "c"]),
            _edges(),
        )


def test_rejects_duplicate_graph_node_ids():
    with pytest.raises(AdjacencyBindingError, match="duplicate.*a"):
        validate_adjacency_binding(
            sparse.eye(2, format="csr"),
            np.array(["a", "a"]),
            pd.DataFrame({"source": [], "target": []}),
        )


def test_rejects_null_or_empty_graph_node_ids():
    for invalid_ids in (
        np.array(["a", None], dtype=object),
        np.array(["a", ""]),
    ):
        with pytest.raises(AdjacencyBindingError, match="null or empty"):
            validate_adjacency_binding(
                sparse.csr_matrix((2, 2)),
                invalid_ids,
                pd.DataFrame({"source": [], "target": []}),
            )


def test_rejects_edges_outside_authoritative_node_domain():
    with pytest.raises(AdjacencyBindingError, match="outside.*node domain"):
        validate_adjacency_binding(
            sparse.csr_matrix(([1.0], ([0], [1])), shape=(2, 2)),
            np.array(["a", "b"]),
            pd.DataFrame(
                {
                    "source": ["a", "outside"],
                    "target": ["b", "a"],
                }
            ),
        )


def test_validates_mutual_reverse_construction_semantics():
    adjacency = sparse.csr_matrix(
        (
            np.ones(2),
            ([0, 1], [1, 0]),
        ),
        shape=(2, 2),
    )
    edges = pd.DataFrame(
        {
            "source": ["a"],
            "target": ["b"],
            "mutual": [True],
        }
    )

    result = validate_adjacency_binding(
        adjacency,
        np.array(["a", "b"]),
        edges,
        add_mutual_reverse=True,
    )

    assert result.adjacency_nnz == 2
    assert result.construction_method == "directed_plus_mutual_reverse"


def test_rejects_multidimensional_graph_node_ids():
    with pytest.raises(AdjacencyBindingError, match="one-dimensional"):
        validate_adjacency_binding(
            sparse.csr_matrix((2, 2)),
            np.array([["a"], ["b"]]),
            pd.DataFrame({"source": [], "target": []}),
        )


def test_digests_bind_order_structure_and_values():
    assert ordered_node_digest(["a", "b"]) != ordered_node_digest(["b", "a"])
    first = sparse.csr_matrix(([1.0], ([0], [1])), shape=(2, 2))
    second = sparse.csr_matrix(([2.0], ([0], [1])), shape=(2, 2))

    first_structure, first_values = csr_digests(first)
    second_structure, second_values = csr_digests(second)

    assert first_structure == second_structure
    assert first_values != second_values
    assert json_sha256({"a": 1, "b": 2}) == json_sha256({"b": 2, "a": 1})
