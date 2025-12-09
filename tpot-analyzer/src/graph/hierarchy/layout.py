"""Layout and connectivity computation for hierarchical clusters."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.graph.hierarchy.models import HierarchicalCluster, HierarchicalEdge

logger = logging.getLogger(__name__)


def compute_positions(clusters: List[HierarchicalCluster]) -> Dict[str, List[float]]:
    """Compute 2D positions via PCA on centroids."""
    if not clusters:
        return {}
    
    centroids = np.stack([c.centroid for c in clusters])
    centroids = np.nan_to_num(centroids.astype(np.float64))
    centroids -= centroids.mean(axis=0, keepdims=True)
    
    if len(clusters) == 1:
        return {clusters[0].id: [0.0, 0.0]}
    
    try:
        U, S, Vt = np.linalg.svd(centroids, full_matrices=False)
        coords = centroids @ Vt[:2].T
    except Exception as e:
        logger.error("PCA failed: %s, using random positions", e)
        coords = np.random.randn(len(clusters), 2) * 100
    
    positions = {}
    for cluster, pos in zip(clusters, coords):
        x = float(pos[0]) if np.isfinite(pos[0]) else 0.0
        y = float(pos[1]) if np.isfinite(pos[1]) else 0.0
        positions[cluster.id] = [x, y]
    
    return positions


def compute_hierarchical_edges(
    clusters: List[HierarchicalCluster],
    micro_labels: np.ndarray,
    adjacency,
    node_ids: np.ndarray,
    louvain_communities: Optional[Dict[str, int]] = None,
    louvain_weight: float = 0.0,
) -> List[HierarchicalEdge]:
    """Compute edges between clusters with connectivity metric and optional Louvain fusion.
    
    When louvain_weight > 0, edges between nodes in the same Louvain community
    are boosted, while edges between different communities are reduced.
    """
    # Build mapping: micro_cluster -> cluster_id
    micro_to_cluster: Dict[int, str] = {}
    for c in clusters:
        for micro_idx in c.member_micro_indices:
            micro_to_cluster[micro_idx] = c.id
    
    # Build Louvain labels array if available
    louvain_labels: Optional[np.ndarray] = None
    if louvain_communities and louvain_weight > 0:
        louvain_labels = np.array([
            louvain_communities.get(str(nid), -1) 
            for nid in node_ids
        ])
    
    # Count edges between clusters (with optional Louvain weighting)
    edge_counts: Dict[Tuple[str, str], float] = {}
    
    if hasattr(adjacency, "tocoo"):
        coo = adjacency.tocoo()
        rows, cols = coo.row, coo.col
    else:
        rows, cols = np.nonzero(adjacency)
    
    for i, j in zip(rows, cols):
        micro_i = micro_labels[i]
        micro_j = micro_labels[j]
        cluster_i = micro_to_cluster.get(micro_i)
        cluster_j = micro_to_cluster.get(micro_j)
        if cluster_i and cluster_j and cluster_i != cluster_j:
            key = (cluster_i, cluster_j) if cluster_i < cluster_j else (cluster_j, cluster_i)
            
            # Apply Louvain fusion factor
            weight = 1.0
            if louvain_labels is not None:
                same_community = louvain_labels[i] == louvain_labels[j] and louvain_labels[i] != -1
                if same_community:
                    weight = 1.0 + louvain_weight  # Boost same-community edges
                else:
                    weight = max(0.0, 1.0 - louvain_weight)  # Reduce cross-community edges
            
            edge_counts[key] = edge_counts.get(key, 0) + weight
    
    # Get cluster sizes
    sizes = {c.id: c.size for c in clusters}
    
    # Build edges with connectivity
    edges = []
    for (src, tgt), count in edge_counts.items():
        size_product = sizes[src] * sizes[tgt]
        connectivity = count / np.sqrt(size_product) if size_product > 0 else 0
        edges.append(HierarchicalEdge(
            source_id=src,
            target_id=tgt,
            raw_count=int(round(count)),  # Raw count may be fractional with fusion
            connectivity=connectivity,
        ))
    
    return edges
