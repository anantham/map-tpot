"""Tests for analysis API routes (src/api/routes/analysis.py).

Covers:
- POST /api/metrics/compute — bounded-supervisor requirement and invalid JSON
- POST /api/signals/feedback — valid submission, malformed payload, missing fields
- GET /api/signals/quality — basic report request
- GET /api/metrics/performance — performance diagnostics
- GET /api/analysis/status — background job status
- POST /api/analysis/run — bounded-supervisor requirement
- Error paths — all validation rejection paths return 400 with descriptive messages
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from flask import Flask

from src.api.routes.analysis import analysis_bp
from src.api.services.analysis_manager import AnalysisManager
from src.api.services.cache_manager import CacheManager
from src.api.services.signal_feedback_store import SignalFeedbackStore


# Fixtures

@pytest.fixture
def analysis_app(tmp_path) -> Flask:
    """Create a minimal Flask app with the analysis blueprint and injected services."""
    app = Flask(__name__)
    app.testing = True

    app.config["ANALYSIS_MANAGER"] = AnalysisManager()
    app.config["CACHE_MANAGER"] = CacheManager()
    app.config["SIGNAL_FEEDBACK_STORE"] = SignalFeedbackStore(db_path=tmp_path / "test_feedback.db")
    app.config["STARTUP_TIME"] = 1000000000.0

    app.register_blueprint(analysis_bp)
    return app


@pytest.fixture
def client(analysis_app: Flask):
    return analysis_app.test_client()


# Unsupervised graph computation

class TestComputeMetrics:
    """Unsupervised whole-graph HTTP computation stays disabled."""

    @pytest.mark.parametrize("payload", [{"seeds": []}, {"seeds": ["synthetic"]}, {"weights": [1, 0, 0]}])
    def test_valid_parameters_require_bounded_supervisor(self, client, payload):
        response = client.post("/api/metrics/compute", json=payload)
        assert response.status_code == 503
        assert response.get_json()["code"] == "BOUNDED_SUPERVISOR_REQUIRED"

    def test_missing_json_body_returns_400(self, client):
        assert client.post("/api/metrics/compute").status_code == 400


# =============================================================================
# POST /api/signals/feedback
# =============================================================================

class TestSignalFeedback:
    """Tests for the POST /api/signals/feedback endpoint."""

    def test_valid_feedback_returns_ok(self, client):
        resp = client.post("/api/signals/feedback", json={
            "account_id": "12345",
            "signal_name": "bio_keyword",
            "user_label": "tpot",
            "score": 0.85,
            "context": {"note": "strong signal"},
        })

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["status"] == "ok"
        assert payload["stored"] is True
        assert payload["total_feedback"] == 1

    def test_multiple_feedback_increments_count(self, client):
        for i in range(3):
            resp = client.post("/api/signals/feedback", json={
                "account_id": f"user_{i}",
                "signal_name": "bio_keyword",
                "user_label": "tpot",
                "score": 0.5,
            })
            assert resp.status_code == 200

        payload = resp.get_json()
        assert payload["total_feedback"] == 3

    def test_missing_account_id_returns_400(self, client):
        resp = client.post("/api/signals/feedback", json={
            "signal_name": "bio_keyword",
            "user_label": "tpot",
        })
        assert resp.status_code == 400
        assert "account_id" in resp.get_json()["error"]

    def test_missing_signal_name_returns_400(self, client):
        resp = client.post("/api/signals/feedback", json={
            "account_id": "12345",
            "user_label": "tpot",
        })
        assert resp.status_code == 400
        assert "signal_name" in resp.get_json()["error"]

    def test_invalid_user_label_returns_400(self, client):
        resp = client.post("/api/signals/feedback", json={
            "account_id": "12345",
            "signal_name": "bio_keyword",
            "user_label": "maybe_tpot",
        })
        assert resp.status_code == 400
        payload = resp.get_json()
        assert "user_label" in payload["error"]
        assert "tpot" in payload["error"]

    def test_missing_user_label_returns_400(self, client):
        resp = client.post("/api/signals/feedback", json={
            "account_id": "12345",
            "signal_name": "bio_keyword",
        })
        assert resp.status_code == 400
        assert "user_label" in resp.get_json()["error"]

    def test_non_numeric_score_returns_400(self, client):
        resp = client.post("/api/signals/feedback", json={
            "account_id": "12345",
            "signal_name": "bio_keyword",
            "user_label": "tpot",
            "score": "not_a_number",
        })
        assert resp.status_code == 400
        assert "score" in resp.get_json()["error"]

    def test_non_dict_context_returns_400(self, client):
        resp = client.post("/api/signals/feedback", json={
            "account_id": "12345",
            "signal_name": "bio_keyword",
            "user_label": "tpot",
            "context": ["not", "a", "dict"],
        })
        assert resp.status_code == 400
        assert "context" in resp.get_json()["error"]

    def test_no_json_body_returns_400(self, client):
        resp = client.post(
            "/api/signals/feedback",
            data="not json",
            content_type="text/plain",
        )
        assert resp.status_code == 400
        payload = resp.get_json()
        assert "error" in payload

    def test_empty_account_id_returns_400(self, client):
        resp = client.post("/api/signals/feedback", json={
            "account_id": "   ",
            "signal_name": "bio_keyword",
            "user_label": "tpot",
        })
        assert resp.status_code == 400
        assert "account_id" in resp.get_json()["error"]

    def test_empty_signal_name_returns_400(self, client):
        resp = client.post("/api/signals/feedback", json={
            "account_id": "12345",
            "signal_name": "",
            "user_label": "tpot",
        })
        assert resp.status_code == 400
        assert "signal_name" in resp.get_json()["error"]

    def test_score_defaults_to_zero(self, client):
        """When score is omitted, it defaults to 0.0 and the request succeeds."""
        resp = client.post("/api/signals/feedback", json={
            "account_id": "12345",
            "signal_name": "bio_keyword",
            "user_label": "not_tpot",
        })
        assert resp.status_code == 200
        assert resp.get_json()["stored"] is True

    def test_context_defaults_to_empty_dict(self, client):
        """When context is omitted, the request succeeds (defaults to {})."""
        resp = client.post("/api/signals/feedback", json={
            "account_id": "12345",
            "signal_name": "bio_keyword",
            "user_label": "tpot",
            "score": 0.5,
        })
        assert resp.status_code == 200
        assert resp.get_json()["stored"] is True


# =============================================================================
# GET /api/signals/quality
# =============================================================================

class TestSignalQuality:
    """Tests for the GET /api/signals/quality endpoint."""

    def test_empty_store_returns_empty_report(self, client):
        resp = client.get("/api/signals/quality")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert isinstance(payload, dict)
        assert len(payload) == 0

    def test_quality_report_after_feedback(self, client):
        """After submitting feedback, the quality report should include that signal."""
        # Submit a few feedback events
        for label, score in [("tpot", 0.9), ("tpot", 0.8), ("not_tpot", 0.2)]:
            client.post("/api/signals/feedback", json={
                "account_id": "user_1",
                "signal_name": "bio_keyword",
                "user_label": label,
                "score": score,
            })

        resp = client.get("/api/signals/quality")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert "bio_keyword" in payload
        report = payload["bio_keyword"]
        assert report["total_feedback"] == 3
        assert "quality" in report
        assert "tpot_ratio" in report
        assert "score_separation" in report


# =============================================================================
# GET /api/metrics/performance
# =============================================================================

class TestPerformanceMetrics:
    """Tests for the GET /api/metrics/performance endpoint."""

    def test_returns_uptime_and_cache_info(self, client):
        resp = client.get("/api/metrics/performance")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert "uptime_seconds" in payload
        assert payload["uptime_seconds"] >= 0
        assert "analysis_status" in payload
        assert "cache" in payload
        assert "graph_entries" in payload["cache"]
        assert "discovery_entries" in payload["cache"]


# =============================================================================
# GET /api/analysis/status + POST /api/analysis/run
# =============================================================================

class TestAnalysisJobLifecycle:
    """Tests for analysis status and run endpoints."""

    def test_status_idle_initially(self, client):
        resp = client.get("/api/analysis/status")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["status"] == "idle"

    def test_http_run_requires_bounded_supervisor(self, analysis_app):
        response = analysis_app.test_client().post("/api/analysis/run")
        assert response.status_code == 503
        assert response.get_json()["code"] == "BOUNDED_SUPERVISOR_REQUIRED"
        assert not analysis_app.config["ANALYSIS_MANAGER"].is_running()


# =============================================================================
# GET /api/metrics/presets
# =============================================================================

class TestPresetsRoute:
    """Tests for the GET /api/metrics/presets endpoint."""

    @patch("src.api.routes.analysis.load_seed_candidates")
    def test_returns_candidates_list(self, mock_load, client):
        mock_load.return_value = ["alice", "bob"]
        resp = client.get("/api/metrics/presets")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert "candidates" in payload
        assert payload["candidates"] == ["alice", "bob"]

    @patch("src.api.routes.analysis.load_seed_candidates")
    def test_empty_candidates(self, mock_load, client):
        mock_load.return_value = []
        resp = client.get("/api/metrics/presets")
        assert resp.status_code == 200
        assert resp.get_json()["candidates"] == []
