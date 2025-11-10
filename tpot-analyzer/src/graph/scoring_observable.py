"""Observable wrapper for scoring functions with validation and events."""

import logging
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx
import numpy as np

from .scoring import (
    compute_neighbor_overlap,
    compute_pagerank_score,
    compute_community_affinity,
    compute_path_distance_score,
    compute_composite_score,
)
from .signal_pipeline import SignalPipeline, get_pipeline

logger = logging.getLogger(__name__)


class ObservableScorer:
    """Wraps scoring functions with observability and validation."""

    def __init__(self, pipeline: Optional[SignalPipeline] = None):
        """Initialize the observable scorer.

        Args:
            pipeline: Signal pipeline instance, or None to use global
        """
        self.pipeline = pipeline or get_pipeline()

    def compute_neighbor_overlap_observable(
        self,
        graph: nx.DiGraph,
        candidate: str,
        seeds: List[str],
        enable_validation: bool = True
    ) -> Tuple[float, Dict]:
        """Compute neighbor overlap with observability.

        Args:
            graph: NetworkX directed graph
            candidate: Handle of the candidate
            seeds: List of seed handles
            enable_validation: Whether to enable pipeline validation

        Returns:
            Tuple of (score, metadata)
        """
        if not enable_validation:
            result = compute_neighbor_overlap(graph, candidate, seeds)
            return result.get("normalized", 0.0), result

        def compute():
            result = compute_neighbor_overlap(graph, candidate, seeds)
            score = result.get("normalized", 0.0)

            # Enhance metadata for explainability
            metadata = {
                "overlap_count": result.get("raw_count", 0),
                "total_seeds": len(seeds),
                "seed_details": result.get("seed_details", {}),
                "overlapping_accounts": result.get("overlapping_accounts", [])
            }

            return score, metadata

        result = self.pipeline.compute_with_validation(
            signal_name="neighbor_overlap",
            compute_fn=compute,
            candidate_id=candidate,
            seeds=seeds
        )

        return result.score, result.metadata

    def compute_pagerank_score_observable(
        self,
        candidate_id: int,
        pagerank_scores: np.ndarray,
        percentile_95: float,
        enable_validation: bool = True
    ) -> Tuple[float, Dict]:
        """Compute PageRank score with observability.

        Args:
            candidate_id: ID of the candidate node
            pagerank_scores: Array of PageRank scores
            percentile_95: 95th percentile value for normalization
            enable_validation: Whether to enable pipeline validation

        Returns:
            Tuple of (score, metadata)
        """
        if not enable_validation:
            score = compute_pagerank_score(candidate_id, pagerank_scores, percentile_95)
            return score, {}

        def compute():
            score = compute_pagerank_score(candidate_id, pagerank_scores, percentile_95)

            # Add metadata for explainability
            raw_pagerank = pagerank_scores[candidate_id] if candidate_id < len(pagerank_scores) else 0
            percentile = np.sum(pagerank_scores <= raw_pagerank) / len(pagerank_scores) * 100

            metadata = {
                "raw_pagerank": float(raw_pagerank),
                "percentile": float(percentile),
                "percentile_95": float(percentile_95)
            }

            return score, metadata

        result = self.pipeline.compute_with_validation(
            signal_name="pagerank",
            compute_fn=compute,
            candidate_id=str(candidate_id)
        )

        return result.score, result.metadata

    def compute_community_score_observable(
        self,
        graph: nx.DiGraph,
        candidate: str,
        seeds: List[str],
        enable_validation: bool = True
    ) -> Tuple[float, Dict]:
        """Compute community score with observability.

        Args:
            graph: Graph with community node attributes
            candidate: Handle of the candidate
            seeds: List of seed handles
            enable_validation: Whether to enable pipeline validation

        Returns:
            Tuple of (score, metadata)
        """
        if not enable_validation:
            result = compute_community_affinity(graph, candidate, seeds)
            return result.get("normalized", 0.0), result

        def compute():
            result = compute_community_affinity(graph, candidate, seeds)
            score = result.get("normalized", 0.0)

            # Enhanced metadata
            metadata = {
                "candidate_community": result.get("community_id"),
                "matching_seeds": result.get("matching_seeds", []),
                "score": score
            }

            return score, metadata

        result = self.pipeline.compute_with_validation(
            signal_name="community",
            compute_fn=compute,
            candidate_id=candidate,
            seeds=seeds
        )

        return result.score, result.metadata

    def compute_path_distance_score_observable(
        self,
        graph: nx.Graph,
        candidate: str,
        seeds: List[str],
        max_distance: int = 3,
        enable_validation: bool = True
    ) -> Tuple[float, Dict]:
        """Compute path distance score with observability.

        Args:
            graph: NetworkX graph
            candidate: Handle of the candidate
            seeds: List of seed handles
            max_distance: Maximum distance to consider
            enable_validation: Whether to enable pipeline validation

        Returns:
            Tuple of (score, metadata)
        """
        if not enable_validation:
            result = compute_path_distance_score(graph, candidate, seeds, max_distance)
            return result.get("normalized", 0.0), result

        def compute():
            result = compute_path_distance_score(graph, candidate, seeds, max_distance)
            score = result.get("normalized", 0.0)

            metadata = {
                "min_distance": result.get("min_distance"),
                "closest_seed": result.get("closest_seed"),
                "per_seed_distances": result.get("per_seed_distances", {})
            }

            return score, metadata

        result = self.pipeline.compute_with_validation(
            signal_name="path_distance",
            compute_fn=compute,
            candidate_id=candidate,
            seeds=seeds
        )

        return result.score, result.metadata

    def combine_scores_observable(
        self,
        scores: Dict[str, float],
        weights: Optional[Dict[str, float]] = None,
        enable_validation: bool = True
    ) -> float:
        """Combine scores with observability.

        Args:
            scores: Dictionary of signal scores
            weights: Optional weights for combination
            enable_validation: Whether to enable pipeline validation

        Returns:
            Combined score
        """
        if not enable_validation:
            return compute_composite_score(scores, weights)

        def compute():
            combined = compute_composite_score(scores, weights)

            # Build metadata showing contribution of each signal
            default_weights = {
                "neighbor_overlap": 0.4,
                "pagerank": 0.3,
                "community": 0.2,
                "path_distance": 0.1
            }

            used_weights = weights or default_weights

            metadata = {
                "input_scores": scores,
                "weights": used_weights,
                "weighted_scores": {}
            }

            # Calculate weighted contributions
            for name, score in scores.items():
                weight = used_weights.get(name, 0)
                metadata["weighted_scores"][name] = score * weight

            return combined, metadata

        result = self.pipeline.compute_with_validation(
            signal_name="composite",
            compute_fn=compute
        )

        return result.score


def compute_signals_with_validation(
    graph: nx.DiGraph,
    candidate: str,
    seeds: List[str],
    pagerank_scores: Optional[np.ndarray] = None,
    percentile_95: Optional[float] = None,
    weights: Optional[Dict[str, float]] = None,
    max_distance: int = 3,
    enable_validation: bool = True
) -> Tuple[float, Dict[str, float], Dict[str, Dict]]:
    """Compute all signals with validation and observability.

    Args:
        graph: NetworkX directed graph
        candidate: Handle of the candidate
        seeds: List of seed handles
        pagerank_scores: Precomputed PageRank scores
        percentile_95: 95th percentile for PageRank normalization
        weights: Weights for score combination
        max_distance: Maximum path distance to consider
        enable_validation: Whether to enable validation

    Returns:
        Tuple of (combined_score, individual_scores, metadata)
    """
    scorer = ObservableScorer()
    individual_scores = {}
    metadata = {}

    # Compute neighbor overlap
    overlap_score, overlap_meta = scorer.compute_neighbor_overlap_observable(
        graph, candidate, seeds, enable_validation
    )
    individual_scores["neighbor_overlap"] = overlap_score
    metadata["neighbor_overlap"] = overlap_meta

    # Compute PageRank score if available
    if pagerank_scores is not None and percentile_95 is not None and candidate in graph:
        # Get node ID for PageRank lookup
        node_id = list(graph.nodes()).index(candidate) if candidate in graph else None
        if node_id is not None:
            pr_score, pr_meta = scorer.compute_pagerank_score_observable(
                node_id, pagerank_scores, percentile_95, enable_validation
            )
            individual_scores["pagerank"] = pr_score
            metadata["pagerank"] = pr_meta

    # Compute community score
    comm_score, comm_meta = scorer.compute_community_score_observable(
        graph, candidate, seeds, enable_validation
    )
    individual_scores["community"] = comm_score
    metadata["community"] = comm_meta

    # Compute path distance
    path_score, path_meta = scorer.compute_path_distance_score_observable(
        graph, candidate, seeds, max_distance, enable_validation
    )
    individual_scores["path_distance"] = path_score
    metadata["path_distance"] = path_meta

    # Combine scores
    combined_score = scorer.combine_scores_observable(
        individual_scores, weights, enable_validation
    )

    return combined_score, individual_scores, metadata