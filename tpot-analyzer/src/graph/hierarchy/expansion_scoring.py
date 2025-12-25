"""Structure-aware scoring for expansion strategy evaluation.

This module implements the scoring system that evaluates how much meaningful
structure an expansion strategy reveals. Rather than using heuristics to
guess which strategy might work, we actually run each candidate strategy
and score the output based on measurable structural properties.

The key insight: a good expansion reveals structure, a bad one either
collapses everything into one blob or fragments into meaningless singletons.

Scoring Components:
- Size entropy: Diverse cluster sizes indicate meaningful groupings
- Collapse ratio: Penalize when one cluster dominates
- Fragmentation: Penalize excessive singletons
- Edge separation: Good clusters have high intra/inter edge ratio
- Tag coherence: Clusters should align with user-provided semantic tags
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from scipy import sparse

logger = logging.getLogger(__name__)


@dataclass
class StructureScoreWeights:
    """Weights for structure score components.

    These can be tuned by the user to reflect what "good structure" means
    to them. All weights should be non-negative.
    """
    size_entropy: float = 1.0       # Reward diverse cluster sizes
    collapse_penalty: float = 1.0   # Penalize single dominant cluster
    fragmentation_penalty: float = 1.0  # Penalize too many singletons
    edge_separation: float = 1.0    # Reward cohesive clusters (high intra/inter ratio)
    tag_coherence: float = 1.0      # Reward alignment with user tags

    def normalize(self) -> "StructureScoreWeights":
        """Return normalized weights that sum to 1."""
        total = (
            self.size_entropy +
            self.collapse_penalty +
            self.fragmentation_penalty +
            self.edge_separation +
            self.tag_coherence
        )
        if total == 0:
            return StructureScoreWeights()
        return StructureScoreWeights(
            size_entropy=self.size_entropy / total,
            collapse_penalty=self.collapse_penalty / total,
            fragmentation_penalty=self.fragmentation_penalty / total,
            edge_separation=self.edge_separation / total,
            tag_coherence=self.tag_coherence / total,
        )


@dataclass
class StructureScoreBreakdown:
    """Detailed breakdown of structure score components."""

    # Individual component scores (0-1 each)
    size_entropy_score: float = 0.0
    collapse_score: float = 0.0  # 1 - collapse_ratio
    fragmentation_score: float = 0.0  # 1 - fragmentation_ratio
    edge_separation_score: float = 0.0
    tag_coherence_score: float = 0.0

    # Raw metrics for debugging/display
    n_clusters: int = 0
    largest_cluster_size: int = 0
    singleton_count: int = 0
    intra_edge_count: int = 0
    inter_edge_count: int = 0

    # Final weighted score
    total_score: float = 0.0

    # Human-readable reason
    reason: str = ""


def compute_size_entropy(cluster_sizes: List[int]) -> float:
    """Compute normalized entropy of cluster size distribution.

    High entropy = diverse sizes = good structure.
    Low entropy = uniform or single-dominated = less interesting.

    Returns:
        Score in [0, 1] where 1 is maximum diversity.
    """
    if len(cluster_sizes) <= 1:
        return 0.0

    total = sum(cluster_sizes)
    if total == 0:
        return 0.0

    # Compute probabilities
    probs = [s / total for s in cluster_sizes]

    # Shannon entropy
    entropy = -sum(p * math.log2(p) for p in probs if p > 0)

    # Normalize by maximum possible entropy (uniform distribution)
    max_entropy = math.log2(len(cluster_sizes))

    if max_entropy == 0:
        return 0.0

    return entropy / max_entropy


def compute_collapse_ratio(cluster_sizes: List[int]) -> float:
    """Compute how much the largest cluster dominates.

    Returns:
        Ratio in [0, 1] where 0 is no collapse, 1 is total collapse.
    """
    if not cluster_sizes:
        return 1.0

    total = sum(cluster_sizes)
    if total == 0:
        return 1.0

    largest = max(cluster_sizes)
    return largest / total


def compute_fragmentation_ratio(cluster_sizes: List[int], total_members: int) -> float:
    """Compute what fraction of output is singletons.

    Returns:
        Ratio in [0, 1] where 0 is no singletons, 1 is all singletons.
    """
    if total_members == 0:
        return 0.0

    singleton_count = sum(1 for s in cluster_sizes if s == 1)
    singleton_members = singleton_count  # Each singleton has 1 member

    return singleton_members / total_members


def compute_edge_separation(
    sub_clusters: List[List[str]],
    adjacency: sparse.spmatrix,
    node_id_to_idx: Dict[str, int],
) -> Tuple[float, int, int]:
    """Compute ratio of intra-cluster to inter-cluster edges.

    Good clusters have dense internal connections and sparse external ones.

    Returns:
        (score, intra_count, inter_count) where score is in [0, 1].
    """
    if len(sub_clusters) <= 1:
        return (0.5, 0, 0)  # Neutral score for single cluster

    # Build cluster membership map
    node_to_cluster: Dict[str, int] = {}
    for cluster_idx, members in enumerate(sub_clusters):
        for nid in members:
            node_to_cluster[nid] = cluster_idx

    # Get all member node IDs
    all_members = set()
    for members in sub_clusters:
        all_members.update(members)

    # Count intra and inter edges
    intra_edges = 0
    inter_edges = 0

    adj_coo = adjacency.tocoo()

    for i, j in zip(adj_coo.row, adj_coo.col):
        # Get node IDs for these indices
        src_nid = None
        tgt_nid = None

        for nid, idx in node_id_to_idx.items():
            if idx == i:
                src_nid = nid
            if idx == j:
                tgt_nid = nid
            if src_nid and tgt_nid:
                break

        if src_nid not in all_members or tgt_nid not in all_members:
            continue

        src_cluster = node_to_cluster.get(src_nid, -1)
        tgt_cluster = node_to_cluster.get(tgt_nid, -1)

        if src_cluster == tgt_cluster and src_cluster >= 0:
            intra_edges += 1
        elif src_cluster >= 0 and tgt_cluster >= 0:
            inter_edges += 1

    # Avoid double-counting (undirected graph)
    intra_edges = intra_edges // 2
    inter_edges = inter_edges // 2

    total_edges = intra_edges + inter_edges
    if total_edges == 0:
        return (0.5, 0, 0)  # No edges, neutral score

    # Score is ratio of intra edges
    score = intra_edges / total_edges

    return (score, intra_edges, inter_edges)


def compute_edge_separation_fast(
    sub_clusters: List[List[str]],
    adjacency: sparse.spmatrix,
    node_id_to_idx: Dict[str, int],
) -> Tuple[float, int, int]:
    """Fast version of edge separation using index sets.

    Optimized for large clusters by avoiding string lookups in inner loop.
    """
    if len(sub_clusters) <= 1:
        return (0.5, 0, 0)

    # Build index-based cluster membership
    all_member_indices: Set[int] = set()
    idx_to_cluster: Dict[int, int] = {}

    for cluster_idx, members in enumerate(sub_clusters):
        for nid in members:
            if nid in node_id_to_idx:
                idx = node_id_to_idx[nid]
                all_member_indices.add(idx)
                idx_to_cluster[idx] = cluster_idx

    # Count edges
    intra_edges = 0
    inter_edges = 0

    adj_coo = adjacency.tocoo()

    for i, j in zip(adj_coo.row, adj_coo.col):
        if i not in all_member_indices or j not in all_member_indices:
            continue
        if i >= j:  # Only count each edge once
            continue

        ci = idx_to_cluster.get(i, -1)
        cj = idx_to_cluster.get(j, -1)

        if ci == cj and ci >= 0:
            intra_edges += 1
        elif ci >= 0 and cj >= 0:
            inter_edges += 1

    total_edges = intra_edges + inter_edges
    if total_edges == 0:
        return (0.5, 0, 0)

    score = intra_edges / total_edges
    return (score, intra_edges, inter_edges)


def compute_tag_coherence(
    sub_clusters: List[List[str]],
    node_tags: Optional[Dict[str, Set[str]]],
) -> float:
    """Compute how well clusters align with user-provided tags.

    Good alignment: each cluster is dominated by a single tag.
    Poor alignment: tags are scattered randomly across clusters.

    Uses normalized mutual information (NMI) concept.

    Returns:
        Score in [0, 1] where 1 is perfect alignment.
    """
    if not node_tags or len(sub_clusters) <= 1:
        return 0.5  # Neutral when no tags or single cluster

    # Collect all tags that appear in these clusters
    all_tags: Set[str] = set()
    for members in sub_clusters:
        for nid in members:
            all_tags.update(node_tags.get(nid, set()))

    if not all_tags:
        return 0.5  # No tags present, neutral

    # For each cluster, compute tag purity (fraction of dominant tag)
    purities = []
    weights = []

    for members in sub_clusters:
        if not members:
            continue

        # Count tags in this cluster
        tag_counts: Dict[str, int] = {}
        tagged_count = 0

        for nid in members:
            nid_tags = node_tags.get(nid, set())
            if nid_tags:
                tagged_count += 1
                for tag in nid_tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

        if tagged_count == 0:
            continue  # Skip clusters with no tagged members

        # Purity = fraction belonging to most common tag
        max_count = max(tag_counts.values()) if tag_counts else 0
        purity = max_count / tagged_count

        purities.append(purity)
        weights.append(len(members))

    if not purities:
        return 0.5

    # Weighted average purity
    total_weight = sum(weights)
    weighted_purity = sum(p * w for p, w in zip(purities, weights)) / total_weight

    return weighted_purity


def compute_structure_score(
    sub_clusters: List[List[str]],
    total_members: int,
    adjacency: sparse.spmatrix,
    node_id_to_idx: Dict[str, int],
    node_tags: Optional[Dict[str, Set[str]]] = None,
    weights: Optional[StructureScoreWeights] = None,
) -> StructureScoreBreakdown:
    """Compute overall structure score for an expansion result.

    This is the main scoring function that evaluates how much meaningful
    structure an expansion strategy has revealed.

    Args:
        sub_clusters: List of member ID lists, one per cluster
        total_members: Total number of members being clustered
        adjacency: Full graph adjacency matrix
        node_id_to_idx: Mapping from node ID to matrix index
        node_tags: Optional mapping from node ID to set of tags
        weights: Optional custom weights for score components

    Returns:
        StructureScoreBreakdown with component scores and total
    """
    if weights is None:
        weights = StructureScoreWeights()

    # Normalize weights
    w = weights.normalize()

    # Compute cluster sizes
    cluster_sizes = [len(c) for c in sub_clusters]
    n_clusters = len(sub_clusters)

    # Handle degenerate cases
    if n_clusters == 0:
        return StructureScoreBreakdown(
            total_score=0.0,
            reason="No clusters produced",
        )

    if n_clusters == 1:
        return StructureScoreBreakdown(
            n_clusters=1,
            largest_cluster_size=cluster_sizes[0] if cluster_sizes else 0,
            collapse_score=0.0,
            total_score=0.2,  # Low score for complete collapse
            reason="All members in single cluster (no structure revealed)",
        )

    # Compute individual components
    size_entropy = compute_size_entropy(cluster_sizes)
    collapse_ratio = compute_collapse_ratio(cluster_sizes)
    fragmentation_ratio = compute_fragmentation_ratio(cluster_sizes, total_members)

    edge_sep_score, intra_edges, inter_edges = compute_edge_separation_fast(
        sub_clusters, adjacency, node_id_to_idx
    )

    tag_coherence = compute_tag_coherence(sub_clusters, node_tags)

    # Convert ratios to scores (higher is better)
    collapse_score = 1.0 - collapse_ratio
    fragmentation_score = 1.0 - fragmentation_ratio

    # Compute weighted total
    total_score = (
        w.size_entropy * size_entropy +
        w.collapse_penalty * collapse_score +
        w.fragmentation_penalty * fragmentation_score +
        w.edge_separation * edge_sep_score +
        w.tag_coherence * tag_coherence
    )

    # Generate human-readable reason
    reasons = []

    if collapse_ratio > 0.7:
        reasons.append(f"high collapse ({collapse_ratio:.0%} in largest)")
    elif collapse_ratio < 0.3:
        reasons.append("well-distributed sizes")

    if fragmentation_ratio > 0.5:
        reasons.append(f"high fragmentation ({fragmentation_ratio:.0%} singletons)")

    if edge_sep_score > 0.7:
        reasons.append(f"strong edge separation ({edge_sep_score:.2f})")
    elif edge_sep_score < 0.3:
        reasons.append(f"weak edge separation ({edge_sep_score:.2f})")

    if node_tags and tag_coherence > 0.7:
        reasons.append(f"good tag alignment ({tag_coherence:.2f})")

    reason = ", ".join(reasons) if reasons else f"{n_clusters} clusters with moderate structure"

    # Count singletons
    singleton_count = sum(1 for s in cluster_sizes if s == 1)

    return StructureScoreBreakdown(
        size_entropy_score=size_entropy,
        collapse_score=collapse_score,
        fragmentation_score=fragmentation_score,
        edge_separation_score=edge_sep_score,
        tag_coherence_score=tag_coherence,
        n_clusters=n_clusters,
        largest_cluster_size=max(cluster_sizes) if cluster_sizes else 0,
        singleton_count=singleton_count,
        intra_edge_count=intra_edges,
        inter_edge_count=inter_edges,
        total_score=total_score,
        reason=reason,
    )


@dataclass
class ScoredStrategy:
    """A strategy with its execution result and score."""

    strategy_name: str
    sub_clusters: List[List[str]]
    score: StructureScoreBreakdown
    execution_time_ms: int = 0


def rank_strategies(scored_strategies: List[ScoredStrategy]) -> List[ScoredStrategy]:
    """Rank strategies by their structure score, highest first."""
    return sorted(scored_strategies, key=lambda s: s.score.total_score, reverse=True)
