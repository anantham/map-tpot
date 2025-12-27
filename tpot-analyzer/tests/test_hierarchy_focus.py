"""Tests for src/graph/hierarchy/focus.py - reveal leaf in visible set.

These tests verify the "teleport to account" functionality that ensures
a specific leaf cluster becomes visible by splitting its ancestors.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.graph.hierarchy.focus import reveal_leaf_in_visible_set, RevealLeafResult


# Reuse fixtures from traversal tests
@pytest.fixture
def simple_linkage() -> np.ndarray:
    """4-leaf dendrogram with balanced binary tree.

    Tree structure:
              6 (root)
             / \
            4   5
           / \ / \
          0  1 2  3
    """
    return np.array([
        [0, 1, 1.0, 2],  # node 4: merge 0,1
        [2, 3, 1.5, 2],  # node 5: merge 2,3
        [4, 5, 2.0, 4],  # node 6 (root): merge 4,5
    ])


@pytest.fixture
def deep_linkage() -> np.ndarray:
    """6-leaf dendrogram with deep left branch.

    Tree structure:
                   10 (root)
                  /   \
                 9     5
               /   \
              8     4
             / \
            7   3
           / \
          6   2
         / \
        0   1
    """
    return np.array([
        [0, 1, 1.0, 2],   # node 6: merge 0,1
        [6, 2, 1.5, 3],   # node 7: merge node6 with leaf 2
        [7, 3, 2.0, 4],   # node 8: merge node7 with leaf 3
        [8, 4, 2.5, 5],   # node 9: merge node8 with leaf 4
        [9, 5, 3.0, 6],   # node 10 (root): merge node9 with leaf 5
    ])


class TestRevealLeafAlreadyVisible:
    """Tests when target leaf is already visible."""

    def test_leaf_already_visible_returns_immediately(self, simple_linkage):
        """If leaf is in visible_nodes, return success with 0 steps."""
        n_leaves = 4
        visible_nodes = {0, 1, 2, 3}  # All leaves visible

        result = reveal_leaf_in_visible_set(
            visible_nodes=visible_nodes,
            linkage_matrix=simple_linkage,
            leaf_idx=0,
            n_leaves=n_leaves,
            budget=10,
        )

        assert result.ok is True
        assert result.steps == 0
        assert result.container_before == 0
        assert result.container_after == 0

    def test_no_side_effects_when_already_visible(self, simple_linkage):
        """Visible set unchanged when leaf already visible."""
        n_leaves = 4
        visible_nodes = {0, 1, 2, 3}
        original = visible_nodes.copy()

        reveal_leaf_in_visible_set(
            visible_nodes=visible_nodes,
            linkage_matrix=simple_linkage,
            leaf_idx=0,
            n_leaves=n_leaves,
            budget=10,
        )

        assert visible_nodes == original


class TestRevealLeafBySplitting:
    """Tests for splitting ancestors to reveal a leaf."""

    def test_split_parent_reveals_leaf(self, simple_linkage):
        """Splitting immediate parent reveals leaf."""
        n_leaves = 4
        # Node 4 is visible (contains leaves 0,1)
        visible_nodes = {4, 5}

        result = reveal_leaf_in_visible_set(
            visible_nodes=visible_nodes,
            linkage_matrix=simple_linkage,
            leaf_idx=0,
            n_leaves=n_leaves,
            budget=10,
        )

        assert result.ok is True
        assert result.steps == 1  # Split node 4 into 0,1
        assert 0 in visible_nodes  # Leaf 0 now visible
        assert 1 in visible_nodes  # Sibling also visible
        assert 4 not in visible_nodes  # Parent removed

    def test_split_root_reveals_nested_leaf(self, simple_linkage):
        """Splitting from root reveals deeply nested leaf."""
        n_leaves = 4
        # Only root visible
        visible_nodes = {6}

        result = reveal_leaf_in_visible_set(
            visible_nodes=visible_nodes,
            linkage_matrix=simple_linkage,
            leaf_idx=0,
            n_leaves=n_leaves,
            budget=10,
        )

        assert result.ok is True
        assert result.steps == 2  # Split root -> split node 4
        assert 0 in visible_nodes  # Target leaf visible
        assert 1 in visible_nodes  # Sibling visible
        assert 5 in visible_nodes  # Other subtree visible

    def test_deep_tree_multiple_splits(self, deep_linkage):
        """Deep tree requires multiple splits to reveal leaf."""
        n_leaves = 6
        # Only root visible
        visible_nodes = {10}

        result = reveal_leaf_in_visible_set(
            visible_nodes=visible_nodes,
            linkage_matrix=deep_linkage,
            leaf_idx=0,
            n_leaves=n_leaves,
            budget=20,
        )

        assert result.ok is True
        assert result.steps >= 4  # Need to split through 10->9->8->7->6->0
        assert 0 in visible_nodes


class TestBudgetConstraints:
    """Tests for budget-constrained reveal operations."""

    def test_budget_exhausted_before_reveal(self, deep_linkage):
        """Stop when budget would be exceeded."""
        n_leaves = 6
        visible_nodes = {10}  # Just root

        result = reveal_leaf_in_visible_set(
            visible_nodes=visible_nodes,
            linkage_matrix=deep_linkage,
            leaf_idx=0,
            n_leaves=n_leaves,
            budget=3,  # Very tight budget
        )

        assert result.ok is False
        assert result.reason == "budget_exhausted"
        assert result.steps >= 0

    def test_exact_budget_allows_reveal(self, simple_linkage):
        """Budget exactly sufficient allows reveal."""
        n_leaves = 4
        visible_nodes = {4, 5}  # 2 nodes visible

        result = reveal_leaf_in_visible_set(
            visible_nodes=visible_nodes,
            linkage_matrix=simple_linkage,
            leaf_idx=0,
            n_leaves=n_leaves,
            budget=3,  # Splitting 4 -> 0,1 gives 3 total (0,1,5)
        )

        assert result.ok is True


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_leaf_not_in_visible_subtrees(self, simple_linkage):
        """Fail if leaf not under any visible node."""
        n_leaves = 4
        # Only node 5 visible (contains leaves 2,3)
        visible_nodes = {5}

        result = reveal_leaf_in_visible_set(
            visible_nodes=visible_nodes,
            linkage_matrix=simple_linkage,
            leaf_idx=0,  # Leaf 0 is under node 4, not node 5
            n_leaves=n_leaves,
            budget=10,
        )

        assert result.ok is False
        assert result.reason == "leaf_not_in_visible_subtrees"

    def test_reveals_smallest_container(self, simple_linkage):
        """When multiple containers exist, use smallest (deepest)."""
        n_leaves = 4
        # Both root (6) and node 4 contain leaf 0
        visible_nodes = {4, 6}  # Unusual state but possible

        result = reveal_leaf_in_visible_set(
            visible_nodes=visible_nodes,
            linkage_matrix=simple_linkage,
            leaf_idx=0,
            n_leaves=n_leaves,
            budget=10,
        )

        # Should split node 4 (smaller container) not root
        assert result.container_before == 4

    def test_visible_set_modified_in_place(self, simple_linkage):
        """Visible set is modified, not replaced."""
        n_leaves = 4
        visible_nodes = {4, 5}
        original_id = id(visible_nodes)

        reveal_leaf_in_visible_set(
            visible_nodes=visible_nodes,
            linkage_matrix=simple_linkage,
            leaf_idx=0,
            n_leaves=n_leaves,
            budget=10,
        )

        assert id(visible_nodes) == original_id  # Same object


class TestRevealLeafResult:
    """Tests for the RevealLeafResult dataclass."""

    def test_result_is_frozen(self):
        """Result dataclass is immutable."""
        result = RevealLeafResult(ok=True, steps=1)
        with pytest.raises(AttributeError):
            result.ok = False  # type: ignore

    def test_result_fields(self, simple_linkage):
        """Result contains all expected fields."""
        n_leaves = 4
        visible_nodes = {4, 5}

        result = reveal_leaf_in_visible_set(
            visible_nodes=visible_nodes,
            linkage_matrix=simple_linkage,
            leaf_idx=0,
            n_leaves=n_leaves,
            budget=10,
        )

        assert hasattr(result, "ok")
        assert hasattr(result, "steps")
        assert hasattr(result, "reason")
        assert hasattr(result, "container_before")
        assert hasattr(result, "container_after")
