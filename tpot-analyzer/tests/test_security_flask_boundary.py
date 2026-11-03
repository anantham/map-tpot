"""Security intent: default-deny private/workload routes before any side effects;
allow health and deliberate open ingest only; retain authenticated analyst UX.
All stores and snapshot fixtures are synthetic and temporary.
"""
from __future__ import annotations

import pytest

from src.api.server import create_app

TOKEN = "security-fixture-token"


@pytest.fixture
def app(temp_snapshot_dir, monkeypatch, tmp_path):
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", TOKEN)
    monkeypatch.setenv("TPOT_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr("src.api.server.init_cluster_routes", lambda _: None)
    return create_app({"TESTING": True})


@pytest.mark.parametrize("method,path", [
    ("post", "/api/metrics/compute"), ("post", "/api/analysis/run"),
    ("post", "/api/signals/feedback"), ("get", "/api/graph-data"),
    ("get", "/api/golden/candidates"), ("post", "/api/golden/labels"),
    ("post", "/api/golden/eval/run"), ("post", "/api/golden/tags"),
    ("post", "/api/clusters/test/label"), ("delete", "/api/clusters/test/label"),
    ("get", "/api/research-notes/source"), ("post", "/api/log"),
    ("get", "/api/extension/settings?ego=fixture"),
    ("get", "/api/extension/feed_events/raw?ego=fixture"),
    ("post", "/api/extension/feed_events/purge_by_tag?ego=fixture"),
])
def test_anonymous_private_routes_fail_before_work(app, method, path):
    response = getattr(app.test_client(), method)(path, json={})
    assert response.status_code == 401
    assert "token" in response.get_json()["error"]
    assert app.config["SIGNAL_FEEDBACK_STORE"].event_count() == 0
    assert not app.config["ANALYSIS_MANAGER"].is_running()


def test_missing_token_configuration_fails_closed(app, monkeypatch):
    monkeypatch.delenv("TPOT_CURATOR_TOKEN")
    assert app.test_client().get("/api/graph-data").status_code == 503
    assert app.test_client().get("/api/health").status_code == 200


def test_authenticated_read_and_mutation(app):
    client = app.test_client()
    headers = {"X-TPOT-Curator-Token": TOKEN}
    assert client.get("/api/analysis/status", headers=headers).status_code == 200
    response = client.post("/api/signals/feedback", headers=headers, json={
        "account_id": "synthetic", "signal_name": "fixture", "user_label": "tpot", "score": .5,
    })
    assert response.status_code == 200
    assert app.config["SIGNAL_FEEDBACK_STORE"].event_count() == 1


def test_preflight_does_not_read_private_data(app):
    response = app.test_client().options("/api/graph-data", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "X-TPOT-Curator-Token",
    })
    assert response.status_code == 200
    assert not response.get_json(silent=True)


def test_oversized_feedback_and_logs_rejected(app):
    client = app.test_client()
    headers = {"X-TPOT-Curator-Token": TOKEN}
    response = client.post("/api/signals/feedback", headers=headers, json={
        "account_id": "synthetic", "signal_name": "fixture", "user_label": "tpot", "score": .5,
        "context": {"text": "x" * 5000},
    })
    assert response.status_code == 400
    assert app.config["SIGNAL_FEEDBACK_STORE"].event_count() == 0
    response = client.post("/api/log", headers=headers, json={"message": "x" * 9000})
    assert response.status_code == 413


def test_open_extension_ingestion_does_not_grant_private_or_admin_access(app, monkeypatch):
    from src.api.routes.extension_runtime import reset_extension_runtime
    reset_extension_runtime()
    monkeypatch.setenv("TPOT_EXTENSION_TOKEN", "ingest-only-token")
    client = app.test_client()
    scope = "?ego=synthetic"
    response = client.put("/api/extension/settings" + scope,
                          headers={"X-TPOT-Curator-Token": TOKEN}, json={"ingestionMode": "open"})
    assert response.status_code == 200
    response = client.post("/api/extension/feed_events" + scope, json={"events": []})
    assert response.status_code == 200
    assert "settings" not in response.get_json()
    assert "path" not in response.get_json()["firehose"]
    for headers in ({}, {"X-TPOT-Extension-Token": "ingest-only-token"}):
        assert client.get("/api/extension/settings" + scope, headers=headers).status_code == 401
        assert client.get("/api/extension/feed_events/raw" + scope, headers=headers).status_code == 401
        assert client.put("/api/extension/settings" + scope, headers=headers, json={}).status_code == 401
        assert client.post("/api/extension/feed_events/purge_by_tag" + scope, headers=headers, json={"tag": "fixture"}).status_code == 401
    assert client.get("/api/extension/feed_events/raw" + scope, headers={"X-TPOT-Curator-Token": TOKEN}).status_code == 200


@pytest.mark.parametrize("path,payload", [
    ("/api/metrics/compute", {"seeds": ["x"] * 21}),
    ("/api/metrics/compute", {"weights": [1, 1]}),
    ("/api/metrics/compute", {"alpha": float("nan")}),
    ("/api/subgraph/discover", {"seeds": ["synthetic"], "filters": "bad"}),
    ("/api/subgraph/discover", {"seeds": ["synthetic"], "weights": {"pagerank": float("inf")}}),
    ("/api/subgraph/discover", {"seeds": ["synthetic"], "limit": "huge"}),
])
def test_invalid_workload_parameters_rejected_before_graph_load(app, path, payload):
    response = app.test_client().post(path, headers={"X-TPOT-Curator-Token": TOKEN}, json=payload)
    assert response.status_code == 400
    assert app.config.get("SNAPSHOT_GRAPH") is None
