"""Gaussian random field membership scoring on sparse account graphs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import cg


@dataclass(frozen=True)
class GRFMembershipConfig:
    """Numerical configuration for GRF membership inference."""

    prior: float = 0.5
    regularization: float = 1e-3
    tolerance: float = 1e-6
    max_iter: int = 800
    entropy_weight: float = 0.7
    degree_weight: float = 0.3

    def normalized(self) -> "GRFMembershipConfig":
        prior = float(np.clip(self.prior, 0.0, 1.0))
        regularization = max(0.0, float(self.regularization))
        tolerance = max(1e-10, float(self.tolerance))
        max_iter = int(max(50, self.max_iter))
        entropy_weight = max(0.0, float(self.entropy_weight))
        degree_weight = max(0.0, float(self.degree_weight))
        total = entropy_weight + degree_weight
        if total <= 0:
            entropy_weight, degree_weight = 0.7, 0.3
        else:
            entropy_weight /= total
            degree_weight /= total
        return GRFMembershipConfig(
            prior=prior,
            regularization=regularization,
            tolerance=tolerance,
            max_iter=max_iter,
            entropy_weight=entropy_weight,
            degree_weight=degree_weight,
        )


@dataclass(frozen=True)
class GRFMembershipResult:
    """Membership and uncertainty outputs for all nodes."""

    probabilities: np.ndarray
    total_uncertainty: np.ndarray
    entropy_uncertainty: np.ndarray
    degree_uncertainty: np.ndarray
    converged: bool
    cg_info: int
    cg_iterations: int
    prior: float
    n_positive_anchors: int
    n_negative_anchors: int


class _IterationCounter:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, _xk: np.ndarray) -> None:
        self.count += 1


def _symmetrize_adjacency(adjacency: sp.spmatrix) -> sp.csr_matrix:
    mat = adjacency.tocsr().astype(np.float64)
    sym = mat.maximum(mat.transpose()).tolil()
    sym.setdiag(0.0)
    sym = sym.tocsr()
    sym.eliminate_zeros()
    return sym


def _dedupe_indices(values: Iterable[int], n_nodes: int) -> np.ndarray:
    deduped = sorted({int(v) for v in values if 0 <= int(v) < n_nodes})
    return np.asarray(deduped, dtype=np.int64)


def _binary_entropy(probabilities: np.ndarray) -> np.ndarray:
    p = np.clip(probabilities, 1e-8, 1.0 - 1e-8)
    return -(p * np.log2(p) + (1.0 - p) * np.log2(1.0 - p))


def compute_grf_membership(
    adjacency: sp.spmatrix,
    positive_anchor_indices: Iterable[int],
    negative_anchor_indices: Iterable[int],
    config: GRFMembershipConfig | None = None,
) -> GRFMembershipResult:
    """Solve harmonic-label membership probabilities with Laplacian regularization."""
    cfg = (config or GRFMembershipConfig()).normalized()
    if adjacency.shape[0] != adjacency.shape[1]:
        raise ValueError("adjacency must be square")
    n_nodes = int(adjacency.shape[0])
    if n_nodes == 0:
        raise ValueError("adjacency must be non-empty")

    pos = _dedupe_indices(positive_anchor_indices, n_nodes)
    neg = _dedupe_indices(negative_anchor_indices, n_nodes)
    if pos.size == 0:
        raise ValueError("positive anchors are required")
    if neg.size == 0:
        raise ValueError("negative anchors are required")

    neg_set = set(neg.tolist())
    if any(idx in neg_set for idx in pos.tolist()):
        raise ValueError("anchor sets must be disjoint")

    graph = _symmetrize_adjacency(adjacency)
    degrees = np.asarray(graph.sum(axis=1)).reshape(-1)
    laplacian = sp.diags(degrees, offsets=0, format="csr") - graph

    anchors = np.concatenate([pos, neg])
    anchor_values = np.concatenate(
        [np.ones(pos.size, dtype=np.float64), np.zeros(neg.size, dtype=np.float64)]
    )

    probabilities = np.full(n_nodes, cfg.prior, dtype=np.float64)
    probabilities[pos] = 1.0
    probabilities[neg] = 0.0

    unlabeled_mask = np.ones(n_nodes, dtype=bool)
    unlabeled_mask[anchors] = False
    unlabeled = np.flatnonzero(unlabeled_mask)

    cg_info = 0
    cg_iterations = 0
    converged = True

    if unlabeled.size > 0:
        l_uu = laplacian[unlabeled][:, unlabeled].tocsr()
        l_ul = laplacian[unlabeled][:, anchors].tocsr()
        rhs = -(l_ul @ anchor_values)

        if cfg.regularization > 0:
            l_uu = l_uu + (cfg.regularization * sp.eye(unlabeled.size, format="csr"))
            rhs = rhs + (cfg.regularization * cfg.prior)

        counter = _IterationCounter()
        solution, cg_info = cg(
            l_uu,
            rhs,
            tol=cfg.tolerance,
            maxiter=cfg.max_iter,
            callback=counter,
        )
        cg_iterations = counter.count
        if cg_info < 0:
            raise RuntimeError(f"cg solver failed with info={cg_info}")
        converged = cg_info == 0
        probabilities[unlabeled] = solution

    probabilities = np.clip(probabilities, 0.0, 1.0)

    entropy_uncertainty = _binary_entropy(probabilities)
    degree_uncertainty = 1.0 / np.sqrt(degrees + 1.0)
    max_degree_uncertainty = float(np.max(degree_uncertainty)) if degree_uncertainty.size else 1.0
    if max_degree_uncertainty > 0:
        degree_uncertainty = degree_uncertainty / max_degree_uncertainty

    total_uncertainty = (
        cfg.entropy_weight * entropy_uncertainty
        + cfg.degree_weight * degree_uncertainty
    )
    total_uncertainty = np.clip(total_uncertainty, 0.0, 1.0)
    total_uncertainty[anchors] = 0.0
    entropy_uncertainty[anchors] = 0.0
    degree_uncertainty[anchors] = 0.0

    return GRFMembershipResult(
        probabilities=probabilities,
        total_uncertainty=total_uncertainty,
        entropy_uncertainty=entropy_uncertainty,
        degree_uncertainty=degree_uncertainty,
        converged=converged,
        cg_info=int(cg_info),
        cg_iterations=int(cg_iterations),
        prior=cfg.prior,
        n_positive_anchors=int(pos.size),
        n_negative_anchors=int(neg.size),
    )
