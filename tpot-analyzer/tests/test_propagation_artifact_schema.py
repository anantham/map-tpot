from __future__ import annotations

import numpy as np
import pytest
from scipy import sparse

from src.artifacts.propagation_alignment import (
    ArtifactCompatibilityError,
    select_aligned_propagation,
)
from tests.propagation_artifact_fixtures import write_propagation


def test_rejects_uncertainty_with_extra_axis(tmp_path):
    candidate = tmp_path / "bad_uncertainty.npz"
    write_propagation(
        candidate,
        ["a", "b", "c"],
        extra_arrays={"uncertainty": np.zeros((3, 1))},
    )

    with pytest.raises(
        ArtifactCompatibilityError,
        match=r"uncertainty must have shape.*3",
    ):
        select_aligned_propagation(
            np.array(["a", "b", "c"]),
            sparse.eye(3, format="csr"),
            [candidate],
        )


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        (
            {"memberships": np.array([[0.6, 0.3, 0.1], [np.nan, 0.5, 0.5]])},
            "memberships must contain finite",
        ),
        (
            {
                "memberships": np.array(
                    [[0.6, 0.3, 0.1], [0.4, 0.4, 0.1]]
                ),
                "mode": np.array("classic"),
            },
            "classic memberships rows must sum to 1",
        ),
        (
            {"uncertainty": np.array([0.0, 1.1])},
            "uncertainty must be finite and in",
        ),
        (
            {"converged": np.array([1, 1, 1])},
            "converged must be boolean",
        ),
        (
            {"labeled_mask": np.array([0, 1])},
            "labeled_mask must be boolean",
        ),
        (
            {"community_ids": np.array(["duplicate", "duplicate"])},
            "community_ids must be unique",
        ),
    ],
)
def test_rejects_scientifically_invalid_propagation_values(
    tmp_path,
    replacement,
    message,
):
    candidate = tmp_path / "invalid_values.npz"
    write_propagation(
        candidate,
        ["a", "b"],
        extra_arrays=replacement,
    )

    with pytest.raises(ArtifactCompatibilityError, match=message):
        select_aligned_propagation(
            np.array(["a", "b"]),
            sparse.eye(2, format="csr"),
            [candidate],
        )


def test_accepts_nonnegative_independent_lift_scores(tmp_path):
    candidate = tmp_path / "independent.npz"
    write_propagation(
        candidate,
        ["a", "b"],
        extra_arrays={
            "mode": np.array("independent"),
            "memberships": np.array(
                [[12.0, 3.0, 0.2], [1.5, 0.0, 7.0]],
                dtype=np.float32,
            ),
        },
    )

    result = select_aligned_propagation(
        np.array(["a", "b"]),
        sparse.eye(2, format="csr"),
        [candidate],
    )

    assert result.arrays["mode"].item() == "independent"
