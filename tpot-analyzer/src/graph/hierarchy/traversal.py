"""Tree traversal utilities for dendrogram navigation."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Set
import numpy as np
from scipy.cluster.hierarchy import leaders


def get_dendrogram_id(node_idx: int) -> str:
    """Convert dendrogram node index to string ID."""
    return f"d_{node_idx}"


def get_node_idx(dendrogram_id: str) -> int:
    """Convert string ID back to node index."""
    return int(dendrogram_id.split("_")[1])


def get_children(linkage_matrix: np.ndarray, node_idx: int, n_leaves: int) -> Optional[Tuple[int, int]]:
    """Get children of a dendrogram internal node."""
    if node_idx < n_leaves:
        return None  # Leaf node, no children
    row = node_idx - n_leaves
    if row < 0 or row >= len(linkage_matrix):
        return None
    left = int(linkage_matrix[row, 0])
    right = int(linkage_matrix[row, 1])
    return (left, right)


def get_parent(linkage_matrix: np.ndarray, node_idx: int, n_leaves: int) -> Optional[int]:
    """Get parent of a dendrogram node."""
    for i, row in enumerate(linkage_matrix):
        if int(row[0]) == node_idx or int(row[1]) == node_idx:
            return n_leaves + i
    return None  # Root has no parent

def get_subtree_leaves(linkage_matrix: np.ndarray, node_idx: int, n_leaves: int) -> List[int]:
    """Get all leaf indices under this dendrogram node."""
    if node_idx < n_leaves:
        return [node_idx]
    children = get_children(linkage_matrix, node_idx, n_leaves)
    if children is None:
        return [node_idx]
    left, right = children
    return get_subtree_leaves(linkage_matrix, left, n_leaves) + \
           get_subtree_leaves(linkage_matrix, right, n_leaves)


def subtree_size(linkage_matrix: np.ndarray, node_idx: int, n_leaves: int, memo: Dict[int, int]) -> int:
    """Compute number of leaves under a dendrogram node (cached)."""
    if node_idx in memo:
        return memo[node_idx]
    if node_idx < n_leaves:
        memo[node_idx] = 1
        return 1
    children = get_children(linkage_matrix, node_idx, n_leaves)
    if not children:
        memo[node_idx] = 1
        return 1
    size = subtree_size(linkage_matrix, children[0], n_leaves, memo) + subtree_size(linkage_matrix, children[1], n_leaves, memo)
    memo[node_idx] = size
    return size

def get_siblings(linkage_matrix: np.ndarray, node_idx: int, n_leaves: int) -> Optional[int]:
    """Get sibling of a dendrogram node."""
    parent = get_parent(linkage_matrix, node_idx, n_leaves)
    if parent is None:
        return None
    children = get_children(linkage_matrix, parent, n_leaves)
    if children is None:
        return None
    left, right = children
    return right if left == node_idx else left

def is_descendant(linkage_matrix: np.ndarray, node_idx: int, ancestor_idx: int, n_leaves: int) -> bool:
    """Check if node_idx is a descendant of ancestor_idx (or equal to it)."""
    if node_idx == ancestor_idx:
        return True
    if ancestor_idx < n_leaves:
        # Ancestor is a leaf, can only be descendant if equal
        return False
    # Get all leaves under ancestor and check if node is one of them
    # (or an internal node whose leaves are a subset)
    ancestor_leaves = set(get_subtree_leaves(linkage_matrix, ancestor_idx, n_leaves))
    if node_idx < n_leaves:
        return node_idx in ancestor_leaves
    node_leaves = set(get_subtree_leaves(linkage_matrix, node_idx, n_leaves))
    return node_leaves.issubset(ancestor_leaves)

def find_cluster_leaders(linkage_matrix: np.ndarray, labels: np.ndarray, n_leaves: int) -> Dict[int, int]:
    """Find the dendrogram node that represents each cluster label.
    
    Returns:
        dict mapping cluster_label -> dendrogram_node_idx
    """
    # Use scipy's leaders function
    leader_nodes, leader_labels = leaders(linkage_matrix, labels)
    return {int(label): int(node) for node, label in zip(leader_nodes, leader_labels)}
