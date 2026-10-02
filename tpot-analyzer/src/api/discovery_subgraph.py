"""Bounded graph neighborhood extraction for discovery."""
import logging
import time
from itertools import islice
from typing import List, Tuple
import networkx as nx

logger = logging.getLogger(__name__)
SUBGRAPH_MAX_DEPTH = 2
SUBGRAPH_MAX_NODES = 5000
MAX_NEIGHBORS_PER_NODE = 100

def extract_subgraph(
    graph: nx.DiGraph,
    seeds: List[str],
    depth: int = SUBGRAPH_MAX_DEPTH
) -> Tuple[nx.DiGraph, List[str]]:
    """Extract k-hop neighborhood around seeds.

    Returns:
        (subgraph, candidate_nodes)
    """
    start_time = time.time()

    # Validate seeds exist in graph
    valid_seeds = [s for s in seeds if s in graph]
    invalid_seeds = [s for s in seeds if s not in graph]

    if not valid_seeds:
        return nx.DiGraph(), []

    # BFS to find k-hop neighborhood
    subgraph_nodes = set(valid_seeds)
    current_layer = set(valid_seeds)

    for hop in range(depth):
        next_layer = set()

        for node in current_layer:
            # Get neighbors (both in and out)
            predecessors = list(islice(graph.predecessors(node), MAX_NEIGHBORS_PER_NODE))
            successors = list(islice(graph.successors(node), MAX_NEIGHBORS_PER_NODE))

            next_layer.update(predecessors)
            next_layer.update(successors)

        # Preserve only unseen neighbors as the next BFS frontier.
        # Computing this before mutating subgraph_nodes prevents frontier collapse.
        next_frontier = next_layer - subgraph_nodes
        if not next_frontier:
            break

        remaining = SUBGRAPH_MAX_NODES - len(subgraph_nodes)
        subgraph_nodes.update(sorted(next_frontier, key=str)[:remaining])

        # Safety check
        if len(subgraph_nodes) >= SUBGRAPH_MAX_NODES:
            logger.warning(f"Subgraph exceeded {SUBGRAPH_MAX_NODES} nodes, stopping at hop {hop+1}")
            break

        current_layer = next_frontier

    # Create subgraph
    subgraph = graph.subgraph(list(subgraph_nodes)).copy()

    # Identify candidates (in subgraph but not seeds)
    candidates = list(subgraph_nodes - set(valid_seeds))

    logger.info(f"Extracted {len(subgraph_nodes)} nodes in {time.time() - start_time:.2f}s")

    return subgraph, candidates
