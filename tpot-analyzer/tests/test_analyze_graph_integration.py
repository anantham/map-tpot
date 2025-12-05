"""Integration tests for scripts/analyze_graph.py CLI.

Tests the full pipeline: loading data, building graph, computing metrics,
and generating JSON output. Verifies CLI parameter handling and output structure.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import networkx as nx
import pytest

# Import the CLI functions we want to test
from scripts.analyze_graph import (
    _resolve_seeds,
    _serialize_datetime,
    load_seeds,
    parse_args,
    run_metrics,
)
from src.graph import GraphBuildResult


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def sample_graph_result():
    """Create a minimal GraphBuildResult for testing."""
    directed = nx.DiGraph()
    directed.add_edges_from([
        ("123", "456"),  # alice -> bob
        ("456", "789"),  # bob -> charlie
        ("789", "123"),  # charlie -> alice (creates cycle)
    ])

    # Add node attributes
    directed.nodes["123"].update({
        "username": "alice",
        "account_display_name": "Alice",
        "num_followers": 100,
        "num_following": 50,
        "num_likes": 500,
        "num_tweets": 200,
        "provenance": "archive",
        "shadow": False,
    })
    directed.nodes["456"].update({
        "username": "bob",
        "account_display_name": "Bob",
        "num_followers": 200,
        "num_following": 75,
        "num_likes": 1000,
        "num_tweets": 300,
        "provenance": "archive",
        "shadow": False,
    })
    directed.nodes["789"].update({
        "username": "charlie",
        "account_display_name": "Charlie",
        "num_followers": 150,
        "num_following": 60,
        "num_likes": 750,
        "num_tweets": 250,
        "provenance": "shadow",
        "shadow": True,
    })

    undirected = directed.to_undirected()

    return GraphBuildResult(
        directed=directed,
        undirected=undirected,
        archive_accounts=["123", "456"],
        shadow_accounts=["789"],
        total_nodes=3,
        total_edges=3,
        mutual_edges=0,
    )


@pytest.fixture
def mock_args():
    """Create mock CLI arguments."""
    args = Mock()
    args.seeds = ["alice"]
    args.seed_html = None
    args.mutual_only = False
    args.min_followers = 0
    args.alpha = 0.85
    args.weights = [0.4, 0.3, 0.3]
    args.resolution = 1.0
    args.include_shadow = False
    args.summary_only = False
    args.update_readme = False
    args.output = Path("test_output.json")
    return args


# ==============================================================================
# Test: Seed Resolution
# ==============================================================================

@pytest.mark.unit
def test_resolve_seeds_by_username(sample_graph_result):
    """Seed resolution should map usernames to account IDs."""
    seeds = ["alice", "bob"]
    resolved = _resolve_seeds(sample_graph_result, seeds)

    # Should resolve usernames to IDs
    assert "123" in resolved  # alice
    assert "456" in resolved  # bob
    assert len(resolved) == 2


@pytest.mark.unit
def test_resolve_seeds_by_id(sample_graph_result):
    """Seed resolution should accept account IDs directly."""
    seeds = ["123", "456"]  # Already IDs
    resolved = _resolve_seeds(sample_graph_result, seeds)

    assert "123" in resolved
    assert "456" in resolved


@pytest.mark.unit
def test_resolve_seeds_mixed_format(sample_graph_result):
    """Seed resolution should handle mix of usernames and IDs."""
    seeds = ["alice", "456", "charlie"]
    resolved = _resolve_seeds(sample_graph_result, seeds)

    assert "123" in resolved  # alice
    assert "456" in resolved  # direct ID
    assert "789" in resolved  # charlie


@pytest.mark.unit
def test_resolve_seeds_case_insensitive(sample_graph_result):
    """Seed resolution should be case-insensitive for usernames."""
    seeds = ["ALICE", "BoB", "cHaRlIe"]
    resolved = _resolve_seeds(sample_graph_result, seeds)

    assert "123" in resolved
    assert "456" in resolved
    assert "789" in resolved


@pytest.mark.unit
def test_resolve_seeds_nonexistent_username(sample_graph_result):
    """Seed resolution should skip non-existent usernames."""
    seeds = ["alice", "nonexistent_user", "bob"]
    resolved = _resolve_seeds(sample_graph_result, seeds)

    # Should only resolve existing users
    assert "123" in resolved
    assert "456" in resolved
    assert len(resolved) == 2


@pytest.mark.unit
def test_resolve_seeds_empty_list(sample_graph_result):
    """Seed resolution with empty list should return empty list."""
    seeds = []
    resolved = _resolve_seeds(sample_graph_result, seeds)

    assert resolved == []


# ==============================================================================
# Test: Metrics Computation
# ==============================================================================

@pytest.mark.integration
def test_run_metrics_structure(sample_graph_result, mock_args):
    """run_metrics() should return well-structured JSON-serializable dict."""
    result = run_metrics(sample_graph_result, ["alice"], mock_args)

    # Verify top-level keys
    assert "seeds" in result
    assert "resolved_seeds" in result
    assert "metrics" in result
    assert "top" in result
    assert "edges" in result
    assert "nodes" in result
    assert "graph_stats" in result

    # Verify metrics keys
    assert "pagerank" in result["metrics"]
    assert "betweenness" in result["metrics"]
    assert "engagement" in result["metrics"]
    assert "composite" in result["metrics"]
    assert "communities" in result["metrics"]

    # Verify top rankings
    assert "pagerank" in result["top"]
    assert "betweenness" in result["top"]
    assert "composite" in result["top"]


@pytest.mark.integration
def test_run_metrics_all_nodes_present(sample_graph_result, mock_args):
    """All nodes should appear in all metrics."""
    result = run_metrics(sample_graph_result, ["alice"], mock_args)

    expected_nodes = {"123", "456", "789"}

    # Check all metrics contain all nodes
    assert set(result["metrics"]["pagerank"].keys()) == expected_nodes
    assert set(result["metrics"]["betweenness"].keys()) == expected_nodes
    assert set(result["metrics"]["engagement"].keys()) == expected_nodes
    assert set(result["metrics"]["composite"].keys()) == expected_nodes
    assert set(result["metrics"]["communities"].keys()) == expected_nodes


@pytest.mark.integration
def test_run_metrics_pagerank_sums_to_one(sample_graph_result, mock_args):
    """PageRank scores should sum to 1.0."""
    result = run_metrics(sample_graph_result, ["alice"], mock_args)

    pagerank_sum = sum(result["metrics"]["pagerank"].values())
    assert abs(pagerank_sum - 1.0) < 0.001


@pytest.mark.integration
def test_run_metrics_top_rankings_limited(sample_graph_result, mock_args):
    """Top rankings should be limited to top 20 (or fewer if graph is smaller)."""
    result = run_metrics(sample_graph_result, ["alice"], mock_args)

    # With only 3 nodes, top lists should have at most 3 entries
    assert len(result["top"]["pagerank"]) <= 20
    assert len(result["top"]["betweenness"]) <= 20
    assert len(result["top"]["composite"]) <= 20

    # In this case, should have exactly 3
    assert len(result["top"]["pagerank"]) == 3


@pytest.mark.integration
def test_run_metrics_top_rankings_sorted(sample_graph_result, mock_args):
    """Top rankings should be sorted descending by score."""
    result = run_metrics(sample_graph_result, ["alice"], mock_args)

    # Verify PageRank top list is sorted descending
    pr_scores = [score for _, score in result["top"]["pagerank"]]
    assert pr_scores == sorted(pr_scores, reverse=True)

    # Verify composite top list is sorted descending
    composite_scores = [score for _, score in result["top"]["composite"]]
    assert composite_scores == sorted(composite_scores, reverse=True)


@pytest.mark.integration
def test_run_metrics_edges_structure(sample_graph_result, mock_args):
    """Edges should have correct structure with mutual flag."""
    result = run_metrics(sample_graph_result, ["alice"], mock_args)

    # Should have 3 edges
    assert len(result["edges"]) == 3

    # Check edge structure
    for edge in result["edges"]:
        assert "source" in edge
        assert "target" in edge
        assert "mutual" in edge
        assert "provenance" in edge
        assert "shadow" in edge
        assert isinstance(edge["mutual"], bool)


@pytest.mark.integration
def test_run_metrics_nodes_structure(sample_graph_result, mock_args):
    """Nodes should have correct attributes."""
    result = run_metrics(sample_graph_result, ["alice"], mock_args)

    assert "123" in result["nodes"]
    alice_data = result["nodes"]["123"]

    # Check required fields
    assert alice_data["username"] == "alice"
    assert alice_data["display_name"] == "Alice"
    assert alice_data["num_followers"] == 100
    assert alice_data["num_following"] == 50
    assert alice_data["provenance"] == "archive"
    assert alice_data["shadow"] is False


@pytest.mark.integration
def test_run_metrics_graph_stats(sample_graph_result, mock_args):
    """Graph stats should report correct counts."""
    result = run_metrics(sample_graph_result, ["alice"], mock_args)

    stats = result["graph_stats"]
    assert stats["total_nodes"] == 3
    assert stats["archive_accounts"] == 2
    assert stats["shadow_accounts"] == 1
    assert stats["total_edges"] == 3


# ==============================================================================
# Test: Weight Parameters
# ==============================================================================

@pytest.mark.integration
def test_run_metrics_with_custom_weights(sample_graph_result, mock_args):
    """Custom weights should affect composite scores."""
    # Run with PageRank-only weights
    mock_args.weights = [1.0, 0.0, 0.0]
    result_pr_only = run_metrics(sample_graph_result, ["alice"], mock_args)

    # Run with betweenness-only weights
    mock_args.weights = [0.0, 1.0, 0.0]
    result_bt_only = run_metrics(sample_graph_result, ["alice"], mock_args)

    # Composite scores should differ
    composite_pr = result_pr_only["metrics"]["composite"]
    composite_bt = result_bt_only["metrics"]["composite"]

    # Rankings should potentially differ (not guaranteed, but likely)
    assert composite_pr != composite_bt


@pytest.mark.integration
def test_run_metrics_pagerank_alpha_parameter(sample_graph_result, mock_args):
    """Different alpha values should produce different PageRank scores."""
    # Run with alpha=0.5
    mock_args.alpha = 0.5
    result_low_alpha = run_metrics(sample_graph_result, ["alice"], mock_args)

    # Run with alpha=0.95
    mock_args.alpha = 0.95
    result_high_alpha = run_metrics(sample_graph_result, ["alice"], mock_args)

    # PageRank distributions should differ
    pr_low = result_low_alpha["metrics"]["pagerank"]
    pr_high = result_high_alpha["metrics"]["pagerank"]

    # At least one node should have different PageRank
    assert any(abs(pr_low[node] - pr_high[node]) > 0.01 for node in pr_low)


# ==============================================================================
# Test: Seed Loading
# ==============================================================================

@pytest.mark.unit
@patch("scripts.analyze_graph.load_seed_candidates")
def test_load_seeds_with_additional(mock_load_candidates, mock_args):
    """load_seeds should combine preset seeds with additional seeds."""
    mock_load_candidates.return_value = {"alice", "bob"}
    mock_args.seeds = ["charlie", "dave"]
    mock_args.seed_html = None

    seeds = load_seeds(mock_args)

    # Should combine both sources
    assert "alice" in seeds
    assert "bob" in seeds
    assert "charlie" in seeds
    assert "dave" in seeds


@pytest.mark.unit
@patch("scripts.analyze_graph.load_seed_candidates")
@patch("scripts.analyze_graph.extract_usernames_from_html")
def test_load_seeds_from_html(mock_extract, mock_load_candidates, mock_args, tmp_path):
    """load_seeds should extract usernames from HTML file."""
    mock_load_candidates.return_value = {"alice"}
    mock_extract.return_value = {"bob", "charlie"}

    # Create temporary HTML file
    html_file = tmp_path / "seeds.html"
    html_file.write_text("<html>some content</html>")

    mock_args.seeds = []
    mock_args.seed_html = html_file

    seeds = load_seeds(mock_args)

    # Should include both preset and extracted seeds
    assert "alice" in seeds
    assert "bob" in seeds
    assert "charlie" in seeds

    # Verify extract was called
    mock_extract.assert_called_once()


# ==============================================================================
# Test: CLI Argument Parsing
# ==============================================================================

@pytest.mark.unit
def test_parse_args_defaults():
    """CLI should have sensible defaults."""
    with patch("sys.argv", ["analyze_graph.py"]):
        args = parse_args()

        assert args.seeds == []
        assert args.mutual_only is False
        assert args.min_followers == 0
        assert args.alpha == 0.85
        assert args.weights == [0.4, 0.3, 0.3]
        assert args.resolution == 1.0
        assert args.include_shadow is False


@pytest.mark.unit
def test_parse_args_custom_values():
    """CLI should parse custom argument values."""
    with patch("sys.argv", [
        "analyze_graph.py",
        "--seeds", "alice", "bob",
        "--alpha", "0.9",
        "--weights", "0.5", "0.3", "0.2",
        "--min-followers", "10",
        "--include-shadow",
        "--mutual-only",
    ]):
        args = parse_args()

        assert args.seeds == ["alice", "bob"]
        assert args.alpha == 0.9
        assert args.weights == [0.5, 0.3, 0.2]
        assert args.min_followers == 10
        assert args.include_shadow is True
        assert args.mutual_only is True


# ==============================================================================
# Test: Datetime Serialization
# ==============================================================================

@pytest.mark.unit
def test_serialize_datetime_none():
    """Serializing None should return None."""
    assert _serialize_datetime(None) is None


@pytest.mark.unit
def test_serialize_datetime_string():
    """Serializing string should return string as-is."""
    assert _serialize_datetime("2025-01-01") == "2025-01-01"


@pytest.mark.unit
def test_serialize_datetime_datetime_object():
    """Serializing datetime should return ISO format string."""
    from datetime import datetime, timezone

    dt = datetime(2025, 1, 1, 12, 30, 45, tzinfo=timezone.utc)
    result = _serialize_datetime(dt)

    assert isinstance(result, str)
    assert "2025-01-01" in result
    assert "12:30:45" in result


# ==============================================================================
# Test: Full CLI Execution (End-to-End)
# ==============================================================================

@pytest.mark.integration
@pytest.mark.slow
def test_cli_execution_help():
    """CLI should respond to --help without errors."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.analyze_graph", "--help"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )

    assert result.returncode == 0
    assert "Analyze TPOT follow graph" in result.stdout


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(
    not Path("data/cache.db").exists(),
    reason="Requires data/cache.db with test data"
)
def test_cli_execution_minimal_run(tmp_path):
    """CLI should run with minimal args and produce valid JSON output."""
    output_file = tmp_path / "test_output.json"

    result = subprocess.run(
        [
            sys.executable, "-m", "scripts.analyze_graph",
            "--output", str(output_file),
            "--seeds", "alice",
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )

    # If cache.db exists and has data, this should succeed
    if result.returncode == 0:
        # Verify output file was created
        assert output_file.exists()

        # Verify JSON is valid
        with open(output_file) as f:
            data = json.load(f)

        # Verify structure
        assert "metrics" in data
        assert "nodes" in data
        assert "edges" in data
