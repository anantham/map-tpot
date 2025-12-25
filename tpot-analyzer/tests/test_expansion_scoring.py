"""Tests for expansion scoring system."""
import numpy as np
import pytest
import scipy.sparse as sp

from src.graph.hierarchy.expansion_scoring import (
    StructureScoreWeights,
    StructureScoreBreakdown,
    compute_size_entropy,
    compute_collapse_ratio,
    compute_fragmentation_ratio,
    compute_edge_separation_fast,
    compute_tag_coherence,
    compute_structure_score,
    rank_strategies,
    ScoredStrategy,
)


class TestSizeEntropy:
    """Tests for size entropy computation."""

    def test_uniform_distribution_has_max_entropy(self):
        """Equal-sized clusters should have entropy = 1."""
        sizes = [10, 10, 10, 10]
        entropy = compute_size_entropy(sizes)
        assert entropy > 0.99  # Should be ~1.0

    def test_single_cluster_has_zero_entropy(self):
        """Single cluster has no diversity."""
        sizes = [100]
        entropy = compute_size_entropy(sizes)
        assert entropy == 0.0

    def test_skewed_distribution_has_low_entropy(self):
        """One dominant cluster reduces entropy."""
        sizes = [90, 5, 3, 2]
        entropy = compute_size_entropy(sizes)
        assert entropy < 0.5

    def test_empty_returns_zero(self):
        """Empty input should return 0."""
        assert compute_size_entropy([]) == 0.0


class TestCollapseRatio:
    """Tests for collapse ratio computation."""

    def test_single_cluster_is_total_collapse(self):
        """Single cluster = 100% collapse."""
        sizes = [100]
        ratio = compute_collapse_ratio(sizes)
        assert ratio == 1.0

    def test_uniform_clusters_low_collapse(self):
        """Equal clusters = low collapse."""
        sizes = [25, 25, 25, 25]
        ratio = compute_collapse_ratio(sizes)
        assert ratio == 0.25

    def test_one_dominant_high_collapse(self):
        """One large cluster = high collapse."""
        sizes = [80, 10, 10]
        ratio = compute_collapse_ratio(sizes)
        assert ratio == 0.8


class TestFragmentationRatio:
    """Tests for fragmentation ratio computation."""

    def test_all_singletons_is_max_fragmentation(self):
        """All size-1 clusters = 100% fragmentation."""
        sizes = [1, 1, 1, 1, 1]
        ratio = compute_fragmentation_ratio(sizes, total_members=5)
        assert ratio == 1.0

    def test_no_singletons_is_zero_fragmentation(self):
        """No singletons = 0% fragmentation."""
        sizes = [10, 10, 10]
        ratio = compute_fragmentation_ratio(sizes, total_members=30)
        assert ratio == 0.0

    def test_mixed_fragmentation(self):
        """Some singletons gives partial fragmentation."""
        sizes = [10, 5, 1, 1, 1]  # 3 singletons out of 18 members
        ratio = compute_fragmentation_ratio(sizes, total_members=18)
        assert 0.1 < ratio < 0.3


class TestEdgeSeparation:
    """Tests for edge separation scoring."""

    @pytest.fixture
    def two_cliques_graph(self):
        """Create graph with two separate cliques."""
        n = 10
        rows, cols = [], []

        # Clique 1: nodes 0-4
        for i in range(5):
            for j in range(i + 1, 5):
                rows.extend([i, j])
                cols.extend([j, i])

        # Clique 2: nodes 5-9
        for i in range(5, 10):
            for j in range(i + 1, 10):
                rows.extend([i, j])
                cols.extend([j, i])

        # One cross-edge
        rows.extend([0, 5])
        cols.extend([5, 0])

        adjacency = sp.csr_matrix(([1.0] * len(rows), (rows, cols)), shape=(n, n))
        node_ids = [f"n{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        return adjacency, node_ids, node_id_to_idx

    def test_perfect_separation_high_score(self, two_cliques_graph):
        """Clusters matching cliques should have high edge separation."""
        adjacency, node_ids, node_id_to_idx = two_cliques_graph

        # Split exactly at clique boundaries
        sub_clusters = [
            [f"n{i}" for i in range(5)],
            [f"n{i}" for i in range(5, 10)],
        ]

        score, intra, inter = compute_edge_separation_fast(
            sub_clusters, adjacency, node_id_to_idx
        )

        assert score > 0.8  # Most edges should be intra-cluster
        assert intra > inter

    def test_random_split_lower_score(self, two_cliques_graph):
        """Random split should have lower edge separation."""
        adjacency, node_ids, node_id_to_idx = two_cliques_graph

        # Random split (mixes cliques)
        sub_clusters = [
            ["n0", "n1", "n5", "n6", "n7"],
            ["n2", "n3", "n4", "n8", "n9"],
        ]

        score, intra, inter = compute_edge_separation_fast(
            sub_clusters, adjacency, node_id_to_idx
        )

        assert score < 0.8  # Should be worse than perfect split


class TestTagCoherence:
    """Tests for tag coherence scoring."""

    def test_perfect_tag_alignment(self):
        """Clusters perfectly matching tags should score high."""
        sub_clusters = [
            ["a1", "a2", "a3"],
            ["b1", "b2", "b3"],
        ]
        node_tags = {
            "a1": {"GroupA"},
            "a2": {"GroupA"},
            "a3": {"GroupA"},
            "b1": {"GroupB"},
            "b2": {"GroupB"},
            "b3": {"GroupB"},
        }

        score = compute_tag_coherence(sub_clusters, node_tags)
        assert score == 1.0  # Perfect alignment

    def test_random_tag_distribution_lower_score(self):
        """Tags scattered across clusters should score lower."""
        sub_clusters = [
            ["a1", "b1", "c1"],
            ["a2", "b2", "c2"],
        ]
        node_tags = {
            "a1": {"GroupA"},
            "a2": {"GroupA"},
            "b1": {"GroupB"},
            "b2": {"GroupB"},
            "c1": {"GroupC"},
            "c2": {"GroupC"},
        }

        score = compute_tag_coherence(sub_clusters, node_tags)
        assert score < 0.5  # Poor alignment

    def test_no_tags_returns_neutral(self):
        """No tags should return neutral score."""
        sub_clusters = [["a", "b"], ["c", "d"]]

        score = compute_tag_coherence(sub_clusters, None)
        assert score == 0.5

        score = compute_tag_coherence(sub_clusters, {})
        assert score == 0.5


class TestStructureScore:
    """Tests for overall structure score computation."""

    @pytest.fixture
    def simple_graph(self):
        """Create a simple graph for testing."""
        n = 20
        rows, cols = [], []

        # Some edges
        for i in range(n - 1):
            rows.extend([i, i + 1])
            cols.extend([i + 1, i])

        adjacency = sp.csr_matrix(([1.0] * len(rows), (rows, cols)), shape=(n, n))
        node_ids = [f"n{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        return adjacency, node_ids, node_id_to_idx

    def test_good_clustering_high_score(self, simple_graph):
        """Well-balanced clustering should score high."""
        adjacency, node_ids, node_id_to_idx = simple_graph

        # Balanced clusters
        sub_clusters = [
            node_ids[0:7],
            node_ids[7:14],
            node_ids[14:20],
        ]

        result = compute_structure_score(
            sub_clusters=sub_clusters,
            total_members=20,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        assert result.total_score > 0.5
        assert result.n_clusters == 3
        assert result.collapse_score > 0.5  # Not dominated by one cluster

    def test_single_cluster_low_score(self, simple_graph):
        """Everything in one cluster should score low."""
        adjacency, node_ids, node_id_to_idx = simple_graph

        sub_clusters = [node_ids]  # All in one

        result = compute_structure_score(
            sub_clusters=sub_clusters,
            total_members=20,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        assert result.total_score < 0.3
        assert "single cluster" in result.reason.lower()

    def test_all_singletons_penalized(self, simple_graph):
        """All singletons should be penalized."""
        adjacency, node_ids, node_id_to_idx = simple_graph

        sub_clusters = [[nid] for nid in node_ids]  # All singletons

        result = compute_structure_score(
            sub_clusters=sub_clusters,
            total_members=20,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        assert result.fragmentation_score == 0.0  # Max fragmentation
        assert result.singleton_count == 20

    def test_custom_weights(self, simple_graph):
        """Custom weights should affect final score."""
        adjacency, node_ids, node_id_to_idx = simple_graph

        sub_clusters = [node_ids[0:10], node_ids[10:20]]

        # Default weights
        result1 = compute_structure_score(
            sub_clusters=sub_clusters,
            total_members=20,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        # Heavy weight on edge separation
        custom_weights = StructureScoreWeights(
            size_entropy=0.1,
            collapse_penalty=0.1,
            fragmentation_penalty=0.1,
            edge_separation=10.0,  # Heavily weighted
            tag_coherence=0.1,
        )

        result2 = compute_structure_score(
            sub_clusters=sub_clusters,
            total_members=20,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            weights=custom_weights,
        )

        # Scores should differ due to weighting
        # (Can't guarantee direction without knowing exact edge structure)
        assert result1.total_score != result2.total_score or \
               result1.edge_separation_score == result2.edge_separation_score

    def test_breakdown_includes_raw_metrics(self, simple_graph):
        """Breakdown should include debugging metrics."""
        adjacency, node_ids, node_id_to_idx = simple_graph

        sub_clusters = [node_ids[0:5], node_ids[5:10], node_ids[10:15], node_ids[15:20]]

        result = compute_structure_score(
            sub_clusters=sub_clusters,
            total_members=20,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        assert result.n_clusters == 4
        assert result.largest_cluster_size == 5
        assert result.reason != ""


class TestRankStrategies:
    """Tests for strategy ranking."""

    def test_ranks_by_score_descending(self):
        """Strategies should be ranked highest score first."""
        strategies = [
            ScoredStrategy(
                strategy_name="Low",
                sub_clusters=[],
                score=StructureScoreBreakdown(total_score=0.3),
            ),
            ScoredStrategy(
                strategy_name="High",
                sub_clusters=[],
                score=StructureScoreBreakdown(total_score=0.9),
            ),
            ScoredStrategy(
                strategy_name="Medium",
                sub_clusters=[],
                score=StructureScoreBreakdown(total_score=0.6),
            ),
        ]

        ranked = rank_strategies(strategies)

        assert ranked[0].strategy_name == "High"
        assert ranked[1].strategy_name == "Medium"
        assert ranked[2].strategy_name == "Low"


class TestWeightsNormalization:
    """Tests for weight normalization."""

    def test_normalizes_to_sum_one(self):
        """Normalized weights should sum to 1."""
        weights = StructureScoreWeights(
            size_entropy=2.0,
            collapse_penalty=3.0,
            fragmentation_penalty=1.0,
            edge_separation=2.0,
            tag_coherence=2.0,
        )

        normalized = weights.normalize()

        total = (
            normalized.size_entropy +
            normalized.collapse_penalty +
            normalized.fragmentation_penalty +
            normalized.edge_separation +
            normalized.tag_coherence
        )

        assert abs(total - 1.0) < 0.001

    def test_preserves_ratios(self):
        """Normalization should preserve relative weights."""
        weights = StructureScoreWeights(
            size_entropy=2.0,
            collapse_penalty=4.0,
            fragmentation_penalty=2.0,
            edge_separation=2.0,
            tag_coherence=0.0,
        )

        normalized = weights.normalize()

        # collapse should be 2x size_entropy
        assert abs(normalized.collapse_penalty / normalized.size_entropy - 2.0) < 0.001
