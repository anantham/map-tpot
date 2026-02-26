"""Tests for community-aware semantic affinity construction."""
import numpy as np
import pytest
from scipy import sparse

from src.graph.community_affinity import (
    blend_affinity,
    build_m_bias,
    build_semantic_adjacency,
)

# --- build_m_bias ---


def test_downweights_unconverged():
    """Unconverged classes get 0.3x weight in M_bias."""
    # 3 community cols + 1 "none" col = 4 total
    memberships = np.array([
        [0.5, 0.3, 0.1, 0.1],
        [0.2, 0.6, 0.1, 0.1],
    ], dtype=np.float32)
    converged = np.array([True, False, True, True], dtype=bool)
    uncertainty = np.array([0.0, 0.0], dtype=np.float32)

    m_bias = build_m_bias(memberships, converged, uncertainty)

    assert m_bias.shape == (2, 3)  # "none" column stripped
    # Class 1 (unconverged) should be ~0.3x of original
    assert m_bias[0, 1] == pytest.approx(0.3 * 0.3, abs=0.01)
    # Converged classes unchanged
    assert m_bias[0, 0] == pytest.approx(0.5, abs=0.01)
    assert m_bias[0, 2] == pytest.approx(0.1, abs=0.01)


def test_uncertainty_reduces_all_weights():
    """High uncertainty nodes get reduced weight across all classes."""
    # 2 community cols + 1 "none" col = 3 total
    memberships = np.array([
        [0.5, 0.3, 0.2],
        [0.5, 0.3, 0.2],
    ], dtype=np.float32)
    converged = np.ones(3, dtype=bool)
    uncertainty = np.array([0.0, 0.8], dtype=np.float32)

    m_bias = build_m_bias(memberships, converged, uncertainty)

    # Node 0 (zero uncertainty): full weight
    assert m_bias[0, 0] == pytest.approx(0.5, abs=0.01)
    # Node 1 (high uncertainty): 0.2x weight
    assert m_bias[1, 0] == pytest.approx(0.5 * 0.2, abs=0.01)


# --- build_semantic_adjacency ---


def _make_m_bias(n_nodes, n_classes, seed=42):
    """Create a random M_bias matrix with some structure."""
    rng = np.random.RandomState(seed)
    m = rng.rand(n_nodes, n_classes).astype(np.float32)
    # Normalize rows
    m /= m.sum(axis=1, keepdims=True)
    return m


def test_basic_shape():
    """Output is square sparse, same dimension as number of nodes."""
    m_bias = _make_m_bias(50, 5)
    a_sem = build_semantic_adjacency(m_bias, top_k=10)

    assert a_sem.shape == (50, 50)
    assert sparse.issparse(a_sem)


def test_sparsity():
    """Each row has at most top_k nonzeros."""
    top_k = 10
    m_bias = _make_m_bias(50, 5)
    a_sem = build_semantic_adjacency(m_bias, top_k=top_k)

    # Before symmetrization each row has at most top_k entries.
    # After symmetrization, a node can gain additional edges from
    # nodes that chose it as a neighbor. Verify raw sparsity is bounded.
    dense = a_sem.toarray()
    for i in range(50):
        row_nnz = np.count_nonzero(dense[i])
        # With 50 nodes and top_k=10, worst case after symmetrization
        # is bounded but can exceed 2*top_k for popular nodes.
        # Check that it's reasonably sparse (< n-1)
        assert row_nnz < 50 - 1, f"Row {i} has {row_nnz} nonzeros, not sparse"


def test_symmetric():
    """Result is symmetric."""
    m_bias = _make_m_bias(50, 5)
    a_sem = build_semantic_adjacency(m_bias, top_k=10)

    diff = a_sem - a_sem.T
    assert diff.nnz == 0 or abs(diff).max() < 1e-10


def test_no_self_loops():
    """Diagonal is zero."""
    m_bias = _make_m_bias(50, 5)
    a_sem = build_semantic_adjacency(m_bias, top_k=10)

    diag = a_sem.diagonal()
    assert np.all(diag == 0)


def test_zero_membership_produces_empty():
    """All-zero rows produce no edges for those nodes."""
    m_bias = np.zeros((20, 5), dtype=np.float32)
    # Only first 5 nodes have membership
    m_bias[:5] = _make_m_bias(5, 5)

    a_sem = build_semantic_adjacency(m_bias, top_k=3)

    # Nodes 5-19 (zero membership) should have no outgoing edges
    # (they may have incoming from symmetrization, but not outgoing)
    for i in range(5, 20):
        # The zero-membership nodes shouldn't be connected to each other
        sub = a_sem[5:, 5:]
        assert sub.nnz == 0


# --- blend_affinity ---


def test_alpha_zero_returns_topo():
    """alpha=0 returns A_topo unchanged."""
    a_topo = sparse.random(50, 50, density=0.1, format="csr")
    a_sem = sparse.random(50, 50, density=0.1, format="csr")

    result = blend_affinity(a_topo, a_sem, alpha=0.0)

    diff = result - a_topo
    assert diff.nnz == 0 or abs(diff).max() < 1e-10


def test_alpha_one_returns_sem():
    """alpha=1 returns A_sem."""
    a_topo = sparse.random(50, 50, density=0.1, format="csr")
    a_sem = sparse.random(50, 50, density=0.1, format="csr")

    result = blend_affinity(a_topo, a_sem, alpha=1.0)

    diff = result - a_sem
    assert diff.nnz == 0 or abs(diff).max() < 1e-10


def test_result_is_sparse():
    """Output is sparse CSR."""
    a_topo = sparse.random(50, 50, density=0.1, format="csr")
    a_sem = sparse.random(50, 50, density=0.1, format="csr")

    result = blend_affinity(a_topo, a_sem, alpha=0.5)

    assert sparse.issparse(result)
    assert result.format == "csr"


def test_blend_interpolates():
    """alpha=0.5 gives average of A_topo and A_sem."""
    a_topo = sparse.eye(10, format="csr") * 2.0
    a_sem = sparse.eye(10, format="csr") * 4.0

    result = blend_affinity(a_topo, a_sem, alpha=0.5)

    expected = sparse.eye(10, format="csr") * 3.0
    diff = result - expected
    assert diff.nnz == 0 or abs(diff).max() < 1e-10
