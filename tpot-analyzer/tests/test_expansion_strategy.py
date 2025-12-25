"""Tests for intelligent expansion strategy selection."""
import numpy as np
import pytest
import scipy.sparse as sp

from src.graph.hierarchy.expansion_strategy import (
    ExpansionStrategy,
    ExpansionDecision,
    LocalStructureMetrics,
    choose_expansion_strategy,
    compute_local_metrics,
    execute_tag_split,
    execute_core_periphery,
    execute_mutual_components,
    execute_bridge_extraction,
    execute_sample_individuals,
)


class TestComputeLocalMetrics:
    """Tests for local structure metric computation."""

    @pytest.fixture
    def simple_graph(self):
        """Create a simple test graph with 20 nodes."""
        n = 20
        # Create sparse adjacency with some edges
        rows = [0, 1, 1, 2, 2, 3, 5, 6, 7, 8, 10, 11, 12, 15, 16]
        cols = [1, 0, 2, 1, 3, 2, 6, 5, 8, 7, 11, 10, 13, 16, 15]
        data = [1.0] * len(rows)
        adjacency = sp.csr_matrix((data, (rows, cols)), shape=(n, n))

        node_ids = [f"node_{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        return adjacency, node_ids, node_id_to_idx

    def test_computes_basic_metrics(self, simple_graph):
        """Should compute density, degree stats, etc."""
        adjacency, node_ids, node_id_to_idx = simple_graph

        metrics = compute_local_metrics(
            member_node_ids=node_ids[:10],  # First 10 nodes
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        assert metrics.n_members == 10
        assert metrics.n_edges >= 0
        assert 0 <= metrics.density <= 1
        assert metrics.degree_mean >= 0

    def test_handles_empty_cluster(self, simple_graph):
        """Should handle empty input gracefully."""
        adjacency, _, node_id_to_idx = simple_graph

        metrics = compute_local_metrics(
            member_node_ids=[],
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        assert metrics.n_members == 0
        assert metrics.n_edges == 0
        assert metrics.density == 0

    def test_computes_tag_entropy(self, simple_graph):
        """Should compute tag entropy when tags provided."""
        adjacency, node_ids, node_id_to_idx = simple_graph

        # Create diverse tags
        node_tags = {
            "node_0": {"AI Safety"},
            "node_1": {"AI Safety"},
            "node_2": {"Rationalist"},
            "node_3": {"Rationalist"},
            "node_4": {"Meditation"},
        }

        metrics = compute_local_metrics(
            member_node_ids=node_ids[:5],
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            node_tags=node_tags,
        )

        assert metrics.n_distinct_tags == 3
        assert metrics.tag_entropy > 0


class TestChooseExpansionStrategy:
    """Tests for strategy selection logic."""

    @pytest.fixture
    def dense_graph(self):
        """Create a dense graph with clear structure."""
        n = 50
        rows, cols = [], []
        rng = np.random.RandomState(42)

        # Create two dense communities
        for i in range(25):
            for j in range(i + 1, 25):
                if rng.random() < 0.6:
                    rows.extend([i, j])
                    cols.extend([j, i])

        for i in range(25, 50):
            for j in range(i + 1, 50):
                if rng.random() < 0.6:
                    rows.extend([i, j])
                    cols.extend([j, i])

        # Few cross-edges
        rows.extend([0, 25])
        cols.extend([25, 0])

        data = [1.0] * len(rows)
        adjacency = sp.csr_matrix((data, (rows, cols)), shape=(n, n))

        node_ids = [f"node_{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        return adjacency, node_ids, node_id_to_idx

    def test_tiny_cluster_returns_individuals(self, dense_graph):
        """Clusters with <=5 members should show as individuals."""
        adjacency, node_ids, node_id_to_idx = dense_graph

        decision = choose_expansion_strategy(
            member_node_ids=node_ids[:3],
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        assert decision.strategy == ExpansionStrategy.INDIVIDUALS
        assert decision.confidence == 1.0

    def test_tag_diversity_triggers_tag_split(self, dense_graph):
        """High tag diversity should trigger tag-based split."""
        adjacency, node_ids, node_id_to_idx = dense_graph

        # Create diverse tags
        node_tags = {}
        for i, nid in enumerate(node_ids[:30]):
            if i < 10:
                node_tags[nid] = {"AI Safety"}
            elif i < 20:
                node_tags[nid] = {"Rationalist"}
            else:
                node_tags[nid] = {"Meditation"}

        decision = choose_expansion_strategy(
            member_node_ids=node_ids[:30],
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            node_tags=node_tags,
        )

        assert decision.strategy == ExpansionStrategy.TAG_SPLIT
        assert "tag" in decision.reason.lower()

    def test_dense_graph_uses_louvain(self, dense_graph):
        """Dense graphs without special structure should use Louvain."""
        adjacency, node_ids, node_id_to_idx = dense_graph

        decision = choose_expansion_strategy(
            member_node_ids=node_ids[:30],
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        # Should either use Louvain or core-periphery depending on degree variance
        assert decision.strategy in [
            ExpansionStrategy.LOUVAIN,
            ExpansionStrategy.CORE_PERIPHERY,
            ExpansionStrategy.MUTUAL_COMPONENTS,
        ]

    def test_no_structure_shows_individuals(self):
        """Cluster with no edges should show individuals or sample."""
        n = 15
        adjacency = sp.csr_matrix((n, n))  # No edges
        node_ids = [f"node_{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        decision = choose_expansion_strategy(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        assert decision.strategy == ExpansionStrategy.INDIVIDUALS
        assert "no internal structure" in decision.reason.lower()

    def test_large_no_structure_samples(self):
        """Large cluster with no edges should sample individuals."""
        n = 30
        adjacency = sp.csr_matrix((n, n))  # No edges
        node_ids = [f"node_{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        decision = choose_expansion_strategy(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        assert decision.strategy == ExpansionStrategy.SAMPLE_INDIVIDUALS

    def test_alternatives_provided(self, dense_graph):
        """Should provide alternative strategies when applicable."""
        adjacency, node_ids, node_id_to_idx = dense_graph

        decision = choose_expansion_strategy(
            member_node_ids=node_ids[:30],
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        # Most decisions should have alternatives
        # (only tiny clusters and no-structure have empty alternatives)
        if decision.strategy not in [ExpansionStrategy.INDIVIDUALS]:
            assert len(decision.alternatives) > 0


class TestExecuteTagSplit:
    """Tests for tag-based splitting."""

    def test_splits_by_tags(self):
        """Should create one sub-cluster per tag."""
        member_ids = [f"node_{i}" for i in range(15)]
        node_tags = {
            "node_0": {"A"},
            "node_1": {"A"},
            "node_2": {"A"},
            "node_3": {"B"},
            "node_4": {"B"},
            "node_5": {"C"},
        }
        tag_counts = {"A": 3, "B": 2, "C": 1}

        result = execute_tag_split(member_ids, node_tags, tag_counts)

        # Should have 4 clusters: A, B, C, and untagged
        assert len(result) == 4

        # All nodes should be assigned
        all_assigned = set()
        for cluster in result:
            all_assigned.update(cluster)
        assert all_assigned == set(member_ids)

    def test_untagged_nodes_grouped(self):
        """Untagged nodes should be grouped together."""
        member_ids = [f"node_{i}" for i in range(10)]
        node_tags = {
            "node_0": {"A"},
            "node_1": {"A"},
        }
        tag_counts = {"A": 2}

        result = execute_tag_split(member_ids, node_tags, tag_counts)

        # Find untagged cluster (should be size 8)
        untagged = [c for c in result if len(c) == 8]
        assert len(untagged) == 1


class TestExecuteCorePeriPhery:
    """Tests for core-periphery decomposition."""

    def test_splits_by_degree(self):
        """Should split into high-degree and low-degree groups."""
        n = 20
        # Create star graph: node 0 connects to all others
        rows = []
        cols = []
        for i in range(1, n):
            rows.extend([0, i])
            cols.extend([i, 0])

        adjacency = sp.csr_matrix(([1.0] * len(rows), (rows, cols)), shape=(n, n))
        node_ids = [f"node_{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        result = execute_core_periphery(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            degree_threshold=5,
        )

        assert len(result) == 2
        # One cluster should be small (core), one large (periphery)
        sizes = sorted([len(c) for c in result])
        assert sizes[0] < sizes[1]


class TestExecuteMutualComponents:
    """Tests for mutual edge component extraction."""

    def test_finds_mutual_components(self):
        """Should find connected components of mutual edges."""
        n = 10
        # Create two mutual cliques
        rows = [0, 1, 1, 0, 2, 3, 3, 2, 5, 6, 6, 5, 7, 8, 8, 7]
        cols = [1, 0, 2, 2, 3, 2, 0, 3, 6, 5, 7, 7, 8, 7, 5, 6]

        # Add non-mutual edge
        rows.extend([0, 9])
        cols.extend([9, 0])  # Wait, this is mutual. Let's make it one-way
        rows = [0, 1, 1, 0, 2, 3, 3, 2, 5, 6, 6, 5, 7, 8, 8, 7, 0]
        cols = [1, 0, 2, 2, 3, 2, 0, 3, 6, 5, 7, 7, 8, 7, 5, 6, 9]

        adjacency = sp.csr_matrix(([1.0] * len(rows), (rows, cols)), shape=(n, n))
        node_ids = [f"node_{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        result = execute_mutual_components(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        # Should find multiple components
        assert len(result) >= 2


class TestExecuteBridgeExtraction:
    """Tests for bridge node extraction."""

    def test_extracts_bridges_as_singletons(self):
        """Bridge nodes should become singleton clusters."""
        member_ids = [f"node_{i}" for i in range(10)]
        bridge_nodes = ["node_0", "node_5"]

        result = execute_bridge_extraction(member_ids, bridge_nodes)

        # Should have 3 clusters: 2 singletons + 1 rest
        assert len(result) == 3

        # Find singletons
        singletons = [c for c in result if len(c) == 1]
        assert len(singletons) == 2

        # Verify bridges are singletons
        bridge_set = set(bridge_nodes)
        for s in singletons:
            assert s[0] in bridge_set


class TestExecuteSampleIndividuals:
    """Tests for sampling top individuals."""

    def test_samples_by_degree(self):
        """Should sample top nodes by in-degree."""
        n = 30
        # Create graph where some nodes have higher degree
        rows, cols = [], []
        # Node 0 gets many edges
        for i in range(1, 20):
            rows.extend([i, 0])
            cols.extend([0, i])

        adjacency = sp.csr_matrix(([1.0] * len(rows), (rows, cols)), shape=(n, n))
        node_ids = [f"node_{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        result = execute_sample_individuals(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            sample_size=5,
        )

        # Should have 6 clusters: 5 singletons + 1 overflow
        assert len(result) == 6

        # First singleton should be highest degree node
        assert result[0] == ["node_0"]

        # Last cluster is overflow
        assert len(result[-1]) == 25

    def test_preserves_all_nodes(self):
        """All nodes should appear in output."""
        n = 20
        adjacency = sp.csr_matrix((n, n))
        node_ids = [f"node_{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        result = execute_sample_individuals(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            sample_size=10,
        )

        all_nodes = set()
        for cluster in result:
            all_nodes.update(cluster)

        assert all_nodes == set(node_ids)


class TestEvaluateAllStrategies:
    """Tests for self-evaluating strategy selection."""

    @pytest.fixture
    def community_graph(self):
        """Create a graph with two clear communities."""
        n = 30
        rows, cols = [], []
        rng = np.random.RandomState(42)

        # Community 1: nodes 0-14 (dense connections)
        for i in range(15):
            for j in range(i + 1, 15):
                if rng.random() < 0.5:
                    rows.extend([i, j])
                    cols.extend([j, i])

        # Community 2: nodes 15-29 (dense connections)
        for i in range(15, 30):
            for j in range(i + 1, 30):
                if rng.random() < 0.5:
                    rows.extend([i, j])
                    cols.extend([j, i])

        # Few cross-community edges
        rows.extend([7, 22, 3, 25])
        cols.extend([22, 7, 25, 3])

        data = [1.0] * len(rows)
        adjacency = sp.csr_matrix((data, (rows, cols)), shape=(n, n))

        node_ids = [f"node_{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        return adjacency, node_ids, node_id_to_idx

    def test_returns_ranked_strategies(self, community_graph):
        """Should return multiple strategies ranked by score."""
        from src.graph.hierarchy.expansion_strategy import evaluate_all_strategies

        adjacency, node_ids, node_id_to_idx = community_graph

        ranked = evaluate_all_strategies(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        assert len(ranked) >= 1
        # Should be sorted by score descending
        for i in range(len(ranked) - 1):
            assert ranked[i].score.total_score >= ranked[i + 1].score.total_score

    def test_louvain_scores_well_on_community_graph(self, community_graph):
        """Louvain should score highly on graph with clear communities."""
        from src.graph.hierarchy.expansion_strategy import evaluate_all_strategies

        adjacency, node_ids, node_id_to_idx = community_graph

        ranked = evaluate_all_strategies(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        # Find Louvain in results
        louvain_strategies = [s for s in ranked if s.strategy_name == "louvain"]

        # Louvain should be present and have reasonable score
        assert len(louvain_strategies) >= 1
        assert louvain_strategies[0].score.total_score > 0.4

    def test_tag_split_ranks_high_with_good_tags(self, community_graph):
        """Tag split should rank highly when tags match communities."""
        from src.graph.hierarchy.expansion_strategy import evaluate_all_strategies

        adjacency, node_ids, node_id_to_idx = community_graph

        # Tags that match the community structure
        node_tags = {}
        for i, nid in enumerate(node_ids):
            if i < 15:
                node_tags[nid] = {"Community-A"}
            else:
                node_tags[nid] = {"Community-B"}

        ranked = evaluate_all_strategies(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            node_tags=node_tags,
        )

        # Find tag split in results
        tag_strategies = [s for s in ranked if s.strategy_name == "tag_split"]

        # Tag split should be present
        assert len(tag_strategies) >= 1
        # With perfect tags, it should score very well on tag coherence
        assert tag_strategies[0].score.tag_coherence_score == 1.0

    def test_small_cluster_includes_individuals(self):
        """Small clusters should include INDIVIDUALS strategy."""
        from src.graph.hierarchy.expansion_strategy import evaluate_all_strategies

        n = 10
        adjacency = sp.csr_matrix((n, n))
        node_ids = [f"node_{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        ranked = evaluate_all_strategies(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        strategy_names = [s.strategy_name for s in ranked]
        assert "individuals" in strategy_names

    def test_includes_execution_time(self, community_graph):
        """Each strategy should have execution time recorded."""
        from src.graph.hierarchy.expansion_strategy import evaluate_all_strategies

        adjacency, node_ids, node_id_to_idx = community_graph

        ranked = evaluate_all_strategies(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        for strategy in ranked:
            assert strategy.execution_time_ms >= 0

    def test_get_best_expansion_returns_top(self, community_graph):
        """get_best_expansion should return the top-ranked strategy."""
        from src.graph.hierarchy.expansion_strategy import (
            evaluate_all_strategies,
            get_best_expansion,
        )

        adjacency, node_ids, node_id_to_idx = community_graph

        ranked = evaluate_all_strategies(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        best = get_best_expansion(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        assert best is not None
        assert best.strategy_name == ranked[0].strategy_name
        assert best.score.total_score == ranked[0].score.total_score


class TestExecuteLouvainLocal:
    """Tests for local Louvain execution."""

    def test_finds_communities(self):
        """Should find communities in a graph with structure."""
        from src.graph.hierarchy.expansion_strategy import execute_louvain_local

        n = 20
        rows, cols = [], []

        # Two dense cliques
        for i in range(10):
            for j in range(i + 1, 10):
                rows.extend([i, j])
                cols.extend([j, i])

        for i in range(10, 20):
            for j in range(i + 1, 20):
                rows.extend([i, j])
                cols.extend([j, i])

        # One cross-edge
        rows.extend([0, 10])
        cols.extend([10, 0])

        data = [1.0] * len(rows)
        adjacency = sp.csr_matrix((data, (rows, cols)), shape=(n, n))

        node_ids = [f"node_{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        result = execute_louvain_local(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        # Should find 2 communities
        assert len(result) == 2

        # Each community should have roughly 10 nodes
        sizes = sorted([len(c) for c in result])
        assert sizes == [10, 10]

    def test_returns_single_cluster_for_no_edges(self):
        """Should return single cluster when no edges."""
        from src.graph.hierarchy.expansion_strategy import execute_louvain_local

        n = 10
        adjacency = sp.csr_matrix((n, n))
        node_ids = [f"node_{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        result = execute_louvain_local(
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )

        assert len(result) == 1
        assert set(result[0]) == set(node_ids)
