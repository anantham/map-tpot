from __future__ import annotations

import pytest
from flask import Flask

import src.api.routes.account_tag_estimates as estimate_routes
from src.api.routes.account_tag_estimates import account_tag_estimates_bp


CURATOR_TOKEN = "test-curator-token"


@pytest.fixture
def estimate_app(monkeypatch, tmp_path) -> Flask:
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", CURATOR_TOKEN)
    estimate_routes._estimate_store = None
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(account_tag_estimates_bp)
    return app


@pytest.mark.integration
def test_estimate_routes_append_and_read_history(estimate_app) -> None:
    """Test intent.

    - Protect estimate trajectories as curator-private data.
    - Append multiple sessions and return both the latest event and full history.
    - Avoid naming the latest event a stabilized endpoint.
    """
    client = estimate_app.test_client()
    url = "/api/accounts/123/tag-estimates?ego=aditya&tag=Dharma"
    assert client.get(url).status_code == 401

    headers = {
        "X-TPOT-Curator-Token": CURATOR_TOKEN,
        "X-TPOT-Curation-Source": "human_curator_api",
    }
    read_headers = {"X-TPOT-Curator-Token": CURATOR_TOKEN}
    empty = client.get(url, headers=read_headers)
    assert empty.status_code == 200
    assert empty.get_json()["current"] is None
    assert empty.get_json()["history"] == []

    for session, point, low, high in [
        ("review-one", 0.55, 0.25, 0.75),
        ("review-two", 0.70, 0.55, 0.85),
    ]:
        response = client.post(
            url,
            json={
                "pointEstimate": point,
                "plausibleLow": low,
                "plausibleHigh": high,
                "reviewSessionId": session,
            },
            headers=headers,
        )
        assert response.status_code == 200

    payload = client.get(url, headers=read_headers).get_json()
    assert payload["current"]["point_estimate"] == 0.70
    assert [row["review_session_id"] for row in payload["history"]] == [
        "review-one",
        "review-two",
    ]
    assert "stabilized" not in payload
    assert "converged" not in payload


@pytest.mark.unit
def test_estimate_route_rejects_missing_receipts_and_bad_ranges(estimate_app) -> None:
    """Test intent.

    - Require a source receipt for every append-only estimate mutation.
    - Surface range-order failures as descriptive client errors.
    """
    client = estimate_app.test_client()
    url = "/api/accounts/123/tag-estimates?ego=aditya&tag=Dharma"
    auth = {"X-TPOT-Curator-Token": CURATOR_TOKEN}
    body = {
        "pointEstimate": 0.5,
        "plausibleLow": 0.7,
        "plausibleHigh": 0.9,
        "reviewSessionId": "review-one",
    }
    assert client.post(url, json=body, headers=auth).status_code == 400

    auth["X-TPOT-Curation-Source"] = "human_curator_api"
    response = client.post(url, json=body, headers=auth)
    assert response.status_code == 400
    assert "low <= point <= high" in response.get_json()["error"]
