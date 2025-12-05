"""Hierarchical cluster navigation with expand/collapse support."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from scipy.cluster.hierarchy import fcluster, leaders

logger = logging.getLogger(__name__)


@dataclass
class HierarchicalCluster:
    """A cluster with hierarchy info for navigation."""
    
    id: str  # Dendrogram node ID: "d_XXX"
    dendrogram_node: int  # Raw node index in dendrogram
    parent_id: Optional[str]  # Parent dendrogram node ID
    children_ids: Optional[Tuple[str, str]]  # Child dendrogram node IDs (if internal node)
    member_micro_indices: List[int]  # Which micro-clusters belong to this cluster
    member_node_ids: List[str]  # Which original nodes belong to this cluster
    centroid: np.ndarray
    size: int
    label: str
    label_source: str
    representative_handles: List[str]
    contains_ego: bool = False
    is_leaf: bool = False  # True if this is a micro-cluster (can't expand further)


@dataclass 
class HierarchicalEdge:
    """Edge between clusters with connectivity metric."""
    
    source_id: str
    target_id: str
    raw_count: int  # Actual edge count between clusters
    connectivity: float  # Normalized: raw_count / sqrt(size_A * size_B)
    

@dataclass
class HierarchicalViewData:
    """Complete data for hierarchical cluster view."""
    
    clusters: List[HierarchicalCluster]
    edges: List[HierarchicalEdge]
    ego_cluster_id: Optional[str]
    total_nodes: int
    n_micro_clusters: int
    positions: Dict[str, List[float]]
    expanded_ids: List[str]  # Which clusters have been expanded
    budget: int  # Max clusters allowed
    budget_remaining: int  # How many more can be added


def _get_dendrogram_id(node_idx: int) -> str:
    """Convert dendrogram node index to string ID."""
    return f"d_{node_idx}"


def _get_node_idx(dendrogram_id: str) -> int:
    """Convert string ID back to node index."""
    return int(dendrogram_id.split("_")[1])


def _get_children(linkage_matrix: np.ndarray, node_idx: int, n_leaves: int) -> Optional[Tuple[int, int]]:
    """Get children of a dendrogram internal node."""
    if node_idx < n_leaves:
        return None  # Leaf node, no children
    row = node_idx - n_leaves
    if row < 0 or row >= len(linkage_matrix):
        return None
    left = int(linkage_matrix[row, 0])
    right = int(linkage_matrix[row, 1])
    return (left, right)


def _get_parent(linkage_matrix: np.ndarray, node_idx: int, n_leaves: int) -> Optional[int]:
    """Get parent of a dendrogram node."""
    for i, row in enumerate(linkage_matrix):
        if int(row[0]) == node_idx or int(row[1]) == node_idx:
            return n_leaves + i
    return None  # Root has no parent


def _get_subtree_leaves(linkage_matrix: np.ndarray, node_idx: int, n_leaves: int) -> List[int]:
    """Get all leaf indices under this dendrogram node."""
    if node_idx < n_leaves:
        return [node_idx]
    children = _get_children(linkage_matrix, node_idx, n_leaves)
    if children is None:
        return [node_idx]
    left, right = children
    return _get_subtree_leaves(linkage_matrix, left, n_leaves) + \
           _get_subtree_leaves(linkage_matrix, right, n_leaves)


def _get_siblings(linkage_matrix: np.ndarray, node_idx: int, n_leaves: int) -> Optional[int]:
    """Get sibling of a dendrogram node."""
    parent = _get_parent(linkage_matrix, node_idx, n_leaves)
    if parent is None:
        return None
    children = _get_children(linkage_matrix, parent, n_leaves)
    if children is None:
        return None
    left, right = children
    return right if left == node_idx else left


def _find_cluster_leaders(linkage_matrix: np.ndarray, labels: np.ndarray, n_leaves: int) -> Dict[int, int]:
    """Find the dendrogram node that represents each cluster label.
    
    Returns: dict mapping cluster_label -> dendrogram_node_idx
    """
    # Use scipy's leaders function
    leader_nodes, leader_labels = leaders(linkage_matrix, labels)
    return {int(label): int(node) for node, label in zip(leader_nodes, leader_labels)}


def build_hierarchical_view(
    linkage_matrix: np.ndarray,
    micro_labels: np.ndarray,  # (n_nodes,) micro-cluster assignment for each node
    micro_centroids: np.ndarray,  # (n_micro, n_dims) centroid for each micro-cluster
    node_ids: np.ndarray,
    adjacency,
    node_metadata: Dict[str, Dict],
    base_granularity: int = 15,
    expanded_ids: Optional[Set[str]] = None,
    ego_node_id: Optional[str] = None,
    budget: int = 25,
    label_store = None,
) -> HierarchicalViewData:
    """Build hierarchical cluster view with expand/collapse support.
    
    Args:
        linkage_matrix: Hierarchical clustering over micro-clusters
        micro_labels: Maps each node to its micro-cluster index
        micro_centroids: Centroid embedding for each micro-cluster
        node_ids: Original node IDs
        adjacency: Sparse adjacency matrix
        node_metadata: Metadata dict per node
        base_granularity: Initial number of clusters before expansion
        expanded_ids: Set of dendrogram node IDs that have been expanded
        ego_node_id: Ego node for highlighting
        budget: Maximum clusters allowed on screen
        label_store: Optional label store for user labels
    """
    expanded_ids = expanded_ids or set()
    n_micro = len(micro_centroids)  # Number of micro-clusters (leaves in dendrogram)
    
    logger.info(
        "Building hierarchical view: %d micro-clusters, base_granularity=%d, expanded=%s",
        n_micro, base_granularity, expanded_ids
    )
    
    # Step 1: Get base cut
    base_granularity = min(base_granularity, n_micro, budget)
    base_labels = fcluster(linkage_matrix, t=base_granularity, criterion="maxclust")
    
    # Step 2: Find dendrogram nodes for each base cluster
    label_to_leader = _find_cluster_leaders(linkage_matrix, base_labels, n_micro)
    
    # Step 3: Build visible set by starting with base clusters, then expanding
    visible_nodes: Set[int] = set(label_to_leader.values())
    
    for exp_id in expanded_ids:
        node_idx = _get_node_idx(exp_id)
        if node_idx in visible_nodes:
            # Replace this node with its children
            children = _get_children(linkage_matrix, node_idx, n_micro)
            if children:
                # Expanding replaces 1 with 2 => net +1; enforce budget
                if len(visible_nodes) + 1 > budget:
                    logger.warning(
                        "Skipping expansion of %s (budget %d would be exceeded by +1)",
                        exp_id, budget
                    )
                    continue
                visible_nodes.discard(node_idx)
                visible_nodes.add(children[0])
                visible_nodes.add(children[1])
    
    logger.info("Visible nodes after expansion: %d", len(visible_nodes))
    
    # Step 4: Build cluster info for each visible node
    # First, map micro-clusters to nodes
    micro_to_nodes: Dict[int, List[int]] = {}  # micro_idx -> list of node indices
    for node_idx, micro_idx in enumerate(micro_labels):
        if micro_idx not in micro_to_nodes:
            micro_to_nodes[micro_idx] = []
        micro_to_nodes[micro_idx].append(node_idx)
    
    # Find ego's micro-cluster
    ego_micro = None
    if ego_node_id is not None:
        ego_indices = np.where(node_ids == ego_node_id)[0]
        if len(ego_indices):
            ego_micro = micro_labels[ego_indices[0]]
    
    clusters: List[HierarchicalCluster] = []
    user_labels = label_store.get_all_labels() if label_store else {}
    
    for dend_node in sorted(visible_nodes):
        # Get all micro-cluster leaves under this dendrogram node
        micro_leaves = _get_subtree_leaves(linkage_matrix, dend_node, n_micro)
        
        # Get all original nodes in these micro-clusters
        member_node_indices = []
        for micro_idx in micro_leaves:
            member_node_indices.extend(micro_to_nodes.get(micro_idx, []))
        member_node_ids_list = node_ids[member_node_indices].tolist()
        
        # Compute centroid from micro-cluster centroids
        if micro_leaves:
            centroid = micro_centroids[micro_leaves].mean(axis=0)
        else:
            centroid = np.zeros(micro_centroids.shape[1])
        
        # Get parent and children
        parent_idx = _get_parent(linkage_matrix, dend_node, n_micro)
        children = _get_children(linkage_matrix, dend_node, n_micro)
        
        # Check if contains ego
        contains_ego = ego_micro is not None and ego_micro in micro_leaves
        
        # Representative handles
        reps = _get_representative_handles(member_node_ids_list, node_metadata)
        
        # Label
        dend_id = _get_dendrogram_id(dend_node)
        user_label = user_labels.get(dend_id)
        auto_label = f"Cluster {dend_node}: " + ", ".join(f"@{h}" for h in reps[:3]) if reps else f"Cluster {dend_node}"
        
        is_leaf = dend_node < n_micro  # Micro-cluster level = can't expand further
        
        clusters.append(HierarchicalCluster(
            id=dend_id,
            dendrogram_node=dend_node,
            parent_id=_get_dendrogram_id(parent_idx) if parent_idx is not None else None,
            children_ids=(_get_dendrogram_id(children[0]), _get_dendrogram_id(children[1])) if children else None,
            member_micro_indices=micro_leaves,
            member_node_ids=member_node_ids_list,
            centroid=centroid,
            size=len(member_node_ids_list),
            label=user_label or auto_label,
            label_source="user" if user_label else "auto",
            representative_handles=reps,
            contains_ego=contains_ego,
            is_leaf=is_leaf,
        ))
    
    # Step 5: Compute edges with connectivity metric
    edges = _compute_hierarchical_edges(clusters, micro_labels, adjacency)
    
    # Step 6: Compute positions via PCA on centroids
    positions = _compute_positions(clusters)
    
    # Find ego cluster
    ego_cluster_id = None
    for c in clusters:
        if c.contains_ego:
            ego_cluster_id = c.id
            break
    
    return HierarchicalViewData(
        clusters=clusters,
        edges=edges,
        ego_cluster_id=ego_cluster_id,
        total_nodes=len(node_ids),
        n_micro_clusters=n_micro,
        positions=positions,
        expanded_ids=list(expanded_ids),
        budget=budget,
        budget_remaining=budget - len(clusters),
    )


def get_collapse_preview(
    linkage_matrix: np.ndarray,
    n_micro: int,
    cluster_id: str,
    visible_ids: Set[str],
) -> Dict:
    """Get preview of what would happen if we collapse this cluster.
    
    Returns dict with:
        - parent_id: The parent cluster that would replace the siblings
        - sibling_ids: List of cluster IDs that would be merged
        - can_collapse: Whether collapse is possible
    """
    node_idx = _get_node_idx(cluster_id)
    parent_idx = _get_parent(linkage_matrix, node_idx, n_micro)
    
    if parent_idx is None:
        return {"can_collapse": False, "reason": "Already at root level"}
    
    # Get all children of the parent
    children = _get_children(linkage_matrix, parent_idx, n_micro)
    if children is None:
        return {"can_collapse": False, "reason": "Parent has no children"}
    
    # Find all visible nodes that are descendants of this parent
    def get_visible_descendants(node):
        node_id = _get_dendrogram_id(node)
        if node_id in visible_ids:
            return [node_id]
        children = _get_children(linkage_matrix, node, n_micro)
        if children is None:
            return []
        return get_visible_descendants(children[0]) + get_visible_descendants(children[1])
    
    siblings = get_visible_descendants(parent_idx)
    
    return {
        "can_collapse": True,
        "parent_id": _get_dendrogram_id(parent_idx),
        "sibling_ids": siblings,
        "nodes_freed": len(siblings) - 1,  # How many nodes we gain back in budget
    }


def get_expand_preview(
    linkage_matrix: np.ndarray,
    n_micro: int,
    cluster_id: str,
    current_count: int,
    budget: int,
) -> Dict:
    """Get preview of what would happen if we expand this cluster.
    
    Returns dict with:
        - children_ids: The two child cluster IDs
        - can_expand: Whether expansion is possible
        - reason: If can't expand, why not
    """
    node_idx = _get_node_idx(cluster_id)
    children = _get_children(linkage_matrix, node_idx, n_micro)
    
    if children is None:
        return {"can_expand": False, "reason": "Already at maximum detail (micro-cluster level)"}
    
    # Expanding removes 1 and adds 2, net +1
    if current_count + 1 > budget:
        return {
            "can_expand": False, 
            "reason": f"Budget exceeded. Collapse some clusters first. ({current_count}/{budget})"
        }
    
    return {
        "can_expand": True,
        "children_ids": [_get_dendrogram_id(children[0]), _get_dendrogram_id(children[1])],
        "new_count": current_count + 1,
    }


def _get_representative_handles(
    member_ids: List[str],
    node_metadata: Dict[str, Dict],
    n: int = 3,
) -> List[str]:
    """Pick top-N handles by follower count."""
    rows = []
    for node_id in member_ids:
        meta = node_metadata.get(node_id, {})
        handle = meta.get("username") or meta.get("handle") or node_id
        followers = meta.get("num_followers") or 0
        rows.append((handle, followers))
    rows.sort(key=lambda x: x[1], reverse=True)
    return [h for h, _ in rows[:n]]


def _compute_hierarchical_edges(
    clusters: List[HierarchicalCluster],
    micro_labels: np.ndarray,
    adjacency,
) -> List[HierarchicalEdge]:
    """Compute edges between clusters with connectivity metric."""
    # Build mapping: micro_cluster -> cluster_id
    micro_to_cluster: Dict[int, str] = {}
    for c in clusters:
        for micro_idx in c.member_micro_indices:
            micro_to_cluster[micro_idx] = c.id
    
    # Count edges between clusters
    edge_counts: Dict[Tuple[str, str], int] = {}
    
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
            edge_counts[key] = edge_counts.get(key, 0) + 1
    
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
            raw_count=count,
            connectivity=connectivity,
        ))
    
    return edges


def _compute_positions(clusters: List[HierarchicalCluster]) -> Dict[str, List[float]]:
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
