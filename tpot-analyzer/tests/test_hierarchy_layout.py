"""Tests for src/graph/hierarchy/layout.py - position and edge computation.

These tests verify:
1. PCA-based position computation for cluster centroids
2. Edge connectivity calculation between clusters
3. Louvain fusion weighting for edge strength
"""
from __future__ import annotations

import numpy as np
import pytest
from scipy import sparse

from src.graph.hierarchy.layout import compute_positions, compute_hierarchical_edges
from src.graph.hierarchy.models import HierarchicalCluster, HierarchicalEdge


def _make_cluster(
    id: str,
    centroid: list[float],
    member_micro_indices: list[int],
    size: int = 10,
) -> HierarchicalCluster:
    """Helper to create minimal HierarchicalCluster for testing."""
    return HierarchicalCluster(
        id=id,
        dendrogram_node=int(id.split("_")[1]),
        parent_id=None,
        children_ids=None,
        member_micro_indices=member_micro_indices,
        member_node_ids=[f"node_{i}" for i in range(size)],
        centroid=np.array(centroid),
        size=size,
        label=f"Cluster {id}",
        label_source="auto",
        representative_handles=["handle1"],
        contains_ego=False,
        is_leaf=False,
    )


class TestComputePositions:
    """Tests for PCA-based 2D positioning."""

    def test_empty_clusters_returns_empty_dict(self):
        """No clusters -> empty positions."""
        positions = compute_positions([])
        assert positions == {}

    def test_single_cluster_at_origin(self):
        """Single cluster positioned at origin."""
        cluster = _make_cluster("d_0", [1.0, 2.0, 3.0], [0])
        positions = compute_positions([cluster])

        assert "d_0" in positions
        assert positions["d_0"] == [0.0, 0.0]

    def test_two_clusters_on_line(self):
        """Two clusters positioned along first principal axis."""
        c1 = _make_cluster("d_0", [0.0, 0.0, 0.0], [0])
        c2 = _make_cluster("d_1", [1.0, 0.0, 0.0], [1])
        positions = compute_positions([c1, c2])

        # Should have 2 positions
        assert len(positions) == 2
        # Positions should differ along x (first PC)
        x_coords = [positions["d_0"][0], positions["d_1"][0]]
        assert x_coords[0] != x_coords[1]

    def test_positions_are_centered(self):
        """Centroid of all positions should be near origin."""
        clusters = [
            _make_cluster("d_0", [0.0, 0.0, 0.0], [0]),
            _make_cluster("d_1", [10.0, 0.0, 0.0], [1]),
            _make_cluster("d_2", [5.0, 5.0, 0.0], [2]),
        ]
        positions = compute_positions(clusters)

        xs = [p[0] for p in positions.values()]
        ys = [p[1] for p in positions.values()]
        assert abs(np.mean(xs)) < 1e-10
        assert abs(np.mean(ys)) < 1e-10

    def test_handles_nan_in_centroids(self):
        """NaN values in centroids are replaced with 0."""
        c1 = _make_cluster("d_0", [np.nan, 0.0, 0.0], [0])
        c2 = _make_cluster("d_1", [1.0, np.nan, 0.0], [1])
        positions = compute_positions([c1, c2])

        # Should not raise, positions should be finite
        assert len(positions) == 2
        for pos in positions.values():
            assert np.isfinite(pos[0])
            assert np.isfinite(pos[1])

    def test_high_dimensional_centroids(self):
        """Works with high-dimensional centroids."""
        dim = 128
        c1 = _make_cluster("d_0", list(np.random.randn(dim)), [0])
        c2 = _make_cluster("d_1", list(np.random.randn(dim)), [1])
        c3 = _make_cluster("d_2", list(np.random.randn(dim)), [2])
        positions = compute_positions([c1, c2, c3])

        # Should reduce to 2D
        for pos in positions.values():
            assert len(pos) == 2

    def test_identical_centroids_handled(self):
        """Identical centroids don't cause SVD failure."""
        c1 = _make_cluster("d_0", [1.0, 2.0, 3.0], [0])
        c2 = _make_cluster("d_1", [1.0, 2.0, 3.0], [1])  # Same centroid
        positions = compute_positions([c1, c2])

        # Should still produce valid positions
        assert len(positions) == 2


class TestComputeHierarchicalEdges:
    """Tests for edge computation between clusters."""

    @pytest.fixture
    def simple_setup(self):
        """Setup with 2 clusters and simple adjacency."""
        # 4 nodes: 0,1 in cluster A; 2,3 in cluster B
        clusters = [
            _make_cluster("d_4", [0.0], member_micro_indices=[0], size=2),
            _make_cluster("d_5", [1.0], member_micro_indices=[1], size=2),
        ]
        # micro_labels: node 0,1 -> micro 0; node 2,3 -> micro 1
        micro_labels = np.array([0, 0, 1, 1])
        node_ids = np.array(["n0", "n1", "n2", "n3"])
        # Adjacency: edge from node 0 -> node 2 (cross-cluster)
        adjacency = sparse.csr_matrix([
            [0, 1, 1, 0],  # node 0 -> node 1, node 2
            [0, 0, 0, 0],
            [0, 0, 0, 1],  # node 2 -> node 3
            [0, 0, 0, 0],
        ])
        return clusters, micro_labels, adjacency, node_ids

    def test_cross_cluster_edges_counted(self, simple_setup):
        """Edges between different clusters are counted."""
        clusters, micro_labels, adjacency, node_ids = simple_setup

        edges = compute_hierarchical_edges(
            clusters, micro_labels, adjacency, node_ids
        )

        # Should have 1 edge between d_4 and d_5
        assert len(edges) == 1
        edge = edges[0]
        assert {edge.source_id, edge.target_id} == {"d_4", "d_5"}

    def test_intra_cluster_edges_not_counted(self, simple_setup):
        """Edges within same cluster are NOT counted."""
        clusters, micro_labels, adjacency, node_ids = simple_setup

        edges = compute_hierarchical_edges(
            clusters, micro_labels, adjacency, node_ids
        )

        # Intra-cluster edges (0->1, 2->3) should not appear
        for edge in edges:
            assert edge.source_id != edge.target_id

    def test_connectivity_normalized_by_size(self):
        """Connectivity = raw_count / sqrt(size_A * size_B)."""
        clusters = [
            _make_cluster("d_0", [0.0], member_micro_indices=[0], size=4),
            _make_cluster("d_1", [1.0], member_micro_indices=[1], size=9),
        ]
        micro_labels = np.array([0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1])
        node_ids = np.array([f"n{i}" for i in range(13)])
        # Single edge from first cluster to second
        adjacency = sparse.lil_matrix((13, 13))
        adjacency[0, 4] = 1
        adjacency = adjacency.tocsr()

        edges = compute_hierarchical_edges(
            clusters, micro_labels, adjacency, node_ids
        )

        assert len(edges) == 1
        edge = edges[0]
        expected_connectivity = 1 / np.sqrt(4 * 9)  # 1/6
        assert abs(edge.connectivity - expected_connectivity) < 1e-10

    def test_edge_canonicalization(self, simple_setup):
        """Edge keys are canonicalized (source < target)."""
        clusters, micro_labels, adjacency, node_ids = simple_setup

        edges = compute_hierarchical_edges(
            clusters, micro_labels, adjacency, node_ids
        )

        for edge in edges:
            assert edge.source_id < edge.target_id

    def test_empty_adjacency_no_edges(self):
        """Empty adjacency produces no edges."""
        clusters = [
            _make_cluster("d_0", [0.0], member_micro_indices=[0], size=2),
            _make_cluster("d_1", [1.0], member_micro_indices=[1], size=2),
        ]
        micro_labels = np.array([0, 0, 1, 1])
        node_ids = np.array(["n0", "n1", "n2", "n3"])
        adjacency = sparse.csr_matrix((4, 4))

        edges = compute_hierarchical_edges(
            clusters, micro_labels, adjacency, node_ids
        )

        assert edges == []


class TestLouvainFusion:
    """Tests for Louvain community weighting on edges."""

    @pytest.fixture
    def louvain_setup(self):
        """Setup with Louvain communities crossing cluster boundaries."""
        clusters = [
            _make_cluster("d_0", [0.0], member_micro_indices=[0], size=2),
            _make_cluster("d_1", [1.0], member_micro_indices=[1], size=2),
        ]
        micro_labels = np.array([0, 0, 1, 1])
        node_ids = np.array(["n0", "n1", "n2", "n3"])
        # Edge from n0 to n2
        adjacency = sparse.csr_matrix([
            [0, 0, 1, 0],
            [0, 0, 0, 0],
            [0, 0, 0, 0],
            [0, 0, 0, 0],
        ])
        return clusters, micro_labels, adjacency, node_ids

    def test_same_community_boosts_edge(self, louvain_setup):
        """Edges within same Louvain community are boosted."""
        clusters, micro_labels, adjacency, node_ids = louvain_setup
        # n0 and n2 in same community
        louvain_communities = {"n0": 1, "n1": 1, "n2": 1, "n3": 2}

        edges_boosted = compute_hierarchical_edges(
            clusters, micro_labels, adjacency, node_ids,
            louvain_communities=louvain_communities,
            louvain_weight=0.5,
        )

        edges_baseline = compute_hierarchical_edges(
            clusters, micro_labels, adjacency, node_ids,
        )

        # Boosted edge should have higher raw_count (weighted)
        assert edges_boosted[0].raw_count > edges_baseline[0].raw_count

    def test_different_community_reduces_edge(self, louvain_setup):
        """Edges across Louvain communities are reduced."""
        clusters, micro_labels, adjacency, node_ids = louvain_setup
        # n0 and n2 in different communities
        louvain_communities = {"n0": 1, "n1": 1, "n2": 2, "n3": 2}

        edges_reduced = compute_hierarchical_edges(
            clusters, micro_labels, adjacency, node_ids,
            louvain_communities=louvain_communities,
            louvain_weight=0.5,
        )

        edges_baseline = compute_hierarchical_edges(
            clusters, micro_labels, adjacency, node_ids,
        )

        # Reduced edge should have lower raw_count (weighted)
        assert edges_reduced[0].raw_count < edges_baseline[0].raw_count

    def test_zero_louvain_weight_no_effect(self, louvain_setup):
        """Louvain weight of 0 has no effect."""
        clusters, micro_labels, adjacency, node_ids = louvain_setup
        louvain_communities = {"n0": 1, "n1": 1, "n2": 1, "n3": 2}

        edges_with = compute_hierarchical_edges(
            clusters, micro_labels, adjacency, node_ids,
            louvain_communities=louvain_communities,
            louvain_weight=0.0,
        )

        edges_without = compute_hierarchical_edges(
            clusters, micro_labels, adjacency, node_ids,
        )

        assert edges_with[0].raw_count == edges_without[0].raw_count

    def test_missing_louvain_label_ignored(self, louvain_setup):
        """Nodes without Louvain label treated as -1 (no boost/reduce)."""
        clusters, micro_labels, adjacency, node_ids = louvain_setup
        # n2 has no Louvain label
        louvain_communities = {"n0": 1, "n1": 1, "n3": 2}

        edges = compute_hierarchical_edges(
            clusters, micro_labels, adjacency, node_ids,
            louvain_communities=louvain_communities,
            louvain_weight=0.5,
        )

        # Should still compute edge (treated as different community)
        assert len(edges) == 1
