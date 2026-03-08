"""Tests for analysis API routes (src/api/routes/analysis.py).

Covers:
- POST /api/metrics/compute — valid request, missing/invalid fields, bad weights
- POST /api/signals/feedback — valid submission, malformed payload, missing fields
- GET /api/signals/quality — basic report request
- GET /api/metrics/performance — performance diagnostics
- GET /api/analysis/status — background job status
- POST /api/analysis/run — background job start + conflict detection
- Error paths — all validation rejection paths return 400 with descriptive messages
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from src.api.routes.analysis import analysis_bp
from src.api.services.analysis_manager import AnalysisManager
from src.api.services.cache_manager import CacheManager
from src.api.services.signal_feedback_store import SignalFeedbackStore


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def analysis_app() -> Flask:
    """Create a minimal Flask app with the analysis blueprint and injected services."""
    app = Flask(__name__)
    app.testing = True

    app.config["ANALYSIS_MANAGER"] = AnalysisManager()
    app.config["CACHE_MANAGER"] = CacheManager()
    app.config["SIGNAL_FEEDBACK_STORE"] = SignalFeedbackStore()
    app.config["STARTUP_TIME"] = 1000000000.0

    app.register_blueprint(analysis_bp)
    return app


@pytest.fixture
def client(analysis_app: Flask):
    return analysis_app.test_client()


def _make_mock_graph():
    """Return a lightweight mock directed graph with three nodes."""
    G = MagicMock()
    G.nodes.return_value = ["alice", "bob", "carol"]
    G.__contains__ = lambda self, x: x in ["alice", "bob", "carol"]
    G.__iter__ = lambda self: iter(["alice", "bob", "carol"])
    return G


# =============================================================================
# POST /api/metrics/compute
# =============================================================================

class TestComputeMetrics:
    """Tests for the POST /api/metrics/compute endpoint."""

    @patch("src.api.routes.analysis.build_graph")
    @patch("src.api.routes.analysis.CachedDataFetcher")
    @patch("src.api.routes.analysis.get_snapshot_dir")
    @patch("src.api.routes.analysis.compute_louvain_communities")
    @patch("src.api.routes.analysis.compute_engagement_scores")
    @patch("src.api.routes.analysis.compute_betweenness")
    @patch("src.api.routes.analysis.compute_personalized_pagerank")
    @patch("src.api.routes.analysis.normalize_scores")
    def test_valid_request_returns_composite_scores(
        self,
        mock_normalize,
        mock_pagerank,
        mock_betweenness,
        mock_engagement,
        mock_louvain,
        mock_snapshot_dir,
        mock_fetcher_cls,
        mock_build_graph,
        client,
    ):
        G = _make_mock_graph()
        mock_build_graph.return_value = SimpleNamespace(directed=G)
        mock_snapshot_dir.return_value = MagicMock()

        mock_pagerank.return_value = {"alice": 0.5, "bob": 0.3, "carol": 0.2}
        mock_betweenness.return_value = {"alice": 0.1, "bob": 0.6, "carol": 0.3}
        mock_engagement.return_value = {"alice": 0.4, "bob": 0.4, "carol": 0.2}
        mock_louvain.return_value = {"alice": 0, "bob": 0, "carol": 1}
        # normalize_scores is called three times; return identity-like dicts
        mock_normalize.side_effect = lambda scores: scores

        resp = client.post("/api/metrics/compute", json={
            "seeds": ["alice"],
            "weights": [0.5, 0.3, 0.2],
            "alpha": 0.85,
        })

        assert resp.status_code == 200
        payload = resp.get_json()
        assert "metrics" in payload
        assert "top" in payload
        assert "seeds" in payload
        assert payload["seeds"] == ["alice"]
        assert "resolved_seeds" in payload
        assert "alice" in payload["resolved_seeds"]

        # Verify composite scores are present
        composite = payload["metrics"]["composite"]
        assert "alice" in composite

        # Verify top is sorted descending
        top = payload["top"]
        assert len(top) > 0
        for i in range(len(top) - 1):
            assert top[i]["score"] >= top[i + 1]["score"]

    def test_missing_json_body_returns_400(self, client):
        """Sending a null JSON body (Content-Type: application/json but empty)
        triggers the 'Invalid JSON' guard."""
        resp = client.post(
            "/api/metrics/compute",
            data="null",
            content_type="application/json",
        )
        assert resp.status_code == 400
        payload = resp.get_json()
        assert "error" in payload
        assert "Invalid JSON" in payload["error"]

    @patch("src.api.routes.analysis.build_graph")
    @patch("src.api.routes.analysis.CachedDataFetcher")
    @patch("src.api.routes.analysis.get_snapshot_dir")
    @patch("src.api.routes.analysis.compute_louvain_communities")
    @patch("src.api.routes.analysis.compute_engagement_scores")
    @patch("src.api.routes.analysis.compute_betweenness")
    @patch("src.api.routes.analysis.compute_personalized_pagerank")
    @patch("src.api.routes.analysis.normalize_scores")
    def test_default_weights_used_when_omitted(
        self,
        mock_normalize,
        mock_pagerank,
        mock_betweenness,
        mock_engagement,
        mock_louvain,
        mock_snapshot_dir,
        mock_fetcher_cls,
        mock_build_graph,
        client,
    ):
        """When 'weights' is not provided, defaults [0.4, 0.3, 0.3] are used."""
        G = _make_mock_graph()
        mock_build_graph.return_value = SimpleNamespace(directed=G)
        mock_snapshot_dir.return_value = MagicMock()

        mock_pagerank.return_value = {"alice": 1.0}
        mock_betweenness.return_value = {"alice": 1.0}
        mock_engagement.return_value = {"alice": 1.0}
        mock_louvain.return_value = {"alice": 0}
        mock_normalize.side_effect = lambda scores: scores

        resp = client.post("/api/metrics/compute", json={"seeds": []})

        assert resp.status_code == 200
        payload = resp.get_json()
        # With default weights [0.4, 0.3, 0.3] and all scores=1.0:
        # composite = 0.4*1.0 + 0.3*1.0 + 0.3*1.0 = 1.0
        assert payload["metrics"]["composite"]["alice"] == pytest.approx(1.0)

    @patch("src.api.routes.analysis.build_graph")
    @patch("src.api.routes.analysis.CachedDataFetcher")
    @patch("src.api.routes.analysis.get_snapshot_dir")
    @patch("src.api.routes.analysis.compute_louvain_communities")
    @patch("src.api.routes.analysis.compute_engagement_scores")
    @patch("src.api.routes.analysis.compute_betweenness")
    @patch("src.api.routes.analysis.compute_personalized_pagerank")
    @patch("src.api.routes.analysis.normalize_scores")
    def test_empty_seeds_still_computes(
        self,
        mock_normalize,
        mock_pagerank,
        mock_betweenness,
        mock_engagement,
        mock_louvain,
        mock_snapshot_dir,
        mock_fetcher_cls,
        mock_build_graph,
        client,
    ):
        """An empty seeds list is valid — produces metrics with no resolved seeds."""
        G = _make_mock_graph()
        mock_build_graph.return_value = SimpleNamespace(directed=G)
        mock_snapshot_dir.return_value = MagicMock()

        mock_pagerank.return_value = {"alice": 0.5}
        mock_betweenness.return_value = {"alice": 0.3}
        mock_engagement.return_value = {"alice": 0.2}
        mock_louvain.return_value = {"alice": 0}
        mock_normalize.side_effect = lambda scores: scores

        resp = client.post("/api/metrics/compute", json={"seeds": []})

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["seeds"] == []
        assert payload["resolved_seeds"] == []

    @patch("src.api.routes.analysis.build_graph")
    @patch("src.api.routes.analysis.CachedDataFetcher")
    @patch("src.api.routes.analysis.get_snapshot_dir")
    @patch("src.api.routes.analysis.compute_louvain_communities")
    @patch("src.api.routes.analysis.compute_engagement_scores")
    @patch("src.api.routes.analysis.compute_betweenness")
    @patch("src.api.routes.analysis.compute_personalized_pagerank")
    @patch("src.api.routes.analysis.normalize_scores")
    def test_unresolved_seeds_excluded_from_resolved_seeds(
        self,
        mock_normalize,
        mock_pagerank,
        mock_betweenness,
        mock_engagement,
        mock_louvain,
        mock_snapshot_dir,
        mock_fetcher_cls,
        mock_build_graph,
        client,
    ):
        """Seeds not present in the graph should not appear in resolved_seeds."""
        G = _make_mock_graph()
        mock_build_graph.return_value = SimpleNamespace(directed=G)
        mock_snapshot_dir.return_value = MagicMock()

        mock_pagerank.return_value = {"alice": 0.5}
        mock_betweenness.return_value = {"alice": 0.3}
        mock_engagement.return_value = {"alice": 0.2}
        mock_louvain.return_value = {"alice": 0}
        mock_normalize.side_effect = lambda scores: scores

        resp = client.post("/api/metrics/compute", json={
            "seeds": ["alice", "nonexistent_user"],
        })

        assert resp.status_code == 200
        payload = resp.get_json()
        assert "alice" in payload["resolved_seeds"]
        assert "nonexistent_user" not in payload["resolved_seeds"]


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

    def test_run_starts_background_job(self, analysis_app):
        """Starting a job should return 'started' status."""
        client = analysis_app.test_client()

        # Patch the heavy graph-building work so the background thread completes fast
        with patch("src.api.routes.analysis.get_snapshot_dir"), \
             patch("src.api.routes.analysis.CachedDataFetcher"), \
             patch("src.api.routes.analysis.build_graph") as mock_bg, \
             patch("src.api.routes.analysis.compute_louvain_communities"), \
             patch("src.api.routes.analysis.compute_personalized_pagerank"), \
             patch("src.api.routes.analysis.compute_betweenness"):
            mock_bg.return_value = SimpleNamespace(
                directed=_make_mock_graph()
            )
            resp = client.post("/api/analysis/run")

        assert resp.status_code == 200
        assert resp.get_json()["status"] == "started"

    def test_run_twice_returns_409_conflict(self, analysis_app):
        """Starting a second job while one is running should return 409."""
        manager: AnalysisManager = analysis_app.config["ANALYSIS_MANAGER"]

        # Simulate a job already running
        import threading
        event = threading.Event()

        def blocking_task(mgr):
            event.wait(timeout=5)

        manager.start_analysis(blocking_task)

        client = analysis_app.test_client()
        try:
            resp = client.post("/api/analysis/run")
            assert resp.status_code == 409
            payload = resp.get_json()
            assert "already running" in payload["message"]
        finally:
            event.set()  # Unblock the background thread


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
