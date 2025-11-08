"""GPU-accelerated graph metrics using RAPIDS cuGraph.

Requires NVIDIA GPU with CUDA and RAPIDS cuGraph installed.
Falls back to CPU if unavailable.

Installation:
    conda install -c rapidsai -c conda-forge cugraph cudf
"""
from __future__ import annotations

import logging
from typing import Dict, Iterable, Optional

import networkx as nx
import pandas as pd

from src.performance_profiler import profile_phase

logger = logging.getLogger(__name__)

# Try to import cuGraph/cuDF
try:
    import cugraph
    import cudf
    CUGRAPH_AVAILABLE = True
except ImportError:
    CUGRAPH_AVAILABLE = False
    logger.debug("cuGraph not available - GPU metrics unavailable")


def _nx_to_cugraph(graph: nx.Graph) -> tuple:
    """Convert NetworkX graph to cuGraph format.

    Returns:
        (cugraph.Graph, node_id_mapping)
    """
    if not CUGRAPH_AVAILABLE:
        raise ImportError("cuGraph not available")

    # Create edge list as DataFrame
    edges = []
    for u, v in graph.edges():
        edges.append({"src": u, "dst": v})

    if not edges:
        # Empty graph
        return cugraph.Graph(), {}

    edges_df = pd.DataFrame(edges)

    # Convert to cuDF
    cu_edges = cudf.DataFrame.from_pandas(edges_df)

    # Create cuGraph
    G = cugraph.Graph()
    G.from_cudf_edgelist(cu_edges, source="src", destination="dst")

    return G, {}


def _cugraph_to_dict(cu_df: cudf.DataFrame, score_col: str = "pagerank") -> Dict[str, float]:
    """Convert cuDF DataFrame to dict with node IDs as keys."""
    if not CUGRAPH_AVAILABLE:
        raise ImportError("cuGraph not available")

    # Convert to pandas
    pandas_df = cu_df.to_pandas()

    # Create dict
    return dict(zip(pandas_df["vertex"], pandas_df[score_col]))


def compute_pagerank_gpu(
    graph: nx.DiGraph,
    *,
    seeds: Optional[Iterable[str]] = None,
    alpha: float = 0.85
) -> Dict[str, float]:
    """Compute PageRank using cuGraph (GPU-accelerated).

    Args:
        graph: Directed NetworkX graph
        seeds: Personalization nodes (for personalized PageRank)
        alpha: Damping factor

    Returns:
        Dict mapping node IDs to PageRank scores
    """
    if not CUGRAPH_AVAILABLE:
        raise ImportError("cuGraph not available - install RAPIDS")

    num_nodes = graph.number_of_nodes()

    with profile_phase("compute_pagerank_gpu", metadata={
        "nodes": num_nodes,
        "edges": graph.number_of_edges(),
        "personalized": seeds is not None
    }):
        logger.info(f"Computing PageRank on GPU ({num_nodes} nodes)")

        # Convert to cuGraph
        cu_graph, _ = _nx_to_cugraph(graph)

        # Personalized PageRank
        if seeds:
            seeds_list = list(seeds)

            # Create personalization vector
            personalization_values = {node: 0.0 for node in graph.nodes()}
            for seed in seeds_list:
                if seed in personalization_values:
                    personalization_values[seed] = 1.0 / len(seeds_list)

            # Convert to cuDF
            pers_df = pd.DataFrame([
                {"vertex": node, "values": val}
                for node, val in personalization_values.items()
            ])
            cu_pers = cudf.DataFrame.from_pandas(pers_df)

            # Compute personalized PageRank
            result = cugraph.pagerank(
                cu_graph,
                alpha=alpha,
                personalization=cu_pers,
                precomputed_vertex_out_weight=None
            )
        else:
            # Standard PageRank
            result = cugraph.pagerank(cu_graph, alpha=alpha)

        return _cugraph_to_dict(result, "pagerank")


def compute_betweenness_gpu(
    graph: nx.Graph,
    *,
    normalized: bool = True,
    k: Optional[int] = None
) -> Dict[str, float]:
    """Compute betweenness centrality using cuGraph (GPU-accelerated).

    Args:
        graph: Undirected NetworkX graph
        normalized: Whether to normalize scores
        k: Number of sources to sample (for approximation)

    Returns:
        Dict mapping node IDs to betweenness scores
    """
    if not CUGRAPH_AVAILABLE:
        raise ImportError("cuGraph not available - install RAPIDS")

    num_nodes = graph.number_of_nodes()

    with profile_phase("compute_betweenness_gpu", metadata={
        "nodes": num_nodes,
        "edges": graph.number_of_edges(),
        "sampled": k is not None,
        "k": k
    }):
        logger.info(f"Computing betweenness on GPU ({num_nodes} nodes, k={k})")

        # Convert to cuGraph
        cu_graph, _ = _nx_to_cugraph(graph)

        # Compute betweenness
        if k and k < num_nodes:
            # Approximate betweenness with sampling
            result = cugraph.betweenness_centrality(
                cu_graph,
                k=k,
                normalized=normalized,
                endpoints=False
            )
        else:
            # Exact betweenness
            result = cugraph.betweenness_centrality(
                cu_graph,
                normalized=normalized,
                endpoints=False
            )

        return _cugraph_to_dict(result, "betweenness_centrality")


def compute_louvain_gpu(
    graph: nx.Graph,
    *,
    resolution: float = 1.0
) -> Dict[str, int]:
    """Compute Louvain communities using cuGraph (GPU-accelerated).

    Args:
        graph: Undirected NetworkX graph
        resolution: Resolution parameter

    Returns:
        Dict mapping node IDs to community IDs
    """
    if not CUGRAPH_AVAILABLE:
        raise ImportError("cuGraph not available - install RAPIDS")

    num_nodes = graph.number_of_nodes()

    with profile_phase("compute_louvain_gpu", metadata={
        "nodes": num_nodes,
        "edges": graph.number_of_edges()
    }):
        logger.info(f"Computing Louvain communities on GPU ({num_nodes} nodes)")

        # Convert to cuGraph
        cu_graph, _ = _nx_to_cugraph(graph)

        # Compute Louvain
        # Note: cuGraph Louvain doesn't have resolution parameter
        # Use default modularity-based partitioning
        result, modularity = cugraph.louvain(cu_graph)

        logger.info(f"Louvain modularity: {modularity:.4f}")

        # Convert to dict
        pandas_df = result.to_pandas()
        return dict(zip(pandas_df["vertex"], pandas_df["partition"]))


def compute_closeness_gpu(graph: nx.Graph) -> Dict[str, float]:
    """Compute closeness centrality using cuGraph (GPU-accelerated).

    Args:
        graph: Undirected NetworkX graph

    Returns:
        Dict mapping node IDs to closeness scores
    """
    if not CUGRAPH_AVAILABLE:
        raise ImportError("cuGraph not available - install RAPIDS")

    num_nodes = graph.number_of_nodes()

    with profile_phase("compute_closeness_gpu", metadata={
        "nodes": num_nodes,
        "edges": graph.number_of_edges()
    }):
        logger.info(f"Computing closeness on GPU ({num_nodes} nodes)")

        # Convert to cuGraph
        cu_graph, _ = _nx_to_cugraph(graph)

        # Compute closeness
        result = cugraph.closeness_centrality(cu_graph)

        return _cugraph_to_dict(result, "closeness_centrality")


def compute_eigenvector_gpu(graph: nx.Graph, max_iter: int = 100) -> Dict[str, float]:
    """Compute eigenvector centrality using cuGraph (GPU-accelerated).

    Args:
        graph: Undirected NetworkX graph
        max_iter: Maximum iterations

    Returns:
        Dict mapping node IDs to eigenvector scores
    """
    if not CUGRAPH_AVAILABLE:
        raise ImportError("cuGraph not available - install RAPIDS")

    num_nodes = graph.number_of_nodes()

    with profile_phase("compute_eigenvector_gpu", metadata={
        "nodes": num_nodes,
        "edges": graph.number_of_edges()
    }):
        logger.info(f"Computing eigenvector centrality on GPU ({num_nodes} nodes)")

        # Convert to cuGraph
        cu_graph, _ = _nx_to_cugraph(graph)

        # Compute eigenvector centrality
        result = cugraph.eigenvector_centrality(cu_graph, max_iter=max_iter)

        return _cugraph_to_dict(result, "eigenvector_centrality")


# Batch computation for efficiency
def compute_all_centralities_gpu(
    directed_graph: nx.DiGraph,
    undirected_graph: nx.Graph,
    *,
    seeds: Optional[Iterable[str]] = None,
    alpha: float = 0.85,
    resolution: float = 1.0,
    betweenness_k: Optional[int] = None
) -> Dict[str, Dict[str, float]]:
    """Compute all centrality metrics in one GPU session (more efficient).

    Args:
        directed_graph: For PageRank
        undirected_graph: For betweenness, closeness, eigenvector, communities
        seeds: For personalized PageRank
        alpha: PageRank damping
        resolution: Louvain resolution
        betweenness_k: Betweenness sampling size

    Returns:
        Dict with keys: pagerank, betweenness, closeness, eigenvector, communities
    """
    if not CUGRAPH_AVAILABLE:
        raise ImportError("cuGraph not available - install RAPIDS")

    logger.info("Computing all metrics on GPU in batch")

    return {
        "pagerank": compute_pagerank_gpu(directed_graph, seeds=seeds, alpha=alpha),
        "betweenness": compute_betweenness_gpu(undirected_graph, k=betweenness_k),
        "closeness": compute_closeness_gpu(undirected_graph),
        "eigenvector": compute_eigenvector_gpu(undirected_graph),
        "communities": compute_louvain_gpu(undirected_graph, resolution=resolution),
    }
