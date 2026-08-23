from __future__ import annotations

import numpy as np
import pytest

from src.artifacts.relevance_binding import (
    RelevanceBindingError,
    validate_saved_relevance,
)


def test_validates_exact_float32_relevance_vector(tmp_path):
    path = tmp_path / "relevance.npy"
    current = np.array([0.1, 0.2, 0.3], dtype=np.float64)
    np.save(path, current.astype(np.float32))

    digest = validate_saved_relevance(path, current)

    assert len(digest) == 64


def test_rejects_changed_or_malformed_relevance_vector(tmp_path):
    path = tmp_path / "relevance.npy"
    np.save(path, np.array([0.1, 0.25], dtype=np.float32))

    with pytest.raises(RelevanceBindingError, match="value mismatch"):
        validate_saved_relevance(path, np.array([0.1, 0.2]))

    np.save(path, np.array([[0.1, 0.2]], dtype=np.float32))
    with pytest.raises(RelevanceBindingError, match="one-dimensional"):
        validate_saved_relevance(path, np.array([0.1, 0.2]))
