"""Shared adjacency matrix loading and construction.

Consolidates the load_adjacency() function that was duplicated across
propagate_community_labels.py, calibrate_tpot_threshold.py, and build_tpot_spectral.py.

SECURITY NOTE: pickle is used intentionally here to load our own precomputed
sparse matrices from data/adjacency_matrix_cache.pkl. This file is generated
by cluster_routes.py from parquet data we control — never from untrusted sources.
"""
from __future__ import annotations

import logging
import pickle  # noqa: S403 — loading our own cached adjacency, not untrusted data
from pathlib import Path

import scipy.sparse as sp

from src.config import DEFAULT_ADJACENCY_CACHE

logger = logging.getLogger(__name__)


def load_adjacency_cache(path: Path | None = None) -> sp.csr_matrix:
    """Load the cached adjacency matrix (built by cluster_routes.py on startup).

    Args:
        path: Path to the adjacency cache. Defaults to data/adjacency_matrix_cache.pkl.
    """
    if path is None:
        path = DEFAULT_ADJACENCY_CACHE
    with open(path, "rb") as f:  # noqa: S301
        cached = pickle.load(f)  # noqa: S301
    if isinstance(cached, dict) and "adjacency" in cached:
        return cached["adjacency"].tocsr()
    return cached.tocsr()
