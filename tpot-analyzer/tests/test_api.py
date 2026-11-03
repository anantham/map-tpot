"""Tests for Flask API endpoints."""
from __future__ import annotations

import json

import pytest

from src.api.server import create_app


@pytest.fixture
def client(temp_snapshot_dir, monkeypatch):
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", "api-fixture-token")
    """Create test client using a deterministic cache.db fixture."""
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        client.environ_base["HTTP_X_TPOT_CURATOR_TOKEN"] = "api-fixture-token"
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
    """Whole-graph HTTP work remains unavailable until it has enforced job limits."""
    response = client.post("/api/metrics/compute", json={"seeds": ["synthetic"], "weights": [1, 0, 0]})
    assert response.status_code == 503
    assert response.get_json()["code"] == "BOUNDED_SUPERVISOR_REQUIRED"


def test_compute_metrics_with_weights(client):
    """Whole-graph HTTP work remains unavailable until it has enforced job limits."""
    response = client.post("/api/metrics/compute", json={"seeds": ["synthetic"], "weights": [1, 0, 0]})
    assert response.status_code == 503
    assert response.get_json()["code"] == "BOUNDED_SUPERVISOR_REQUIRED"


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
    assert data["code"] == "VALIDATION_ERROR"
    assert any("seeds:" in detail for detail in data["details"])


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
