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


def make_graph():
    g = nx.DiGraph()
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    g.add_node("c")
    for node in g.nodes:
        g.nodes[node]["num_likes"] = 2
        g.nodes[node]["num_tweets"] = 3
        g.nodes[node]["num_followers"] = g.in_degree(node)
    undirected = g.to_undirected()
    return g, undirected


def test_pagerank_with_seeds():
    directed, _ = make_graph()
    pr = compute_personalized_pagerank(directed, seeds=["a"], alpha=0.85)
    assert sum(pr.values()) == pytest.approx(1.0)
    assert pr["a"] > pr["c"]


def test_louvain():
    _, undirected = make_graph()
    communities = compute_louvain_communities(undirected)
    assert set(communities.keys()) == set(undirected.nodes)


def test_betweenness():
    _, undirected = make_graph()
    bt = compute_betweenness(undirected)
    assert bt["b"] >= bt["a"]


def test_engagement_and_composite():
    directed, undirected = make_graph()
    pr = compute_personalized_pagerank(directed, seeds=["a"])
    bt = compute_betweenness(undirected)
    eg = compute_engagement_scores(undirected)
    composite = compute_composite_score(pagerank=pr, betweenness=bt, engagement=eg)
    assert set(composite.keys()) == set(directed.nodes)


def test_normalize_scores_constant():
    scores = {"a": 1, "b": 1}
    normalized = normalize_scores(scores)
    assert all(value == 0.5 for value in normalized.values())
