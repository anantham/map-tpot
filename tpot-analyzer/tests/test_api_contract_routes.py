"""Contract coverage for frontend-consumed API endpoints."""
from __future__ import annotations

import json

import pytest

from src.api.server import create_app


@pytest.fixture
def client(temp_snapshot_dir):
    app = create_app({"TESTING": True})
    with app.test_client() as test_client:
        yield test_client


def test_metrics_performance_contract_shape(client):
    response = client.get("/api/metrics/performance")
    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, dict)
    assert isinstance(payload["uptime_seconds"], (int, float))
    assert isinstance(payload["analysis_status"], str)
    assert isinstance(payload["cache"], dict)
    assert isinstance(payload["cache"]["graph_entries"], int)
    assert isinstance(payload["cache"]["discovery_entries"], int)


def test_signal_feedback_rejects_invalid_payload(client):
    response = client.post(
        "/api/signals/feedback",
        data=json.dumps(["bad", "payload"]),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "JSON object" in response.get_json()["error"]

    response = client.post(
        "/api/signals/feedback",
        data=json.dumps(
            {
                "account_id": "user_a",
                "signal_name": "neighbor_overlap",
                "score": 0.9,
                "user_label": "maybe",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "user_label" in response.get_json()["error"]


def test_signal_feedback_and_quality_roundtrip(client):
    events = [
        {
            "account_id": "user_a",
            "signal_name": "neighbor_overlap",
            "score": 0.85,
            "user_label": "tpot",
            "context": {"seed_count": 2},
        },
        {
            "account_id": "user_b",
            "signal_name": "neighbor_overlap",
            "score": 0.15,
            "user_label": "not_tpot",
            "context": {"seed_count": 2},
        },
    ]
    for event in events:
        response = client.post(
            "/api/signals/feedback",
            data=json.dumps(event),
            content_type="application/json",
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body["status"] == "ok"
        assert body["stored"] is True

    quality_response = client.get("/api/signals/quality")
    assert quality_response.status_code == 200
    report = quality_response.get_json()
    assert "neighbor_overlap" in report
    stats = report["neighbor_overlap"]
    assert stats["total_feedback"] >= 2
    assert "quality" in stats
    assert 0.0 <= stats["tpot_ratio"] <= 1.0
