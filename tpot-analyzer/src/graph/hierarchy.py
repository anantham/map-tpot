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
    expanded_ids: List[str]  # Which clusters have been expanded (show children)
    collapsed_ids: List[str]  # Which clusters have been collapsed upward (merged into parent)
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


def _subtree_size(linkage_matrix: np.ndarray, node_idx: int, n_leaves: int, memo: Dict[int, int]) -> int:
    """Compute number of leaves under a dendrogram node (cached)."""
    if node_idx in memo:
        return memo[node_idx]
    if node_idx < n_leaves:
        memo[node_idx] = 1
        return 1
    children = _get_children(linkage_matrix, node_idx, n_leaves)
    if not children:
        memo[node_idx] = 1
        return 1
    size = _subtree_size(linkage_matrix, children[0], n_leaves, memo) + _subtree_size(linkage_matrix, children[1], n_leaves, memo)
    memo[node_idx] = size
    return size


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


def _is_descendant(linkage_matrix: np.ndarray, node_idx: int, ancestor_idx: int, n_leaves: int) -> bool:
    """Check if node_idx is a descendant of ancestor_idx (or equal to it)."""
    if node_idx == ancestor_idx:
        return True
    if ancestor_idx < n_leaves:
        # Ancestor is a leaf, can only be descendant if equal
        return False
    # Get all leaves under ancestor and check if node is one of them
    # (or an internal node whose leaves are a subset)
    ancestor_leaves = set(_get_subtree_leaves(linkage_matrix, ancestor_idx, n_leaves))
    if node_idx < n_leaves:
        return node_idx in ancestor_leaves
    node_leaves = set(_get_subtree_leaves(linkage_matrix, node_idx, n_leaves))
    return node_leaves.issubset(ancestor_leaves)


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
    collapsed_ids: Optional[Set[str]] = None,  # Parent IDs to show instead of descendants
    ego_node_id: Optional[str] = None,
    budget: int = 25,
    label_store = None,
    louvain_communities: Optional[Dict[str, int]] = None,
    louvain_weight: float = 0.0,
    expand_depth: float = 0.5,  # 0.0 = conservative (size^0.4), 1.0 = aggressive (size^0.7)
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
        expanded_ids: Set of dendrogram node IDs that have been expanded (show children)
        collapsed_ids: Set of dendrogram node IDs to show instead of their descendants (collapse upward)
        ego_node_id: Ego node for highlighting
        budget: Maximum clusters allowed on screen
        label_store: Optional label store for user labels
        louvain_communities: Optional dict mapping node_id -> Louvain community ID
        louvain_weight: Weight for Louvain fusion (0.0 = pure spectral, 1.0 = heavily favor Louvain)
        expand_depth: Controls expansion aggressiveness (0.0 = size^0.4, 1.0 = size^0.7)
    """
    expanded_ids = expanded_ids or set()
    collapsed_ids = collapsed_ids or set()
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
    subtree_cache: Dict[int, int] = {}
    
    for exp_id in expanded_ids:
        node_idx = _get_node_idx(exp_id)
        if node_idx not in visible_nodes:
            continue
        # Target child count grows with size, controlled by expand_depth
        # expand_depth 0.0 = exponent 0.4 (conservative, ~4 children for size 50)
        # expand_depth 1.0 = exponent 0.7 (aggressive, ~14 children for size 50)
        subtree_sz = _subtree_size(linkage_matrix, node_idx, n_micro, subtree_cache)
        exponent = 0.4 + expand_depth * 0.3
        target_children = max(3, int(subtree_sz ** exponent))
        budget_remaining = budget - len(visible_nodes) + 1  # removing 1 node
        target_children = min(target_children, budget_remaining + 1)  # cannot exceed budget
        # Greedy split: replace node with its children iteratively
        current = {node_idx}
        while len(current) < target_children:
            # pick largest splittable node
            splittable = [(n, _subtree_size(linkage_matrix, n, n_micro, subtree_cache)) for n in current if _get_children(linkage_matrix, n, n_micro)]
            if not splittable:
                break
            splittable.sort(key=lambda x: x[1], reverse=True)
            node_to_split = splittable[0][0]
            children = _get_children(linkage_matrix, node_to_split, n_micro)
            if not children:
                break
            # check budget impact: replacing 1 with 2 => +1
            if len(visible_nodes) - len(current) + (len(current) - 1 + 2) > budget:
                logger.warning("Budget cap hit while expanding %s; stopping at %d visible", exp_id, len(visible_nodes))
                break
            current.remove(node_to_split)
            current.add(children[0])
            current.add(children[1])
        # apply expansion
        visible_nodes.discard(node_idx)
        visible_nodes.update(current)
    
    logger.info("Visible nodes after expansion: %d", len(visible_nodes))
    
    # Step 3b: Apply collapse-upward operations
    # For each collapsed parent, replace its visible descendants with the parent itself
    for col_id in collapsed_ids:
        col_idx = _get_node_idx(col_id)
        # Find all visible nodes that are descendants of this collapsed parent
        descendants_to_remove = set()
        for vis_node in visible_nodes:
            # Check if vis_node is a descendant of col_idx
            if _is_descendant(linkage_matrix, vis_node, col_idx, n_micro):
                descendants_to_remove.add(vis_node)
        
        if descendants_to_remove:
            logger.info(
                "Collapsing %d nodes into parent %s: %s",
                len(descendants_to_remove), col_id, [_get_dendrogram_id(d) for d in descendants_to_remove]
            )
            visible_nodes -= descendants_to_remove
            visible_nodes.add(col_idx)
    
    logger.info("Visible nodes after collapse: %d", len(visible_nodes))
    
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
    
    # Create node_id -> index mapping for in-degree lookups
    node_id_to_idx = {str(nid): i for i, nid in enumerate(node_ids)}
    
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
        
        # Representative handles (uses in-degree as fallback for missing follower counts)
        reps = _get_representative_handles(
            member_node_ids_list, 
            node_metadata,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )
        
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
    
    # Step 5: Compute edges with connectivity metric (with optional Louvain fusion)
    edges = _compute_hierarchical_edges(
        clusters, 
        micro_labels, 
        adjacency, 
        node_ids,
        louvain_communities,
        louvain_weight,
    )
    
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
        collapsed_ids=list(collapsed_ids),
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
    expand_depth: float = 0.5,
) -> Dict:
    """Get preview of what would happen if we expand this cluster.
    
    Returns dict with:
        - can_expand: Whether expansion is possible
        - reason: If can't expand, why not
        - predicted_children: Number of clusters after greedy split
        - predicted_new_total: New total visible count
        - budget_impact: How many slots this will consume (predicted_children - 1)
    """
    node_idx = _get_node_idx(cluster_id)
    children = _get_children(linkage_matrix, node_idx, n_micro)
    
    if children is None:
        return {"can_expand": False, "reason": "Already at maximum detail (micro-cluster level)"}
    
    # Simulate greedy split to predict actual child count
    subtree_cache: Dict[int, int] = {}
    subtree_sz = _subtree_size(linkage_matrix, node_idx, n_micro, subtree_cache)
    exponent = 0.4 + expand_depth * 0.3
    target_children = max(3, int(subtree_sz ** exponent))
    budget_remaining = budget - current_count + 1  # removing 1 node
    target_children = min(target_children, budget_remaining + 1)
    
    # Simulate greedy split
    current = {node_idx}
    while len(current) < target_children:
        splittable = [
            (n, _subtree_size(linkage_matrix, n, n_micro, subtree_cache))
            for n in current if _get_children(linkage_matrix, n, n_micro)
        ]
        if not splittable:
            break
        splittable.sort(key=lambda x: x[1], reverse=True)
        node_to_split = splittable[0][0]
        split_children = _get_children(linkage_matrix, node_to_split, n_micro)
        if not split_children:
            break
        current.remove(node_to_split)
        current.add(split_children[0])
        current.add(split_children[1])
    
    predicted_children = len(current)
    budget_impact = predicted_children - 1  # Net change in visible count
    new_total = current_count + budget_impact
    
    if new_total > budget:
        return {
            "can_expand": False, 
            "reason": f"Budget exceeded. Collapse some clusters first. ({current_count}/{budget})"
        }
    
    return {
        "can_expand": True,
        "predicted_children": predicted_children,
        "predicted_new_total": new_total,
        "budget_impact": budget_impact,
        "budget_remaining_after": budget - new_total,
    }


def _get_representative_handles(
    member_ids: List[str],
    node_metadata: Dict[str, Dict],
    adjacency=None,
    node_id_to_idx: Optional[Dict[str, int]] = None,
    n: int = 3,
) -> List[str]:
    """Pick top-N handles by follower count, with in-degree fallback.
    
    When num_followers is 0/None, uses adjacency in-degree as proxy.
    """
    rows = []
    for node_id in member_ids:
        meta = node_metadata.get(node_id, {})
        handle = meta.get("username") or meta.get("handle") or node_id
        followers = meta.get("num_followers") or 0
        
        # Fallback to in-degree if followers is 0 and we have adjacency
        if followers == 0 and adjacency is not None and node_id_to_idx is not None:
            idx = node_id_to_idx.get(node_id)
            if idx is not None:
                # in-degree = sum of column idx (who points to this node)
                followers = int(adjacency[:, idx].sum())
        
        rows.append((handle, followers))
    rows.sort(key=lambda x: x[1], reverse=True)
    return [h for h, _ in rows[:n]]


def _compute_hierarchical_edges(
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
