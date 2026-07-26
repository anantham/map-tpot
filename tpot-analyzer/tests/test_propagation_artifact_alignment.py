from __future__ import annotations

import numpy as np
import pytest
from scipy import sparse

from src.artifacts.propagation_alignment import (
    ArtifactCompatibilityError,
    select_aligned_propagation,
)
from tests.propagation_artifact_fixtures import (
    write_propagation as _write_propagation,
)


def test_selects_exact_compatible_fallback(tmp_path):
    graph_ids = np.array(["a", "b", "c"])
    active = tmp_path / "active.npz"
    train = tmp_path / "train.npz"
    _write_propagation(active, ["a", "x"], offset=100)
    _write_propagation(train, graph_ids, offset=10)

    result = select_aligned_propagation(
        graph_ids,
        sparse.eye(3, format="csr"),
        [active, train],
    )

    assert result.path == train
    assert result.exact_order is True
    np.testing.assert_array_equal(result.graph_node_ids, graph_ids)
    np.testing.assert_array_equal(
        result.arrays["uncertainty"],
        np.array([0.25, 0.5, 0.75], dtype=np.float32),
    )
    assert result.evaluations[0].missing_node_count == 2


def test_aligns_full_coverage_superset_by_id(tmp_path):
    graph_ids = np.array(["a", "b", "c"])
    candidate = tmp_path / "superset.npz"
    _write_propagation(
        candidate,
        ["c", "a", "extra", "b"],
        offset=10,
        include_optional=True,
    )

    result = select_aligned_propagation(
        graph_ids,
        sparse.eye(3, format="csr"),
        [candidate],
    )

    assert result.exact_order is False
    assert result.source_node_count == 4
    np.testing.assert_array_equal(
        result.arrays["uncertainty"],
        np.array([0.4, 0.8, 0.2], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        result.arrays["seed_neighbor_counts"][:, 0],
        np.array([11.0, 13.0, 10.0]),
    )
    np.testing.assert_array_equal(
        result.arrays["confidence_intervals"][:, 0, 0],
        np.array([51.0, 53.0, 50.0]),
    )


def test_preserves_explicit_candidate_priority_when_reindex_is_safe(tmp_path):
    graph_ids = np.array(["a", "b", "c"])
    superset = tmp_path / "superset.npz"
    exact = tmp_path / "exact.npz"
    _write_propagation(superset, ["c", "extra", "a", "b"], offset=100)
    _write_propagation(exact, graph_ids, offset=10)

    result = select_aligned_propagation(
        graph_ids,
        sparse.eye(3, format="csr"),
        [superset, exact],
    )

    assert result.path == superset
    assert result.exact_order is False
    np.testing.assert_array_equal(
        result.arrays["uncertainty"],
        np.array([0.6, 0.8, 0.2], dtype=np.float32),
    )


def test_rejects_partial_overlap_with_counts_and_sample(tmp_path):
    candidate = tmp_path / "partial.npz"
    _write_propagation(candidate, ["a", "x"])

    with pytest.raises(
        ArtifactCompatibilityError,
        match=r"matched=1/3.*missing=2.*sample=\['b', 'c'\]",
    ):
        select_aligned_propagation(
            np.array(["a", "b", "c"]),
            sparse.eye(3, format="csr"),
            [candidate],
        )


def test_rejects_adjacency_shape_before_loading_candidates(tmp_path):
    candidate = tmp_path / "candidate.npz"
    _write_propagation(candidate, ["a", "b", "c"])

    with pytest.raises(ArtifactCompatibilityError, match=r"adjacency.*2, 2.*3"):
        select_aligned_propagation(
            np.array(["a", "b", "c"]),
            sparse.eye(2, format="csr"),
            [candidate],
        )


def test_rejects_duplicate_source_node_ids(tmp_path):
    candidate = tmp_path / "duplicates.npz"
    _write_propagation(candidate, ["a", "a", "b"])

    with pytest.raises(ArtifactCompatibilityError, match="duplicate.*a"):
        select_aligned_propagation(
            np.array(["a", "b"]),
            sparse.eye(2, format="csr"),
            [candidate],
        )


def test_rejects_unknown_node_indexed_array_instead_of_leaving_it_unaligned(
    tmp_path,
):
    candidate = tmp_path / "future_schema.npz"
    _write_propagation(
        candidate,
        ["c", "a", "extra", "b"],
        extra_arrays={"future_node_score": np.arange(4)},
    )

    with pytest.raises(
        ArtifactCompatibilityError,
        match=r"unsupported node-indexed arrays.*future_node_score",
    ):
        select_aligned_propagation(
            np.array(["a", "b", "c"]),
            sparse.eye(3, format="csr"),
            [candidate],
        )
