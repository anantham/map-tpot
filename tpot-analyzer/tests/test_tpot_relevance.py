"""Tests for TPOT relevance scoring and graph reweighting."""
import numpy as np
import pytest
from scipy import sparse

from src.graph.tpot_relevance import (
    _normalized_entropy,
    build_core_halo_mask,
    compute_relevance,
    reweight_adjacency,
)

# --- _normalized_entropy ---


def test_entropy_uniform():
    """Uniform distribution has entropy = 1."""
    p = np.array([[0.25, 0.25, 0.25, 0.25]])
    h = _normalized_entropy(p)
    assert h[0] == pytest.approx(1.0, abs=1e-6)


def test_entropy_deterministic():
    """Deterministic distribution has entropy = 0."""
    p = np.array([[1.0, 0.0, 0.0]])
    h = _normalized_entropy(p)
    assert h[0] == pytest.approx(0.0, abs=1e-6)


def test_entropy_between():
    """Partially concentrated has entropy between 0 and 1."""
    p = np.array([[0.8, 0.1, 0.1]])
    h = _normalized_entropy(p)
    assert 0.0 < h[0] < 1.0


# --- compute_relevance ---


def _make_test_data(n=10, K=3):
    """Create test data with known properties."""
    rng = np.random.RandomState(42)
    # K community columns + 1 "none" column
    memberships = rng.rand(n, K + 1).astype(np.float64)
    # Normalize rows to sum to 1
    memberships /= memberships.sum(axis=1, keepdims=True)
    uncertainty = rng.rand(n).astype(np.float32) * 0.5  # 0 to 0.5
    converged = np.ones(K + 1, dtype=bool)
    degrees = rng.randint(1, 20, size=n).astype(np.float64)
    median_deg = float(np.median(degrees))
    return memberships, uncertainty, converged, degrees, median_deg


def test_relevance_shape():
    """Output has same length as number of nodes."""
    memberships, uncertainty, converged, degrees, median_deg = _make_test_data(20)
    r = compute_relevance(memberships, uncertainty, converged, degrees, median_deg)
    assert r.shape == (20,)


def test_relevance_bounded():
    """Relevance scores are in [0, 1]."""
    memberships, uncertainty, converged, degrees, median_deg = _make_test_data(50)
    r = compute_relevance(memberships, uncertainty, converged, degrees, median_deg)
    assert np.all(r >= 0.0)
    assert np.all(r <= 1.0)


def test_pure_none_gets_zero():
    """A node that is 100% 'none' has relevance 0."""
    # 3 communities + none
    memberships = np.array([[0.0, 0.0, 0.0, 1.0]])
    uncertainty = np.array([0.0])
    converged = np.ones(4, dtype=bool)
    degrees = np.array([10.0])
    median_deg = 5.0

    r = compute_relevance(memberships, uncertainty, converged, degrees, median_deg)
    assert r[0] == pytest.approx(0.0, abs=1e-10)


def test_strong_single_community_high_relevance():
    """A node strongly in one community, low uncertainty, good degree → high r."""
    memberships = np.array([[0.9, 0.05, 0.0, 0.05]])
    uncertainty = np.array([0.0])
    converged = np.ones(4, dtype=bool)
    degrees = np.array([10.0])
    median_deg = 5.0

    r = compute_relevance(memberships, uncertainty, converged, degrees, median_deg)
    assert r[0] > 0.5


def test_high_uncertainty_reduces_relevance():
    """High uncertainty should reduce relevance."""
    memberships = np.array([
        [0.8, 0.1, 0.0, 0.1],
        [0.8, 0.1, 0.0, 0.1],
    ])
    converged = np.ones(4, dtype=bool)
    degrees = np.array([10.0, 10.0])
    median_deg = 5.0

    r_low_unc = compute_relevance(
        memberships, np.array([0.0, 0.0]), converged, degrees, median_deg
    )
    r_high_unc = compute_relevance(
        memberships, np.array([0.0, 0.9]), converged, degrees, median_deg
    )
    assert r_high_unc[1] < r_low_unc[0]


def test_unconverged_dominant_reduces_relevance():
    """Unconverged dominant class gets 0.3x confidence penalty."""
    memberships = np.array([
        [0.8, 0.1, 0.0, 0.1],
        [0.8, 0.1, 0.0, 0.1],
    ])
    uncertainty = np.zeros(2)
    degrees = np.array([10.0, 10.0])
    median_deg = 5.0

    converged_all = np.ones(4, dtype=bool)
    converged_first_bad = np.array([False, True, True, True])

    r_good = compute_relevance(memberships, uncertainty, converged_all, degrees, median_deg)
    r_bad = compute_relevance(memberships, uncertainty, converged_first_bad, degrees, median_deg)

    # Node 0's dominant is class 0 (unconverged) → 0.3x penalty
    assert r_bad[0] == pytest.approx(r_good[0] * 0.3, abs=0.01)


def test_low_degree_suppressed():
    """Degree-0 node gets g(deg)=0, degree-1 node gets less than median-degree node."""
    memberships = np.array([
        [0.8, 0.1, 0.0, 0.1],
        [0.8, 0.1, 0.0, 0.1],
        [0.8, 0.1, 0.0, 0.1],
    ])
    uncertainty = np.zeros(3)
    converged = np.ones(4, dtype=bool)
    degrees = np.array([0.0, 1.0, 10.0])
    median_deg = 10.0

    r = compute_relevance(memberships, uncertainty, converged, degrees, median_deg)
    assert r[0] == pytest.approx(0.0, abs=1e-10)  # degree 0 → g=0
    assert r[1] < r[2]  # degree 1 < degree 10


def test_degree_cap_at_one():
    """g(deg) is capped at 1.0 — high-degree hubs don't get boosted beyond 1."""
    memberships = np.array([[0.8, 0.1, 0.0, 0.1]])
    uncertainty = np.array([0.0])
    converged = np.ones(4, dtype=bool)
    median_deg = 5.0

    r_med = compute_relevance(memberships, uncertainty, converged, np.array([5.0]), median_deg)
    r_hub = compute_relevance(memberships, uncertainty, converged, np.array([1000.0]), median_deg)

    # Hub should have g(deg)=1.0, not higher. Same signal → same or equal relevance.
    assert r_hub[0] >= r_med[0] - 1e-10
    # g(1000) should be exactly 1.0 (capped)
    assert r_hub[0] <= r_med[0] * 1.01  # within 1% (g(5)≈1.0 already near cap)


def test_spread_memberships_low_focus():
    """Uniform community memberships → high entropy → low focus → lower r."""
    # Spread evenly across 4 communities, low none
    memberships_spread = np.array([[0.24, 0.24, 0.24, 0.24, 0.04]])
    # Concentrated in one community, low none
    memberships_focused = np.array([[0.9, 0.03, 0.03, 0.0, 0.04]])

    uncertainty = np.array([0.0])
    converged = np.ones(5, dtype=bool)
    degrees = np.array([10.0])
    median_deg = 5.0

    r_spread = compute_relevance(memberships_spread, uncertainty, converged, degrees, median_deg)
    r_focused = compute_relevance(memberships_focused, uncertainty, converged, degrees, median_deg)

    assert r_focused[0] > r_spread[0]


# --- build_core_halo_mask ---


def _make_chain_adjacency(n=10):
    """Linear chain: 0-1-2-...-9."""
    rows = list(range(n - 1)) + list(range(1, n))
    cols = list(range(1, n)) + list(range(n - 1))
    data = [1.0] * len(rows)
    return sparse.csr_matrix((data, (rows, cols)), shape=(n, n))


def test_core_halo_includes_neighbors():
    """Halo includes 1-hop neighbors of core nodes."""
    adj = _make_chain_adjacency(10)
    # Only node 5 is core
    r = np.zeros(10)
    r[5] = 1.0

    mask = build_core_halo_mask(r, adj, threshold=0.5)
    assert mask[5]  # core
    assert mask[4]  # halo (neighbor of 5)
    assert mask[6]  # halo (neighbor of 5)
    assert not mask[0]  # too far


def test_core_halo_empty_when_no_core():
    """If no nodes exceed threshold, mask is all False."""
    adj = _make_chain_adjacency(10)
    r = np.full(10, 0.1)

    mask = build_core_halo_mask(r, adj, threshold=0.5)
    assert not mask.any()


def test_core_halo_all_when_all_core():
    """If all nodes are core, all are included."""
    adj = _make_chain_adjacency(10)
    r = np.ones(10)

    mask = build_core_halo_mask(r, adj, threshold=0.5)
    assert mask.all()


def test_core_halo_directed_symmetrized():
    """Directed adjacency is symmetrized for neighbor lookup."""
    # Directed: 0→1, 1→2 (no reverse)
    adj = sparse.csr_matrix(
        ([1.0, 1.0], ([0, 1], [1, 2])),
        shape=(3, 3),
    )
    r = np.array([1.0, 0.0, 0.0])

    mask = build_core_halo_mask(r, adj, threshold=0.5)
    assert mask[0]  # core
    assert mask[1]  # halo (neighbor via 0→1 or reverse)
    assert not mask[2]  # 2-hop away from core


# --- reweight_adjacency ---


def test_reweight_shape():
    """Output has same shape as input."""
    adj = sparse.random(20, 20, density=0.1, format="csr")
    r = np.random.rand(20)
    result = reweight_adjacency(adj, r)
    assert result.shape == (20, 20)


def test_reweight_zero_score_kills_edges():
    """Node with r=0 has all its edges zeroed out."""
    adj = sparse.csr_matrix(
        ([1.0, 1.0, 1.0], ([0, 1, 2], [1, 2, 0])),
        shape=(3, 3),
    )
    r = np.array([0.0, 1.0, 1.0])

    result = reweight_adjacency(adj, r)
    dense = result.toarray()
    # Node 0 has r=0: edges 0→1 and 2→0 should be zero
    assert dense[0, 1] == pytest.approx(0.0)
    assert dense[2, 0] == pytest.approx(0.0)
    # Edge 1→2 is preserved (both have r=1)
    assert dense[1, 2] == pytest.approx(1.0)


def test_reweight_all_ones_unchanged():
    """If all r=1.0, adjacency is unchanged."""
    adj = sparse.random(10, 10, density=0.2, format="csr")
    r = np.ones(10)

    result = reweight_adjacency(adj, r)
    diff = result - adj
    assert abs(diff).max() < 1e-10


def test_reweight_symmetric_input_stays_symmetric():
    """Symmetric adjacency stays symmetric after reweighting."""
    adj = sparse.random(20, 20, density=0.1, format="csr")
    adj = adj.maximum(adj.T).tocsr()  # symmetrize
    r = np.random.rand(20)

    result = reweight_adjacency(adj, r)
    diff = result - result.T
    assert diff.nnz == 0 or abs(diff).max() < 1e-10


def test_reweight_is_sparse():
    """Output is sparse CSR."""
    adj = sparse.random(20, 20, density=0.1, format="csr")
    r = np.random.rand(20)

    result = reweight_adjacency(adj, r)
    assert sparse.issparse(result)
    assert result.format == "csr"
