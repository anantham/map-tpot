"""Graph metric computations."""
from __future__ import annotations

import logging
import math
from typing import Dict, Iterable, Optional, Tuple

import networkx as nx
from networkx.exception import PowerIterationFailedConvergence

from src.performance_profiler import profile_phase

logger = logging.getLogger(__name__)


def compute_gini_coefficient(scores: Dict[str, float]) -> float:
    """Compute Gini coefficient for distribution inequality.

    Returns:
        Gini coefficient in range [0, 1]
        - 0 = perfect equality (all nodes have same score)
        - 1 = perfect inequality (one node has all score)
    """
    if not scores:
        return 0.0

    sorted_scores = sorted(scores.values())
    n = len(sorted_scores)

    if n == 0:
        return 0.0

    # Gini formula: G = (2 * sum(i * x_i)) / (n * sum(x_i)) - (n + 1) / n
    cumsum = sum((i + 1) * score for i, score in enumerate(sorted_scores))
    total = sum(sorted_scores)

    if total == 0:
        return 0.0

    gini = (2 * cumsum) / (n * total) - (n + 1) / n
    return gini


def compute_entropy(scores: Dict[str, float]) -> float:
    """Compute Shannon entropy of score distribution.

    Returns:
        Entropy in bits
        - Higher entropy = more dispersed/uniform distribution
        - Lower entropy = more concentrated distribution
    """
    if not scores:
        return 0.0

    values = list(scores.values())
    total = sum(values)

    if total == 0:
        return 0.0

    # Normalize to probabilities
    probs = [v / total for v in values if v > 0]

    # Shannon entropy: H = -sum(p * log2(p))
    entropy = -sum(p * math.log2(p) for p in probs)
    return entropy


def analyze_score_distribution(scores: Dict[str, float], label: str = "Score") -> Dict:
    """Analyze distribution properties of scores.

    Returns:
        Dictionary with distribution statistics
    """
    if not scores:
        return {}

    sorted_scores = sorted(scores.values(), reverse=True)
    total = sum(sorted_scores)
    n = len(sorted_scores)

    if total == 0:
        return {
            "total_mass": 0.0,
            "num_nodes": n,
            "concentration": {},
            "gini": 0.0,
            "entropy": 0.0,
        }

    # Concentration at different percentiles
    percentiles = {"1%": 0.01, "5%": 0.05, "10%": 0.10, "25%": 0.25}
    concentration = {}

    for pct_label, pct in percentiles.items():
        idx = max(1, int(n * pct))
        mass = sum(sorted_scores[:idx]) / total
        concentration[pct_label] = mass

    # Gini and entropy
    gini = compute_gini_coefficient(scores)
    entropy = compute_entropy(scores)

    # Percentile scores (what score puts you in top X%)
    percentile_scores = {
        "top_1%": sorted_scores[max(0, int(n * 0.01) - 1)] if n >= 100 else sorted_scores[0],
        "top_5%": sorted_scores[max(0, int(n * 0.05) - 1)] if n >= 20 else sorted_scores[0],
        "top_10%": sorted_scores[max(0, int(n * 0.10) - 1)] if n >= 10 else sorted_scores[0],
    }

    stats = {
        "total_mass": total,
        "num_nodes": n,
        "max": sorted_scores[0],
        "min": sorted_scores[-1],
        "median": sorted_scores[n // 2],
        "mean": total / n,
        "concentration": concentration,
        "percentile_thresholds": percentile_scores,
        "gini": gini,
        "entropy": entropy,
    }

    return stats


def log_distribution_analysis(scores: Dict[str, float], label: str = "PageRank") -> None:
    """Log detailed distribution analysis."""
    stats = analyze_score_distribution(scores, label)

    if not stats:
        logger.info(f"{label} distribution: No scores available")
        return

    logger.info(f"\n{'='*60}")
    logger.info(f"{label} Distribution Analysis")
    logger.info(f"{'='*60}")
    logger.info(f"Total nodes: {stats['num_nodes']:,}")
    logger.info(f"Total mass: {stats['total_mass']:.6f}")
    logger.info(f"")
    logger.info(f"Score Range:")
    logger.info(f"  Max:    {stats['max']:.6f}")
    logger.info(f"  Median: {stats['median']:.6f}")
    logger.info(f"  Mean:   {stats['mean']:.6f}")
    logger.info(f"  Min:    {stats['min']:.6f}")
    logger.info(f"")
    logger.info(f"Concentration (what % of total mass is held by top X% of nodes):")
    for pct, mass in stats['concentration'].items():
        logger.info(f"  Top {pct:>4} of nodes hold: {mass*100:5.1f}% of total {label}")
    logger.info(f"")
    logger.info(f"Inequality Metrics:")
    logger.info(f"  Gini coefficient: {stats['gini']:.4f}  (0=equality, 1=inequality)")
    logger.info(f"  Entropy:          {stats['entropy']:.2f} bits  (higher=more dispersed)")
    logger.info(f"")
    logger.info(f"Threshold Scores (minimum score to be in top X%):")
    for pct, score in stats['percentile_thresholds'].items():
        logger.info(f"  {pct:>7}: {score:.6f}")
    logger.info(f"{'='*60}\n")


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

            # Analyze distribution
            log_distribution_analysis(result, label=f"PageRank (α={alpha:.4f})")

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
