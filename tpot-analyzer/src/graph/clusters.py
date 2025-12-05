"""Cluster utilities for spectral visualization."""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from scipy.cluster.hierarchy import fcluster

logger = logging.getLogger(__name__)

MIN_CLUSTER_SIZE = 4


@dataclass
class ClusterInfo:
    """Information about a single cluster."""

    id: str
    member_indices: List[int]
    member_ids: List[str]
    centroid: np.ndarray
    size: int
    label: str
    label_source: str  # 'auto' or 'user'
    representative_handles: List[str]
    contains_ego: bool = False


@dataclass
class ClusterEdge:
    """Edge between clusters."""

    source_id: str
    target_id: str
    weight: float
    raw_count: int


@dataclass
class ClusterViewData:
    """Complete data for rendering a cluster view."""

    clusters: List[ClusterInfo]
    individual_nodes: List[str]
    edges: List[ClusterEdge]
    ego_cluster_id: Optional[str]
    granularity: int
    total_nodes: int
    positions: Optional[Dict[str, List[float]]] = None
    approximate_mode: bool = False


def cut_hierarchy_at_granularity(linkage_matrix: np.ndarray, n_clusters: int) -> np.ndarray:
    """Cut dendrogram to get specified number of clusters."""
    # Ensure n_clusters doesn't exceed number of items
    max_clusters = linkage_matrix.shape[0] + 1
    n_clusters = min(n_clusters, max_clusters)
    return fcluster(linkage_matrix, t=n_clusters, criterion="maxclust")


def compute_soft_memberships(
    embedding: np.ndarray,
    cluster_labels: np.ndarray,
    temperature: float = 1.0,
) -> np.ndarray:
    """Compute soft cluster memberships via distance-based softmax."""
    unique_labels = np.unique(cluster_labels)
    n_clusters = len(unique_labels)

    centroids = np.zeros((n_clusters, embedding.shape[1]))
    for i, label in enumerate(unique_labels):
        mask = cluster_labels == label
        centroids[i] = embedding[mask].mean(axis=0)

    # Distances to centroids
    dists = np.linalg.norm(embedding[:, None, :] - centroids[None, :, :], axis=2)
    scores = np.exp(-dists / max(temperature, 1e-6))
    scores_sum = scores.sum(axis=1, keepdims=True)
    scores_sum[scores_sum == 0] = 1.0
    memberships = scores / scores_sum
    return memberships


def compute_cluster_edges(
    adjacency,
    cluster_labels: np.ndarray,
    soft_memberships: np.ndarray,
    min_weight: float = 0.0,
) -> List[ClusterEdge]:
    """Compute weighted edges between clusters using membership-weighted counts."""
    unique_labels = np.unique(cluster_labels)
    n_clusters = len(unique_labels)
    label_to_idx = {label: i for i, label in enumerate(unique_labels)}

    # Weighted edges: soft.T @ A @ soft
    if hasattr(adjacency, "dot"):
        soft = soft_memberships.astype(np.float64)
        weighted = soft.T @ (adjacency @ soft)
    else:
        A = np.asarray(adjacency)
        soft = soft_memberships.astype(np.float64)
        weighted = soft.T @ (A @ soft)

    # Raw counts from hard labels
    raw_counts = np.zeros((n_clusters, n_clusters), dtype=int)
    if hasattr(adjacency, "tocoo"):
        coo = adjacency.tocoo()
        rows, cols = coo.row, coo.col
    else:
        rows, cols = np.nonzero(adjacency)
    for i, j in zip(rows, cols):
        ci = label_to_idx[cluster_labels[i]]
        cj = label_to_idx[cluster_labels[j]]
        raw_counts[ci, cj] += 1

    edges: List[ClusterEdge] = []
    for i, label_i in enumerate(unique_labels):
        for j, label_j in enumerate(unique_labels):
            if i == j:
                continue
            weight = float(weighted[i, j])
            if weight < min_weight:
                continue
            edges.append(
                ClusterEdge(
                    source_id=f"cluster_{label_i}",
                    target_id=f"cluster_{label_j}",
                    weight=weight,
                    raw_count=int(raw_counts[i, j]),
                )
            )
    return edges


def get_representative_handles(
    member_ids: List[str],
    node_metadata: Dict[str, Dict],
    n: int = 3,
) -> List[str]:
    """Pick top-N handles by follower count for labeling."""
    rows = []
    for node_id in member_ids:
        meta = node_metadata.get(node_id, {})
        handle = meta.get("username") or meta.get("handle") or node_id
        followers = meta.get("num_followers") or 0
        rows.append((handle, followers))
    rows.sort(key=lambda x: x[1], reverse=True)
    return [h for h, _ in rows[:n]]


def generate_auto_label(cluster_id: int, representative_handles: List[str]) -> str:
    """Generate auto label."""
    if not representative_handles:
        return f"Cluster {cluster_id}"
    handles_str = ", ".join(f"@{h}" for h in representative_handles[:3])
    return f"Cluster {cluster_id}: {handles_str}"


class ClusterLabelStore:
    """SQLite-backed user labels."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cluster_labels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_key TEXT UNIQUE NOT NULL,
                    user_label TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cluster_key 
                ON cluster_labels(cluster_key)
                """
            )

    def get_all_labels(self) -> Dict[str, str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT cluster_key, user_label FROM cluster_labels")
            return {row[0]: row[1] for row in cursor.fetchall()}

    def set_label(self, cluster_key: str, label: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO cluster_labels (cluster_key, user_label)
                VALUES (?, ?)
                ON CONFLICT(cluster_key) DO UPDATE SET
                    user_label = excluded.user_label,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (cluster_key, label),
            )

    def delete_label(self, cluster_key: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM cluster_labels WHERE cluster_key = ?", (cluster_key,))


def _louvain_factors(
    louvain_labels: Optional[np.ndarray],
    louvain_weight: float,
    rows: np.ndarray,
    cols: np.ndarray,
) -> Optional[np.ndarray]:
    """Compute per-edge factors for Louvain co-membership."""
    if louvain_labels is None or louvain_weight <= 0:
        return None
    same = louvain_labels[rows] == louvain_labels[cols]
    factors = np.where(same, 1.0 + louvain_weight, np.maximum(0.0, 1.0 - louvain_weight))
    return factors.astype(np.float64)


def build_cluster_view(
    embedding: np.ndarray,
    linkage_matrix: np.ndarray,
    node_ids: np.ndarray,
    adjacency,
    node_metadata: Dict[str, Dict],
    granularity: int,
    ego_node_id: Optional[str] = None,
    label_store: Optional[ClusterLabelStore] = None,
    louvain_communities: Optional[Dict[str, int]] = None,
    signal_weights: Optional[Dict[str, float]] = None,
    positions: Optional[Dict[str, List[float]]] = None,
    # Approximate mode parameters
    micro_labels: Optional[np.ndarray] = None,
    micro_centroids: Optional[np.ndarray] = None,
) -> ClusterViewData:
    """Build cluster view for a given granularity.
    
    In approximate mode (micro_labels provided):
    - linkage_matrix is over micro-clusters, not individual nodes
    - micro_labels maps each node to its micro-cluster
    - We cut the hierarchy to get macro-cluster assignments for micro-clusters,
      then map back to nodes
    """
    weights = signal_weights or {"spectral": 1.0, "louvain": 0.0}
    
    # Determine if we're in approximate mode
    approximate_mode = micro_labels is not None
    
    if approximate_mode:
        # Approximate mode: linkage is over micro-clusters
        n_micro = linkage_matrix.shape[0] + 1
        
        # Cap granularity at number of micro-clusters
        effective_granularity = min(granularity, n_micro)
        
        # Cut hierarchy to get macro-cluster labels for micro-clusters
        micro_to_macro = cut_hierarchy_at_granularity(linkage_matrix, effective_granularity)
        
        # Map back to node labels: node -> micro -> macro
        # micro_labels[i] is the micro-cluster for node i (0-indexed)
        # micro_to_macro[micro] is the macro-cluster for that micro-cluster (1-indexed from fcluster)
        node_cluster_labels = np.array([micro_to_macro[m] for m in micro_labels])
        
        logger.info(
            "Approximate mode: %d nodes -> %d micro-clusters -> %d macro-clusters (requested %d)",
            len(node_ids), n_micro, len(np.unique(node_cluster_labels)), granularity
        )
        logger.info(
            "micro_labels shape=%s, range=[%d, %d], micro_to_macro shape=%s, node_cluster_labels unique=%d",
            micro_labels.shape, micro_labels.min(), micro_labels.max(),
            micro_to_macro.shape, len(np.unique(node_cluster_labels))
        )
    else:
        # Exact mode: linkage is over all nodes
        node_cluster_labels = cut_hierarchy_at_granularity(linkage_matrix, granularity)
        logger.info("Exact mode: %d nodes -> %d clusters", len(node_ids), len(np.unique(node_cluster_labels)))
    
    unique_labels = np.unique(node_cluster_labels)

    # Soft memberships always computed on node embedding
    soft_memberships = compute_soft_memberships(embedding, node_cluster_labels)

    ego_cluster_label = None
    if ego_node_id is not None:
        ego_idx = np.where(node_ids == ego_node_id)[0]
        if len(ego_idx):
            ego_cluster_label = node_cluster_labels[ego_idx[0]]

    user_labels = label_store.get_all_labels() if label_store else {}

    clusters: List[ClusterInfo] = []
    individual_nodes: List[str] = []
    for label in unique_labels:
        mask = node_cluster_labels == label
        member_indices = np.where(mask)[0].tolist()
        member_ids = node_ids[mask].tolist()

        if len(member_ids) < MIN_CLUSTER_SIZE:
            individual_nodes.extend(member_ids)
            continue

        # Centroid from node embeddings
        centroid = embedding[mask].mean(axis=0)
        
        reps = get_representative_handles(member_ids, node_metadata)
        ws = round(weights.get("spectral", 1.0), 1)
        wl = round(weights.get("louvain", 0.0), 1)
        key = f"spectral_w{ws:.1f}_l{wl:.1f}_n{granularity}_c{label}"
        user_label = user_labels.get(key)

        clusters.append(
            ClusterInfo(
                id=f"cluster_{label}",
                member_indices=member_indices,
                member_ids=member_ids,
                centroid=centroid,
                size=len(member_ids),
                label=user_label or generate_auto_label(label, reps),
                label_source="user" if user_label else "auto",
                representative_handles=reps,
                contains_ego=(label == ego_cluster_label),
            )
        )

    # Prepare Louvain labels aligned to node order
    louvain_labels_arr: Optional[np.ndarray] = None
    if louvain_communities:
        l_labels = []
        for nid in node_ids:
            l_labels.append(louvain_communities.get(str(nid), -1))
        louvain_labels_arr = np.array(l_labels)

    louvain_weight = round(weights.get("louvain", 0.0), 1)

    edges = _compute_cluster_edges_with_fusion(
        adjacency=adjacency,
        cluster_labels=node_cluster_labels,
        soft_memberships=soft_memberships,
        louvain_labels=louvain_labels_arr,
        louvain_weight=louvain_weight,
        min_weight=0.0,
    )

    ego_cluster_id = f"cluster_{ego_cluster_label}" if ego_cluster_label is not None else None

    logger.info(
        "build_cluster_view result: %d clusters, %d individual_nodes, %d edges, approximate=%s",
        len(clusters), len(individual_nodes), len(edges), approximate_mode
    )
    
    return ClusterViewData(
        clusters=clusters,
        individual_nodes=individual_nodes,
        edges=edges,
        ego_cluster_id=ego_cluster_id,
        granularity=granularity,
        total_nodes=len(node_ids),
        positions=positions,
        approximate_mode=approximate_mode,
    )


def _compute_cluster_edges_with_fusion(
    adjacency,
    cluster_labels: np.ndarray,
    soft_memberships: np.ndarray,
    louvain_labels: Optional[np.ndarray],
    louvain_weight: float,
    min_weight: float = 0.0,
) -> List[ClusterEdge]:
    """Compute cluster edges with optional Louvain fusion."""
    unique_labels = np.unique(cluster_labels)
    n_clusters = len(unique_labels)
    label_to_idx = {label: i for i, label in enumerate(unique_labels)}

    # Build modified adjacency for weighted edges
    if hasattr(adjacency, "tocoo"):
        coo = adjacency.tocoo()
        factors = _louvain_factors(louvain_labels, louvain_weight, coo.row, coo.col)
        data = coo.data if factors is None else coo.data * factors
        adj_mod = adjacency.__class__((data, (coo.row, coo.col)), shape=adjacency.shape).tocsr()
        rows, cols = coo.row, coo.col
    else:
        A = np.asarray(adjacency, dtype=float)
        rows, cols = np.nonzero(A)
        if louvain_labels is not None and louvain_weight > 0:
            same = louvain_labels[:, None] == louvain_labels[None, :]
            factors = np.where(same, 1.0 + louvain_weight, np.maximum(0.0, 1.0 - louvain_weight))
            adj_mod = A * factors
        else:
            adj_mod = A

    soft = soft_memberships.astype(np.float64)
    weighted = soft.T @ (adj_mod @ soft)

    # Raw counts from hard labels (unmodified adjacency)
    raw_counts = np.zeros((n_clusters, n_clusters), dtype=int)
    for i, j in zip(rows, cols):
        ci = label_to_idx[cluster_labels[i]]
        cj = label_to_idx[cluster_labels[j]]
        raw_counts[ci, cj] += 1

    edges: List[ClusterEdge] = []
    for i, label_i in enumerate(unique_labels):
        for j, label_j in enumerate(unique_labels):
            if i == j:
                continue
            weight = float(weighted[i, j])
            if weight < min_weight:
                continue
            edges.append(
                ClusterEdge(
                    source_id=f"cluster_{label_i}",
                    target_id=f"cluster_{label_j}",
                    weight=weight,
                    raw_count=int(raw_counts[i, j]),
                )
            )
    return edges
