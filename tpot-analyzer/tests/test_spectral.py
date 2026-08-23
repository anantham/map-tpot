import numpy as np
import pytest
from scipy.sparse import csr_matrix

from src.graph.spectral import (
    SpectralConfig,
    compute_normalized_laplacian,
    compute_spectral_embedding,
    load_spectral_result,
    save_spectral_result,
)


def test_normalized_laplacian_triangle():
    # Triangle graph: all degrees 2
    adj = csr_matrix(
        [
            [0, 1, 1],
            [1, 0, 1],
            [1, 1, 0],
        ]
    )
    L = compute_normalized_laplacian(adj)
    diag = L.diagonal()
    assert np.allclose(diag, 1.0)
    assert np.isclose(L[0, 1], -0.5)


def test_spectral_embedding_shapes_and_metadata():
    # Two cliques of 5 bridged by one edge
    n = 10
    adj = np.zeros((n, n))
    for i in range(5):
        for j in range(5):
            if i != j:
                adj[i, j] = 1
    for i in range(5, 10):
        for j in range(5, 10):
            if i != j:
                adj[i, j] = 1
    adj[4, 5] = adj[5, 4] = 1
    node_ids = [f"node_{i}" for i in range(n)]

    cfg = SpectralConfig(n_dims=4, stability_runs=2, eigensolver_maxiter=300)
    result = compute_spectral_embedding(csr_matrix(adj), node_ids, cfg)

    assert result.embedding.shape == (n, 4)
    assert len(result.eigenvalues) == 4
    assert result.linkage_matrix.shape[0] == n - 1
    metrics = result.metadata["computation_metrics"]
    assert "stability_ari_mean" in metrics
    assert metrics["stability_ari_mean"] >= 0.0


def test_save_and_load_round_trip(tmp_path):
    adj = csr_matrix(
        [
            [0, 1],
            [1, 0],
        ]
    )
    node_ids = ["a", "b"]
    cfg = SpectralConfig(n_dims=1, eigensolver_maxiter=50)
    result = compute_spectral_embedding(adj, node_ids, cfg)

    base = tmp_path / "graph_snapshot"
    save_spectral_result(result, base)
    loaded = load_spectral_result(base)

    assert np.allclose(result.embedding, loaded.embedding)
    assert np.allclose(result.eigenvalues, loaded.eigenvalues)
    assert np.allclose(result.linkage_matrix, loaded.linkage_matrix)
    assert loaded.metadata["n_nodes"] == 2
    assert loaded.metadata["n_dims"] == result.embedding.shape[1]


def test_spectral_embedding_rejects_node_count_mismatch():
    adjacency = csr_matrix(np.eye(3))

    with pytest.raises(
        ValueError,
        match=r"adjacency shape=.*3, 3.*node_ids=2",
    ):
        compute_spectral_embedding(adjacency, ["a", "b"])


def test_spectral_embedding_rejects_non_square_adjacency():
    adjacency = csr_matrix(np.ones((2, 3)))

    with pytest.raises(ValueError, match=r"adjacency must be square.*2, 3"):
        compute_spectral_embedding(adjacency, ["a", "b"])


def test_spectral_embedding_rejects_duplicate_node_ids():
    adjacency = csr_matrix(np.eye(2))

    with pytest.raises(ValueError, match=r"duplicate node_ids.*a"):
        compute_spectral_embedding(adjacency, ["a", "a"])


def test_spectral_embedding_rejects_multidimensional_node_ids():
    adjacency = csr_matrix(np.eye(2))

    with pytest.raises(ValueError, match="node_ids must be one-dimensional"):
        compute_spectral_embedding(adjacency, np.array([["a"], ["b"]]))


@pytest.mark.parametrize(
    ("adjacency", "message"),
    [
        (csr_matrix([[0.0, np.nan], [1.0, 0.0]]), "finite"),
        (csr_matrix([[0.0, -1.0], [1.0, 0.0]]), "non-negative"),
    ],
)
def test_spectral_embedding_rejects_invalid_adjacency_values(
    adjacency,
    message,
):
    with pytest.raises(ValueError, match=message):
        compute_spectral_embedding(adjacency, ["a", "b"])


def test_spectral_embedding_rejects_invalid_config():
    adjacency = csr_matrix(np.eye(2))

    with pytest.raises(ValueError, match="n_dims must be positive"):
        compute_spectral_embedding(
            adjacency,
            ["a", "b"],
            SpectralConfig(n_dims=0),
        )
