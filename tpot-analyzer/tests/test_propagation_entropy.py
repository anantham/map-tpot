"""Behavioral contracts for propagation entropy calculations."""

from __future__ import annotations

import numpy as np
import pytest

from scripts.classify_bands import compute_normalized_entropy
from src.propagation.bands import compute_legacy_classic_entropy
from src.propagation.engine import multiclass_entropy


def test_entropy_of_affinities_is_scale_invariant_and_bounded() -> None:
    """Changing affinity units must not change concentration."""
    affinities = np.array(
        [
            [10.0, 2.0, 0.0],
            [5.0, 1.0, 0.0],
        ]
    )

    entropy = compute_normalized_entropy(affinities)

    assert entropy[0] == pytest.approx(entropy[1])
    assert np.all((0.0 <= entropy) & (entropy <= 1.0))


def test_propagation_entropy_preserves_relative_lift_magnitudes() -> None:
    """Values above one must be normalized, not clipped to one."""
    affinities = np.array(
        [
            [100.0, 2.0, 0.0],
            [1.0, 0.02, 0.0],
        ]
    )

    entropy = multiclass_entropy(affinities)

    assert entropy[0] == pytest.approx(entropy[1])


def test_negative_affinity_is_rejected() -> None:
    """Shannon entropy is undefined for negative affinity weights."""
    with pytest.raises(ValueError, match="non-negative"):
        compute_normalized_entropy(np.array([[1.0, -0.1, 0.0]]))


def test_entropy_normalization_does_not_overflow_on_large_finite_lift() -> None:
    """Finite unbounded affinities must retain their relative composition."""
    entropy = compute_normalized_entropy(
        np.array([[1e308, 1e308, 0.0]])
    )

    assert entropy[0] == pytest.approx(np.log(2) / np.log(3))


def test_entropy_accepts_an_empty_batch() -> None:
    entropy = compute_normalized_entropy(np.empty((0, 3)))

    assert entropy.shape == (0,)


@pytest.mark.parametrize("invalid", [np.nan, np.inf, -1.0])
def test_single_column_entropy_still_validates_values(invalid) -> None:
    with pytest.raises(ValueError, match="finite|non-negative"):
        compute_normalized_entropy(np.array([[invalid]]))


def test_legacy_classic_entropy_preserves_tiny_weight_cutoff() -> None:
    entropy = compute_legacy_classic_entropy(
        np.array([[0.5, 1e-12]])
    )
    expected = -(0.5 * np.log(0.5)) / np.log(2)

    assert entropy[0] == pytest.approx(expected, abs=1e-15)
