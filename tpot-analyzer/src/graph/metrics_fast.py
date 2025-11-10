"""Fast graph metric computations using NetworKit.

NetworKit is 10-100x faster than NetworkX for large graphs due to its C++ core.
Falls back to NetworkX if NetworKit is unavailable.
"""
from __future__ import annotations

import logging
from typing import Dict, Iterable, Optional

import networkx as nx

from src.performance_profiler import profile_phase

logger = logging.getLogger(__name__)

# Try to import NetworKit
try:
    import networkit as nk
    NETWORKIT_AVAILABLE = True
    logger.info("NetworKit available - using fast C++ algorithms")
except ImportError:
    NETWORKIT_AVAILABLE = False
    logger.warning("NetworKit not available - falling back to NetworkX (slower)")


def _nx_to_nk(graph: nx.Graph) -> nk.Graph:
    """Convert NetworkX graph to NetworKit graph."""
    # Create node ID mapping
    nx_to_nk_id = {node: i for i, node in enumerate(graph.nodes())}

    # Create NetworKit graph
    nk_graph = nk.Graph(n=len(graph.nodes()), weighted=False, directed=False)

    # Add edges
    for u, v in graph.edges():
        nk_graph.addEdge(nx_to_nk_id[u], nx_to_nk_id[v])

    return nk_graph, nx_to_nk_id


def _nk_to_dict(nk_scores: list, nx_to_nk_id: dict) -> Dict[str, float]:
    """Convert NetworKit score list to dict with original node IDs."""
    nk_to_nx_id = {v: k for k, v in nx_to_nk_id.items()}
    return {nk_to_nx_id[i]: score for i, score in enumerate(nk_scores)}


def compute_betweenness_fast(
    graph: nx.Graph,
    *,
    normalized: bool = True,
    sample_size: Optional[int] = None
) -> Dict[str, float]:
    """Compute betweenness centrality using NetworKit (fast) or NetworkX (fallback).

    NetworKit is 10-100x faster for large graphs.

    Args:
        graph: Undirected NetworkX graph
        normalized: Whether to normalize scores
        sample_size: Number of nodes to sample (for approximation)
    """
    num_nodes = graph.number_of_nodes()

    with profile_phase("compute_betweenness_fast", metadata={
        "nodes": num_nodes,
        "edges": graph.number_of_edges(),
        "using_networkit": NETWORKIT_AVAILABLE
    }):
        if NETWORKIT_AVAILABLE and num_nodes > 100:
            # Use NetworKit for speed
            nk_graph, nx_to_nk_id = _nx_to_nk(graph)

            # Use approximate betweenness for very large graphs
            if sample_size or num_nodes > 1000:
                n_samples = sample_size or min(500, num_nodes)
                logger.info(f"Computing approximate betweenness with {n_samples} samples (NetworKit)")
                bc = nk.centrality.ApproxBetweenness(nk_graph, epsilon=0.1, delta=0.1)
            else:
                logger.info(f"Computing exact betweenness (NetworKit)")
                bc = nk.centrality.Betweenness(nk_graph, normalized=normalized)

            bc.run()
            scores = bc.scores()

            return _nk_to_dict(scores, nx_to_nk_id)

        else:
            # Fallback to NetworkX
            logger.info(f"Using NetworkX betweenness (slower)")

            # Use sampling for large graphs
            if sample_size is None and num_nodes > 500:
                sample_size = min(500, num_nodes)

            if sample_size and sample_size < num_nodes:
                return nx.betweenness_centrality(graph, normalized=normalized, k=sample_size)

            return nx.betweenness_centrality(graph, normalized=normalized)


def compute_pagerank_fast(
    graph: nx.DiGraph,
    *,
    seeds: Optional[Iterable[str]] = None,
    alpha: float = 0.85
) -> Dict[str, float]:
    """Compute PageRank using NetworKit (fast) or NetworkX (fallback).

    Args:
        graph: Directed NetworkX graph
        seeds: Personalization nodes (for personalized PageRank)
        alpha: Damping factor
    """
    num_nodes = graph.number_of_nodes()

    with profile_phase("compute_pagerank_fast", metadata={
        "nodes": num_nodes,
        "edges": graph.number_of_edges(),
        "using_networkit": NETWORKIT_AVAILABLE,
        "personalized": seeds is not None
    }):
        # NetworKit doesn't support personalized PageRank easily, so use NetworkX
        # (PageRank is relatively fast anyway compared to betweenness)

        seeds_list = list(seeds) if seeds else []

        if not seeds_list:
            return nx.pagerank(graph, alpha=alpha)

        personalization = {node: 0.0 for node in graph.nodes}
        for seed in seeds_list:
            if seed in personalization:
                personalization[seed] = 1.0 / len(seeds_list)

        return nx.pagerank(graph, alpha=alpha, personalization=personalization)


def compute_closeness_fast(graph: nx.Graph) -> Dict[str, float]:
    """Compute closeness centrality using NetworKit (fast) or NetworkX (fallback)."""
    num_nodes = graph.number_of_nodes()

    with profile_phase("compute_closeness_fast", metadata={
        "nodes": num_nodes,
        "edges": graph.number_of_edges(),
        "using_networkit": NETWORKIT_AVAILABLE
    }):
        if NETWORKIT_AVAILABLE and num_nodes > 100:
            nk_graph, nx_to_nk_id = _nx_to_nk(graph)

            # Use approximate closeness for large graphs
            if num_nodes > 1000:
                logger.info(f"Computing approximate closeness (NetworKit)")
                cc = nk.centrality.ApproxCloseness(nk_graph, nSamples=min(500, num_nodes))
            else:
                logger.info(f"Computing exact closeness (NetworKit)")
                cc = nk.centrality.Closeness(nk_graph, normalized=True)

            cc.run()
            scores = cc.scores()

            return _nk_to_dict(scores, nx_to_nk_id)

        else:
            logger.info(f"Using NetworkX closeness (slower)")
            return nx.closeness_centrality(graph)


def compute_eigenvector_fast(graph: nx.Graph) -> Dict[str, float]:
    """Compute eigenvector centrality using NetworKit (fast) or NetworkX (fallback)."""
    num_nodes = graph.number_of_nodes()

    with profile_phase("compute_eigenvector_fast", metadata={
        "nodes": num_nodes,
        "edges": graph.number_of_edges(),
        "using_networkit": NETWORKIT_AVAILABLE
    }):
        if NETWORKIT_AVAILABLE and num_nodes > 100:
            nk_graph, nx_to_nk_id = _nx_to_nk(graph)

            logger.info(f"Computing eigenvector centrality (NetworKit)")
            ec = nk.centrality.EigenvectorCentrality(nk_graph)
            ec.run()
            scores = ec.scores()

            return _nk_to_dict(scores, nx_to_nk_id)

        else:
            logger.info(f"Using NetworkX eigenvector centrality (slower)")
            try:
                return nx.eigenvector_centrality(graph, max_iter=1000)
            except nx.PowerIterationFailedConvergence:
                logger.warning("Eigenvector centrality failed to converge")
                return {node: 0.0 for node in graph.nodes()}
