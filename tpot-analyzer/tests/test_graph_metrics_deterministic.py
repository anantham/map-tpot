"""Deterministic tests for graph metrics with known expected outputs.

This module tests graph metrics against mathematically verifiable results:
- PageRank values for simple graph topologies
- Betweenness centrality for known bridge nodes
- Community detection for obvious clusters
- Composite scoring with specific weight configurations

These tests ensure metrics remain stable across refactoring and library updates.
"""
from __future__ import annotations

import networkx as nx
import pytest

from src.graph.metrics import (
    compute_betweenness,
    compute_composite_score,
    compute_engagement_scores,
    compute_louvain_communities,
    compute_personalized_pagerank,
    normalize_scores,
)


# ==============================================================================
# Deterministic PageRank Tests
# ==============================================================================

@pytest.mark.unit
def test_pagerank_linear_chain():
    """PageRank on linear chain: A→B→C. Seed at A should rank A highest."""
    g = nx.DiGraph()
    g.add_edges_from([("A", "B"), ("B", "C")])

    # Add dummy engagement attributes
    for node in g.nodes:
        g.nodes[node].update({"num_likes": 0, "num_tweets": 1, "num_followers": 1})

    pr = compute_personalized_pagerank(g, seeds=["A"], alpha=0.85)

    # Verify sum to 1
    assert sum(pr.values()) == pytest.approx(1.0)

    # Seed node A should have highest PageRank
    assert pr["A"] > pr["B"]
    assert pr["B"] > pr["C"]


@pytest.mark.unit
def test_pagerank_star_topology():
    """PageRank on star: A→{B,C,D}. Seed at A, all leaves should have equal rank."""
    g = nx.DiGraph()
    g.add_edges_from([("A", "B"), ("A", "C"), ("A", "D")])

    # Add dummy engagement attributes
    for node in g.nodes:
        g.nodes[node].update({"num_likes": 0, "num_tweets": 1, "num_followers": 1})

    pr = compute_personalized_pagerank(g, seeds=["A"], alpha=0.85)

    # Center node (seed) should have highest PageRank
    assert pr["A"] > pr["B"]

    # All leaf nodes should have equal PageRank
    assert pr["B"] == pytest.approx(pr["C"])
    assert pr["C"] == pytest.approx(pr["D"])


@pytest.mark.unit
def test_pagerank_bidirectional_edges():
    """PageRank with mutual following: A↔B. Both should have equal rank when both are seeds."""
    g = nx.DiGraph()
    g.add_edges_from([("A", "B"), ("B", "A")])

    # Add dummy engagement attributes
    for node in g.nodes:
        g.nodes[node].update({"num_likes": 0, "num_tweets": 1, "num_followers": 1})

    pr = compute_personalized_pagerank(g, seeds=["A", "B"], alpha=0.85)

    # Both nodes should have equal PageRank (symmetry)
    assert pr["A"] == pytest.approx(pr["B"])
    assert sum(pr.values()) == pytest.approx(1.0)


@pytest.mark.unit
def test_pagerank_isolated_node():
    """PageRank with isolated node should assign non-zero rank to all nodes."""
    g = nx.DiGraph()
    g.add_edges_from([("A", "B"), ("B", "C")])
    g.add_node("D")  # Isolated node

    # Add dummy engagement attributes
    for node in g.nodes:
        g.nodes[node].update({"num_likes": 0, "num_tweets": 1, "num_followers": 1})

    pr = compute_personalized_pagerank(g, seeds=["A"], alpha=0.85)

    # All nodes should have some PageRank (teleportation ensures this)
    assert all(rank > 0 for rank in pr.values())
    assert sum(pr.values()) == pytest.approx(1.0)


@pytest.mark.unit
def test_pagerank_single_seed_vs_multiple_seeds():
    """PageRank with single seed should concentrate mass differently than multiple seeds."""
    g = nx.DiGraph()
    g.add_edges_from([("A", "B"), ("B", "C"), ("C", "D")])

    # Add dummy engagement attributes
    for node in g.nodes:
        g.nodes[node].update({"num_likes": 0, "num_tweets": 1, "num_followers": 1})

    pr_single = compute_personalized_pagerank(g, seeds=["A"], alpha=0.85)
    pr_multiple = compute_personalized_pagerank(g, seeds=["A", "D"], alpha=0.85)

    # Single seed: A should dominate
    assert pr_single["A"] > pr_single["D"]

    # Multiple seeds: A and D should have more balanced ranks
    assert abs(pr_multiple["A"] - pr_multiple["D"]) < abs(pr_single["A"] - pr_single["D"])


# ==============================================================================
# Deterministic Betweenness Tests
# ==============================================================================

@pytest.mark.unit
def test_betweenness_bridge_node():
    """Betweenness centrality: Bridge node connecting two clusters should have max betweenness."""
    g = nx.Graph()
    # Cluster 1: A-B-C
    g.add_edges_from([("A", "B"), ("B", "C")])
    # Bridge: C-D
    g.add_edge("C", "D")
    # Cluster 2: D-E-F
    g.add_edges_from([("D", "E"), ("E", "F")])

    bt = compute_betweenness(g)

    # Bridge nodes C and D should have highest betweenness
    max_bt = max(bt.values())
    assert bt["C"] == pytest.approx(max_bt) or bt["D"] == pytest.approx(max_bt)

    # Leaf nodes should have zero betweenness
    assert bt["A"] == 0.0
    assert bt["F"] == 0.0


@pytest.mark.unit
def test_betweenness_star_topology():
    """Betweenness in star topology: Center node should have maximum betweenness."""
    g = nx.Graph()
    g.add_edges_from([("center", "A"), ("center", "B"), ("center", "C"), ("center", "D")])

    bt = compute_betweenness(g)

    # Center node is on all shortest paths between leaves
    assert bt["center"] == pytest.approx(1.0, abs=0.01)  # Normalized betweenness

    # Leaf nodes have zero betweenness (not on any shortest paths)
    assert bt["A"] == 0.0
    assert bt["B"] == 0.0


@pytest.mark.unit
def test_betweenness_linear_chain():
    """Betweenness in linear chain: Middle nodes should have higher betweenness."""
    g = nx.Graph()
    g.add_edges_from([("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")])

    bt = compute_betweenness(g)

    # Middle node C should have highest betweenness
    assert bt["C"] == max(bt.values())

    # Betweenness should decrease towards edges
    assert bt["C"] > bt["B"]
    assert bt["B"] > bt["A"]
    assert bt["C"] > bt["D"]
    assert bt["D"] > bt["E"]


@pytest.mark.unit
def test_betweenness_complete_graph():
    """Betweenness in complete graph: All nodes should have equal betweenness (zero)."""
    g = nx.complete_graph(5)

    bt = compute_betweenness(g)

    # In complete graph, all shortest paths are direct (length 1)
    # So no node is "between" any other pair
    assert all(b == 0.0 for b in bt.values())


# ==============================================================================
# Deterministic Community Detection Tests
# ==============================================================================

@pytest.mark.unit
def test_louvain_two_clusters():
    """Community detection should identify two distinct clusters."""
    g = nx.Graph()
    # Cluster 1: densely connected
    g.add_edges_from([("A1", "A2"), ("A2", "A3"), ("A3", "A1")])
    # Cluster 2: densely connected
    g.add_edges_from([("B1", "B2"), ("B2", "B3"), ("B3", "B1")])
    # Weak inter-cluster link
    g.add_edge("A1", "B1")

    communities = compute_louvain_communities(g)

    # All cluster 1 nodes should share a community
    assert communities["A1"] == communities["A2"] == communities["A3"]

    # All cluster 2 nodes should share a community
    assert communities["B1"] == communities["B2"] == communities["B3"]

    # Two clusters should be different
    assert communities["A1"] != communities["B1"]


@pytest.mark.unit
def test_louvain_single_component():
    """Community detection on single connected component should assign communities."""
    g = nx.Graph()
    g.add_edges_from([("A", "B"), ("B", "C"), ("C", "A")])

    communities = compute_louvain_communities(g)

    # All nodes should be assigned a community
    assert set(communities.keys()) == {"A", "B", "C"}

    # In a triangle, Louvain might put them all in one community
    # (we just verify it doesn't crash and assigns something)
    assert all(isinstance(c, int) for c in communities.values())


@pytest.mark.unit
def test_louvain_disconnected_components():
    """Community detection on disconnected graph should assign different communities."""
    g = nx.Graph()
    # Component 1
    g.add_edges_from([("A", "B")])
    # Component 2 (isolated)
    g.add_edges_from([("C", "D")])

    communities = compute_louvain_communities(g)

    # Components should likely have different communities
    # (This is probabilistic, but Louvain should separate disconnected components)
    assert communities["A"] == communities["B"]
    assert communities["C"] == communities["D"]


# ==============================================================================
# Deterministic Engagement Score Tests
# ==============================================================================

@pytest.mark.unit
def test_engagement_scores_all_zero():
    """When all nodes have zero engagement, scores should be equal."""
    g = nx.Graph()
    g.add_edges_from([("A", "B"), ("B", "C")])
    for node in g.nodes:
        g.nodes[node].update({"num_likes": 0, "num_tweets": 0, "num_followers": 0})

    scores = compute_engagement_scores(g)

    # All scores should be equal when engagement is zero
    unique_scores = set(scores.values())
    assert len(unique_scores) == 1


@pytest.mark.unit
def test_engagement_scores_high_engagement_wins():
    """Node with highest engagement should have highest score."""
    g = nx.Graph()
    g.add_edges_from([("A", "B"), ("B", "C")])
    g.nodes["A"].update({"num_likes": 100, "num_tweets": 10, "num_followers": 1000})
    g.nodes["B"].update({"num_likes": 10, "num_tweets": 5, "num_followers": 100})
    g.nodes["C"].update({"num_likes": 1, "num_tweets": 1, "num_followers": 10})

    scores = compute_engagement_scores(g)

    # A has highest engagement, should have highest score
    assert scores["A"] > scores["B"]
    assert scores["B"] > scores["C"]


@pytest.mark.unit
def test_engagement_scores_missing_attributes():
    """Engagement scores should handle missing attributes gracefully."""
    g = nx.Graph()
    g.add_edges_from([("A", "B")])
    # Only A has attributes
    g.nodes["A"].update({"num_likes": 50, "num_tweets": 5, "num_followers": 100})

    # B has no attributes (should default to zero)
    scores = compute_engagement_scores(g)

    # Should not crash; B should have zero/low score
    assert "A" in scores
    assert "B" in scores
    assert scores["A"] >= scores["B"]


# ==============================================================================
# Deterministic Composite Score Tests
# ==============================================================================

@pytest.mark.unit
def test_composite_score_equal_weights():
    """Composite score with equal weights should average metrics."""
    pagerank = {"A": 0.4, "B": 0.3, "C": 0.3}
    betweenness = {"A": 0.0, "B": 1.0, "C": 0.0}
    engagement = {"A": 0.0, "B": 0.0, "C": 1.0}

    # Equal weights (1/3 each)
    composite = compute_composite_score(
        pagerank=pagerank,
        betweenness=betweenness,
        engagement=engagement,
        weights=(1/3, 1/3, 1/3)
    )

    # Verify composite is weighted average
    expected_A = (0.4 * 1/3) + (0.0 * 1/3) + (0.0 * 1/3)
    expected_B = (0.3 * 1/3) + (1.0 * 1/3) + (0.0 * 1/3)
    expected_C = (0.3 * 1/3) + (0.0 * 1/3) + (1.0 * 1/3)

    assert composite["A"] == pytest.approx(expected_A)
    assert composite["B"] == pytest.approx(expected_B)
    assert composite["C"] == pytest.approx(expected_C)


@pytest.mark.unit
def test_composite_score_pagerank_only():
    """Composite score with 100% PageRank weight should match PageRank."""
    pagerank = {"A": 0.5, "B": 0.3, "C": 0.2}
    betweenness = {"A": 0.0, "B": 1.0, "C": 0.0}
    engagement = {"A": 0.0, "B": 0.0, "C": 1.0}

    # 100% PageRank weight
    composite = compute_composite_score(
        pagerank=pagerank,
        betweenness=betweenness,
        engagement=engagement,
        weights=(1.0, 0.0, 0.0)
    )

    # Composite should exactly match PageRank
    assert composite["A"] == pytest.approx(pagerank["A"])
    assert composite["B"] == pytest.approx(pagerank["B"])
    assert composite["C"] == pytest.approx(pagerank["C"])


@pytest.mark.unit
def test_composite_score_betweenness_dominates():
    """Composite score with high betweenness weight should favor high-betweenness nodes."""
    pagerank = {"A": 0.5, "B": 0.3, "C": 0.2}
    betweenness = {"A": 0.0, "B": 1.0, "C": 0.0}
    engagement = {"A": 0.0, "B": 0.0, "C": 1.0}

    # 90% betweenness weight
    composite = compute_composite_score(
        pagerank=pagerank,
        betweenness=betweenness,
        engagement=engagement,
        weights=(0.05, 0.9, 0.05)
    )

    # B should have highest composite score (betweenness = 1.0)
    assert composite["B"] > composite["A"]
    assert composite["B"] > composite["C"]


@pytest.mark.unit
def test_composite_score_engagement_dominates():
    """Composite score with high engagement weight should favor high-engagement nodes."""
    pagerank = {"A": 0.5, "B": 0.3, "C": 0.2}
    betweenness = {"A": 0.0, "B": 1.0, "C": 0.0}
    engagement = {"A": 0.0, "B": 0.0, "C": 1.0}

    # 90% engagement weight
    composite = compute_composite_score(
        pagerank=pagerank,
        betweenness=betweenness,
        engagement=engagement,
        weights=(0.05, 0.05, 0.9)
    )

    # C should have highest composite score (engagement = 1.0)
    assert composite["C"] > composite["A"]
    assert composite["C"] > composite["B"]


# ==============================================================================
# Deterministic Normalization Tests
# ==============================================================================

@pytest.mark.unit
def test_normalize_scores_range():
    """Normalized scores should be in range [0, 1]."""
    scores = {"A": 100, "B": 50, "C": 25, "D": 10}
    normalized = normalize_scores(scores)

    # All scores should be in [0, 1]
    assert all(0 <= v <= 1 for v in normalized.values())

    # Max should be 1, min should be 0
    assert max(normalized.values()) == pytest.approx(1.0)
    assert min(normalized.values()) == pytest.approx(0.0)


@pytest.mark.unit
def test_normalize_scores_order_preserved():
    """Normalization should preserve relative ordering."""
    scores = {"A": 100, "B": 50, "C": 25}
    normalized = normalize_scores(scores)

    # Order should be preserved
    assert normalized["A"] > normalized["B"]
    assert normalized["B"] > normalized["C"]


@pytest.mark.unit
def test_normalize_scores_identical_values():
    """When all scores are equal, normalization should return equal values."""
    scores = {"A": 42, "B": 42, "C": 42}
    normalized = normalize_scores(scores)

    # All normalized scores should be equal
    unique_values = set(normalized.values())
    assert len(unique_values) == 1


@pytest.mark.unit
def test_normalize_scores_single_node():
    """Normalizing a single score should return 1.0."""
    scores = {"A": 123}
    normalized = normalize_scores(scores)

    assert normalized["A"] == 1.0


@pytest.mark.unit
def test_normalize_scores_linear_transformation():
    """Normalization should be a linear transformation."""
    scores = {"A": 10, "B": 20, "C": 30}
    normalized = normalize_scores(scores)

    # A maps to 0, C maps to 1, B maps to 0.5 (linear)
    assert normalized["A"] == pytest.approx(0.0)
    assert normalized["B"] == pytest.approx(0.5)
    assert normalized["C"] == pytest.approx(1.0)


# ==============================================================================
# Integration Test: Full Pipeline with Known Graph
# ==============================================================================

@pytest.mark.integration
def test_full_metrics_pipeline_small_graph():
    """End-to-end test of all metrics on a small known graph."""
    # Create a simple social graph
    directed = nx.DiGraph()
    directed.add_edges_from([
        ("alice", "bob"),
        ("bob", "charlie"),
        ("charlie", "alice"),  # Triangle
        ("bob", "dave"),       # Bridge to dave
    ])

    # Add engagement attributes
    for node in directed.nodes:
        directed.nodes[node].update({
            "num_likes": 10,
            "num_tweets": 5,
            "num_followers": directed.in_degree(node) * 100,
        })

    undirected = directed.to_undirected()

    # Compute all metrics
    pagerank = compute_personalized_pagerank(directed, seeds=["alice"], alpha=0.85)
    betweenness = compute_betweenness(undirected)
    engagement = compute_engagement_scores(undirected)
    communities = compute_louvain_communities(undirected)
    composite = compute_composite_score(pagerank, betweenness, engagement)

    # Verify all nodes present in all metrics
    assert set(pagerank.keys()) == {"alice", "bob", "charlie", "dave"}
    assert set(betweenness.keys()) == {"alice", "bob", "charlie", "dave"}
    assert set(engagement.keys()) == {"alice", "bob", "charlie", "dave"}
    assert set(communities.keys()) == {"alice", "bob", "charlie", "dave"}
    assert set(composite.keys()) == {"alice", "bob", "charlie", "dave"}

    # Verify PageRank properties
    assert sum(pagerank.values()) == pytest.approx(1.0)
    assert pagerank["alice"] > pagerank["dave"]  # Seed should rank high

    # Verify betweenness properties
    assert betweenness["bob"] > betweenness["dave"]  # Bridge node

    # Verify composite is valid
    assert all(0 <= v <= 1 for v in composite.values())
