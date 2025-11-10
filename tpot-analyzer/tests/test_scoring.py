"""Tests for graph scoring functions."""
from __future__ import annotations

import pytest
import networkx as nx

from src.graph.scoring import (
    compute_neighbor_overlap,
    compute_community_affinity,
    compute_path_distance_score,
    compute_pagerank_score,
    process_weights,
    compute_composite_score,
    score_candidate,
    DEFAULT_WEIGHTS
)


@pytest.fixture
def sample_graph():
    """Create a sample graph for testing."""
    G = nx.DiGraph()

    # Add nodes with communities
    nodes = [
        ("seed1", {"community": 1, "num_followers": 1000}),
        ("seed2", {"community": 1, "num_followers": 500}),
        ("seed3", {"community": 2, "num_followers": 800}),
        ("candidate1", {"community": 1, "num_followers": 300}),
        ("candidate2", {"community": 2, "num_followers": 5000}),
        ("candidate3", {"community": 3, "num_followers": 100}),
        ("mutual1", {"community": 1, "num_followers": 200}),
        ("mutual2", {"community": 1, "num_followers": 150}),
        ("distant", {"community": 4, "num_followers": 50}),
    ]
    G.add_nodes_from(nodes)

    # Add edges (u follows v)
    edges = [
        # Seeds follow some accounts
        ("seed1", "mutual1"),
        ("seed1", "mutual2"),
        ("seed1", "candidate1"),
        ("seed2", "mutual1"),
        ("seed2", "candidate1"),
        ("seed3", "mutual2"),
        ("seed3", "candidate2"),

        # Others follow candidates (making them discoverable)
        ("mutual1", "candidate1"),  # mutual1 follows candidate1
        ("mutual2", "candidate1"),  # mutual2 follows candidate1
        ("mutual1", "candidate2"),  # mutual1 follows candidate2

        # Distant node with no direct connections
        ("distant", "candidate3"),
    ]
    G.add_edges_from(edges)

    return G


@pytest.fixture
def pagerank_scores():
    """Sample PageRank scores."""
    return {
        "seed1": 0.15,
        "seed2": 0.12,
        "seed3": 0.10,
        "candidate1": 0.08,
        "candidate2": 0.20,  # High PageRank
        "candidate3": 0.02,  # Low PageRank
        "mutual1": 0.06,
        "mutual2": 0.05,
        "distant": 0.01,
    }


class TestNeighborOverlap:
    """Tests for compute_neighbor_overlap."""

    def test_high_overlap(self, sample_graph):
        """Test candidate with high overlap with seeds."""
        result = compute_neighbor_overlap(
            sample_graph,
            "candidate1",
            ["seed1", "seed2", "seed3"]
        )

        # Both mutual1 and mutual2 follow candidate1
        assert result["raw_count"] == 2
        assert result["normalized"] > 0.0
        assert "mutual1" in result["overlapping_accounts"]
        assert "mutual2" in result["overlapping_accounts"]
        assert result["seed_details"]["seed1"] == 2  # seed1 follows both mutuals
        assert result["seed_details"]["seed2"] == 1  # seed2 follows mutual1

    def test_no_overlap(self, sample_graph):
        """Test candidate with no overlap."""
        result = compute_neighbor_overlap(
            sample_graph,
            "candidate3",
            ["seed1", "seed2"]
        )

        assert result["raw_count"] == 0
        assert result["normalized"] == 0.0
        assert result["overlapping_accounts"] == []

    def test_candidate_not_in_graph(self, sample_graph):
        """Test handling of unknown candidate."""
        result = compute_neighbor_overlap(
            sample_graph,
            "unknown",
            ["seed1"]
        )

        assert result["normalized"] == 0.0
        assert result["raw_count"] == 0

    def test_seed_not_in_graph(self, sample_graph):
        """Test handling of unknown seed."""
        result = compute_neighbor_overlap(
            sample_graph,
            "candidate1",
            ["unknown_seed", "seed1"]
        )

        # Should still compute for valid seeds
        assert result["raw_count"] > 0
        assert "unknown_seed" in result["seed_details"]
        assert result["seed_details"]["unknown_seed"] == 0


class TestCommunityAffinity:
    """Tests for compute_community_affinity."""

    def test_same_community(self, sample_graph):
        """Test candidate in same community as seeds."""
        result = compute_community_affinity(
            sample_graph,
            "candidate1",
            ["seed1", "seed2", "seed3"]
        )

        assert result["community_id"] == 1
        assert result["normalized"] == 2/3  # 2 out of 3 seeds
        assert set(result["matching_seeds"]) == {"seed1", "seed2"}

    def test_different_community(self, sample_graph):
        """Test candidate in different community."""
        result = compute_community_affinity(
            sample_graph,
            "candidate3",
            ["seed1", "seed2"]
        )

        assert result["community_id"] == 3
        assert result["normalized"] == 0.0
        assert result["matching_seeds"] == []

    def test_no_community(self, sample_graph):
        """Test candidate without community assignment."""
        # Remove community attribute
        sample_graph.nodes["candidate1"]["community"] = None

        result = compute_community_affinity(
            sample_graph,
            "candidate1",
            ["seed1", "seed2"]
        )

        assert result["community_id"] is None
        assert result["normalized"] == 0.0

    def test_unknown_candidate(self, sample_graph):
        """Test unknown candidate."""
        result = compute_community_affinity(
            sample_graph,
            "unknown",
            ["seed1"]
        )

        assert result["normalized"] == 0.0
        assert result["community_id"] is None


class TestPathDistance:
    """Tests for compute_path_distance_score."""

    def test_direct_connection(self, sample_graph):
        """Test distance 1 (direct connection)."""
        undirected = sample_graph.to_undirected()
        result = compute_path_distance_score(
            undirected,
            "mutual1",
            ["seed1", "seed2"]
        )

        assert result["min_distance"] == 1
        assert result["normalized"] == 1.0  # Distance 1 = score 1.0
        assert result["seed_distances"]["seed1"] == 1
        assert result["seed_distances"]["seed2"] == 1

    def test_two_hop_distance(self, sample_graph):
        """Test distance 2."""
        undirected = sample_graph.to_undirected()
        result = compute_path_distance_score(
            undirected,
            "candidate2",
            ["seed1"]
        )

        # seed1 -> mutual1 -> candidate2
        assert result["min_distance"] == 2
        assert 0.0 < result["normalized"] < 1.0

    def test_unreachable(self, sample_graph):
        """Test unreachable candidate."""
        undirected = sample_graph.to_undirected()

        # Remove edges to make distant unreachable
        undirected.remove_node("distant")
        undirected.add_node("distant")

        result = compute_path_distance_score(
            undirected,
            "distant",
            ["seed1", "seed2"]
        )

        assert result["min_distance"] is None
        assert result["normalized"] == 0.0
        assert result["seed_distances"]["seed1"] is None

    def test_max_distance_cutoff(self, sample_graph):
        """Test max_distance parameter."""
        undirected = sample_graph.to_undirected()

        # Add long path
        undirected.add_edges_from([
            ("seed1", "hop1"),
            ("hop1", "hop2"),
            ("hop2", "hop3"),
            ("hop3", "faraway")
        ])

        result = compute_path_distance_score(
            undirected,
            "faraway",
            ["seed1"],
            max_distance=3
        )

        assert result["min_distance"] == 4
        assert result["normalized"] == 0.0  # Beyond max_distance


class TestPageRankScore:
    """Tests for compute_pagerank_score."""

    def test_high_pagerank(self, pagerank_scores):
        """Test high PageRank candidate."""
        result = compute_pagerank_score(
            "candidate2",
            pagerank_scores
        )

        assert result["raw"] == 0.20
        assert result["normalized"] > 0.8  # Should be high
        assert result["percentile"] > 0.8

    def test_low_pagerank(self, pagerank_scores):
        """Test low PageRank candidate."""
        result = compute_pagerank_score(
            "distant",
            pagerank_scores
        )

        assert result["raw"] == 0.01
        assert result["normalized"] < 0.2  # Should be low
        assert result["percentile"] < 0.2

    def test_unknown_candidate(self, pagerank_scores):
        """Test unknown candidate."""
        result = compute_pagerank_score(
            "unknown",
            pagerank_scores
        )

        assert result["raw"] == 0.0
        assert result["normalized"] == 0.0
        assert result["percentile"] == 0.0

    def test_percentile_capping(self):
        """Test that normalization uses percentile capping."""
        scores = {f"node{i}": 0.01 for i in range(100)}
        scores["outlier"] = 10.0  # Extreme outlier

        result = compute_pagerank_score("outlier", scores)

        # Should be capped at 1.0 despite being an outlier
        assert result["normalized"] == 1.0


class TestWeightProcessing:
    """Tests for process_weights."""

    def test_default_weights(self):
        """Test that None returns defaults."""
        weights = process_weights(None)
        assert weights == DEFAULT_WEIGHTS

    def test_normalization(self):
        """Test weight normalization."""
        raw = {
            "neighbor_overlap": 1.0,
            "pagerank": 1.0,
            "community": 1.0,
            "path_distance": 1.0
        }
        weights = process_weights(raw)

        assert sum(weights.values()) == pytest.approx(1.0, rel=1e-3)
        assert weights["neighbor_overlap"] == 0.25

    def test_zero_weights(self):
        """Test all-zero weights revert to defaults."""
        raw = {
            "neighbor_overlap": 0,
            "pagerank": 0,
            "community": 0,
            "path_distance": 0
        }
        weights = process_weights(raw)

        assert weights == DEFAULT_WEIGHTS

    def test_partial_weights(self):
        """Test partial weight specification."""
        raw = {"pagerank": 1.0}  # Only specify one

        weights = process_weights(raw)

        # Should use default for others, then normalize
        assert weights["pagerank"] > DEFAULT_WEIGHTS["pagerank"]
        assert sum(weights.values()) == pytest.approx(1.0, rel=1e-3)

    def test_invalid_weights(self):
        """Test invalid weight values."""
        raw = {
            "neighbor_overlap": -1.0,  # Negative
            "pagerank": 2.0,  # > 1
            "invalid_key": 0.5,  # Unknown key
        }
        weights = process_weights(raw)

        # Should clamp and ignore invalid
        assert 0.0 <= weights["neighbor_overlap"] <= 1.0
        assert 0.0 <= weights["pagerank"] <= 1.0
        assert "invalid_key" not in weights
        assert sum(weights.values()) == pytest.approx(1.0, rel=1e-3)


class TestCompositeScore:
    """Tests for compute_composite_score."""

    def test_weighted_sum(self):
        """Test basic weighted sum."""
        scores = {
            "neighbor_overlap": 0.8,
            "pagerank": 0.6,
            "community": 0.4,
            "path_distance": 0.2
        }
        weights = {
            "neighbor_overlap": 0.4,
            "pagerank": 0.3,
            "community": 0.2,
            "path_distance": 0.1
        }

        composite = compute_composite_score(scores, weights)

        expected = (0.8 * 0.4 + 0.6 * 0.3 + 0.4 * 0.2 + 0.2 * 0.1)
        assert composite == pytest.approx(expected, rel=1e-3)

    def test_missing_scores(self):
        """Test handling of missing score components."""
        scores = {
            "neighbor_overlap": 0.8,
            # Missing other scores
        }

        composite = compute_composite_score(scores)

        # Should treat missing as 0
        assert composite < 0.8
        assert composite > 0.0

    def test_cap_at_one(self):
        """Test that composite is capped at 1.0."""
        scores = {
            "neighbor_overlap": 1.0,
            "pagerank": 1.0,
            "community": 1.0,
            "path_distance": 1.0
        }

        composite = compute_composite_score(scores)
        assert composite == 1.0


class TestScoreCandidate:
    """Tests for score_candidate (integration)."""

    def test_full_scoring(self, sample_graph, pagerank_scores):
        """Test complete scoring of a candidate."""
        result = score_candidate(
            sample_graph,
            "candidate1",
            ["seed1", "seed2"],
            pagerank_scores
        )

        assert result["candidate"] == "candidate1"
        assert 0.0 <= result["composite_score"] <= 1.0

        # Check all components present
        assert "neighbor_overlap" in result["scores"]
        assert "pagerank" in result["scores"]
        assert "community" in result["scores"]
        assert "path_distance" in result["scores"]

        # Check details
        assert "overlap" in result["details"]
        assert "community" in result["details"]
        assert "distance" in result["details"]
        assert "pagerank" in result["details"]

    def test_custom_weights(self, sample_graph, pagerank_scores):
        """Test scoring with custom weights."""
        # Heavily weight neighbor overlap
        weights = {
            "neighbor_overlap": 0.9,
            "pagerank": 0.05,
            "community": 0.03,
            "path_distance": 0.02
        }

        result1 = score_candidate(
            sample_graph,
            "candidate1",  # High overlap
            ["seed1", "seed2"],
            pagerank_scores,
            weights
        )

        result2 = score_candidate(
            sample_graph,
            "candidate2",  # Low overlap but high PageRank
            ["seed1", "seed2"],
            pagerank_scores,
            weights
        )

        # With these weights, candidate1 should score higher
        assert result1["composite_score"] > result2["composite_score"]

    def test_unknown_candidate(self, sample_graph, pagerank_scores):
        """Test scoring of unknown candidate."""
        result = score_candidate(
            sample_graph,
            "unknown",
            ["seed1"],
            pagerank_scores
        )

        assert result["composite_score"] == 0.0
        assert all(score == 0.0 for score in result["scores"].values())


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_seeds(self, sample_graph, pagerank_scores):
        """Test with empty seed list."""
        result = score_candidate(
            sample_graph,
            "candidate1",
            [],
            pagerank_scores
        )

        # Should handle gracefully
        assert result["composite_score"] >= 0.0

    def test_single_seed(self, sample_graph, pagerank_scores):
        """Test with single seed."""
        result = score_candidate(
            sample_graph,
            "candidate1",
            ["seed1"],
            pagerank_scores
        )

        assert result["composite_score"] > 0.0

    def test_disconnected_graph(self):
        """Test with completely disconnected graph."""
        G = nx.DiGraph()
        G.add_nodes_from([
            ("seed", {"community": 1}),
            ("candidate", {"community": 2})
        ])
        # No edges

        scores = {"seed": 0.1, "candidate": 0.1}

        result = score_candidate(
            G,
            "candidate",
            ["seed"],
            scores
        )

        # Should still compute (mostly zeros)
        assert result["composite_score"] >= 0.0
        assert result["scores"]["neighbor_overlap"] == 0.0
        assert result["scores"]["path_distance"] == 0.0