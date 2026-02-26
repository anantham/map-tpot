"""Community-aware semantic affinity matrix construction.

Builds a sparse semantic adjacency from propagation memberships,
then blends it with the topological adjacency for spectral embedding.

CRITICAL: Never materialize M_bias @ M_bias.T densely (95K x 95K = 72GB).
Uses sklearn NearestNeighbors with cosine metric instead.
"""
from __future__ import annotations

import logging

import numpy as np
from scipy import sparse
from sklearn.neighbors import NearestNeighbors

logger = logging.getLogger(__name__)


def build_m_bias(
    memberships: np.ndarray,
    converged: np.ndarray,
    uncertainty: np.ndarray,
) -> np.ndarray:
    """Build confidence-weighted membership matrix for spectral bias.

    Args:
        memberships: (n, K+1) soft memberships from propagation.
            Columns 0..K-1 are communities, column K is "none".
        converged: (K+1,) bool per-class convergence flag.
        uncertainty: (n,) per-node uncertainty [0, 1].

    Returns:
        M_bias: (n, K) confidence-weighted memberships (no "none" column).
        Unconverged classes get 0.3x weight, each node scaled by (1-uncertainty).
    """
    K = memberships.shape[1] - 1  # exclude "none"
    m = memberships[:, :K].copy()

    # Downweight unconverged classes
    confidence_per_class = np.where(converged[:K], 1.0, 0.3)
    m *= confidence_per_class[np.newaxis, :]

    # Downweight uncertain nodes
    confidence_per_node = (1.0 - uncertainty).clip(0.0, 1.0)
    m *= confidence_per_node[:, np.newaxis]

    return m.astype(np.float32)


def build_semantic_adjacency(
    m_bias: np.ndarray,
    top_k: int = 20,
) -> sparse.csr_matrix:
    """Build sparse semantic adjacency via top-k cosine neighbors.

    For each node with nonzero membership, finds the top_k most similar
    nodes by cosine distance on the M_bias vectors.

    Args:
        m_bias: (n, K) confidence-weighted membership matrix.
        top_k: Number of nearest neighbors per node.

    Returns:
        Symmetric sparse CSR matrix (n, n) with cosine similarity weights.
    """
    n = m_bias.shape[0]

    # Find active nodes (nonzero membership vector)
    row_norms = np.linalg.norm(m_bias, axis=1)
    active_mask = row_norms > 1e-10
    active_indices = np.where(active_mask)[0]
    n_active = len(active_indices)

    logger.info(
        "Building A_sem: %d active nodes out of %d total, top_k=%d",
        n_active, n, top_k,
    )

    if n_active < 2:
        return sparse.csr_matrix((n, n), dtype=np.float32)

    # Fit nearest neighbors on active nodes only
    m_active = m_bias[active_indices]
    effective_k = min(top_k + 1, n_active)  # +1 because self is a neighbor
    nn = NearestNeighbors(
        n_neighbors=effective_k,
        metric="cosine",
        algorithm="brute",
    )
    nn.fit(m_active)
    distances, neighbor_idx = nn.kneighbors(m_active)

    # Build sparse matrix in COO format
    rows = []
    cols = []
    vals = []

    for i in range(n_active):
        global_i = active_indices[i]
        for j_pos in range(effective_k):
            local_j = neighbor_idx[i, j_pos]
            global_j = active_indices[local_j]
            if global_i == global_j:
                continue  # skip self-loop
            # Cosine similarity = 1 - cosine distance
            sim = max(1.0 - distances[i, j_pos], 0.0)
            if sim > 1e-10:
                rows.append(global_i)
                cols.append(global_j)
                vals.append(sim)

    if not rows:
        return sparse.csr_matrix((n, n), dtype=np.float32)

    a_sem = sparse.csr_matrix(
        (np.array(vals, dtype=np.float32),
         (np.array(rows), np.array(cols))),
        shape=(n, n),
    )

    # Symmetrize via element-wise max: max(A, A.T)
    a_sem_t = a_sem.T.tocsr()
    a_sem = a_sem.maximum(a_sem_t)

    # Ensure no self-loops
    a_sem.setdiag(0)
    a_sem.eliminate_zeros()

    logger.info("A_sem: %d nonzeros (%.1f per active node)",
                a_sem.nnz, a_sem.nnz / max(n_active, 1))

    return a_sem


def blend_affinity(
    a_topo: sparse.csr_matrix,
    a_sem: sparse.csr_matrix,
    alpha: float,
) -> sparse.csr_matrix:
    """Blend topological and semantic adjacency matrices.

    W' = (1 - alpha) * A_topo + alpha * A_sem

    Args:
        a_topo: Topological adjacency (sparse CSR).
        a_sem: Semantic adjacency (sparse CSR, same shape).
        alpha: Blending weight [0, 1]. 0 = pure topology, 1 = pure semantic.

    Returns:
        Blended sparse CSR matrix.
    """
    if alpha <= 0.0:
        return a_topo.copy().tocsr()
    if alpha >= 1.0:
        return a_sem.copy().tocsr()

    result = (1.0 - alpha) * a_topo + alpha * a_sem
    return result.tocsr()
