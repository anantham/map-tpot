"""Tests for local Louvain-based cluster expansion."""
import numpy as np
import pytest
import scipy.sparse as sp

from src.graph.hierarchy.local_expand import (
    expand_cluster_locally,
    should_use_local_expansion,
    LARGE_CLUSTER_FRACTION,
    _local_expansion_cache,
    _cache_timestamps,
)


class TestShouldUseLocalExpansion:
    """Tests for the should_use_local_expansion heuristic."""

    def test_triggers_for_majority_cluster(self):
        """Clusters with >50% of nodes should always trigger local expansion."""
        assert should_use_local_expansion(
            cluster_size=600,
            total_nodes=1000,
            micro_cluster_count=100,
            cluster_micro_count=10,
        ) is True

    def test_triggers_for_large_cluster_with_few_micros(self):
        """Large clusters (>15%) with <=3 micro-clusters should trigger."""
        assert should_use_local_expansion(
            cluster_size=200,  # 20%
            total_nodes=1000,
            micro_cluster_count=100,
            cluster_micro_count=2,  # Very few micro-clusters
        ) is True

    def test_does_not_trigger_for_small_cluster(self):
        """Clusters with <15% of nodes should not trigger."""
        assert should_use_local_expansion(
            cluster_size=100,  # 10%
            total_nodes=1000,
            micro_cluster_count=100,
            cluster_micro_count=10,
        ) is False

    def test_does_not_trigger_for_well_subdivided_cluster(self):
        """Large clusters with many micro-clusters and normal density should not trigger."""
        # 20% of nodes, but with 30 micro-clusters (well subdivided)
        assert should_use_local_expansion(
            cluster_size=200,
            total_nodes=1000,
            micro_cluster_count=100,
            cluster_micro_count=30,
        ) is False

    def test_mega_cluster_real_data_parameters(self):
        """Test with actual data parameters from the 76% mega-cluster case."""
        # 71,761 total nodes, 106 micro-clusters, mega-cluster has 54,834 nodes
        assert should_use_local_expansion(
            cluster_size=54834,
            total_nodes=71761,
            micro_cluster_count=106,
            cluster_micro_count=9,  # Mega-cluster spans 9 micro-clusters
        ) is True


class TestExpandClusterLocally:
    """Tests for the expand_cluster_locally function."""

    @pytest.fixture
    def two_communities_graph(self):
        """Create a graph with two clearly separated communities."""
        n = 100
        rows, cols = [], []
        rng = np.random.RandomState(42)

        # Dense connections within group 1 (nodes 0-49)
        for i in range(50):
            for j in range(i + 1, 50):
                if rng.random() < 0.5:  # High density
                    rows.extend([i, j])
                    cols.extend([j, i])

        # Dense connections within group 2 (nodes 50-99)
        for i in range(50, 100):
            for j in range(i + 1, 100):
                if rng.random() < 0.5:  # High density
                    rows.extend([i, j])
                    cols.extend([j, i])

        # Only 1 cross-group edge to keep communities clearly separated
        rows.extend([0, 50])
        cols.extend([50, 0])

        data = [1.0] * len(rows)
        adjacency = sp.csr_matrix((data, (rows, cols)), shape=(n, n))

        node_ids = [f"node_{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        return adjacency, node_ids, node_id_to_idx

    def test_finds_two_communities(self, two_communities_graph):
        """Should find the two clear community structure."""
        adjacency, node_ids, node_id_to_idx = two_communities_graph

        result = expand_cluster_locally(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            target_children=10,
        )

        assert result.success is True
        assert result.n_communities >= 2

        # With clearly separated communities, the two largest should
        # roughly correspond to our two groups (allowing some overlap)
        top_two = result.sub_clusters[:2]
        for sc in top_two:
            group1_count = sum(1 for n in sc if int(n.split("_")[1]) < 50)
            group2_count = len(sc) - group1_count
            # Each of the top communities should be mostly from one group
            assert group1_count > 0.6 * len(sc) or group2_count > 0.6 * len(sc)

    def test_returns_failure_for_tiny_cluster(self):
        """Clusters with <10 nodes should fail."""
        adjacency = sp.csr_matrix((5, 5))
        node_ids = [f"node_{i}" for i in range(5)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        result = expand_cluster_locally(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            target_children=3,
        )

        assert result.success is False
        assert "too small" in result.reason.lower()

    def test_returns_single_cluster_for_no_edges(self):
        """Cluster with no internal edges should return single cluster."""
        n = 20
        adjacency = sp.csr_matrix((n, n))  # No edges
        node_ids = [f"node_{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        result = expand_cluster_locally(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            target_children=5,
        )

        # Should fail gracefully (no edges = can't find communities)
        assert result.n_communities == 1

    def test_preserves_all_nodes(self, two_communities_graph):
        """All input nodes should be present in output sub-clusters."""
        adjacency, node_ids, node_id_to_idx = two_communities_graph

        result = expand_cluster_locally(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            target_children=5,
        )

        all_output_nodes = set()
        for sc in result.sub_clusters:
            all_output_nodes.update(sc)

        assert all_output_nodes == set(node_ids)

    def test_sub_clusters_sorted_by_size(self, two_communities_graph):
        """Sub-clusters should be sorted by size descending."""
        adjacency, node_ids, node_id_to_idx = two_communities_graph

        result = expand_cluster_locally(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            target_children=10,
        )

        sizes = [len(sc) for sc in result.sub_clusters]
        assert sizes == sorted(sizes, reverse=True)

    def test_resolution_scales_with_target(self, two_communities_graph):
        """Higher target_children should use higher resolution."""
        adjacency, node_ids, node_id_to_idx = two_communities_graph

        result_low = expand_cluster_locally(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            target_children=5,
        )

        result_high = expand_cluster_locally(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            target_children=50,
        )

        assert result_high.resolution_used > result_low.resolution_used

    def test_caching_returns_same_result(self, two_communities_graph):
        """Second call with same inputs should return cached result."""
        adjacency, node_ids, node_id_to_idx = two_communities_graph

        # Clear cache first
        _local_expansion_cache.clear()
        _cache_timestamps.clear()

        # First call - computes result
        result1 = expand_cluster_locally(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            target_children=10,
        )

        # Second call - should hit cache
        result2 = expand_cluster_locally(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            target_children=10,
        )

        # Results should be identical (same object from cache)
        assert result1 is result2
        assert result1.n_communities == result2.n_communities
        assert result1.sub_clusters == result2.sub_clusters

    def test_cache_differentiates_by_resolution(self, two_communities_graph):
        """Different target_children should produce different cache entries."""
        adjacency, node_ids, node_id_to_idx = two_communities_graph

        # Clear cache first
        _local_expansion_cache.clear()
        _cache_timestamps.clear()

        result_low = expand_cluster_locally(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            target_children=5,
        )

        result_high = expand_cluster_locally(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            target_children=50,
        )

        # Should have 2 separate cache entries
        assert len(_local_expansion_cache) == 2
        # Results should differ
        assert result_low.resolution_used != result_high.resolution_used
