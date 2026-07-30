"""Entropy calculations shared by propagation and display-band code."""

from __future__ import annotations

import math

import numpy as np


def validate_affinity_matrix(affinities: np.ndarray) -> np.ndarray:
    """Return a finite, non-negative 2D float affinity matrix."""
    values = np.asarray(affinities, dtype=np.float64)
    if values.ndim != 2:
        raise ValueError(
            f"affinities must be a 2D array; received shape {values.shape}"
        )
    if not np.all(np.isfinite(values)):
        raise ValueError("affinities must contain only finite values")
    if np.any(values < 0):
        raise ValueError("affinities must be non-negative")
    return values


def normalized_row_entropy(affinities: np.ndarray) -> np.ndarray:
    """Return row-wise Shannon entropy after normalizing non-negative affinities.

    Entropy describes the *relative concentration* of each row, so multiplying
    every value in a row by the same positive constant cannot change it. A
    zero-sum row has no distribution; it receives entropy 0 by convention and
    must be handled by a separate evidence/abstention gate.
    """
    values = validate_affinity_matrix(affinities)
    if values.shape[0] == 0 or values.shape[1] < 2:
        return np.zeros(values.shape[0], dtype=np.float64)

    row_max = values.max(axis=1, keepdims=True)
    scaled = np.divide(
        values,
        row_max,
        out=np.zeros_like(values),
        where=row_max > 0,
    )
    row_sums = scaled.sum(axis=1, keepdims=True)
    probabilities = np.divide(
        scaled,
        row_sums,
        out=np.zeros_like(values),
        where=row_sums > 0,
    )
    positive = probabilities > 0
    contributions = np.zeros_like(probabilities)
    contributions[positive] = (
        probabilities[positive] * np.log(probabilities[positive])
    )
    entropy = -contributions.sum(axis=1) / math.log(values.shape[1])
    return np.clip(entropy, 0.0, 1.0)
