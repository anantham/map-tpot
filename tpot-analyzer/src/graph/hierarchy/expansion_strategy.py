"""Intelligent expansion strategy selection for hierarchical clustering.

This module implements the "intelligence layer" that analyzes local structure
and chooses the best expansion strategy for a cluster based on multiple signals:
- Tag diversity (semantic groupings from user labels)
- Edge density and mutual edges (strong vs weak ties)
- Degree variance (core-periphery structure)
- Soft membership entropy (bridge/integrative nodes)
- Dendrogram structure (Ward linkage hierarchy)

The goal is to surface meaningful structure at every scale, allowing drill-down
to individual accounts when no more structure exists.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx
import numpy as np
from scipy import sparse

logger = logging.getLogger(__name__)


class ExpansionStrategy(Enum):
    """Available expansion strategies."""

    INDIVIDUALS = "individuals"  # Show accounts as individual nodes
    SAMPLE_INDIVIDUALS = "sample_individuals"  # Show top N accounts by metric
    HIERARCHICAL = "hierarchical"  # Use Ward linkage dendrogram children
    LOUVAIN = "louvain"  # Local Louvain community detection
    TAG_SPLIT = "tag_split"  # Split by user-assigned tags
    CORE_PERIPHERY = "core_periphery"  # Split into high-degree core vs periphery
    MUTUAL_COMPONENTS = "mutual_components"  # Connected components of mutual edges
    BRIDGE_EXTRACTION = "bridge_extraction"  # Extract bridge nodes as individuals


@dataclass
class ExpansionDecision:
    """Result of expansion strategy analysis."""

    strategy: ExpansionStrategy
    reason: str  # Human-readable explanation
    params: Dict  # Strategy-specific parameters
    confidence: float  # 0-1, how confident we are this is the right choice
    alternatives: List[Tuple[ExpansionStrategy, str]]  # Other viable options


@dataclass
class LocalStructureMetrics:
    """Metrics computed from local cluster structure."""

    n_members: int
    n_edges: int
    density: float  # edges / max_possible_edges
    n_mutual_edges: int  # bidirectional edges
    mutual_ratio: float  # mutual_edges / total_edges
    degree_mean: float
    degree_std: float
    degree_cv: float  # coefficient of variation (std/mean)
    tag_entropy: float  # entropy of tag distribution
    n_distinct_tags: int
    n_bridge_nodes: int  # nodes with high soft-membership entropy
    bridge_ratio: float
    has_dendrogram_children: bool


def compute_local_metrics(
    member_node_ids: List[str],
    adjacency: sparse.spmatrix,
    node_id_to_idx: Dict[str, int],
    node_tags: Optional[Dict[str, Set[str]]] = None,
    soft_memberships: Optional[Dict[str, List[Tuple[str, float]]]] = None,
    linkage_matrix: Optional[np.ndarray] = None,
    dendrogram_node: int = -1,
    n_micro: int = 0,
) -> LocalStructureMetrics:
    """Compute structural metrics for a cluster's local neighborhood.

    Args:
        member_node_ids: List of node IDs in this cluster
        adjacency: Full graph adjacency matrix (sparse)
        node_id_to_idx: Mapping from node ID to matrix index
        node_tags: Optional mapping from node ID to set of tags
        soft_memberships: Optional mapping from node ID to (cluster_id, prob) list
        linkage_matrix: Optional Ward linkage matrix
        dendrogram_node: Dendrogram node index (-1 if virtual/local cluster)
        n_micro: Number of micro-clusters (for dendrogram traversal)

    Returns:
        LocalStructureMetrics with computed values
    """
    n = len(member_node_ids)

    if n == 0:
        return LocalStructureMetrics(
            n_members=0, n_edges=0, density=0, n_mutual_edges=0, mutual_ratio=0,
            degree_mean=0, degree_std=0, degree_cv=0, tag_entropy=0, n_distinct_tags=0,
            n_bridge_nodes=0, bridge_ratio=0, has_dendrogram_children=False
        )

    # Build subgraph
    member_indices = [node_id_to_idx[nid] for nid in member_node_ids if nid in node_id_to_idx]
    idx_set = set(member_indices)
    idx_to_nid = {node_id_to_idx[nid]: nid for nid in member_node_ids if nid in node_id_to_idx}

    # Count edges and compute degrees
    adj_coo = adjacency.tocoo()
    edges = []
    degrees = {nid: 0 for nid in member_node_ids}

    for i, j in zip(adj_coo.row, adj_coo.col):
        if i in idx_set and j in idx_set and i != j:
            src_nid = idx_to_nid.get(i)
            tgt_nid = idx_to_nid.get(j)
            if src_nid and tgt_nid:
                edges.append((src_nid, tgt_nid))
                degrees[src_nid] = degrees.get(src_nid, 0) + 1

    n_edges = len(edges) // 2  # Undirected, counted twice
    max_edges = n * (n - 1) / 2
    density = n_edges / max_edges if max_edges > 0 else 0

    # Count mutual edges (bidirectional)
    edge_set = set(edges)
    mutual_count = sum(1 for (a, b) in edges if (b, a) in edge_set) // 2
    mutual_ratio = mutual_count / n_edges if n_edges > 0 else 0

    # Degree statistics
    degree_values = list(degrees.values())
    degree_mean = np.mean(degree_values) if degree_values else 0
    degree_std = np.std(degree_values) if degree_values else 0
    degree_cv = degree_std / degree_mean if degree_mean > 0 else 0

    # Tag entropy
    tag_entropy = 0.0
    n_distinct_tags = 0
    if node_tags:
        tag_counts: Dict[str, int] = {}
        for nid in member_node_ids:
            for tag in node_tags.get(nid, set()):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        n_distinct_tags = len(tag_counts)
        if tag_counts:
            total = sum(tag_counts.values())
            probs = [c / total for c in tag_counts.values()]
            tag_entropy = -sum(p * np.log2(p) for p in probs if p > 0)

    # Bridge nodes (high soft-membership entropy)
    n_bridge_nodes = 0
    if soft_memberships:
        for nid in member_node_ids:
            memberships = soft_memberships.get(nid, [])
            if len(memberships) >= 2:
                probs = [p for _, p in memberships]
                entropy = -sum(p * np.log2(p) for p in probs if p > 0)
                max_entropy = np.log2(len(probs))
                if max_entropy > 0 and entropy / max_entropy > 0.7:
                    n_bridge_nodes += 1

    bridge_ratio = n_bridge_nodes / n if n > 0 else 0

    # Check dendrogram children
    has_dendrogram_children = False
    if linkage_matrix is not None and dendrogram_node >= n_micro:
        # Non-leaf dendrogram node has children
        has_dendrogram_children = True

    return LocalStructureMetrics(
        n_members=n,
        n_edges=n_edges,
        density=density,
        n_mutual_edges=mutual_count,
        mutual_ratio=mutual_ratio,
        degree_mean=degree_mean,
        degree_std=degree_std,
        degree_cv=degree_cv,
        tag_entropy=tag_entropy,
        n_distinct_tags=n_distinct_tags,
        n_bridge_nodes=n_bridge_nodes,
        bridge_ratio=bridge_ratio,
        has_dendrogram_children=has_dendrogram_children,
    )


def choose_expansion_strategy(
    member_node_ids: List[str],
    adjacency: sparse.spmatrix,
    node_id_to_idx: Dict[str, int],
    node_tags: Optional[Dict[str, Set[str]]] = None,
    soft_memberships: Optional[Dict[str, List[Tuple[str, float]]]] = None,
    linkage_matrix: Optional[np.ndarray] = None,
    dendrogram_node: int = -1,
    n_micro: int = 0,
) -> ExpansionDecision:
    """Analyze local structure and choose the best expansion strategy.

    This is the "intelligence layer" that decides HOW to expand a cluster
    based on what kind of structure exists within it.

    Decision Priority:
    1. Tiny clusters (<=5) → show individuals
    2. High tag diversity → split by tags (semantic structure)
    3. Many bridge nodes → extract bridges (integrative nodes are interesting)
    4. High degree variance → core-periphery decomposition
    5. Dense with mutuals → mutual-network components (strong ties)
    6. Has edges → Louvain community detection
    7. Has dendrogram children → hierarchical split
    8. No structure → show individuals or sample

    Args:
        member_node_ids: List of node IDs in this cluster
        adjacency: Full graph adjacency matrix (sparse)
        node_id_to_idx: Mapping from node ID to matrix index
        node_tags: Optional mapping from node ID to set of tags
        soft_memberships: Optional soft membership data
        linkage_matrix: Optional Ward linkage matrix
        dendrogram_node: Dendrogram node index (-1 if virtual)
        n_micro: Number of micro-clusters

    Returns:
        ExpansionDecision with chosen strategy and alternatives
    """
    n = len(member_node_ids)

    # Compute local metrics
    metrics = compute_local_metrics(
        member_node_ids=member_node_ids,
        adjacency=adjacency,
        node_id_to_idx=node_id_to_idx,
        node_tags=node_tags,
        soft_memberships=soft_memberships,
        linkage_matrix=linkage_matrix,
        dendrogram_node=dendrogram_node,
        n_micro=n_micro,
    )

    logger.debug(
        "Expansion metrics for %d members: density=%.3f, mutual_ratio=%.3f, "
        "degree_cv=%.2f, tag_entropy=%.2f, bridge_ratio=%.2f",
        n, metrics.density, metrics.mutual_ratio, metrics.degree_cv,
        metrics.tag_entropy, metrics.bridge_ratio
    )

    alternatives: List[Tuple[ExpansionStrategy, str]] = []

    # Decision 1: Tiny clusters → show individuals
    if n <= 5:
        return ExpansionDecision(
            strategy=ExpansionStrategy.INDIVIDUALS,
            reason=f"Cluster has only {n} members - showing as individual accounts",
            params={},
            confidence=1.0,
            alternatives=[],
        )

    # Decision 2: High tag diversity → tag-based split
    if metrics.tag_entropy > 1.5 and metrics.n_distinct_tags >= 2:
        # Collect tags for params
        tag_counts: Dict[str, int] = {}
        if node_tags:
            for nid in member_node_ids:
                for tag in node_tags.get(nid, set()):
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

        return ExpansionDecision(
            strategy=ExpansionStrategy.TAG_SPLIT,
            reason=f"High tag diversity ({metrics.n_distinct_tags} distinct tags, entropy={metrics.tag_entropy:.2f})",
            params={"tag_counts": tag_counts},
            confidence=0.9,
            alternatives=[
                (ExpansionStrategy.LOUVAIN, "Split by graph structure instead"),
                (ExpansionStrategy.INDIVIDUALS, f"Show all {n} accounts"),
            ],
        )

    # Decision 3: Many bridge nodes → extract bridges
    if metrics.bridge_ratio > 0.2 and n > 10:
        # Identify bridge nodes
        bridge_nodes = []
        if soft_memberships:
            for nid in member_node_ids:
                memberships = soft_memberships.get(nid, [])
                if len(memberships) >= 2:
                    probs = [p for _, p in memberships]
                    entropy = -sum(p * np.log2(p) for p in probs if p > 0)
                    max_entropy = np.log2(len(probs))
                    if max_entropy > 0 and entropy / max_entropy > 0.7:
                        bridge_nodes.append(nid)

        alternatives.append((ExpansionStrategy.LOUVAIN, "Use Louvain instead"))

        return ExpansionDecision(
            strategy=ExpansionStrategy.BRIDGE_EXTRACTION,
            reason=f"Found {len(bridge_nodes)} bridge nodes ({metrics.bridge_ratio:.0%} of cluster)",
            params={"bridge_nodes": bridge_nodes},
            confidence=0.8,
            alternatives=alternatives,
        )

    # Decision 4: High degree variance → core-periphery
    if metrics.degree_cv > 1.5 and n > 15:
        threshold = metrics.degree_mean

        alternatives.append((ExpansionStrategy.LOUVAIN, "Use Louvain instead"))
        if metrics.has_dendrogram_children:
            alternatives.append((ExpansionStrategy.HIERARCHICAL, "Use dendrogram split"))

        return ExpansionDecision(
            strategy=ExpansionStrategy.CORE_PERIPHERY,
            reason=f"High degree variance (CV={metrics.degree_cv:.2f}) suggests core-periphery structure",
            params={"degree_threshold": threshold},
            confidence=0.75,
            alternatives=alternatives,
        )

    # Decision 5: Dense with mutual edges → mutual components
    if metrics.density > 0.1 and metrics.mutual_ratio > 0.3 and n < 50:
        alternatives.append((ExpansionStrategy.LOUVAIN, "Use Louvain instead"))

        return ExpansionDecision(
            strategy=ExpansionStrategy.MUTUAL_COMPONENTS,
            reason=f"Dense cluster ({metrics.density:.0%}) with strong mutual ties ({metrics.mutual_ratio:.0%})",
            params={},
            confidence=0.7,
            alternatives=alternatives,
        )

    # Decision 6: Has edges → Louvain
    if metrics.n_edges > n // 2:  # At least 0.5 edges per node on average
        resolution = 1.0 + np.log10(max(10, n)) / 2  # Scale resolution with size

        if metrics.has_dendrogram_children:
            alternatives.append((ExpansionStrategy.HIERARCHICAL, "Use dendrogram split"))
        alternatives.append((ExpansionStrategy.INDIVIDUALS, f"Show all {n} accounts"))

        return ExpansionDecision(
            strategy=ExpansionStrategy.LOUVAIN,
            reason=f"Using Louvain community detection (density={metrics.density:.2%}, {metrics.n_edges} edges)",
            params={"resolution": resolution},
            confidence=0.8,
            alternatives=alternatives,
        )

    # Decision 7: Has dendrogram children → hierarchical
    if metrics.has_dendrogram_children:
        alternatives.append((ExpansionStrategy.INDIVIDUALS, f"Show all {n} accounts"))

        return ExpansionDecision(
            strategy=ExpansionStrategy.HIERARCHICAL,
            reason="Using Ward linkage dendrogram structure",
            params={"dendrogram_node": dendrogram_node},
            confidence=0.85,
            alternatives=alternatives,
        )

    # Decision 8: No structure found → individuals or sample
    if n <= 20:
        return ExpansionDecision(
            strategy=ExpansionStrategy.INDIVIDUALS,
            reason=f"No internal structure found - showing {n} individual accounts",
            params={},
            confidence=0.6,
            alternatives=[],
        )
    else:
        return ExpansionDecision(
            strategy=ExpansionStrategy.SAMPLE_INDIVIDUALS,
            reason=f"No internal structure found - sampling top accounts from {n} members",
            params={"sample_size": 15, "method": "by_degree"},
            confidence=0.5,
            alternatives=[
                (ExpansionStrategy.INDIVIDUALS, f"Show all {n} accounts (may be slow)"),
            ],
        )


def execute_tag_split(
    member_node_ids: List[str],
    node_tags: Dict[str, Set[str]],
    tag_counts: Dict[str, int],
) -> List[List[str]]:
    """Split cluster members by their tags.

    Args:
        member_node_ids: All members of the cluster
        node_tags: Mapping from node ID to set of tags
        tag_counts: Count of each tag in this cluster

    Returns:
        List of sub-cluster member lists, one per tag + untagged
    """
    # Sort tags by count descending
    sorted_tags = sorted(tag_counts.keys(), key=lambda t: tag_counts[t], reverse=True)

    sub_clusters: Dict[str, List[str]] = {tag: [] for tag in sorted_tags}
    sub_clusters["_untagged"] = []

    assigned = set()

    # Assign each node to its primary (most specific) tag
    for nid in member_node_ids:
        nid_tags = node_tags.get(nid, set())
        if nid_tags:
            # Use the first matching tag in sorted order (most common)
            for tag in sorted_tags:
                if tag in nid_tags:
                    sub_clusters[tag].append(nid)
                    assigned.add(nid)
                    break
        else:
            sub_clusters["_untagged"].append(nid)
            assigned.add(nid)

    # Filter empty clusters and return
    result = [members for members in sub_clusters.values() if members]
    result.sort(key=len, reverse=True)

    return result


def execute_core_periphery(
    member_node_ids: List[str],
    adjacency: sparse.spmatrix,
    node_id_to_idx: Dict[str, int],
    degree_threshold: float,
) -> List[List[str]]:
    """Split cluster into core (high-degree) and periphery (low-degree).

    Args:
        member_node_ids: All members of the cluster
        adjacency: Full adjacency matrix
        node_id_to_idx: Node ID to index mapping
        degree_threshold: Degree cutoff for core vs periphery

    Returns:
        [core_members, periphery_members]
    """
    # Compute degrees within cluster
    member_set = set(member_node_ids)
    idx_set = {node_id_to_idx[nid] for nid in member_node_ids if nid in node_id_to_idx}
    idx_to_nid = {node_id_to_idx[nid]: nid for nid in member_node_ids if nid in node_id_to_idx}

    degrees = {nid: 0 for nid in member_node_ids}
    adj_coo = adjacency.tocoo()

    for i, j in zip(adj_coo.row, adj_coo.col):
        if i in idx_set and j in idx_set:
            src_nid = idx_to_nid.get(i)
            if src_nid:
                degrees[src_nid] = degrees.get(src_nid, 0) + 1

    core = [nid for nid in member_node_ids if degrees.get(nid, 0) >= degree_threshold]
    periphery = [nid for nid in member_node_ids if degrees.get(nid, 0) < degree_threshold]

    # Only return if both are non-empty
    if core and periphery:
        return [core, periphery]
    else:
        # Fallback: split at median
        sorted_by_degree = sorted(member_node_ids, key=lambda nid: degrees.get(nid, 0), reverse=True)
        mid = len(sorted_by_degree) // 2
        return [sorted_by_degree[:mid], sorted_by_degree[mid:]]


def execute_mutual_components(
    member_node_ids: List[str],
    adjacency: sparse.spmatrix,
    node_id_to_idx: Dict[str, int],
) -> List[List[str]]:
    """Find connected components of the mutual (bidirectional) edge subgraph.

    Args:
        member_node_ids: All members of the cluster
        adjacency: Full adjacency matrix
        node_id_to_idx: Node ID to index mapping

    Returns:
        List of connected component member lists
    """
    # Build mutual-edge subgraph
    member_indices = [node_id_to_idx[nid] for nid in member_node_ids if nid in node_id_to_idx]
    idx_set = set(member_indices)
    idx_to_nid = {node_id_to_idx[nid]: nid for nid in member_node_ids if nid in node_id_to_idx}

    G = nx.Graph()
    G.add_nodes_from(member_node_ids)

    adj_coo = adjacency.tocoo()
    edge_set = set()

    for i, j in zip(adj_coo.row, adj_coo.col):
        if i in idx_set and j in idx_set and i != j:
            edge_set.add((i, j))

    # Add only mutual edges
    for i, j in edge_set:
        if (j, i) in edge_set:
            src = idx_to_nid.get(i)
            tgt = idx_to_nid.get(j)
            if src and tgt and not G.has_edge(src, tgt):
                G.add_edge(src, tgt)

    # Find connected components
    components = list(nx.connected_components(G))

    if len(components) <= 1:
        # No meaningful split from mutuals
        return [member_node_ids]

    result = [list(comp) for comp in components]
    result.sort(key=len, reverse=True)

    return result


def execute_bridge_extraction(
    member_node_ids: List[str],
    bridge_nodes: List[str],
) -> List[List[str]]:
    """Extract bridge nodes as individuals, group the rest.

    Args:
        member_node_ids: All members of the cluster
        bridge_nodes: Nodes identified as bridges

    Returns:
        List with each bridge as singleton + one cluster of non-bridges
    """
    bridge_set = set(bridge_nodes)
    non_bridges = [nid for nid in member_node_ids if nid not in bridge_set]

    result = []

    # Each bridge is its own "cluster" of size 1
    for bridge in bridge_nodes:
        result.append([bridge])

    # Non-bridges stay together (for now - could sub-cluster them)
    if non_bridges:
        result.append(non_bridges)

    return result


def execute_sample_individuals(
    member_node_ids: List[str],
    adjacency: sparse.spmatrix,
    node_id_to_idx: Dict[str, int],
    sample_size: int = 15,
    method: str = "by_degree",
) -> List[List[str]]:
    """Sample top N individuals by some metric, rest become overflow cluster.

    Args:
        member_node_ids: All members of the cluster
        adjacency: Full adjacency matrix
        node_id_to_idx: Node ID to index mapping
        sample_size: How many to show as individuals
        method: Sampling method ("by_degree", "random")

    Returns:
        List of singletons for sampled nodes + one overflow cluster
    """
    if method == "by_degree":
        # Compute in-degree within cluster
        member_indices = [node_id_to_idx[nid] for nid in member_node_ids if nid in node_id_to_idx]
        idx_set = set(member_indices)
        idx_to_nid = {node_id_to_idx[nid]: nid for nid in member_node_ids if nid in node_id_to_idx}

        degrees = {nid: 0 for nid in member_node_ids}
        adj_coo = adjacency.tocoo()

        for i, j in zip(adj_coo.row, adj_coo.col):
            if i in idx_set and j in idx_set:
                tgt = idx_to_nid.get(j)
                if tgt:
                    degrees[tgt] = degrees.get(tgt, 0) + 1

        sorted_nodes = sorted(member_node_ids, key=lambda nid: degrees.get(nid, 0), reverse=True)
    else:
        # Random sample
        rng = np.random.default_rng(42)
        sorted_nodes = list(rng.permutation(member_node_ids))

    sampled = sorted_nodes[:sample_size]
    overflow = sorted_nodes[sample_size:]

    result = [[nid] for nid in sampled]
    if overflow:
        result.append(overflow)

    return result


def execute_louvain_local(
    member_node_ids: List[str],
    adjacency: sparse.spmatrix,
    node_id_to_idx: Dict[str, int],
    resolution: float = 1.0,
) -> List[List[str]]:
    """Execute local Louvain community detection on the induced subgraph.

    Args:
        member_node_ids: All members of the cluster
        adjacency: Full adjacency matrix
        node_id_to_idx: Node ID to index mapping
        resolution: Louvain resolution parameter

    Returns:
        List of community member lists
    """
    from community import community_louvain

    # Build induced subgraph
    member_indices = [node_id_to_idx[nid] for nid in member_node_ids if nid in node_id_to_idx]
    idx_set = set(member_indices)
    idx_to_nid = {node_id_to_idx[nid]: nid for nid in member_node_ids if nid in node_id_to_idx}

    G = nx.Graph()
    G.add_nodes_from(member_node_ids)

    adj_coo = adjacency.tocoo()
    for i, j, w in zip(adj_coo.row, adj_coo.col, adj_coo.data):
        if i in idx_set and j in idx_set and i < j:
            src = idx_to_nid.get(i)
            tgt = idx_to_nid.get(j)
            if src and tgt:
                G.add_edge(src, tgt, weight=float(w))

    if G.number_of_edges() == 0:
        return [member_node_ids]

    # Run Louvain
    try:
        partition = community_louvain.best_partition(G, resolution=resolution, random_state=42)
    except Exception as e:
        logger.warning("Louvain failed: %s", e)
        return [member_node_ids]

    # Group by community
    communities: Dict[int, List[str]] = {}
    for nid, comm_id in partition.items():
        if comm_id not in communities:
            communities[comm_id] = []
        communities[comm_id].append(nid)

    result = list(communities.values())
    result.sort(key=len, reverse=True)

    return result


def evaluate_all_strategies(
    member_node_ids: List[str],
    adjacency: sparse.spmatrix,
    node_id_to_idx: Dict[str, int],
    node_tags: Optional[Dict[str, Set[str]]] = None,
    soft_memberships: Optional[Dict[str, List[Tuple[str, float]]]] = None,
    linkage_matrix: Optional[np.ndarray] = None,
    dendrogram_node: int = -1,
    n_micro: int = 0,
    weights: Optional["StructureScoreWeights"] = None,
) -> List["ScoredStrategy"]:
    """Execute all applicable strategies and score their results.

    This is the core "self-evaluating" expansion function. Rather than using
    heuristics to guess which strategy will work, we actually run each candidate
    and score how much meaningful structure it reveals.

    Args:
        member_node_ids: All members of the cluster
        adjacency: Full adjacency matrix
        node_id_to_idx: Node ID to index mapping
        node_tags: Optional tag data for tag-based scoring
        soft_memberships: Optional soft membership data
        linkage_matrix: Optional Ward linkage matrix
        dendrogram_node: Dendrogram node index
        n_micro: Number of micro-clusters
        weights: Optional custom scoring weights

    Returns:
        List of ScoredStrategy objects, ranked by score (best first)
    """
    from src.graph.hierarchy.expansion_scoring import (
        StructureScoreWeights,
        ScoredStrategy,
        compute_structure_score,
        rank_strategies,
    )

    import time

    if weights is None:
        weights = StructureScoreWeights()

    n = len(member_node_ids)
    total_members = n
    scored_strategies: List[ScoredStrategy] = []

    # Compute local metrics to determine which strategies are applicable
    metrics = compute_local_metrics(
        member_node_ids=member_node_ids,
        adjacency=adjacency,
        node_id_to_idx=node_id_to_idx,
        node_tags=node_tags,
        soft_memberships=soft_memberships,
        linkage_matrix=linkage_matrix,
        dendrogram_node=dendrogram_node,
        n_micro=n_micro,
    )

    # Strategy 1: INDIVIDUALS (only for small clusters)
    if n <= 20:
        start = time.time()
        sub_clusters = [[nid] for nid in member_node_ids]
        elapsed = int((time.time() - start) * 1000)

        score = compute_structure_score(
            sub_clusters=sub_clusters,
            total_members=total_members,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            node_tags=node_tags,
            weights=weights,
        )

        scored_strategies.append(ScoredStrategy(
            strategy_name=ExpansionStrategy.INDIVIDUALS.value,
            sub_clusters=sub_clusters,
            score=score,
            execution_time_ms=elapsed,
        ))

    # Strategy 2: SAMPLE_INDIVIDUALS (for larger clusters without structure)
    if n > 15:
        start = time.time()
        sub_clusters = execute_sample_individuals(
            member_node_ids=member_node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            sample_size=15,
            method="by_degree",
        )
        elapsed = int((time.time() - start) * 1000)

        score = compute_structure_score(
            sub_clusters=sub_clusters,
            total_members=total_members,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            node_tags=node_tags,
            weights=weights,
        )

        scored_strategies.append(ScoredStrategy(
            strategy_name=ExpansionStrategy.SAMPLE_INDIVIDUALS.value,
            sub_clusters=sub_clusters,
            score=score,
            execution_time_ms=elapsed,
        ))

    # Strategy 3: TAG_SPLIT (if tags exist with diversity)
    if node_tags and metrics.n_distinct_tags >= 2:
        tag_counts: Dict[str, int] = {}
        for nid in member_node_ids:
            for tag in node_tags.get(nid, set()):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        if tag_counts:
            start = time.time()
            sub_clusters = execute_tag_split(
                member_node_ids=member_node_ids,
                node_tags=node_tags,
                tag_counts=tag_counts,
            )
            elapsed = int((time.time() - start) * 1000)

            score = compute_structure_score(
                sub_clusters=sub_clusters,
                total_members=total_members,
                adjacency=adjacency,
                node_id_to_idx=node_id_to_idx,
                node_tags=node_tags,
                weights=weights,
            )

            scored_strategies.append(ScoredStrategy(
                strategy_name=ExpansionStrategy.TAG_SPLIT.value,
                sub_clusters=sub_clusters,
                score=score,
                execution_time_ms=elapsed,
            ))

    # Strategy 4: CORE_PERIPHERY (if degree variance is high)
    if n > 10 and metrics.degree_cv > 0.5:
        start = time.time()
        sub_clusters = execute_core_periphery(
            member_node_ids=member_node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            degree_threshold=metrics.degree_mean,
        )
        elapsed = int((time.time() - start) * 1000)

        score = compute_structure_score(
            sub_clusters=sub_clusters,
            total_members=total_members,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            node_tags=node_tags,
            weights=weights,
        )

        scored_strategies.append(ScoredStrategy(
            strategy_name=ExpansionStrategy.CORE_PERIPHERY.value,
            sub_clusters=sub_clusters,
            score=score,
            execution_time_ms=elapsed,
        ))

    # Strategy 5: MUTUAL_COMPONENTS (if mutual edges exist)
    if metrics.mutual_ratio > 0.1 and n > 5:
        start = time.time()
        sub_clusters = execute_mutual_components(
            member_node_ids=member_node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
        )
        elapsed = int((time.time() - start) * 1000)

        # Only score if it actually split
        if len(sub_clusters) > 1:
            score = compute_structure_score(
                sub_clusters=sub_clusters,
                total_members=total_members,
                adjacency=adjacency,
                node_id_to_idx=node_id_to_idx,
                node_tags=node_tags,
                weights=weights,
            )

            scored_strategies.append(ScoredStrategy(
                strategy_name=ExpansionStrategy.MUTUAL_COMPONENTS.value,
                sub_clusters=sub_clusters,
                score=score,
                execution_time_ms=elapsed,
            ))

    # Strategy 6: BRIDGE_EXTRACTION (if bridge nodes exist)
    if metrics.bridge_ratio > 0.1 and soft_memberships:
        bridge_nodes = []
        for nid in member_node_ids:
            memberships = soft_memberships.get(nid, [])
            if len(memberships) >= 2:
                probs = [p for _, p in memberships]
                if probs:
                    entropy = -sum(p * np.log2(p) for p in probs if p > 0)
                    max_entropy = np.log2(len(probs))
                    if max_entropy > 0 and entropy / max_entropy > 0.7:
                        bridge_nodes.append(nid)

        if bridge_nodes:
            start = time.time()
            sub_clusters = execute_bridge_extraction(
                member_node_ids=member_node_ids,
                bridge_nodes=bridge_nodes,
            )
            elapsed = int((time.time() - start) * 1000)

            score = compute_structure_score(
                sub_clusters=sub_clusters,
                total_members=total_members,
                adjacency=adjacency,
                node_id_to_idx=node_id_to_idx,
                node_tags=node_tags,
                weights=weights,
            )

            scored_strategies.append(ScoredStrategy(
                strategy_name=ExpansionStrategy.BRIDGE_EXTRACTION.value,
                sub_clusters=sub_clusters,
                score=score,
                execution_time_ms=elapsed,
            ))

    # Strategy 7: LOUVAIN (if edges exist)
    if metrics.n_edges > 0 and n > 5:
        resolution = 1.0 + np.log10(max(10, n)) / 2

        start = time.time()
        sub_clusters = execute_louvain_local(
            member_node_ids=member_node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            resolution=resolution,
        )
        elapsed = int((time.time() - start) * 1000)

        # Only score if it actually split
        if len(sub_clusters) > 1:
            score = compute_structure_score(
                sub_clusters=sub_clusters,
                total_members=total_members,
                adjacency=adjacency,
                node_id_to_idx=node_id_to_idx,
                node_tags=node_tags,
                weights=weights,
            )

            scored_strategies.append(ScoredStrategy(
                strategy_name=ExpansionStrategy.LOUVAIN.value,
                sub_clusters=sub_clusters,
                score=score,
                execution_time_ms=elapsed,
            ))

    # Rank by score
    return rank_strategies(scored_strategies)


def get_best_expansion(
    member_node_ids: List[str],
    adjacency: sparse.spmatrix,
    node_id_to_idx: Dict[str, int],
    node_tags: Optional[Dict[str, Set[str]]] = None,
    soft_memberships: Optional[Dict[str, List[Tuple[str, float]]]] = None,
    linkage_matrix: Optional[np.ndarray] = None,
    dendrogram_node: int = -1,
    n_micro: int = 0,
    weights: Optional["StructureScoreWeights"] = None,
) -> Optional["ScoredStrategy"]:
    """Get the best expansion strategy for a cluster.

    Convenience wrapper around evaluate_all_strategies that returns
    just the top-ranked strategy.

    Returns:
        Best ScoredStrategy, or None if no strategies are applicable
    """
    ranked = evaluate_all_strategies(
        member_node_ids=member_node_ids,
        adjacency=adjacency,
        node_id_to_idx=node_id_to_idx,
        node_tags=node_tags,
        soft_memberships=soft_memberships,
        linkage_matrix=linkage_matrix,
        dendrogram_node=dendrogram_node,
        n_micro=n_micro,
        weights=weights,
    )

    return ranked[0] if ranked else None
