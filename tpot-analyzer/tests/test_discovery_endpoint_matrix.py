"""Regression matrix for /api/subgraph/discover endpoint behavior."""
from __future__ import annotations

import json

import pytest

from src.api.server import create_app


@pytest.fixture
def client(temp_snapshot_dir):
    """Create an API client backed by deterministic cache.db fixtures."""
    app = create_app({"TESTING": True})
    with app.test_client() as test_client:
        yield test_client


def _valid_payload(seed: str = "user_a", *, debug: bool = True, offset: int = 0) -> dict:
    return {
        "seeds": [seed],
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
        "limit": 2,
        "offset": offset,
        "debug": debug,
    }


@pytest.mark.parametrize("seed", ["user_a", "a", "@USER_A"])
def test_discovery_accepts_username_id_and_at_prefixed_seed(client, seed):
    response = client.post(
        "/api/subgraph/discover",
        data=json.dumps(_valid_payload(seed)),
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert "error" not in payload
    assert payload["meta"]["seed_count"] == 1
    assert payload["meta"]["recommendation_count"] >= 1
    assert isinstance(payload["recommendations"], list)


def test_discovery_rejects_non_object_json_body(client):
    response = client.post(
        "/api/subgraph/discover",
        data=json.dumps(["not", "an", "object"]),
        content_type="application/json",
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert payload["error"]["message"] == "Request body must be a JSON object"


def test_discovery_returns_unknown_handles_for_all_unknown_seeds(client):
    payload = _valid_payload("not_present_handle")
    response = client.post(
        "/api/subgraph/discover",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["error"]["code"] == "NO_VALID_SEEDS"
    assert data["error"]["unknown_handles"] == ["not_present_handle"]


def test_discovery_warns_when_mixed_known_and_unknown_seeds(client):
    payload = _valid_payload("user_a")
    payload["seeds"] = ["user_a", "not_present_handle"]
    response = client.post(
        "/api/subgraph/discover",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert "error" not in data
    assert data["meta"]["seed_count"] == 1
    assert "warnings" in data
    assert any("not_present_handle" in warning for warning in data["warnings"])


def test_discovery_rejects_out_of_range_filter_values(client):
    payload = _valid_payload("user_a")
    payload["filters"]["max_distance"] = 7
    response = client.post(
        "/api/subgraph/discover",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any("filters.max_distance" in detail for detail in body["error"]["details"])


def test_discovery_cache_returns_stable_request_identity_for_same_payload(client):
    payload = _valid_payload("user_a", debug=True)
    first = client.post(
        "/api/subgraph/discover",
        data=json.dumps(payload),
        content_type="application/json",
    )
    second = client.post(
        "/api/subgraph/discover",
        data=json.dumps(payload),
        content_type="application/json",
    )
    first_data = first.get_json()
    second_data = second.get_json()
    assert first.status_code == 200
    assert second.status_code == 200
    assert first_data["meta"]["request_id"] == second_data["meta"]["request_id"]
    assert first_data["meta"]["cache_key"] == second_data["meta"]["cache_key"]


def test_discovery_pagination_contract_fields(client):
    payload = _valid_payload("user_a", debug=False, offset=0)
    response = client.post(
        "/api/subgraph/discover",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert "debug" not in data
    pagination = data["meta"]["pagination"]
    assert pagination["limit"] == 2
    assert pagination["offset"] == 0
    assert isinstance(pagination["has_more"], bool)
