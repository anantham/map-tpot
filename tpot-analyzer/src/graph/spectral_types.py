"""Data contracts for spectral embedding computation and persistence."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np


@dataclass
class SpectralConfig:
    """Configuration for spectral embedding computation."""

    n_dims: int = 30
    eigensolver_tol: float = 1e-10
    eigensolver_maxiter: int = 5000
    linkage_method: str = "ward"
    stability_runs: int = 1
    max_linkage_nodes: int = 12000
    birch_threshold: float = 0.3


@dataclass
class SpectralResult:
    """Result of spectral embedding computation."""

    embedding: np.ndarray
    node_ids: np.ndarray
    eigenvalues: np.ndarray
    linkage_matrix: np.ndarray
    metadata: Dict[str, Any]
    micro_labels: Optional[np.ndarray] = None
    micro_centroids: Optional[np.ndarray] = None
