"""Local Louvain-based expansion for large clusters.

When a cluster is too large to meaningfully split using the global dendrogram
(because it's part of a densely-connected core), we use Louvain community
detection on the subgraph to find natural sub-communities.
"""
from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx
import numpy as np
from networkx.algorithms.community import louvain_communities

logger = logging.getLogger(__name__)

# Threshold: clusters with more than this fraction of total nodes get local expansion
LARGE_CLUSTER_FRACTION = 0.15  # 15% of total nodes

# Resolution mapping for Louvain based on target child count
# Higher resolution = more communities
RESOLUTION_BY_TARGET = {
    5: 0.5,
    10: 1.0,
    15: 1.5,
    25: 2.0,
    50: 4.0,
}

# Cache for local expansion results
# Key: (cluster_id_hash, resolution) -> LocalExpansionResult
_local_expansion_cache: OrderedDict[Tuple[str, float], "LocalExpansionResult"] = OrderedDict()
_CACHE_MAX_SIZE = 50  # Max cached expansions
_CACHE_TTL_SECONDS = 3600  # 1 hour TTL
_cache_timestamps: Dict[Tuple[str, float], float] = {}


@dataclass
class LocalExpansionResult:
    """Result of local Louvain expansion."""

    success: bool
    reason: str
    sub_clusters: List[List[str]]  # List of node ID lists, one per sub-cluster
    resolution_used: float
    n_communities: int
    compute_time_ms: int


def _get_resolution_for_target(target_children: int) -> float:
    """Get Louvain resolution that approximately yields target_children communities."""
    # Find closest target in our mapping
    targets = sorted(RESOLUTION_BY_TARGET.keys())
    for t in targets:
        if target_children <= t:
            return RESOLUTION_BY_TARGET[t]
    return RESOLUTION_BY_TARGET[targets[-1]]


def _get_cache_key(member_node_ids: List[str], resolution: float) -> Tuple[str, float]:
    """Generate a cache key from member node IDs and resolution."""
    # Use a hash of sorted member IDs for the key
    sorted_ids = sorted(member_node_ids)
    id_hash = hashlib.md5(",".join(sorted_ids).encode()).hexdigest()[:16]
    return (id_hash, resolution)


def _check_cache(key: Tuple[str, float]) -> Optional[LocalExpansionResult]:
    """Check if result is in cache and not expired."""
    if key not in _local_expansion_cache:
        return None

    timestamp = _cache_timestamps.get(key, 0)
    if time.time() - timestamp > _CACHE_TTL_SECONDS:
        # Expired
        _local_expansion_cache.pop(key, None)
        _cache_timestamps.pop(key, None)
        return None

    # Move to end (LRU)
    _local_expansion_cache.move_to_end(key)
    return _local_expansion_cache[key]


def _store_cache(key: Tuple[str, float], result: LocalExpansionResult) -> None:
    """Store result in cache."""
    _local_expansion_cache[key] = result
    _cache_timestamps[key] = time.time()
    _local_expansion_cache.move_to_end(key)

    # Evict oldest if over capacity
    while len(_local_expansion_cache) > _CACHE_MAX_SIZE:
        oldest_key = next(iter(_local_expansion_cache))
        _local_expansion_cache.pop(oldest_key)
        _cache_timestamps.pop(oldest_key, None)


def expand_cluster_locally(
    member_node_ids: List[str],
    adjacency,  # scipy sparse matrix
    node_id_to_idx: Dict[str, int],
    target_children: int = 10,
    min_community_size: int = 2,
) -> LocalExpansionResult:
    """Expand a large cluster using Louvain on its induced subgraph.

    Args:
        member_node_ids: Node IDs belonging to this cluster
        adjacency: Full graph adjacency matrix (sparse)
        node_id_to_idx: Mapping from node ID to matrix index
        target_children: Approximate number of sub-clusters to create
        min_community_size: Minimum size for a valid community

    Returns:
        LocalExpansionResult with sub-cluster assignments

    Note:
        Results are cached by (member_ids_hash, resolution) for up to 1 hour.
    """
    t_start = time.time()

    # Check size first (no caching needed for tiny clusters)
    if len(member_node_ids) < 10:
        return LocalExpansionResult(
            success=False,
            reason="Cluster too small for local expansion",
            sub_clusters=[],
            resolution_used=0.0,
            n_communities=0,
            compute_time_ms=0,
        )

    # Check cache before expensive computation
    resolution = _get_resolution_for_target(target_children)
    cache_key = _get_cache_key(member_node_ids, resolution)
    cached = _check_cache(cache_key)
    if cached:
        logger.info(
            "Local expansion cache HIT: hash=%s, resolution=%.2f, %d communities",
            cache_key[0][:8], resolution, cached.n_communities
        )
        return cached

    # Build subgraph
    member_set = set(member_node_ids)
    member_indices = [node_id_to_idx[nid] for nid in member_node_ids if nid in node_id_to_idx]

    if len(member_indices) < 10:
        return LocalExpansionResult(
            success=False,
            reason="Not enough valid node indices",
            sub_clusters=[],
            resolution_used=0.0,
            n_communities=0,
            compute_time_ms=0,
        )

    # Extract subgraph edges
    t_subgraph = time.time()
    idx_set = set(member_indices)
    idx_to_nid = {node_id_to_idx[nid]: nid for nid in member_node_ids if nid in node_id_to_idx}

    # Get edges within the cluster
    G = nx.Graph()
    G.add_nodes_from(member_node_ids)

    # Convert to COO for efficient iteration
    adj_coo = adjacency.tocoo()
    for i, j in zip(adj_coo.row, adj_coo.col):
        if i in idx_set and j in idx_set and i != j:
            src_nid = idx_to_nid.get(i)
            tgt_nid = idx_to_nid.get(j)
            if src_nid and tgt_nid:
                G.add_edge(src_nid, tgt_nid)

    subgraph_time = time.time() - t_subgraph
    logger.debug(
        "Local expansion subgraph: %d nodes, %d edges in %.2fms",
        G.number_of_nodes(), G.number_of_edges(), subgraph_time * 1000
    )

    if G.number_of_edges() == 0:
        return LocalExpansionResult(
            success=False,
            reason="No edges in subgraph",
            sub_clusters=[member_node_ids],  # Return as single cluster
            resolution_used=0.0,
            n_communities=1,
            compute_time_ms=int((time.time() - t_start) * 1000),
        )

    # Run Louvain with appropriate resolution (resolution already computed for cache key)
    t_louvain = time.time()

    try:
        communities = louvain_communities(G, resolution=resolution, seed=42)
    except Exception as e:
        logger.warning("Louvain failed: %s", e)
        return LocalExpansionResult(
            success=False,
            reason=f"Louvain failed: {e}",
            sub_clusters=[member_node_ids],
            resolution_used=resolution,
            n_communities=1,
            compute_time_ms=int((time.time() - t_start) * 1000),
        )

    louvain_time = time.time() - t_louvain

    # Convert communities to lists, filter by size
    sub_clusters = []
    orphans = []
    for community in communities:
        community_list = list(community)
        if len(community_list) >= min_community_size:
            sub_clusters.append(community_list)
        else:
            orphans.extend(community_list)

    # Assign orphans to nearest community (by edge count)
    if orphans and sub_clusters:
        for orphan in orphans:
            best_cluster_idx = 0
            best_edge_count = 0
            for idx, cluster in enumerate(sub_clusters):
                cluster_set = set(cluster)
                edge_count = sum(1 for neighbor in G.neighbors(orphan) if neighbor in cluster_set)
                if edge_count > best_edge_count:
                    best_edge_count = edge_count
                    best_cluster_idx = idx
            sub_clusters[best_cluster_idx].append(orphan)
    elif orphans:
        # No valid sub-clusters, return all as one
        sub_clusters = [member_node_ids]

    # Sort by size descending
    sub_clusters.sort(key=len, reverse=True)

    compute_time_ms = int((time.time() - t_start) * 1000)

    logger.info(
        "Local expansion: %d nodes -> %d communities (resolution=%.2f, target=%d) in %dms",
        len(member_node_ids), len(sub_clusters), resolution, target_children, compute_time_ms
    )

    result = LocalExpansionResult(
        success=True,
        reason="OK",
        sub_clusters=sub_clusters,
        resolution_used=resolution,
        n_communities=len(sub_clusters),
        compute_time_ms=compute_time_ms,
    )

    # Store in cache for future requests
    _store_cache(cache_key, result)
    logger.debug(
        "Local expansion cached: hash=%s, resolution=%.2f",
        cache_key[0][:8], resolution
    )

    return result


def should_use_local_expansion(
    cluster_size: int,
    total_nodes: int,
    micro_cluster_count: int,
    cluster_micro_count: int,
) -> bool:
    """Determine if a cluster should use local Louvain expansion.

    Uses local expansion when:
    1. Cluster contains >15% of all nodes, OR
    2. Cluster contains >50% of all nodes (definitely needs local expansion)

    The key insight: when a cluster is very large relative to the total,
    the global dendrogram isn't providing useful sub-structure because
    it was optimized to separate this core from the periphery, not to
    find structure within the core.
    """
    cluster_fraction = cluster_size / total_nodes if total_nodes > 0 else 0

    # Always use local expansion for clusters with >50% of all nodes
    if cluster_fraction > 0.5:
        logger.info(
            "Local expansion triggered (>50%%): cluster_size=%d (%.1f%% of %d)",
            cluster_size, cluster_fraction * 100, total_nodes
        )
        return True

    # Use local expansion for clusters with >15% that have few micro-clusters
    # (meaning dendrogram grouped them too coarsely)
    if cluster_fraction > LARGE_CLUSTER_FRACTION:
        # If cluster has very few micro-clusters relative to its size,
        # the dendrogram won't help subdivide it
        if cluster_micro_count <= 3:
            logger.info(
                "Local expansion triggered (large + coarse): cluster_size=%d (%.1f%%), micro_count=%d",
                cluster_size, cluster_fraction * 100, cluster_micro_count
            )
            return True

        # Also check if this cluster's micro-clusters are much larger than average
        avg_micro_size = total_nodes / micro_cluster_count if micro_cluster_count > 0 else total_nodes
        cluster_micro_density = cluster_size / max(1, cluster_micro_count)

        if cluster_micro_density > avg_micro_size * 3:
            logger.info(
                "Local expansion triggered (dense): cluster_size=%d, density=%.1f vs avg=%.1f",
                cluster_size, cluster_micro_density, avg_micro_size
            )
            return True

    return False
