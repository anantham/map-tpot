"""Shared non-executable CSR adjacency cache loading.

Legacy pickle caches are deliberately rejected. Rebuild NPZ caches from the
source graph tables; never deserialize an unknown cache to migrate it.
"""
from __future__ import annotations

from pathlib import Path

import scipy.sparse as sp

from src.artifacts.safe_io import load_sparse_cache
from src.config import DEFAULT_ADJACENCY_CACHE


def load_adjacency_cache(path: Path | None = None) -> sp.csr_matrix:
    """Load numeric CSR arrays and JSON metadata with pickle disabled."""
    return load_sparse_cache(Path(path) if path is not None else DEFAULT_ADJACENCY_CACHE)[0]
