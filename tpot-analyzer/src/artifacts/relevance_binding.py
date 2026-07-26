"""Bind recomputed TPOT relevance scores to a saved calibration vector."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from src.artifacts.digests import file_sha256


class RelevanceBindingError(ValueError):
    """Raised when saved relevance is not the current scorer output."""


def validate_saved_relevance(path: Path, current_relevance) -> str:
    """Require exact equality with the producer's persisted float32 scores."""
    path = Path(path)
    try:
        saved = np.load(path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise RelevanceBindingError(
            f"cannot load saved relevance vector {path}: {exc}"
        ) from exc
    current = np.asarray(current_relevance)
    if saved.ndim != 1:
        raise RelevanceBindingError(
            f"saved relevance must be one-dimensional; got shape={saved.shape}"
        )
    if current.ndim != 1:
        raise RelevanceBindingError(
            f"current relevance must be one-dimensional; got shape={current.shape}"
        )
    if saved.dtype != np.float32:
        raise RelevanceBindingError(
            f"saved relevance must use float32 producer format; got {saved.dtype}"
        )
    expected = current.astype(np.float32)
    if saved.shape != expected.shape:
        raise RelevanceBindingError(
            "saved relevance shape mismatch: "
            f"saved={saved.shape}, current={expected.shape}"
        )
    if not np.array_equal(saved, expected):
        differing = int(np.count_nonzero(saved != expected))
        max_difference = float(np.max(np.abs(saved - expected)))
        raise RelevanceBindingError(
            "saved relevance value mismatch: "
            f"differing={differing}/{len(saved)}, "
            f"max_abs_difference={max_difference}"
        )
    return file_sha256(path)
