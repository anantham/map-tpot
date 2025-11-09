"""Graph metric computations."""
from __future__ import annotations

import logging
from typing import Dict, Iterable, Optional, Tuple

import networkx as nx
from networkx.exception import PowerIterationFailedConvergence

from src.performance_profiler import profile_phase

logger = logging.getLogger(__name__)


def compute_personalized_pagerank(
    graph: nx.DiGraph,
    *,
    seeds: Iterable[str],
    alpha: float = 0.85,
    weight: Optional[str] = None,
    max_iter: Optional[int] = None,
    tol: float = 1.0e-6,
) -> Dict[str, float]:
    """Personalized PageRank seeded on provided nodes.

    Args:
        graph: Directed graph
        seeds: Seed nodes for personalization
        alpha: Damping factor (0.85 default, higher values = slower convergence)
        weight: Edge weight attribute name
        max_iter: Maximum iterations (auto-scales with alpha if not provided)
        tol: Convergence tolerance

    Returns:
        Dictionary mapping node to PageRank score

    Notes:
        - High alpha values (>0.95) require more iterations to converge
        - Auto-adjusts max_iter based on alpha if not specified
        - Logs convergence diagnostics and warnings
    """

    with profile_phase("compute_personalized_pagerank", metadata={
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "seeds": len(list(seeds)) if seeds else 0,
        "alpha": alpha
    }):
        seeds = list(seeds)

        # Auto-scale max_iter based on alpha
        if max_iter is None:
            if alpha >= 0.99:
                max_iter = 500
            elif alpha >= 0.95:
                max_iter = 300
            elif alpha >= 0.90:
                max_iter = 200
            else:
                max_iter = 100

        logger.info(
            f"Computing PageRank: alpha={alpha:.4f}, max_iter={max_iter}, "
            f"tol={tol:.2e}, seeds={len(seeds)}, nodes={graph.number_of_nodes()}"
        )

        # Warn about high alpha values
        if alpha > 0.95:
            logger.warning(
                f"⚠️  High alpha={alpha:.4f} detected. This may slow convergence. "
                f"Consider using alpha ≤ 0.95 for faster results."
            )

        try:
            if not seeds:
                result = nx.pagerank(
                    graph,
                    alpha=alpha,
                    weight=weight,
                    max_iter=max_iter,
                    tol=tol
                )
            else:
                personalization = {node: 0.0 for node in graph.nodes}
                for seed in seeds:
                    if seed in personalization:
                        personalization[seed] = 1.0 / len(seeds)
                result = nx.pagerank(
                    graph,
                    alpha=alpha,
                    personalization=personalization,
                    weight=weight,
                    max_iter=max_iter,
                    tol=tol
                )

            logger.info(f"✅ PageRank converged successfully")
            return result

        except PowerIterationFailedConvergence as e:
            logger.error(
                f"❌ PageRank FAILED to converge in {max_iter} iterations!\n"
                f"   Alpha: {alpha:.4f} (high alpha = slower convergence)\n"
                f"   Tolerance: {tol:.2e}\n"
                f"   Graph size: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges\n"
                f"   \n"
                f"   Recommendations:\n"
                f"   1. Lower alpha (try 0.90 or 0.85)\n"
                f"   2. Increase --max-iter (current: {max_iter})\n"
                f"   3. Increase tolerance (try 1e-5 or 1e-4)\n"
                f"   4. Check for disconnected components or dead ends"
            )
            raise


def compute_louvain_communities(graph: nx.Graph, *, resolution: float = 1.0) -> Dict[str, int]:
    """Compute Louvain communities (requires networkx>=3.1)."""

    with profile_phase("compute_louvain_communities", metadata={
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges()
    }):
        from networkx.algorithms.community import louvain_communities

        communities = louvain_communities(graph, resolution=resolution, seed=42)
        membership: Dict[str, int] = {}
        for idx, community in enumerate(communities):
            for node in community:
                membership[node] = idx
        return membership


def compute_betweenness(graph: nx.Graph, *, normalized: bool = True, sample_size: Optional[int] = None) -> Dict[str, float]:
    """Compute betweenness centrality.

    For large graphs (>500 nodes), uses approximate algorithm with sampling
    to avoid O(n³) complexity.

    Args:
        graph: Undirected graph
        normalized: Whether to normalize scores
        sample_size: Number of nodes to sample (auto: min(500, n) for graphs >500 nodes)
    """

    with profile_phase("compute_betweenness", metadata={
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges()
    }):
        num_nodes = graph.number_of_nodes()

        # Use approximate betweenness for large graphs
        if sample_size is None and num_nodes > 500:
            sample_size = min(500, num_nodes)

        if sample_size and sample_size < num_nodes:
            return nx.betweenness_centrality(graph, normalized=normalized, k=sample_size)

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
