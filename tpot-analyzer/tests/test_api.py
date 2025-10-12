"""Tests for Flask API endpoints."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.api.server import create_app


@pytest.fixture
def client(tmp_path):
    """Create test client with temporary cache DB."""
    # Use existing cache.db for integration tests
    cache_path = Path("data/cache.db")
    if not cache_path.exists():
        pytest.skip("cache.db not found - run data pipeline first")

    app = create_app(cache_db_path=cache_path)
    app.config["TESTING"] = True

    with app.test_client() as client:
        yield client


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "ok"


def test_graph_data_endpoint(client):
    """Test graph data endpoint returns valid structure."""
    response = client.get("/api/graph-data?include_shadow=true")
    assert response.status_code == 200

    data = json.loads(response.data)
    assert "nodes" in data
    assert "edges" in data
    assert "directed_nodes" in data
    assert "directed_edges" in data

    # Verify we got some data
    assert len(data["nodes"]) > 0
    assert len(data["edges"]) > 0

    # Verify node structure
    first_node_id = next(iter(data["nodes"]))
    node = data["nodes"][first_node_id]
    assert "username" in node or "display_name" in node
    assert "provenance" in node


def test_graph_data_filters(client):
    """Test graph data endpoint with filters."""
    # Test mutual_only filter
    response = client.get("/api/graph-data?mutual_only=true")
    assert response.status_code == 200
    data = json.loads(response.data)

    # All edges should be mutual
    for edge in data["edges"]:
        assert edge["mutual"] is True


def test_compute_metrics_endpoint(client):
    """Test metrics computation endpoint."""
    payload = {
        "seeds": ["nosilverv", "DefenderOfBasic"],
        "weights": [0.4, 0.3, 0.3],
        "alpha": 0.85,
        "resolution": 1.0,
        "include_shadow": True,
        "mutual_only": False,
        "min_followers": 0,
    }

    response = client.post(
        "/api/metrics/compute",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = json.loads(response.data)

    # Verify response structure
    assert "seeds" in data
    assert "resolved_seeds" in data
    assert "metrics" in data
    assert "top" in data

    # Verify metrics computed
    metrics = data["metrics"]
    assert "pagerank" in metrics
    assert "betweenness" in metrics
    assert "engagement" in metrics
    assert "composite" in metrics
    assert "communities" in metrics

    # Verify some nodes got scores
    assert len(metrics["pagerank"]) > 0
    assert len(metrics["composite"]) > 0

    # Verify seeds were resolved
    assert len(data["resolved_seeds"]) > 0


def test_compute_metrics_with_weights(client):
    """Test that different weights produce different composite scores."""
    seeds = ["nosilverv"]

    # Compute with weight favoring PageRank
    response1 = client.post(
        "/api/metrics/compute",
        data=json.dumps({
            "seeds": seeds,
            "weights": [1.0, 0.0, 0.0],  # All PageRank
        }),
        content_type="application/json",
    )
    data1 = json.loads(response1.data)

    # Compute with weight favoring Betweenness
    response2 = client.post(
        "/api/metrics/compute",
        data=json.dumps({
            "seeds": seeds,
            "weights": [0.0, 1.0, 0.0],  # All Betweenness
        }),
        content_type="application/json",
    )
    data2 = json.loads(response2.data)

    # Composite scores should be different
    composite1 = data1["metrics"]["composite"]
    composite2 = data2["metrics"]["composite"]

    # Find a node that appears in both
    common_nodes = set(composite1.keys()) & set(composite2.keys())
    assert len(common_nodes) > 0

    # At least some nodes should have different composite scores
    different_count = sum(
        1 for node in common_nodes
        if abs(composite1[node] - composite2[node]) > 0.01
    )
    assert different_count > 0


def test_presets_endpoint(client):
    """Test presets endpoint."""
    response = client.get("/api/metrics/presets")
    assert response.status_code == 200

    data = json.loads(response.data)
    assert isinstance(data, dict)
    # Should have at least one preset
    assert len(data) > 0


def test_error_handling_invalid_payload(client):
    """Test error handling for invalid requests."""
    # Send invalid JSON
    response = client.post(
        "/api/metrics/compute",
        data="not-json",
        content_type="application/json",
    )
    assert response.status_code == 400 or response.status_code == 500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
