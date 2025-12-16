"""Hierarchical cluster navigation with expand/collapse support."""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from scipy.cluster.hierarchy import fcluster

from src.graph.hierarchy.models import (
    HierarchicalCluster,
    HierarchicalViewData,
)
from src.graph.hierarchy.traversal import (
    find_cluster_leaders,
    get_children,
    get_dendrogram_id,
    get_node_idx,
    get_parent,
    get_subtree_leaves,
    is_descendant,
    subtree_size,
)
from src.graph.hierarchy.focus import reveal_leaf_in_visible_set
from src.graph.hierarchy.layout import (
    compute_hierarchical_edges,
    compute_positions,
)

logger = logging.getLogger(__name__)


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
    focus_leaf_id: Optional[str] = None,  # Leaf cluster ID to ensure becomes visible (teleport)
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
    expected_rows = max(0, n_micro - 1)
    if linkage_matrix.shape[0] != expected_rows:
        n_leaves_in_linkage = linkage_matrix.shape[0] + 1
        raise ValueError(
            "linkage_matrix shape mismatch: expected %d rows for %d micro-clusters, got %d rows "
            "(linkage implies %d leaves). Compute linkage over micro_centroids (n_micro x d), "
            "or ensure micro_centroids matches the linkage leaves."
            % (expected_rows, n_micro, linkage_matrix.shape[0], n_leaves_in_linkage)
        )
    t_start = time.time()
    
    logger.info(
        "Building hierarchical view: %d micro-clusters, base_granularity=%d, expanded=%s",
        n_micro, base_granularity, expanded_ids
    )
    
    # Step 1: Get base cut
    base_granularity = min(base_granularity, n_micro, budget)
    t0 = time.time()
    base_labels = fcluster(linkage_matrix, t=base_granularity, criterion="maxclust")
    logger.info("hierarchy timing: fcluster=%.2fs granularity=%d", time.time() - t0, base_granularity)
    
    # Step 2: Find dendrogram nodes for each base cluster
    label_to_leader = find_cluster_leaders(linkage_matrix, base_labels, n_micro)
    
    # Step 3: Build visible set by starting with base clusters, then expanding
    visible_nodes: Set[int] = set(label_to_leader.values())
    subtree_cache: Dict[int, int] = {}
    
    logger.info(
        "Expansion phase: visible_nodes=%s expanded_ids=%s",
        sorted(visible_nodes)[:20],  # First 20 to avoid spam
        expanded_ids,
    )

    # Optional: deterministically reveal a specific leaf (used for "teleport to account")
    if focus_leaf_id:
        try:
            leaf_idx = get_node_idx(focus_leaf_id)
            result = reveal_leaf_in_visible_set(
                visible_nodes=visible_nodes,
                linkage_matrix=linkage_matrix,
                leaf_idx=leaf_idx,
                n_leaves=n_micro,
                budget=budget,
            )
            logger.info(
                "focus leaf applied: leaf=%s ok=%s steps=%d visible_now=%d reason=%s",
                focus_leaf_id,
                result.ok,
                result.steps,
                len(visible_nodes),
                result.reason,
            )
        except Exception as exc:
            logger.warning("Failed to apply focus leaf %s: %s", focus_leaf_id, exc)
    
    for exp_id in expanded_ids:
        t_exp_start = time.time()
        try:
            node_idx = get_node_idx(exp_id)
        except Exception as e:
            logger.warning("Invalid expanded_id %s: %s", exp_id, e)
            continue
        if node_idx not in visible_nodes:
            logger.info("Skipping expand %s (node %d not in visible_nodes)", exp_id, node_idx)
            continue
        # Target child count grows with size, controlled by expand_depth
        # expand_depth 0.0 = exponent 0.4 (conservative, ~4 children for size 50)
        # expand_depth 1.0 = exponent 0.7 (aggressive, ~14 children for size 50)
        subtree_sz = subtree_size(linkage_matrix, node_idx, n_micro, subtree_cache)
        exponent = 0.4 + expand_depth * 0.3
        target_children = max(3, int(subtree_sz ** exponent))
        budget_remaining = budget - len(visible_nodes) + 1  # removing 1 node
        target_children = min(target_children, budget_remaining + 1)  # cannot exceed budget
        # Greedy split: replace node with its children iteratively
        current = {node_idx}
        while len(current) < target_children:
            # pick largest splittable node
            splittable = [(n, subtree_size(linkage_matrix, n, n_micro, subtree_cache)) for n in current if get_children(linkage_matrix, n, n_micro)]
            if not splittable:
                break
            splittable.sort(key=lambda x: x[1], reverse=True)
            node_to_split = splittable[0][0]
            children = get_children(linkage_matrix, node_to_split, n_micro)
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
        logger.info(
            "hierarchy timing: expand_node=%.2fs node=%s target_children=%d visible_now=%d",
            time.time() - t_exp_start,
            exp_id,
            target_children,
            len(visible_nodes),
        )
    
    logger.info("Visible nodes after expansion: %d", len(visible_nodes))
    
    # Step 3b: Apply collapse-upward operations
    # For each collapsed parent, replace its visible descendants with the parent itself
    for col_id in collapsed_ids:
        col_idx = get_node_idx(col_id)
        # Find all visible nodes that are descendants of this collapsed parent
        descendants_to_remove = set()
        for vis_node in visible_nodes:
            # Check if vis_node is a descendant of col_idx
            if is_descendant(linkage_matrix, vis_node, col_idx, n_micro):
                descendants_to_remove.add(vis_node)
        
        if descendants_to_remove:
            logger.info(
                "Collapsing %d nodes into parent %s: %s",
                len(descendants_to_remove), col_id, [get_dendrogram_id(d) for d in descendants_to_remove]
            )
            visible_nodes -= descendants_to_remove
            visible_nodes.add(col_idx)
    
    logger.info("Visible nodes after collapse: %d", len(visible_nodes))

    # Step 4: Build cluster info for each visible node
    t_cluster_info = time.time()
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
    in_degrees = None
    if adjacency is not None:
        try:
            in_degrees = np.array(adjacency.sum(axis=0)).ravel()
        except Exception:
            in_degrees = None
    
    clusters: List[HierarchicalCluster] = []
    user_labels = label_store.get_all_labels() if label_store else {}
    
    for dend_node in sorted(visible_nodes):
        # Get all micro-cluster leaves under this dendrogram node
        micro_leaves = get_subtree_leaves(linkage_matrix, dend_node, n_micro)
        
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
        parent_idx = get_parent(linkage_matrix, dend_node, n_micro)
        children = get_children(linkage_matrix, dend_node, n_micro)
        
        # Check if contains ego
        contains_ego = ego_micro is not None and ego_micro in micro_leaves
        
        # Representative handles (uses in-degree as fallback for missing follower counts)
        reps = _get_representative_handles(
            member_node_ids_list, 
            node_metadata,
            in_degrees=in_degrees,
            node_id_to_idx=node_id_to_idx,
        )
        
        # Label
        dend_id = get_dendrogram_id(dend_node)
        user_label = user_labels.get(dend_id)
        auto_label = f"Cluster {dend_node}: " + ", ".join(f"@{h}" for h in reps[:3]) if reps else f"Cluster {dend_node}"
        
        is_leaf = dend_node < n_micro  # Micro-cluster level = can't expand further
        
        clusters.append(HierarchicalCluster(
            id=dend_id,
            dendrogram_node=dend_node,
            parent_id=get_dendrogram_id(parent_idx) if parent_idx is not None else None,
            children_ids=(get_dendrogram_id(children[0]), get_dendrogram_id(children[1])) if children else None,
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
    logger.info("hierarchy timing: cluster_info=%.2fs clusters=%d", time.time() - t_cluster_info, len(clusters))

    # Step 5: Compute edges with connectivity metric (with optional Louvain fusion)
    t_edges_start = time.time()
    edges = compute_hierarchical_edges(
        clusters, 
        micro_labels, 
        adjacency, 
        node_ids,
        louvain_communities,
        louvain_weight,
    )
    logger.info("hierarchy timing: compute_edges=%.2fs", time.time() - t_edges_start)

    # Step 6: Compute positions via PCA on centroids
    t_pos_start = time.time()
    positions = compute_positions(clusters)
    logger.info("hierarchy timing: compute_positions=%.2fs", time.time() - t_pos_start)
    
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
    node_idx = get_node_idx(cluster_id)
    parent_idx = get_parent(linkage_matrix, node_idx, n_micro)
    
    if parent_idx is None:
        return {"can_collapse": False, "reason": "Already at root level"}
    
    # Get all children of the parent
    children = get_children(linkage_matrix, parent_idx, n_micro)
    if children is None:
        return {"can_collapse": False, "reason": "Parent has no children"}
    
    # Find all visible nodes that are descendants of this parent
    def get_visible_descendants(node):
        node_id = get_dendrogram_id(node)
        if node_id in visible_ids:
            return [node_id]
        children = get_children(linkage_matrix, node, n_micro)
        if children is None:
            return []
        return get_visible_descendants(children[0]) + get_visible_descendants(children[1])
    
    siblings = get_visible_descendants(parent_idx)
    
    return {
        "can_collapse": True,
        "parent_id": get_dendrogram_id(parent_idx),
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
    node_idx = get_node_idx(cluster_id)
    children = get_children(linkage_matrix, node_idx, n_micro)
    
    if children is None:
        return {"can_expand": False, "reason": "Already at maximum detail (micro-cluster level)"}
    
    # Simulate greedy split to predict actual child count
    subtree_cache: Dict[int, int] = {}
    subtree_sz = subtree_size(linkage_matrix, node_idx, n_micro, subtree_cache)
    exponent = 0.4 + expand_depth * 0.3
    target_children = max(3, int(subtree_sz ** exponent))
    budget_remaining = budget - current_count + 1  # removing 1 node
    target_children = min(target_children, budget_remaining + 1)
    
    # Simulate greedy split
    current = {node_idx}
    while len(current) < target_children:
        splittable = [
            (n, subtree_size(linkage_matrix, n, n_micro, subtree_cache))
            for n in current if get_children(linkage_matrix, n, n_micro)
        ]
        if not splittable:
            break
        splittable.sort(key=lambda x: x[1], reverse=True)
        node_to_split = splittable[0][0]
        split_children = get_children(linkage_matrix, node_to_split, n_micro)
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
    in_degrees=None,
    adjacency=None,  # kept for backward compatibility; prefer in_degrees
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
        if followers == 0 and node_id_to_idx is not None:
            idx = node_id_to_idx.get(node_id)
            if idx is not None:
                if in_degrees is not None:
                    followers = int(in_degrees[idx])
                elif adjacency is not None:
                    followers = int(adjacency[:, idx].sum())
        
        rows.append((handle, followers))
    rows.sort(key=lambda x: x[1], reverse=True)
    return [h for h, _ in rows[:n]]
