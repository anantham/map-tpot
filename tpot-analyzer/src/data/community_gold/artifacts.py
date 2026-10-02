"""Load graph artifacts needed for evaluator methods."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import numpy as np
import scipy.sparse as sp

from src.artifacts.safe_io import load_npz_arrays, load_sparse_cache, string_array


class SnapshotArtifacts:
    """Lazy loader for graph-side evaluation artifacts."""

    def __init__(self, snapshot_dir: Path) -> None:
        self.snapshot_dir = Path(snapshot_dir)
        self._node_ids: np.ndarray | None = None
        self._id_to_idx: Dict[str, int] | None = None
        self._adjacency: sp.csr_matrix | None = None
        self._louvain: Dict[str, int] | None = None

    def load_node_ids(self) -> np.ndarray:
        if self._node_ids is not None:
            return self._node_ids
        for name in ("graph_snapshot.spectral.npz", "community_propagation.npz"):
            path = self.snapshot_dir / name
            if not path.exists():
                continue
            payload = load_npz_arrays(path)
            if "node_ids" not in payload:
                continue
            self._node_ids = string_array(payload["node_ids"], label="node IDs")
            return self._node_ids
        raise FileNotFoundError(
            f"Missing node-id artifact in {self.snapshot_dir} (expected graph_snapshot.spectral.npz or community_propagation.npz)"
        )

    def id_to_index(self) -> Dict[str, int]:
        if self._id_to_idx is not None:
            return self._id_to_idx
        node_ids = self.load_node_ids()
        self._id_to_idx = {str(account_id): idx for idx, account_id in enumerate(node_ids)}
        return self._id_to_idx

    def load_louvain(self) -> Dict[str, int]:
        if self._louvain is not None:
            return self._louvain
        path = self.snapshot_dir / "graph_snapshot.louvain.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing Louvain artifact: {path}")
        payload = json.loads(path.read_text())
        self._louvain = {str(account_id): int(cluster_id) for account_id, cluster_id in payload.items()}
        return self._louvain

    def load_adjacency(self) -> sp.csr_matrix:
        if self._adjacency is not None:
            return self._adjacency
        path = self.snapshot_dir / "adjacency_matrix_cache.npz"
        if not path.exists():
            raise FileNotFoundError(f"Missing adjacency artifact: {path}")
        self._adjacency = load_sparse_cache(path)[0]
        return self._adjacency
