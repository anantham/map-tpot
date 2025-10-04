"""Graph metric computations."""
from __future__ import annotations

from typing import Dict, Iterable, Optional, Tuple

import networkx as nx


def compute_personalized_pagerank(
    graph: nx.DiGraph,
    *,
    seeds: Iterable[str],
    alpha: float = 0.85,
    weight: Optional[str] = None,
) -> Dict[str, float]:
    """Personalized PageRank seeded on provided nodes."""

    seeds = list(seeds)
    if not seeds:
        return nx.pagerank(graph, alpha=alpha, weight=weight)
    personalization = {node: 0.0 for node in graph.nodes}
    for seed in seeds:
        if seed in personalization:
            personalization[seed] = 1.0 / len(seeds)
    return nx.pagerank(graph, alpha=alpha, personalization=personalization, weight=weight)


def compute_louvain_communities(graph: nx.Graph, *, resolution: float = 1.0) -> Dict[str, int]:
    """Compute Louvain communities (requires networkx>=3.1)."""

    from networkx.algorithms.community import louvain_communities

    communities = louvain_communities(graph, resolution=resolution, seed=42)
    membership: Dict[str, int] = {}
    for idx, community in enumerate(communities):
        for node in community:
            membership[node] = idx
    return membership


def compute_betweenness(graph: nx.Graph, *, normalized: bool = True) -> Dict[str, float]:
    """Compute betweenness centrality."""

    return nx.betweenness_centrality(graph, normalized=normalized)


def compute_engagement_scores(graph: nx.Graph) -> Dict[str, float]:
    """Proxy engagement score using node attributes (likes + tweets)."""

    scores: Dict[str, float] = {}
    for node, data in graph.nodes(data=True):
        likes = data.get("num_likes") or 0
        tweets = data.get("num_tweets") or 0
        followers = data.get("num_followers") or 0
        # Simple heuristic: engagement per follower
        denom = max(followers, 1)
        scores[node] = (likes + tweets) / denom
    return scores


def normalize_scores(scores: Dict[str, float]) -> Dict[str, float]:
    """Normalize scores to 0-1 range."""

    if not scores:
        return {}
    values = list(scores.values())
    minimum = min(values)
    maximum = max(values)
    if maximum == minimum:
        return {node: 0.5 for node in scores}
    return {node: (score - minimum) / (maximum - minimum) for node, score in scores.items()}


def compute_composite_score(
    *,
    pagerank: Dict[str, float],
    betweenness: Dict[str, float],
    engagement: Dict[str, float],
    weights: Tuple[float, float, float] = (0.4, 0.3, 0.3),
) -> Dict[str, float]:
    """Combine normalized metrics according to weights."""

    pr_norm = normalize_scores(pagerank)
    bt_norm = normalize_scores(betweenness)
    eg_norm = normalize_scores(engagement)

    alpha, beta, gamma = weights
    composite: Dict[str, float] = {}
    for node in pr_norm:
        composite[node] = (
            alpha * pr_norm.get(node, 0.0)
            + beta * bt_norm.get(node, 0.0)
            + gamma * eg_norm.get(node, 0.0)
        )
    return composite
