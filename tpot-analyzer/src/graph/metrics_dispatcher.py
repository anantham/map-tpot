"""Smart dispatcher for graph metrics - routes to GPU/NetworKit/NetworkX.

Routing priority:
1. GPU (cuGraph) - if enabled and available
2. NetworKit - if available and graph > 100 nodes
3. NetworkX - fallback

Environment Variables:
    USE_GPU_METRICS=true - Enable GPU acceleration
    FORCE_CPU_METRICS=true - Force CPU (disable GPU)
    PREFER_NETWORKIT=true - Prefer NetworKit over GPU (for testing)
"""
from __future__ import annotations

import logging
from typing import Dict, Iterable, Optional, Tuple

import networkx as nx

from src.graph.gpu_capability import get_gpu_capability

logger = logging.getLogger(__name__)


def _get_compute_backend(
    num_nodes: int,
    allow_gpu: bool = True,
    prefer_networkit: bool = False
) -> str:
    """Determine which backend to use for computation.

    Args:
        num_nodes: Number of nodes in graph
        allow_gpu: Whether GPU is allowed for this computation
        prefer_networkit: Prefer NetworKit over GPU (for testing)

    Returns:
        "gpu", "networkit", or "networkx"
    """
    import os

    # Check GPU capability
    gpu_cap = get_gpu_capability()

    # Check if NetworKit is available
    try:
        import networkit
        networkit_available = True
    except ImportError:
        networkit_available = False

    # Routing logic
    if allow_gpu and gpu_cap.can_use_gpu and not prefer_networkit:
        return "gpu"
    elif networkit_available and num_nodes > 100:
        return "networkit"
    else:
        return "networkx"


def compute_pagerank(
    graph: nx.DiGraph,
    *,
    seeds: Optional[Iterable[str]] = None,
    alpha: float = 0.85,
    allow_gpu: bool = True
) -> Tuple[Dict[str, float], str]:
    """Compute PageRank with automatic backend selection.

    Args:
        graph: Directed graph
        seeds: Personalization nodes
        alpha: Damping factor
        allow_gpu: Whether to allow GPU computation

    Returns:
        (scores_dict, backend_used)
    """
    num_nodes = graph.number_of_nodes()
    backend = _get_compute_backend(num_nodes, allow_gpu)

    logger.info(f"Computing PageRank using {backend} ({num_nodes} nodes)")

    if backend == "gpu":
        try:
            from src.graph.gpu_metrics import compute_pagerank_gpu
            return compute_pagerank_gpu(graph, seeds=seeds, alpha=alpha), "gpu"
        except Exception as e:
            logger.warning(f"GPU PageRank failed: {e}, falling back to CPU")
            backend = "networkx"

    if backend == "networkit":
        try:
            from src.graph.metrics_fast import compute_pagerank_fast
            return compute_pagerank_fast(graph, seeds=seeds, alpha=alpha), "networkit"
        except Exception as e:
            logger.warning(f"NetworKit PageRank failed: {e}, falling back to NetworkX")
            backend = "networkx"

    # NetworkX fallback
    from src.graph.metrics import compute_personalized_pagerank
    return compute_personalized_pagerank(graph, seeds=seeds, alpha=alpha), "networkx"


def compute_betweenness(
    graph: nx.Graph,
    *,
    normalized: bool = True,
    sample_size: Optional[int] = None,
    allow_gpu: bool = True
) -> Tuple[Dict[str, float], str]:
    """Compute betweenness centrality with automatic backend selection.

    Args:
        graph: Undirected graph
        normalized: Normalize scores
        sample_size: Number of nodes to sample (for approximation)
        allow_gpu: Whether to allow GPU computation

    Returns:
        (scores_dict, backend_used)
    """
    num_nodes = graph.number_of_nodes()
    backend = _get_compute_backend(num_nodes, allow_gpu)

    # Auto-sample for large graphs
    if sample_size is None and num_nodes > 1000:
        sample_size = min(500, num_nodes)

    logger.info(f"Computing betweenness using {backend} ({num_nodes} nodes, k={sample_size})")

    if backend == "gpu":
        try:
            from src.graph.gpu_metrics import compute_betweenness_gpu
            return compute_betweenness_gpu(graph, normalized=normalized, k=sample_size), "gpu"
        except Exception as e:
            logger.warning(f"GPU betweenness failed: {e}, falling back to CPU")
            backend = "networkit"

    if backend == "networkit":
        try:
            from src.graph.metrics_fast import compute_betweenness_fast
            return compute_betweenness_fast(graph, normalized=normalized, sample_size=sample_size), "networkit"
        except Exception as e:
            logger.warning(f"NetworKit betweenness failed: {e}, falling back to NetworkX")
            backend = "networkx"

    # NetworkX fallback
    from src.graph.metrics import compute_betweenness
    return compute_betweenness(graph, normalized=normalized, sample_size=sample_size), "networkx"


def compute_louvain(
    graph: nx.Graph,
    *,
    resolution: float = 1.0,
    allow_gpu: bool = True
) -> Tuple[Dict[str, int], str]:
    """Compute Louvain communities with automatic backend selection.

    Args:
        graph: Undirected graph
        resolution: Resolution parameter
        allow_gpu: Whether to allow GPU computation

    Returns:
        (communities_dict, backend_used)
    """
    num_nodes = graph.number_of_nodes()
    backend = _get_compute_backend(num_nodes, allow_gpu)

    logger.info(f"Computing Louvain using {backend} ({num_nodes} nodes)")

    if backend == "gpu":
        try:
            from src.graph.gpu_metrics import compute_louvain_gpu
            # Note: cuGraph Louvain doesn't support resolution parameter
            return compute_louvain_gpu(graph), "gpu"
        except Exception as e:
            logger.warning(f"GPU Louvain failed: {e}, falling back to CPU")
            backend = "networkx"

    # NetworkX (NetworKit doesn't have Louvain)
    from src.graph.metrics import compute_louvain_communities
    return compute_louvain_communities(graph, resolution=resolution), "networkx"


def compute_all_metrics(
    directed_graph: nx.DiGraph,
    undirected_graph: nx.Graph,
    *,
    seeds: Optional[Iterable[str]] = None,
    alpha: float = 0.85,
    resolution: float = 1.0,
    betweenness_sample: Optional[int] = None,
    allow_gpu: bool = True
) -> Dict[str, any]:
    """Compute all metrics with optimal backend routing.

    Args:
        directed_graph: For PageRank
        undirected_graph: For other metrics
        seeds: For personalized PageRank
        alpha: PageRank damping
        resolution: Louvain resolution
        betweenness_sample: Betweenness sampling size
        allow_gpu: Whether to allow GPU computation

    Returns:
        Dict with metrics and metadata about backends used
    """
    num_nodes = undirected_graph.number_of_nodes()
    backend = _get_compute_backend(num_nodes, allow_gpu)

    logger.info(f"Computing all metrics using {backend} backend")

    # Try batch GPU computation if available
    if backend == "gpu":
        try:
            from src.graph.gpu_metrics import compute_all_centralities_gpu

            results = compute_all_centralities_gpu(
                directed_graph,
                undirected_graph,
                seeds=seeds,
                alpha=alpha,
                resolution=resolution,
                betweenness_k=betweenness_sample
            )

            # Add engagement (not GPU-accelerated)
            from src.graph.metrics import compute_engagement_scores, compute_composite_score
            results["engagement"] = compute_engagement_scores(undirected_graph)
            results["composite"] = compute_composite_score(
                pagerank=results["pagerank"],
                betweenness=results["betweenness"],
                engagement=results["engagement"],
                weights=(0.4, 0.3, 0.3)
            )

            return {
                **results,
                "_backend": "gpu",
                "_backend_details": {
                    "pagerank": "gpu",
                    "betweenness": "gpu",
                    "closeness": "gpu",
                    "eigenvector": "gpu",
                    "communities": "gpu",
                    "engagement": "cpu",
                    "composite": "cpu"
                }
            }

        except Exception as e:
            logger.warning(f"Batch GPU computation failed: {e}, falling back to individual metrics")

    # Compute individually with smart routing
    pagerank, pr_backend = compute_pagerank(directed_graph, seeds=seeds, alpha=alpha, allow_gpu=allow_gpu)
    betweenness, bt_backend = compute_betweenness(undirected_graph, sample_size=betweenness_sample, allow_gpu=allow_gpu)
    communities, comm_backend = compute_louvain(undirected_graph, resolution=resolution, allow_gpu=allow_gpu)

    # CPU-only metrics
    from src.graph.metrics import compute_engagement_scores, compute_composite_score
    engagement = compute_engagement_scores(undirected_graph)
    composite = compute_composite_score(
        pagerank=pagerank,
        betweenness=betweenness,
        engagement=engagement,
        weights=(0.4, 0.3, 0.3)
    )

    return {
        "pagerank": pagerank,
        "betweenness": betweenness,
        "engagement": engagement,
        "composite": composite,
        "communities": communities,
        "_backend": backend,
        "_backend_details": {
            "pagerank": pr_backend,
            "betweenness": bt_backend,
            "communities": comm_backend,
            "engagement": "cpu",
            "composite": "cpu"
        }
    }
