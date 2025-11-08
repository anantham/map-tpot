"""Scoring functions for TPOT discovery recommendations.

This module provides various scoring metrics to identify accounts
that are most relevant to a user's seed set.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx

logger = logging.getLogger(__name__)


# Default weights for composite scoring
DEFAULT_WEIGHTS = {
    "neighbor_overlap": 0.4,
    "pagerank": 0.3,
    "community": 0.2,
    "path_distance": 0.1
}


def compute_neighbor_overlap(
    graph: nx.DiGraph,
    candidate: str,
    seeds: List[str]
) -> Dict[str, any]:
    """Compute overlap between seeds' followings and candidate's followers.

    This measures how many of the accounts that seeds follow also follow
    the candidate - a strong signal of relevance.

    Args:
        graph: Directed graph where edge u→v means u follows v
        candidate: Handle of the candidate account
        seeds: List of seed handles

    Returns:
        Dict with overlap metrics:
        - normalized: Normalized score [0, 1]
        - raw_count: Number of overlapping accounts
        - seed_details: Per-seed overlap counts
        - overlapping_accounts: List of accounts that overlap (max 10)
    """
    if candidate not in graph:
        return {
            "normalized": 0.0,
            "raw_count": 0,
            "seed_details": {},
            "overlapping_accounts": []
        }

    # Get candidate's followers (who follows the candidate)
    candidate_followers = set(graph.predecessors(candidate))

    # Compute overlap with each seed's following
    seed_details = {}
    all_overlaps = set()

    for seed in seeds:
        if seed not in graph:
            seed_details[seed] = 0
            continue

        # Who does this seed follow?
        seed_following = set(graph.successors(seed))

        # Overlap: seed's followings that also follow candidate
        overlap = seed_following & candidate_followers
        seed_details[seed] = len(overlap)
        all_overlaps.update(overlap)

    raw_count = len(all_overlaps)

    # Normalize by total possible overlap (all seeds' followings)
    all_seed_following = set()
    for seed in seeds:
        if seed in graph:
            all_seed_following.update(graph.successors(seed))

    max_possible = len(all_seed_following)
    normalized = raw_count / max_possible if max_possible > 0 else 0.0

    return {
        "normalized": min(1.0, normalized),  # Cap at 1.0
        "raw_count": raw_count,
        "seed_details": seed_details,
        "overlapping_accounts": list(all_overlaps)[:10]  # Sample for explanation
    }


def compute_community_affinity(
    graph: nx.DiGraph,
    candidate: str,
    seeds: List[str]
) -> Dict[str, any]:
    """Compute community-based similarity between candidate and seeds.

    Args:
        graph: Graph with node attribute 'community'
        candidate: Handle of the candidate
        seeds: List of seed handles

    Returns:
        Dict with community metrics:
        - normalized: Fraction of seeds in same community [0, 1]
        - community_id: Candidate's community (if any)
        - matching_seeds: Seeds in same community
    """
    if candidate not in graph:
        return {
            "normalized": 0.0,
            "community_id": None,
            "matching_seeds": []
        }

    candidate_community = graph.nodes[candidate].get('community')
    if candidate_community is None:
        return {
            "normalized": 0.0,
            "community_id": None,
            "matching_seeds": []
        }

    # Count how many seeds share this community
    matching_seeds = []
    for seed in seeds:
        if seed in graph:
            seed_community = graph.nodes[seed].get('community')
            if seed_community == candidate_community:
                matching_seeds.append(seed)

    # Normalize by number of seeds
    normalized = len(matching_seeds) / len(seeds) if seeds else 0.0

    return {
        "normalized": normalized,
        "community_id": candidate_community,
        "matching_seeds": matching_seeds
    }


def compute_path_distance_score(
    graph: nx.Graph,
    candidate: str,
    seeds: List[str],
    max_distance: int = 3
) -> Dict[str, any]:
    """Compute proximity score based on shortest path distances.

    Args:
        graph: Undirected graph for path computation
        candidate: Handle of the candidate
        seeds: List of seed handles
        max_distance: Maximum distance to consider (beyond = 0 score)

    Returns:
        Dict with distance metrics:
        - normalized: Inverse distance score [0, 1]
        - min_distance: Shortest distance to any seed
        - avg_distance: Average distance to all reachable seeds
        - seed_distances: Distance to each seed
    """
    if candidate not in graph:
        return {
            "normalized": 0.0,
            "min_distance": None,
            "avg_distance": None,
            "seed_distances": {}
        }

    # Compute distance to each seed
    seed_distances = {}
    valid_distances = []

    for seed in seeds:
        if seed not in graph:
            seed_distances[seed] = None
            continue

        try:
            distance = nx.shortest_path_length(graph, seed, candidate)
            seed_distances[seed] = distance
            valid_distances.append(distance)
        except nx.NetworkXNoPath:
            seed_distances[seed] = None

    if not valid_distances:
        return {
            "normalized": 0.0,
            "min_distance": None,
            "avg_distance": None,
            "seed_distances": seed_distances
        }

    min_distance = min(valid_distances)
    avg_distance = sum(valid_distances) / len(valid_distances)

    # Normalize: closer = higher score
    # Distance 1 = score 1.0, distance max_distance = score 0.1
    if min_distance <= max_distance:
        # Linear decay: 1.0 at distance 1, 0.1 at max_distance
        normalized = 1.0 - (min_distance - 1) * (0.9 / (max_distance - 1))
    else:
        normalized = 0.0  # Beyond max distance

    return {
        "normalized": max(0.0, normalized),
        "min_distance": min_distance,
        "avg_distance": round(avg_distance, 2),
        "seed_distances": seed_distances
    }


def compute_pagerank_score(
    candidate: str,
    pagerank_scores: Dict[str, float],
    percentile_threshold: float = 0.95
) -> Dict[str, any]:
    """Normalize pre-computed PageRank score.

    Args:
        candidate: Handle of the candidate
        pagerank_scores: Pre-computed PageRank scores for all nodes
        percentile_threshold: Top percentile for max normalization

    Returns:
        Dict with PageRank metrics:
        - normalized: Normalized score [0, 1]
        - raw: Raw PageRank value
        - percentile: Percentile rank
    """
    if candidate not in pagerank_scores:
        return {
            "normalized": 0.0,
            "raw": 0.0,
            "percentile": 0.0
        }

    raw_score = pagerank_scores[candidate]
    all_scores = list(pagerank_scores.values())
    all_scores.sort()

    # Find percentile
    rank = all_scores.index(raw_score) if raw_score in all_scores else 0
    percentile = rank / len(all_scores) if all_scores else 0.0

    # Normalize using 95th percentile as max (to avoid outlier influence)
    p95_index = int(len(all_scores) * percentile_threshold)
    p95_value = all_scores[p95_index] if p95_index < len(all_scores) else all_scores[-1]

    normalized = min(1.0, raw_score / p95_value) if p95_value > 0 else 0.0

    return {
        "normalized": normalized,
        "raw": raw_score,
        "percentile": round(percentile, 3)
    }


def process_weights(raw_weights: Optional[Dict[str, float]]) -> Dict[str, float]:
    """Process and normalize weight inputs.

    Args:
        raw_weights: User-provided weights (may be None or partial)

    Returns:
        Normalized weights that sum to 1.0
    """
    # Start with defaults
    weights = DEFAULT_WEIGHTS.copy()

    # Override with provided values
    if raw_weights:
        for key in DEFAULT_WEIGHTS:
            if key in raw_weights and isinstance(raw_weights[key], (int, float)):
                # Clamp to [0, 1]
                weights[key] = max(0.0, min(1.0, float(raw_weights[key])))

    # Check for zero-sum
    total = sum(weights.values())
    if total == 0:
        # All zeros → revert to defaults
        logger.warning("All weights zero, using defaults")
        return DEFAULT_WEIGHTS.copy()

    # Normalize to sum to 1.0 and round to avoid float drift
    normalized = {k: round(v/total, 4) for k, v in weights.items()}

    return normalized


def compute_composite_score(
    scores: Dict[str, float],
    weights: Optional[Dict[str, float]] = None
) -> float:
    """Compute weighted composite score.

    Args:
        scores: Individual normalized scores (each [0, 1])
        weights: Weights for each score (will be normalized)

    Returns:
        Composite score [0, 1]
    """
    weights = process_weights(weights)

    composite = 0.0
    for metric, weight in weights.items():
        score = scores.get(metric, 0.0)
        composite += score * weight

    return round(min(1.0, composite), 4)


def score_candidate(
    graph: nx.DiGraph,
    candidate: str,
    seeds: List[str],
    pagerank_scores: Dict[str, float],
    weights: Optional[Dict[str, float]] = None,
    undirected_graph: Optional[nx.Graph] = None
) -> Dict[str, any]:
    """Compute all scores for a candidate.

    Args:
        graph: Directed graph
        candidate: Handle to score
        seeds: Seed handles
        pagerank_scores: Pre-computed PageRank scores
        weights: Score weights (will be normalized)
        undirected_graph: Undirected version for path computation

    Returns:
        Complete scoring breakdown
    """
    # Use undirected for paths if not provided
    if undirected_graph is None:
        undirected_graph = graph.to_undirected()

    # Compute individual scores
    overlap = compute_neighbor_overlap(graph, candidate, seeds)
    community = compute_community_affinity(graph, candidate, seeds)
    distance = compute_path_distance_score(undirected_graph, candidate, seeds)
    pagerank = compute_pagerank_score(candidate, pagerank_scores)

    # Normalized scores for composite
    normalized_scores = {
        "neighbor_overlap": overlap["normalized"],
        "pagerank": pagerank["normalized"],
        "community": community["normalized"],
        "path_distance": distance["normalized"]
    }

    # Composite score
    composite = compute_composite_score(normalized_scores, weights)

    return {
        "candidate": candidate,
        "composite_score": composite,
        "scores": normalized_scores,
        "details": {
            "overlap": overlap,
            "community": community,
            "distance": distance,
            "pagerank": pagerank
        }
    }