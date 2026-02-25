"""Tests for Flask API endpoints."""
from __future__ import annotations

import json

import pytest

from src.api.server import create_app


@pytest.fixture
def client(temp_snapshot_dir):
    """Create test client using a deterministic cache.db fixture."""
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        yield client


def _assert_graph_data_payload(data):
    assert isinstance(data, dict)
    assert "nodes" in data
    assert "edges" in data
    assert "directed_nodes" in data
    assert "directed_edges" in data
    assert "meta" in data

    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)
    assert isinstance(data["directed_nodes"], list)
    assert isinstance(data["directed_edges"], list)
    assert isinstance(data["meta"], dict)

    if data["nodes"]:
        node = data["nodes"][0]
        assert "id" in node
        assert "username" in node or "account_display_name" in node

    if data["edges"]:
        edge = data["edges"][0]
        assert "source" in edge
        assert "target" in edge


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
    _assert_graph_data_payload(data)

    # Verify we got some data
    assert len(data["nodes"]) > 0
    assert len(data["edges"]) > 0

    # Verify node structure
    node = data["nodes"][0]
    assert "username" in node or "display_name" in node
    assert "provenance" in node


def test_graph_data_filters(client):
    """Test graph data endpoint with filters."""
    # Test mutual_only filter
    response = client.get("/api/graph-data?mutual_only=true")
    assert response.status_code == 200
    data = json.loads(response.data)
    _assert_graph_data_payload(data)

    # All edges should be mutual
    for edge in data["edges"]:
        assert edge["mutual"] is True


def test_compute_metrics_endpoint(client):
    """Test metrics computation endpoint."""
    # 1. Get a valid seed from the graph first
    graph_resp = client.get("/api/graph-data")
    assert graph_resp.status_code == 200, (
        f"Expected /api/graph-data 200, got {graph_resp.status_code}"
    )
        
    graph_data = json.loads(graph_resp.data)
    _assert_graph_data_payload(graph_data)
    assert graph_data["nodes"], "Graph is empty; cache fixture should supply nodes."
        
    # Pick a real node ID from the DB
    valid_seed = graph_data["nodes"][0]["id"]

    payload = {
        "seeds": [valid_seed],
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
    # 1. Get a valid seed
    graph_resp = client.get("/api/graph-data")
    graph_data = json.loads(graph_resp.data)
    _assert_graph_data_payload(graph_data)
    assert graph_data["nodes"], "Graph is empty; cache fixture should supply nodes."
    
    seeds = [graph_data["nodes"][0]["id"]]

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


def test_subgraph_discover_endpoint_resolves_username_seed(client):
    """Discovery endpoint should accept username seeds and return ranked output."""
    payload = {
        "seeds": ["user_a"],
        "weights": {
            "neighbor_overlap": 0.4,
            "pagerank": 0.3,
            "community": 0.2,
            "path_distance": 0.1,
        },
        "filters": {
            "max_distance": 3,
            "min_overlap": 0,
            "min_followers": 0,
            "max_followers": 1_000_000,
            "include_shadow": True,
        },
        "limit": 50,
        "offset": 0,
        "debug": True,
    }
    response = client.post(
        "/api/subgraph/discover",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "error" not in data
    assert "recommendations" in data
    assert "meta" in data
    assert isinstance(data["recommendations"], list)
    assert data["meta"]["seed_count"] == 1
    assert data["meta"]["recommendation_count"] >= 1


def test_subgraph_discover_endpoint_rejects_invalid_payload(client):
    """Discovery endpoint should return 400 for invalid request bodies."""
    response = client.post(
        "/api/subgraph/discover",
        data=json.dumps({"seeds": []}),
        content_type="application/json",
    )
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert any("seeds:" in detail for detail in data["error"]["details"])


def test_error_handling_invalid_payload(client):
    """Test error handling for invalid requests."""
    # Send invalid JSON - should get 400 Bad Request, not 500 Internal Server Error
    response = client.post(
        "/api/metrics/compute",
        data="not-json",
        content_type="application/json",
    )
    # 400 is correct (client error); 500 would indicate missing error handling (bug)
    assert response.status_code == 400, f"Expected 400 Bad Request, got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
