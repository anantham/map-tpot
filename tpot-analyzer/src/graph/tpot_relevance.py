"""TPOT relevance scoring and graph reweighting.

Computes a per-node relevance score from propagation posteriors,
builds a core+halo subgraph, and reweights the adjacency for
spectral embedding focused on the TPOT-relevant portion of the graph.

See plan: calibrated relevance scoring (ADR 012 extension).
"""
from __future__ import annotations

import logging

import numpy as np
from scipy import sparse

logger = logging.getLogger(__name__)


def _normalized_entropy(memberships: np.ndarray) -> np.ndarray:
    """Shannon entropy of each row, normalized to [0, 1].

    H_norm(p) = -sum(p_k * log(p_k)) / log(K)
    Returns 0 for deterministic rows, 1 for uniform.
    """
    K = memberships.shape[1]
    if K <= 1:
        return np.zeros(memberships.shape[0])
    p = np.clip(memberships, 1e-10, 1.0)
    raw = -np.sum(p * np.log(p), axis=1)
    return raw / np.log(K)


def compute_relevance(
    memberships: np.ndarray,
    uncertainty: np.ndarray,
    converged: np.ndarray,
    degrees: np.ndarray,
    median_deg: float,
) -> np.ndarray:
    """Compute per-node TPOT relevance score.

    r_i = (1 - p_none) * (1 - H_norm) * c_i * g(deg)

    where:
        p_none = memberships[:, -1] (last column is "none")
        H_norm = normalized entropy of community columns (excl. "none")
        c_i = (1 - uncertainty_i) * max(converged[dominant_class], 0.3)
        g(deg) = min(1, log(1+deg) / log(1+median_deg))

    Args:
        memberships: (n, K+1) soft memberships. Last column is "none".
        uncertainty: (n,) per-node uncertainty in [0, 1].
        converged: (K+1,) bool per-class convergence flag.
        degrees: (n,) node degree in the graph.
        median_deg: Median degree for g(deg) normalization.

    Returns:
        r: (n,) relevance scores in [0, 1].
    """
    n = memberships.shape[0]
    K = memberships.shape[1] - 1  # exclude "none"

    # (1 - p_none): community signal strength
    p_none = memberships[:, -1]
    signal = (1.0 - p_none).clip(0.0, 1.0)

    # (1 - H_norm): signal focus / concentration
    community_memberships = memberships[:, :K]
    # Normalize community columns to sum to 1 for entropy computation
    row_sums = community_memberships.sum(axis=1, keepdims=True)
    safe_sums = np.where(row_sums > 1e-10, row_sums, 1.0)
    normalized = community_memberships / safe_sums
    h_norm = _normalized_entropy(normalized)
    focus = (1.0 - h_norm).clip(0.0, 1.0)

    # c_i: convergence/uncertainty confidence
    # dominant class per node (among community columns only)
    dominant_class = np.argmax(community_memberships, axis=1)
    conv_factor = np.where(converged[dominant_class], 1.0, 0.3)
    unc_factor = (1.0 - uncertainty).clip(0.0, 1.0)
    confidence = conv_factor * unc_factor

    # g(deg): degree gate — adapts to graph density, suppresses leaves, caps hubs
    if median_deg <= 0:
        median_deg = 1.0
    log_norm = np.log(1.0 + median_deg)
    g_deg = np.minimum(1.0, np.log(1.0 + degrees) / log_norm)

    r = signal * focus * confidence * g_deg
    return r.astype(np.float64)


def build_core_halo_mask(
    r_scores: np.ndarray,
    adjacency: sparse.csr_matrix,
    threshold: float,
) -> np.ndarray:
    """Build boolean mask for core + 1-hop halo nodes.

    Core: r_i >= threshold.
    Halo: any node that has at least one core neighbor.

    Args:
        r_scores: (n,) relevance scores.
        adjacency: (n, n) sparse adjacency (directed or undirected).
        threshold: Relevance threshold for core membership.

    Returns:
        mask: (n,) boolean — True for nodes in core+halo.
    """
    n = len(r_scores)
    core_mask = r_scores >= threshold

    # Symmetrize for neighbor lookup (treat edges as undirected)
    sym = adjacency.maximum(adjacency.T).tocsr()

    # Halo: nodes adjacent to any core node
    core_indices = np.flatnonzero(core_mask)
    if len(core_indices) == 0:
        return core_mask

    # Efficient: sum adjacency rows for core nodes
    # If a node has any nonzero entry in a core node's row, it's a halo candidate
    halo_mask = np.zeros(n, dtype=bool)
    for idx in core_indices:
        neighbors = sym[idx].indices
        halo_mask[neighbors] = True

    # Combine: core OR halo (core is already included)
    combined = core_mask | halo_mask
    logger.info(
        "Core+halo: %d core + %d halo = %d total (of %d)",
        core_mask.sum(),
        (combined & ~core_mask).sum(),
        combined.sum(),
        n,
    )
    return combined


def reweight_adjacency(
    adjacency: sparse.csr_matrix,
    r_scores: np.ndarray,
) -> sparse.csr_matrix:
    """Reweight adjacency: W' = D_r^{1/2} * W * D_r^{1/2}.

    Continuously downweights edges involving low-relevance nodes
    without hard-dropping them.

    Args:
        adjacency: (n, n) sparse adjacency (can be directed).
        r_scores: (n,) relevance scores in [0, 1].

    Returns:
        W': (n, n) reweighted sparse CSR matrix.
    """
    sqrt_r = np.sqrt(np.clip(r_scores, 0.0, 1.0))
    D_sqrt = sparse.diags(sqrt_r, format="csr")
    result = D_sqrt @ adjacency @ D_sqrt
    return result.tocsr()
