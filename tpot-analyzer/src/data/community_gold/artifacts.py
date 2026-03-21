"""Load graph artifacts needed for evaluator methods."""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Dict

import numpy as np
import scipy.sparse as sp


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
            payload = np.load(path, allow_pickle=True)
            if "node_ids" not in payload:
                continue
            self._node_ids = payload["node_ids"]
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
        path = self.snapshot_dir / "adjacency_matrix_cache.pkl"
        if not path.exists():
            raise FileNotFoundError(f"Missing adjacency artifact: {path}")
        with open(path, "rb") as handle:
            cached = pickle.load(handle)
        adjacency = cached["adjacency"] if isinstance(cached, dict) and "adjacency" in cached else cached
        self._adjacency = adjacency.tocsr()
        return self._adjacency
