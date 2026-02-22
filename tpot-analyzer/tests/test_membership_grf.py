from __future__ import annotations

import numpy as np
from scipy import sparse

from src.graph.membership_grf import GRFMembershipConfig, compute_grf_membership


def test_grf_membership_balanced_chain_midpoint_near_half() -> None:
    adjacency = sparse.csr_matrix(
        [
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 1.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )

    result = compute_grf_membership(
        adjacency,
        positive_anchor_indices=[0],
        negative_anchor_indices=[2],
        config=GRFMembershipConfig(prior=0.5, regularization=1e-3),
    )

    assert result.probabilities[0] == 1.0
    assert result.probabilities[2] == 0.0
    assert 0.45 <= result.probabilities[1] <= 0.55
    assert result.total_uncertainty[0] == 0.0
    assert result.total_uncertainty[2] == 0.0


def test_grf_membership_biases_toward_stronger_positive_connectivity() -> None:
    adjacency = sparse.csr_matrix(
        [
            [0.0, 3.0, 0.0],
            [3.0, 0.0, 1.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )

    result = compute_grf_membership(
        adjacency,
        positive_anchor_indices=[0],
        negative_anchor_indices=[2],
    )

    assert result.probabilities[1] > 0.5
    assert result.converged is True


def test_grf_membership_requires_both_anchor_classes() -> None:
    adjacency = sparse.csr_matrix(np.eye(3))
    try:
        compute_grf_membership(
            adjacency,
            positive_anchor_indices=[0],
            negative_anchor_indices=[],
        )
    except ValueError as exc:
        assert "negative anchors" in str(exc)
    else:
        raise AssertionError("expected ValueError for missing negative anchors")
