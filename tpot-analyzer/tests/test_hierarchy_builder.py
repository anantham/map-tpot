"""Tests for src/graph/hierarchy/builder.py - hierarchical view construction.

These tests verify the main build_hierarchical_view function and its
expand/collapse preview helpers.
"""
from __future__ import annotations

import numpy as np
import pytest
from scipy import sparse
from scipy.cluster.hierarchy import linkage

from src.graph.hierarchy.builder import (
    build_hierarchical_view,
    get_collapse_preview,
    get_expand_preview,
)
from src.graph.hierarchy.models import HierarchicalViewData


class TestBuildHierarchicalViewBasic:
    """Basic tests for build_hierarchical_view."""

    @pytest.fixture
    def minimal_setup(self):
        """Minimal setup with 4 micro-clusters."""
        # 4 micro-clusters at known positions
        micro_centroids = np.array([
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [1.0, 1.0],
        ])
        # Linkage over micro-clusters
        linkage_matrix = linkage(micro_centroids, method="ward")

        # 8 nodes, 2 per micro-cluster
        n_nodes = 8
        micro_labels = np.array([0, 0, 1, 1, 2, 2, 3, 3])
        node_ids = np.array([f"node_{i}" for i in range(n_nodes)])

        # Simple adjacency: some cross-cluster edges
        adjacency = sparse.lil_matrix((n_nodes, n_nodes))
        adjacency[0, 2] = 1  # micro 0 -> micro 1
        adjacency[4, 6] = 1  # micro 2 -> micro 3
        adjacency = adjacency.tocsr()

        # Minimal metadata
        node_metadata = {
            f"node_{i}": {"username": f"user_{i}", "num_followers": i * 100}
            for i in range(n_nodes)
        }

        return {
            "linkage_matrix": linkage_matrix,
            "micro_labels": micro_labels,
            "micro_centroids": micro_centroids,
            "node_ids": node_ids,
            "adjacency": adjacency,
            "node_metadata": node_metadata,
        }

    def test_returns_hierarchical_view_data(self, minimal_setup):
        """Returns HierarchicalViewData instance."""
        result = build_hierarchical_view(**minimal_setup, base_granularity=2)
        assert isinstance(result, HierarchicalViewData)

    def test_respects_base_granularity(self, minimal_setup):
        """Number of clusters matches base_granularity (or less)."""
        result = build_hierarchical_view(**minimal_setup, base_granularity=2)
        assert len(result.clusters) <= 2

        result = build_hierarchical_view(**minimal_setup, base_granularity=4)
        assert len(result.clusters) <= 4

    def test_clusters_have_required_fields(self, minimal_setup):
        """Each cluster has all required fields."""
        result = build_hierarchical_view(**minimal_setup, base_granularity=2)

        for cluster in result.clusters:
            assert cluster.id.startswith("d_")
            assert isinstance(cluster.dendrogram_node, int)
            assert isinstance(cluster.member_node_ids, list)
            assert isinstance(cluster.centroid, np.ndarray)
            assert cluster.size > 0
            assert cluster.label
            assert cluster.label_source in ("user", "auto")

    def test_positions_match_clusters(self, minimal_setup):
        """Position dict has entry for each cluster."""
        result = build_hierarchical_view(**minimal_setup, base_granularity=2)

        for cluster in result.clusters:
            assert cluster.id in result.positions
            pos = result.positions[cluster.id]
            assert len(pos) == 2

    def test_total_nodes_preserved(self, minimal_setup):
        """Sum of cluster sizes equals total nodes."""
        result = build_hierarchical_view(**minimal_setup, base_granularity=2)

        total_in_clusters = sum(c.size for c in result.clusters)
        assert total_in_clusters == len(minimal_setup["node_ids"])

    def test_all_nodes_assigned_to_clusters(self, minimal_setup):
        """Every node appears in exactly one cluster."""
        result = build_hierarchical_view(**minimal_setup, base_granularity=2)

        all_member_ids = []
        for cluster in result.clusters:
            all_member_ids.extend(cluster.member_node_ids)

        # Check no duplicates
        assert len(all_member_ids) == len(set(all_member_ids))
        # Check all nodes present
        assert set(all_member_ids) == set(minimal_setup["node_ids"].tolist())


class TestExpandCollapse:
    """Tests for expand/collapse behavior."""

    @pytest.fixture
    def expandable_setup(self):
        """Setup with enough depth for expansion."""
        # 8 micro-clusters
        np.random.seed(42)
        micro_centroids = np.random.randn(8, 4)
        linkage_matrix = linkage(micro_centroids, method="ward")

        # 16 nodes, 2 per micro-cluster
        n_nodes = 16
        micro_labels = np.repeat(np.arange(8), 2)
        node_ids = np.array([f"node_{i}" for i in range(n_nodes)])
        adjacency = sparse.csr_matrix((n_nodes, n_nodes))
        node_metadata = {f"node_{i}": {"username": f"user_{i}"} for i in range(n_nodes)}

        return {
            "linkage_matrix": linkage_matrix,
            "micro_labels": micro_labels,
            "micro_centroids": micro_centroids,
            "node_ids": node_ids,
            "adjacency": adjacency,
            "node_metadata": node_metadata,
        }

    def test_expand_increases_cluster_count(self, expandable_setup):
        """Expanding a cluster increases visible count."""
        # First, get base view with few clusters
        base = build_hierarchical_view(**expandable_setup, base_granularity=2, budget=20)
        base_count = len(base.clusters)

        # Find an expandable cluster (non-leaf)
        expandable = [c for c in base.clusters if not c.is_leaf]
        assert expandable, "Expected at least one expandable cluster; check fixture granularity."

        # Expand it
        expanded = build_hierarchical_view(
            **expandable_setup,
            base_granularity=2,
            expanded_ids={expandable[0].id},
            budget=20,
        )

        assert len(expanded.clusters) > base_count

    def test_collapse_decreases_cluster_count(self, expandable_setup):
        """Collapsing reduces visible count."""
        # Get view with more clusters
        base = build_hierarchical_view(**expandable_setup, base_granularity=4, budget=20)

        # Find a cluster with a parent
        collapsible = [c for c in base.clusters if c.parent_id is not None]
        assert collapsible, "Expected at least one collapsible cluster; check fixture granularity."

        parent_id = collapsible[0].parent_id

        # Collapse to parent
        collapsed = build_hierarchical_view(
            **expandable_setup,
            base_granularity=4,
            collapsed_ids={parent_id},
            budget=20,
        )

        # Parent should now be visible instead of children
        collapsed_ids = {c.id for c in collapsed.clusters}
        assert parent_id in collapsed_ids

    def test_budget_limits_expansion(self, expandable_setup):
        """Expansion stops when budget is reached."""
        # Tight budget
        result = build_hierarchical_view(
            **expandable_setup,
            base_granularity=2,
            expanded_ids={"d_10", "d_11", "d_12"},  # Try to expand multiple
            budget=4,
        )

        assert len(result.clusters) <= 4
        assert result.budget_remaining >= 0

    def test_expanded_ids_in_result(self, expandable_setup):
        """Result includes which IDs were expanded."""
        expand_set = {"d_10"}
        result = build_hierarchical_view(
            **expandable_setup,
            base_granularity=2,
            expanded_ids=expand_set,
            budget=20,
        )

        assert result.expanded_ids == list(expand_set)


class TestEgoHighlighting:
    """Tests for ego node highlighting."""

    @pytest.fixture
    def ego_setup(self):
        """Setup with designated ego node."""
        # Need 2D centroids for PCA position computation
        micro_centroids = np.array([
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [1.0, 1.0],
        ])
        linkage_matrix = linkage(micro_centroids, method="ward")

        n_nodes = 8
        micro_labels = np.repeat(np.arange(4), 2)
        node_ids = np.array([f"node_{i}" for i in range(n_nodes)])
        adjacency = sparse.csr_matrix((n_nodes, n_nodes))
        node_metadata = {}

        return {
            "linkage_matrix": linkage_matrix,
            "micro_labels": micro_labels,
            "micro_centroids": micro_centroids,
            "node_ids": node_ids,
            "adjacency": adjacency,
            "node_metadata": node_metadata,
        }

    def test_ego_cluster_marked(self, ego_setup):
        """Cluster containing ego has contains_ego=True."""
        result = build_hierarchical_view(
            **ego_setup,
            base_granularity=2,
            ego_node_id="node_0",
        )

        ego_clusters = [c for c in result.clusters if c.contains_ego]
        assert len(ego_clusters) == 1
        assert "node_0" in ego_clusters[0].member_node_ids

    def test_ego_cluster_id_in_result(self, ego_setup):
        """Result includes ego_cluster_id."""
        result = build_hierarchical_view(
            **ego_setup,
            base_granularity=2,
            ego_node_id="node_0",
        )

        assert result.ego_cluster_id is not None
        ego_cluster = next(c for c in result.clusters if c.id == result.ego_cluster_id)
        assert "node_0" in ego_cluster.member_node_ids

    def test_missing_ego_handled(self, ego_setup):
        """Missing ego_node_id doesn't crash."""
        result = build_hierarchical_view(
            **ego_setup,
            base_granularity=2,
            ego_node_id="nonexistent_node",
        )

        assert result.ego_cluster_id is None


class TestLinkageValidation:
    """Tests for linkage matrix validation."""

    def test_mismatched_linkage_raises(self):
        """Linkage matrix must match micro_centroids size."""
        # 4 micro-clusters but linkage for 3
        micro_centroids = np.array([[0.0], [1.0], [2.0], [3.0]])
        wrong_linkage = linkage(np.array([[0.0], [1.0], [2.0]]), method="ward")

        with pytest.raises(ValueError, match="linkage_matrix shape mismatch"):
            build_hierarchical_view(
                linkage_matrix=wrong_linkage,
                micro_labels=np.array([0, 1, 2, 3]),
                micro_centroids=micro_centroids,
                node_ids=np.array(["a", "b", "c", "d"]),
                adjacency=sparse.csr_matrix((4, 4)),
                node_metadata={},
            )


class TestGetExpandPreview:
    """Tests for get_expand_preview helper."""

    @pytest.fixture
    def preview_linkage(self):
        """Linkage for preview testing."""
        centroids = np.array([[0.0], [1.0], [2.0], [3.0]])
        return linkage(centroids, method="ward"), 4

    def test_can_expand_internal_node(self, preview_linkage):
        """Internal nodes can be expanded."""
        linkage_matrix, n_micro = preview_linkage

        preview = get_expand_preview(
            linkage_matrix=linkage_matrix,
            n_micro=n_micro,
            cluster_id="d_6",  # Root
            current_count=1,
            budget=10,
        )

        assert preview["can_expand"] is True
        assert preview["predicted_children"] >= 2

    def test_cannot_expand_leaf(self, preview_linkage):
        """Leaf nodes cannot be expanded."""
        linkage_matrix, n_micro = preview_linkage

        preview = get_expand_preview(
            linkage_matrix=linkage_matrix,
            n_micro=n_micro,
            cluster_id="d_0",  # Leaf
            current_count=1,
            budget=10,
        )

        assert preview["can_expand"] is False
        assert "micro-cluster" in preview["reason"].lower()

    def test_budget_prevents_expansion(self, preview_linkage):
        """Cannot expand when budget exhausted."""
        linkage_matrix, n_micro = preview_linkage

        preview = get_expand_preview(
            linkage_matrix=linkage_matrix,
            n_micro=n_micro,
            cluster_id="d_6",
            current_count=10,
            budget=10,  # Already at budget
        )

        assert preview["can_expand"] is False
        assert "budget" in preview["reason"].lower()


class TestGetCollapsePreview:
    """Tests for get_collapse_preview helper."""

    @pytest.fixture
    def collapse_linkage(self):
        """Linkage for collapse testing."""
        centroids = np.array([[0.0], [1.0], [2.0], [3.0]])
        return linkage(centroids, method="ward"), 4

    def test_can_collapse_non_root(self, collapse_linkage):
        """Non-root nodes can be collapsed."""
        linkage_matrix, n_micro = collapse_linkage
        # Visible: two children of root
        visible_ids = {"d_4", "d_5"}

        preview = get_collapse_preview(
            linkage_matrix=linkage_matrix,
            n_micro=n_micro,
            cluster_id="d_4",
            visible_ids=visible_ids,
        )

        assert preview["can_collapse"] is True
        assert preview["parent_id"] == "d_6"  # Root

    def test_cannot_collapse_root(self, collapse_linkage):
        """Root node cannot be collapsed further."""
        linkage_matrix, n_micro = collapse_linkage
        visible_ids = {"d_6"}

        preview = get_collapse_preview(
            linkage_matrix=linkage_matrix,
            n_micro=n_micro,
            cluster_id="d_6",  # Root
            visible_ids=visible_ids,
        )

        assert preview["can_collapse"] is False
        assert "root" in preview["reason"].lower()

    def test_collapse_shows_siblings(self, collapse_linkage):
        """Preview shows which siblings will be merged."""
        linkage_matrix, n_micro = collapse_linkage
        visible_ids = {"d_4", "d_5"}

        preview = get_collapse_preview(
            linkage_matrix=linkage_matrix,
            n_micro=n_micro,
            cluster_id="d_4",
            visible_ids=visible_ids,
        )

        assert "sibling_ids" in preview
        assert len(preview["sibling_ids"]) >= 2
