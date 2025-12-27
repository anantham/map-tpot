"""Tests for src/graph/hierarchy/traversal.py - dendrogram tree navigation.

These tests verify the core tree traversal operations that underpin the
hierarchical cluster expand/collapse behavior.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.graph.hierarchy.traversal import (
    find_cluster_leaders,
    get_children,
    get_dendrogram_id,
    get_node_idx,
    get_parent,
    get_siblings,
    get_subtree_leaves,
    is_descendant,
    subtree_size,
)


# Fixture: Simple 4-leaf dendrogram
#
# Linkage matrix for 4 leaves:
#   Row 0: merge leaves 0,1 -> node 4  (height 1.0, count 2)
#   Row 1: merge leaves 2,3 -> node 5  (height 1.5, count 2)
#   Row 2: merge 4,5 -> node 6 (root)  (height 2.0, count 4)
#
# Tree structure:
#           6 (root)
#          / \
#         4   5
#        / \ / \
#       0  1 2  3
#
@pytest.fixture
def simple_linkage() -> np.ndarray:
    """4-leaf dendrogram with balanced binary tree."""
    return np.array([
        [0, 1, 1.0, 2],  # node 4: merge 0,1
        [2, 3, 1.5, 2],  # node 5: merge 2,3
        [4, 5, 2.0, 4],  # node 6 (root): merge 4,5
    ])


# Fixture: Asymmetric 5-leaf dendrogram
#
#   Row 0: merge 0,1 -> node 5
#   Row 1: merge 2,5 -> node 6
#   Row 2: merge 3,4 -> node 7
#   Row 3: merge 6,7 -> node 8 (root)
#
# Tree structure:
#              8 (root)
#            /   \
#           6     7
#          / \   / \
#         2   5 3   4
#            / \
#           0   1
#
@pytest.fixture
def asymmetric_linkage() -> np.ndarray:
    """5-leaf dendrogram with asymmetric structure."""
    return np.array([
        [0, 1, 1.0, 2],  # node 5: merge 0,1
        [2, 5, 1.5, 3],  # node 6: merge 2 and node5 -> contains 0,1,2
        [3, 4, 1.2, 2],  # node 7: merge 3,4
        [6, 7, 2.5, 5],  # node 8 (root)
    ])


class TestDendrogramIDConversion:
    """Tests for ID <-> index conversion."""

    def test_get_dendrogram_id_format(self):
        """Dendrogram IDs have d_<index> format."""
        assert get_dendrogram_id(0) == "d_0"
        assert get_dendrogram_id(42) == "d_42"
        assert get_dendrogram_id(999) == "d_999"

    def test_get_node_idx_parses_correctly(self):
        """Node index extracted from dendrogram ID."""
        assert get_node_idx("d_0") == 0
        assert get_node_idx("d_42") == 42
        assert get_node_idx("d_999") == 999

    def test_round_trip_conversion(self):
        """ID -> index -> ID preserves value."""
        for idx in [0, 5, 100]:
            assert get_node_idx(get_dendrogram_id(idx)) == idx


class TestGetChildren:
    """Tests for child node retrieval."""

    def test_leaf_nodes_have_no_children(self, simple_linkage):
        """Leaves (indices < n_leaves) return None."""
        n_leaves = 4
        for leaf in range(n_leaves):
            assert get_children(simple_linkage, leaf, n_leaves) is None

    def test_internal_node_returns_children(self, simple_linkage):
        """Internal nodes return (left, right) tuple."""
        n_leaves = 4
        # Node 4 has children 0, 1
        assert get_children(simple_linkage, 4, n_leaves) == (0, 1)
        # Node 5 has children 2, 3
        assert get_children(simple_linkage, 5, n_leaves) == (2, 3)
        # Node 6 (root) has children 4, 5
        assert get_children(simple_linkage, 6, n_leaves) == (4, 5)

    def test_invalid_node_returns_none(self, simple_linkage):
        """Out-of-bounds node index returns None."""
        n_leaves = 4
        assert get_children(simple_linkage, 100, n_leaves) is None

    def test_asymmetric_tree_children(self, asymmetric_linkage):
        """Asymmetric tree correctly reports children."""
        n_leaves = 5
        # Node 5 has leaves 0, 1
        assert get_children(asymmetric_linkage, 5, n_leaves) == (0, 1)
        # Node 6 has leaf 2 and internal node 5
        assert get_children(asymmetric_linkage, 6, n_leaves) == (2, 5)


class TestGetParent:
    """Tests for parent node retrieval."""

    def test_root_has_no_parent(self, simple_linkage):
        """Root node returns None for parent."""
        n_leaves = 4
        root = 6
        assert get_parent(simple_linkage, root, n_leaves) is None

    def test_internal_node_parent(self, simple_linkage):
        """Internal nodes return correct parent."""
        n_leaves = 4
        # Node 4's parent is node 6
        assert get_parent(simple_linkage, 4, n_leaves) == 6
        # Node 5's parent is node 6
        assert get_parent(simple_linkage, 5, n_leaves) == 6

    def test_leaf_parent(self, simple_linkage):
        """Leaf nodes return correct parent."""
        n_leaves = 4
        # Leaves 0, 1 have parent 4
        assert get_parent(simple_linkage, 0, n_leaves) == 4
        assert get_parent(simple_linkage, 1, n_leaves) == 4
        # Leaves 2, 3 have parent 5
        assert get_parent(simple_linkage, 2, n_leaves) == 5
        assert get_parent(simple_linkage, 3, n_leaves) == 5

    def test_asymmetric_tree_parent(self, asymmetric_linkage):
        """Asymmetric tree correctly reports parents."""
        n_leaves = 5
        # Node 5 (containing 0,1) has parent 6
        assert get_parent(asymmetric_linkage, 5, n_leaves) == 6
        # Leaf 2 has parent 6 (directly)
        assert get_parent(asymmetric_linkage, 2, n_leaves) == 6


class TestGetSubtreeLeaves:
    """Tests for collecting all leaves under a node."""

    def test_leaf_returns_itself(self, simple_linkage):
        """Leaf node returns single-element list with itself."""
        n_leaves = 4
        assert get_subtree_leaves(simple_linkage, 0, n_leaves) == [0]
        assert get_subtree_leaves(simple_linkage, 3, n_leaves) == [3]

    def test_internal_node_returns_all_leaves(self, simple_linkage):
        """Internal node returns all descendant leaves."""
        n_leaves = 4
        # Node 4 contains leaves 0, 1
        assert sorted(get_subtree_leaves(simple_linkage, 4, n_leaves)) == [0, 1]
        # Node 5 contains leaves 2, 3
        assert sorted(get_subtree_leaves(simple_linkage, 5, n_leaves)) == [2, 3]

    def test_root_returns_all_leaves(self, simple_linkage):
        """Root returns all leaves in tree."""
        n_leaves = 4
        assert sorted(get_subtree_leaves(simple_linkage, 6, n_leaves)) == [0, 1, 2, 3]

    def test_asymmetric_subtree_leaves(self, asymmetric_linkage):
        """Asymmetric tree correctly collects leaves."""
        n_leaves = 5
        # Node 6 contains leaves 0, 1, 2 (via node 5 and direct leaf 2)
        assert sorted(get_subtree_leaves(asymmetric_linkage, 6, n_leaves)) == [0, 1, 2]
        # Root (8) contains all leaves
        assert sorted(get_subtree_leaves(asymmetric_linkage, 8, n_leaves)) == [0, 1, 2, 3, 4]


class TestSubtreeSize:
    """Tests for subtree size computation with memoization."""

    def test_leaf_size_is_one(self, simple_linkage):
        """Leaves have size 1."""
        n_leaves = 4
        memo = {}
        for leaf in range(n_leaves):
            assert subtree_size(simple_linkage, leaf, n_leaves, memo) == 1

    def test_internal_node_size(self, simple_linkage):
        """Internal node size equals sum of children."""
        n_leaves = 4
        memo = {}
        # Node 4 = leaves 0,1 = size 2
        assert subtree_size(simple_linkage, 4, n_leaves, memo) == 2
        # Node 5 = leaves 2,3 = size 2
        assert subtree_size(simple_linkage, 5, n_leaves, memo) == 2
        # Root = all 4 leaves
        assert subtree_size(simple_linkage, 6, n_leaves, memo) == 4

    def test_memoization_fills_cache(self, simple_linkage):
        """Computing root size populates cache for all nodes."""
        n_leaves = 4
        memo = {}
        subtree_size(simple_linkage, 6, n_leaves, memo)
        # All visited nodes should be cached
        assert memo[0] == 1
        assert memo[1] == 1
        assert memo[4] == 2
        assert memo[6] == 4

    def test_asymmetric_sizes(self, asymmetric_linkage):
        """Asymmetric tree has correct subtree sizes."""
        n_leaves = 5
        memo = {}
        # Node 5 (0,1) = 2
        assert subtree_size(asymmetric_linkage, 5, n_leaves, memo) == 2
        # Node 6 (2, node5) = 3
        assert subtree_size(asymmetric_linkage, 6, n_leaves, memo) == 3
        # Node 7 (3,4) = 2
        assert subtree_size(asymmetric_linkage, 7, n_leaves, memo) == 2
        # Root (8) = 5
        assert subtree_size(asymmetric_linkage, 8, n_leaves, memo) == 5


class TestGetSiblings:
    """Tests for sibling retrieval."""

    def test_root_has_no_sibling(self, simple_linkage):
        """Root node has no sibling."""
        n_leaves = 4
        assert get_siblings(simple_linkage, 6, n_leaves) is None

    def test_internal_node_sibling(self, simple_linkage):
        """Internal nodes return correct sibling."""
        n_leaves = 4
        # Node 4's sibling is 5
        assert get_siblings(simple_linkage, 4, n_leaves) == 5
        # Node 5's sibling is 4
        assert get_siblings(simple_linkage, 5, n_leaves) == 4

    def test_leaf_sibling(self, simple_linkage):
        """Leaf nodes return correct sibling."""
        n_leaves = 4
        # Leaf 0's sibling is 1
        assert get_siblings(simple_linkage, 0, n_leaves) == 1
        # Leaf 1's sibling is 0
        assert get_siblings(simple_linkage, 1, n_leaves) == 0


class TestIsDescendant:
    """Tests for descendant relationship checking."""

    def test_node_is_descendant_of_itself(self, simple_linkage):
        """A node is considered its own descendant."""
        n_leaves = 4
        for node in range(7):  # 0-6 all nodes
            assert is_descendant(simple_linkage, node, node, n_leaves) is True

    def test_leaf_descendant_of_parent(self, simple_linkage):
        """Leaves are descendants of their parent."""
        n_leaves = 4
        # Leaves 0,1 are descendants of node 4
        assert is_descendant(simple_linkage, 0, 4, n_leaves) is True
        assert is_descendant(simple_linkage, 1, 4, n_leaves) is True
        # Leaves 2,3 are descendants of node 5
        assert is_descendant(simple_linkage, 2, 5, n_leaves) is True
        assert is_descendant(simple_linkage, 3, 5, n_leaves) is True

    def test_leaf_descendant_of_root(self, simple_linkage):
        """All leaves are descendants of root."""
        n_leaves = 4
        for leaf in range(n_leaves):
            assert is_descendant(simple_linkage, leaf, 6, n_leaves) is True

    def test_leaf_not_descendant_of_unrelated_subtree(self, simple_linkage):
        """Leaf not descendant of node in different subtree."""
        n_leaves = 4
        # Leaf 0 is NOT a descendant of node 5 (which contains 2,3)
        assert is_descendant(simple_linkage, 0, 5, n_leaves) is False
        # Leaf 2 is NOT a descendant of node 4 (which contains 0,1)
        assert is_descendant(simple_linkage, 2, 4, n_leaves) is False

    def test_internal_node_descendant_of_root(self, simple_linkage):
        """Internal nodes are descendants of root."""
        n_leaves = 4
        assert is_descendant(simple_linkage, 4, 6, n_leaves) is True
        assert is_descendant(simple_linkage, 5, 6, n_leaves) is True

    def test_parent_not_descendant_of_child(self, simple_linkage):
        """Parent is NOT a descendant of child (direction matters)."""
        n_leaves = 4
        # Node 4 is NOT a descendant of leaf 0
        assert is_descendant(simple_linkage, 4, 0, n_leaves) is False
        # Root is NOT a descendant of node 4
        assert is_descendant(simple_linkage, 6, 4, n_leaves) is False


class TestFindClusterLeaders:
    """Tests for finding dendrogram nodes that represent cluster labels."""

    def test_single_cluster_returns_root(self, simple_linkage):
        """When all leaves in one cluster, root is the leader."""
        n_leaves = 4
        # All leaves labeled as cluster 1 - scipy requires int32 contiguous array
        labels = np.array([1, 1, 1, 1], dtype=np.int32)
        leaders = find_cluster_leaders(simple_linkage, labels, n_leaves)
        # Should map cluster 1 to root (node 6)
        assert 1 in leaders
        assert leaders[1] == 6

    def test_two_clusters_returns_correct_leaders(self, simple_linkage):
        """Two clusters map to their respective subtree roots."""
        n_leaves = 4
        # Cluster 1: leaves 0,1; Cluster 2: leaves 2,3
        labels = np.array([1, 1, 2, 2], dtype=np.int32)
        leaders = find_cluster_leaders(simple_linkage, labels, n_leaves)
        # Cluster 1 -> node 4 (contains 0,1)
        assert leaders[1] == 4
        # Cluster 2 -> node 5 (contains 2,3)
        assert leaders[2] == 5

    def test_four_clusters_returns_leaves(self, simple_linkage):
        """Four clusters (one per leaf) map to leaf nodes."""
        n_leaves = 4
        # Each leaf is its own cluster
        labels = np.array([1, 2, 3, 4], dtype=np.int32)
        leaders = find_cluster_leaders(simple_linkage, labels, n_leaves)
        # Each cluster maps to its leaf
        assert leaders[1] == 0
        assert leaders[2] == 1
        assert leaders[3] == 2
        assert leaders[4] == 3

    def test_asymmetric_labels(self, asymmetric_linkage):
        """Asymmetric tree with asymmetric cluster assignment."""
        n_leaves = 5
        # Cluster 1: leaves 0,1,2 (under node 6); Cluster 2: leaves 3,4 (under node 7)
        labels = np.array([1, 1, 1, 2, 2], dtype=np.int32)
        leaders = find_cluster_leaders(asymmetric_linkage, labels, n_leaves)
        assert leaders[1] == 6  # Contains 0,1,2
        assert leaders[2] == 7  # Contains 3,4
