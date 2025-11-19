"""End-to-end workflow integration tests.

Tests complete workflows from data fetching through graph analysis to API responses.
These tests verify that all components work together correctly.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, Mock, patch

import networkx as nx
import pandas as pd
import pytest

from src.data.fetcher import CachedDataFetcher
from src.graph.builder import build_graph_from_data
from src.graph.metrics import compute_personalized_pagerank
from src.graph.seeds import resolve_seeds


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def sample_accounts_df():
    """Sample accounts DataFrame for testing."""
    return pd.DataFrame({
        "username": ["alice", "bob", "charlie", "diana"],
        "follower_count": [1000, 500, 2000, 1500],
        "is_shadow": [False, False, False, False],
    })


@pytest.fixture
def sample_edges_df():
    """Sample edges DataFrame for testing."""
    return pd.DataFrame({
        "source": ["alice", "alice", "bob", "charlie", "diana"],
        "target": ["bob", "charlie", "charlie", "diana", "alice"],
        "is_shadow": [False, False, False, False, False],
        "is_mutual": [True, False, True, False, True],
    })


@pytest.fixture
def mock_fetcher(sample_accounts_df, sample_edges_df):
    """Mock CachedDataFetcher for testing."""
    fetcher = Mock(spec=CachedDataFetcher)
    fetcher.fetch_accounts.return_value = sample_accounts_df
    fetcher.fetch_edges.return_value = sample_edges_df
    return fetcher


# ==============================================================================
# End-to-End Workflow Tests
# ==============================================================================

@pytest.mark.integration
def test_complete_workflow_from_fetch_to_metrics(mock_fetcher):
    """Test complete workflow: fetch data → build graph → compute metrics."""
    # Step 1: Fetch data
    accounts_df = mock_fetcher.fetch_accounts()
    edges_df = mock_fetcher.fetch_edges()

    assert len(accounts_df) == 4
    assert len(edges_df) == 5

    # Step 2: Build graph
    graph = build_graph_from_data(
        accounts_df=accounts_df,
        edges_df=edges_df,
        include_shadow=False,
        mutual_only=False,
        min_followers=0,
    )

    assert isinstance(graph, nx.DiGraph)
    assert graph.number_of_nodes() == 4
    assert graph.number_of_edges() == 5

    # Step 3: Resolve seeds
    seeds = ["alice", "bob"]
    resolved = resolve_seeds(graph, seeds)

    assert resolved == ["alice", "bob"]

    # Step 4: Compute metrics
    pagerank = compute_personalized_pagerank(graph, seeds=resolved, alpha=0.85)

    assert len(pagerank) == 4
    assert sum(pagerank.values()) == pytest.approx(1.0, abs=0.01)
    assert all(score >= 0 for score in pagerank.values())


@pytest.mark.integration
def test_workflow_with_invalid_seeds(mock_fetcher):
    """Test workflow gracefully handles invalid seeds."""
    # Fetch and build graph
    accounts_df = mock_fetcher.fetch_accounts()
    edges_df = mock_fetcher.fetch_edges()
    graph = build_graph_from_data(accounts_df, edges_df)

    # Try to resolve invalid seeds
    seeds = ["nonexistent_user"]
    resolved = resolve_seeds(graph, seeds)

    # Should return empty list
    assert resolved == []


@pytest.mark.integration
def test_workflow_with_shadow_filtering(sample_accounts_df, sample_edges_df):
    """Test workflow filters shadow accounts correctly."""
    # Add shadow accounts
    shadow_df = pd.DataFrame({
        "username": ["shadow1", "shadow2"],
        "follower_count": [100, 200],
        "is_shadow": [True, True],
    })
    accounts_with_shadow = pd.concat([sample_accounts_df, shadow_df], ignore_index=True)

    # Add shadow edges
    shadow_edges = pd.DataFrame({
        "source": ["alice", "shadow1"],
        "target": ["shadow1", "shadow2"],
        "is_shadow": [True, True],
        "is_mutual": [False, False],
    })
    edges_with_shadow = pd.concat([sample_edges_df, shadow_edges], ignore_index=True)

    # Build graph WITHOUT shadow (include_shadow=False)
    graph = build_graph_from_data(
        accounts_df=accounts_with_shadow,
        edges_df=edges_with_shadow,
        include_shadow=False,
    )

    # Shadow accounts should be excluded
    assert graph.number_of_nodes() == 4  # Only non-shadow accounts
    assert "shadow1" not in graph.nodes()
    assert "shadow2" not in graph.nodes()


@pytest.mark.integration
def test_workflow_with_mutual_only_filtering(sample_accounts_df, sample_edges_df):
    """Test workflow filters to mutual follows only."""
    # Build graph with mutual_only=True
    graph = build_graph_from_data(
        accounts_df=sample_accounts_df,
        edges_df=sample_edges_df,
        mutual_only=True,
    )

    # Should only have mutual edges
    # From sample data: alice↔bob, bob↔charlie, diana↔alice are mutual
    assert graph.number_of_edges() <= 3


@pytest.mark.integration
def test_workflow_with_min_followers_filtering(sample_accounts_df, sample_edges_df):
    """Test workflow filters by minimum follower count."""
    # Build graph with min_followers=1000
    graph = build_graph_from_data(
        accounts_df=sample_accounts_df,
        edges_df=sample_edges_df,
        min_followers=1000,
    )

    # Should exclude bob (500 followers)
    # alice (1000), charlie (2000), diana (1500) should remain
    assert graph.number_of_nodes() == 3
    assert "bob" not in graph.nodes()


@pytest.mark.integration
def test_workflow_produces_consistent_metrics():
    """Test that running workflow multiple times produces consistent results."""
    # Create deterministic test data
    accounts_df = pd.DataFrame({
        "username": ["a", "b", "c"],
        "follower_count": [100, 200, 300],
        "is_shadow": [False, False, False],
    })
    edges_df = pd.DataFrame({
        "source": ["a", "b"],
        "target": ["b", "c"],
        "is_shadow": [False, False],
        "is_mutual": [False, False],
    })

    # Run workflow twice
    graph1 = build_graph_from_data(accounts_df, edges_df)
    pagerank1 = compute_personalized_pagerank(graph1, seeds=["a"], alpha=0.85)

    graph2 = build_graph_from_data(accounts_df, edges_df)
    pagerank2 = compute_personalized_pagerank(graph2, seeds=["a"], alpha=0.85)

    # Results should be identical
    assert pagerank1.keys() == pagerank2.keys()
    for node in pagerank1:
        assert pagerank1[node] == pytest.approx(pagerank2[node], abs=1e-6)


@pytest.mark.integration
def test_workflow_with_empty_graph():
    """Test workflow handles empty graph gracefully without crashing."""
    # Empty dataframes
    accounts_df = pd.DataFrame(columns=["username", "follower_count", "is_shadow"])
    edges_df = pd.DataFrame(columns=["source", "target", "is_mutual"])

    # Build graph
    graph = build_graph_from_data(accounts_df, edges_df)

    # Property 1: Empty input creates empty graph (not null, not broken)
    assert isinstance(graph, nx.DiGraph), "Empty input should still create valid DiGraph"
    assert graph.number_of_nodes() == 0
    assert graph.number_of_edges() == 0

    # Property 2: Metrics on empty graph should handle gracefully (not crash)
    # Test PageRank with empty seeds
    try:
        pagerank = compute_personalized_pagerank(graph, seeds=[], alpha=0.85)
        # If no error, result should be empty dict
        assert pagerank == {}, "PageRank on empty graph should return empty dict"
    except ValueError as e:
        # Also acceptable to raise informative error
        assert "empty" in str(e).lower() or "no" in str(e).lower(), \
            "Error message should mention empty graph or missing nodes"

    # Property 3: Seed resolution on empty graph should return empty list
    resolved = resolve_seeds(graph, ["nonexistent"])
    assert resolved == [], "Seed resolution on empty graph should return empty list"


@pytest.mark.integration
def test_workflow_with_disconnected_components():
    """Test workflow handles disconnected graph components."""
    accounts_df = pd.DataFrame({
        "username": ["a", "b", "c", "d"],
        "follower_count": [100, 100, 100, 100],
        "is_shadow": [False, False, False, False],
    })
    # Two disconnected components: a→b and c→d
    edges_df = pd.DataFrame({
        "source": ["a", "c"],
        "target": ["b", "d"],
        "is_shadow": [False, False],
        "is_mutual": [False, False],
    })

    graph = build_graph_from_data(accounts_df, edges_df)
    pagerank = compute_personalized_pagerank(graph, seeds=["a"], alpha=0.85)

    # PageRank should still work
    assert sum(pagerank.values()) == pytest.approx(1.0, abs=0.01)

    # Seed component should have higher scores
    assert pagerank["a"] > pagerank["c"]
    assert pagerank["a"] > pagerank["d"]


# ==============================================================================
# API Workflow Tests
# ==============================================================================

@pytest.mark.integration
def test_api_workflow_base_metrics_computation():
    """Test full API workflow for base metrics computation."""
    # Simulate API request payload
    request_data = {
        "seeds": ["alice", "bob"],
        "alpha": 0.85,
        "resolution": 1.0,
        "include_shadow": False,
        "mutual_only": False,
        "min_followers": 0,
    }

    # Mock data fetching
    accounts_df = pd.DataFrame({
        "username": ["alice", "bob", "charlie"],
        "follower_count": [1000, 500, 2000],
        "is_shadow": [False, False, False],
    })
    edges_df = pd.DataFrame({
        "source": ["alice", "bob"],
        "target": ["bob", "charlie"],
        "is_shadow": [False, False],
        "is_mutual": [False, False],
    })

    # Build graph
    graph = build_graph_from_data(
        accounts_df=accounts_df,
        edges_df=edges_df,
        include_shadow=request_data["include_shadow"],
        mutual_only=request_data["mutual_only"],
        min_followers=request_data["min_followers"],
    )

    # Resolve seeds
    resolved_seeds = resolve_seeds(graph, request_data["seeds"])

    # Compute metrics
    pagerank = compute_personalized_pagerank(
        graph, seeds=resolved_seeds, alpha=request_data["alpha"]
    )

    # Verify response structure
    assert len(resolved_seeds) == 2
    assert len(pagerank) == 3
    assert sum(pagerank.values()) == pytest.approx(1.0, abs=0.01)


@pytest.mark.integration
def test_api_workflow_with_caching():
    """Test API workflow benefits from caching."""
    from src.api.cache import MetricsCache

    cache = MetricsCache(max_size=10, ttl_seconds=60)

    # First request (cache miss)
    cache_key = {"seeds": ["alice"], "alpha": 0.85}
    cached_result = cache.get("test_metrics", cache_key)
    assert cached_result is None

    # Simulate computation
    result = {"pagerank": {"alice": 0.5, "bob": 0.3, "charlie": 0.2}}

    # Cache result
    cache.set("test_metrics", cache_key, result, computation_time_ms=100.0)

    # Second request (cache hit)
    cached_result = cache.get("test_metrics", cache_key)
    assert cached_result == result

    # Stats should show hit
    stats = cache.get_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1


# ==============================================================================
# Data Pipeline Tests
# ==============================================================================

@pytest.mark.integration
def test_data_pipeline_dataframe_to_graph():
    """Test data pipeline from DataFrame to NetworkX graph with invariant checks."""
    # Create test data
    accounts = pd.DataFrame({
        "username": ["user1", "user2", "user3"],
        "follower_count": [100, 200, 300],
        "is_shadow": [False, False, False],
    })

    edges = pd.DataFrame({
        "source": ["user1", "user2"],
        "target": ["user2", "user3"],
        "is_shadow": [False, False],
        "is_mutual": [True, False],
    })

    # Convert to graph
    graph = build_graph_from_data(accounts, edges)

    # Property 1: Node count cannot exceed account count (no phantom nodes)
    assert graph.number_of_nodes() <= len(accounts), \
        "Graph should not have more nodes than accounts in input"

    # Property 2: Edge count cannot exceed input edge count (no phantom edges)
    assert graph.number_of_edges() <= len(edges), \
        "Graph should not have more edges than in input (may have fewer due to filtering)"

    # Property 3: All nodes in graph must have been in accounts DataFrame
    account_usernames = set(accounts["username"])
    for node in graph.nodes():
        assert node in account_usernames, \
            f"Node {node} in graph but not in accounts DataFrame"

    # Property 4: All edges in graph must reference existing nodes
    for source, target in graph.edges():
        assert source in graph.nodes(), f"Edge source {source} not in nodes"
        assert target in graph.nodes(), f"Edge target {target} not in nodes"

    # Property 5: Node attributes must be preserved from DataFrame
    for username in graph.nodes():
        account_row = accounts[accounts["username"] == username].iloc[0]
        assert graph.nodes[username]["follower_count"] == account_row["follower_count"], \
            "Node attributes must match DataFrame values"

    # Regression test: Verify specific graph structure
    assert set(graph.nodes()) == {"user1", "user2", "user3"}
    assert graph.has_edge("user1", "user2")
    assert graph.has_edge("user2", "user3")
    assert graph.nodes["user1"]["follower_count"] == 100
    assert graph.nodes["user2"]["follower_count"] == 200


@pytest.mark.integration
def test_data_pipeline_preserves_node_attributes():
    """Test that data pipeline preserves all node attributes."""
    accounts = pd.DataFrame({
        "username": ["user1"],
        "follower_count": [500],
        "is_shadow": [False],
        "bio": ["Test bio"],
        "verified": [True],
    })

    edges = pd.DataFrame(columns=["source", "target", "is_shadow", "is_mutual"])

    graph = build_graph_from_data(accounts, edges)

    # All attributes should be preserved
    node_data = graph.nodes["user1"]
    assert node_data["follower_count"] == 500
    assert node_data["is_shadow"] is False


@pytest.mark.integration
def test_data_pipeline_handles_duplicate_edges():
    """Test that duplicate edges are handled correctly."""
    accounts = pd.DataFrame({
        "username": ["a", "b"],
        "follower_count": [100, 100],
        "is_shadow": [False, False],
    })

    # Duplicate edge a→b
    edges = pd.DataFrame({
        "source": ["a", "a"],
        "target": ["b", "b"],
        "is_shadow": [False, False],
        "is_mutual": [False, False],
    })

    graph = build_graph_from_data(accounts, edges)

    # Should have only one edge (not duplicate)
    assert graph.number_of_edges() == 1


# ==============================================================================
# Metrics Computation Pipeline Tests
# ==============================================================================

@pytest.mark.integration
def test_metrics_pipeline_multiple_algorithms():
    """Test computing multiple metrics in sequence."""
    # Create simple graph
    graph = nx.DiGraph()
    graph.add_edges_from([("a", "b"), ("b", "c"), ("c", "a")])

    seeds = ["a"]

    # Compute PageRank
    pagerank = compute_personalized_pagerank(graph, seeds, alpha=0.85)

    # Compute betweenness
    betweenness = nx.betweenness_centrality(graph)

    # Both should succeed
    assert len(pagerank) == 3
    assert len(betweenness) == 3

    # Scores should be valid
    assert all(0 <= score <= 1 for score in pagerank.values())
    assert all(score >= 0 for score in betweenness.values())


# ==============================================================================
# Error Handling and Edge Cases
# ==============================================================================
# Category C tests deleted (Phase 1, Task 1.4):
# - test_metrics_pipeline_community_detection (weak: just len() >= 2)
# - test_workflow_handles_missing_columns (weak: try/except pass)


@pytest.mark.integration
def test_workflow_handles_self_loops():
    """Test workflow handles self-loop edges correctly."""
    accounts_df = pd.DataFrame({
        "username": ["a", "b"],
        "follower_count": [100, 200],
        "is_shadow": [False, False],
    })

    # Include self-loop
    edges_df = pd.DataFrame({
        "source": ["a", "a"],
        "target": ["a", "b"],
        "is_shadow": [False, False],
        "is_mutual": [False, False],
    })

    graph = build_graph_from_data(accounts_df, edges_df)

    # Self-loops should be handled (either included or excluded based on policy)
    assert graph.number_of_nodes() == 2


@pytest.mark.integration
def test_workflow_performance_with_large_seed_set():
    """Test workflow performance with many seeds."""
    # Create larger graph
    n_nodes = 50
    accounts_df = pd.DataFrame({
        "username": [f"user{i}" for i in range(n_nodes)],
        "follower_count": [1000] * n_nodes,
        "is_shadow": [False] * n_nodes,
    })

    # Create random edges
    edges = []
    for i in range(n_nodes - 1):
        edges.append((f"user{i}", f"user{i+1}"))
    edges_df = pd.DataFrame({
        "source": [e[0] for e in edges],
        "target": [e[1] for e in edges],
        "is_shadow": [False] * len(edges),
        "is_mutual": [False] * len(edges),
    })

    # Build graph
    graph = build_graph_from_data(accounts_df, edges_df)

    # Use many seeds
    seeds = [f"user{i}" for i in range(10)]
    resolved = resolve_seeds(graph, seeds)

    # Compute metrics
    pagerank = compute_personalized_pagerank(graph, seeds=resolved, alpha=0.85)

    # Should complete successfully
    assert len(pagerank) == n_nodes
    assert sum(pagerank.values()) == pytest.approx(1.0, abs=0.01)
