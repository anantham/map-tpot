"""Fail-fast input validation for spectral embedding."""
from __future__ import annotations

import math

import numpy as np


def validate_spectral_inputs(adjacency, node_ids, config) -> np.ndarray:
    """Validate dimensions, identities, weights, and solver configuration."""
    normalized_ids = np.asarray(list(node_ids))
    if normalized_ids.ndim != 1:
        raise ValueError(
            f"node_ids must be one-dimensional; got shape={normalized_ids.shape}"
        )
    if adjacency.ndim != 2 or adjacency.shape[0] != adjacency.shape[1]:
        raise ValueError(f"adjacency must be square; got shape={adjacency.shape}")
    if adjacency.shape[0] != len(normalized_ids):
        raise ValueError(
            "adjacency shape must match node_ids: "
            f"adjacency shape={adjacency.shape}, node_ids={len(normalized_ids)}"
        )
    if len(normalized_ids) < 2:
        raise ValueError(
            f"spectral embedding requires at least 2 nodes; got {len(normalized_ids)}"
        )
    string_ids = normalized_ids.astype(str)
    unique_ids, counts = np.unique(string_ids, return_counts=True)
    duplicates = unique_ids[counts > 1]
    if len(duplicates):
        raise ValueError(f"duplicate node_ids: sample={duplicates[:5].tolist()}")

    values = np.asarray(adjacency.data)
    if not np.all(np.isfinite(values)):
        raise ValueError("adjacency values must all be finite")
    if np.any(values < 0):
        raise ValueError("adjacency values must be non-negative")

    if isinstance(config.n_dims, bool) or config.n_dims < 1:
        raise ValueError(f"n_dims must be positive; got {config.n_dims!r}")
    if (
        not math.isfinite(float(config.eigensolver_tol))
        or config.eigensolver_tol < 0
    ):
        raise ValueError(
            "eigensolver_tol must be finite and non-negative; "
            f"got {config.eigensolver_tol!r}"
        )
    if config.eigensolver_maxiter < 1:
        raise ValueError(
            f"eigensolver_maxiter must be positive; got {config.eigensolver_maxiter!r}"
        )
    if config.max_linkage_nodes < 2:
        raise ValueError(
            f"max_linkage_nodes must be at least 2; got {config.max_linkage_nodes!r}"
        )
    if (
        not math.isfinite(float(config.birch_threshold))
        or config.birch_threshold <= 0
    ):
        raise ValueError(
            f"birch_threshold must be finite and positive; got {config.birch_threshold!r}"
        )
    return normalized_ids
