"""Tests for graph API routes (/api/graph-data, /api/graph/settings)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest
from flask import Flask

from src.api.routes.graph import graph_bp
from src.api.services.cache_manager import CacheManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class _FakeGraphBuildResult:
    """Minimal stand-in for GraphBuildResult used by the route."""
    directed: nx.DiGraph
    undirected: Optional[nx.Graph] = None


def _make_digraph() -> nx.DiGraph:
    """Build a small deterministic DiGraph for assertions."""
    G = nx.DiGraph()
    G.add_node("n1", username="alice", community=1, pagerank=0.5)
    G.add_node("n2", username="bob", community=2, pagerank=0.3)
    G.add_edge("n1", "n2", weight=1.5, mutual=True)
    G.add_edge("n2", "n1", weight=0.8, mutual=False)
    return G


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def graph_app() -> Flask:
    """Create a minimal Flask app with the graph blueprint registered."""
    app = Flask(__name__)
    app.testing = True
    app.config["CACHE_MANAGER"] = CacheManager()
    app.config["STARTUP_TIME"] = "2026-01-01T00:00:00"
    app.register_blueprint(graph_bp)
    return app


@pytest.fixture
def graph_app_no_propagate() -> Flask:
    """App that swallows exceptions to test HTTP error status codes.

    With testing=True Flask propagates exceptions to the test.  For tests
    that need to assert on 4xx/5xx *status codes* we disable propagation so
    Flask returns the real error response.
    """
    app = Flask(__name__)
    app.testing = True
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.config["TRAP_HTTP_EXCEPTIONS"] = False
    app.config["CACHE_MANAGER"] = CacheManager()
    app.config["STARTUP_TIME"] = "2026-01-01T00:00:00"
    app.register_blueprint(graph_bp)
    return app


@pytest.fixture
def client(graph_app: Flask):
    return graph_app.test_client()


@pytest.fixture
def error_client(graph_app_no_propagate: Flask):
    return graph_app_no_propagate.test_client()


# ---------------------------------------------------------------------------
# GET /api/graph-data -- happy path
# ---------------------------------------------------------------------------

class TestGetGraphData:
    """Tests for the GET /api/graph-data endpoint."""

    @patch("src.api.routes.graph.get_snapshot_dir")
    @patch("src.api.routes.graph.CachedDataFetcher")
    @patch("src.api.routes.graph.build_graph")
    def test_returns_nodes_and_edges(
        self, mock_build, mock_fetcher_cls, mock_snapshot_dir, client
    ):
        """Basic request returns 200 with nodes, edges, and meta."""
        mock_snapshot_dir.return_value = MagicMock()
        mock_build.return_value = _FakeGraphBuildResult(directed=_make_digraph())

        resp = client.get("/api/graph-data")

        assert resp.status_code == 200
        payload = json.loads(resp.data)
        assert len(payload["nodes"]) == 2
        assert len(payload["edges"]) == 2
        assert payload["meta"]["node_count"] == 2
        assert payload["meta"]["edge_count"] == 2

        # Verify node shape
        alice = next(n for n in payload["nodes"] if n["label"] == "alice")
        assert alice["id"] == "n1"
        assert alice["group"] == 1
        assert alice["value"] == 0.5 * 100  # pagerank * 100

        # Verify edge shape
        edge = payload["edges"][0]
        assert "source" in edge
        assert "target" in edge
        assert "value" in edge
        assert "mutual" in edge

    @patch("src.api.routes.graph.get_snapshot_dir")
    @patch("src.api.routes.graph.CachedDataFetcher")
    @patch("src.api.routes.graph.build_graph")
    def test_query_params_forwarded_to_builder(
        self, mock_build, mock_fetcher_cls, mock_snapshot_dir, client
    ):
        """Query params include_shadow, mutual_only, min_followers are forwarded."""
        mock_snapshot_dir.return_value = MagicMock()
        mock_build.return_value = _FakeGraphBuildResult(directed=_make_digraph())

        resp = client.get(
            "/api/graph-data?include_shadow=false&mutual_only=true&min_followers=10"
        )

        assert resp.status_code == 200
        _, kwargs = mock_build.call_args
        assert kwargs["include_shadow"] is False
        assert kwargs["mutual_only"] is True
        assert kwargs["min_followers"] == 10

    @patch("src.api.routes.graph.get_snapshot_dir")
    @patch("src.api.routes.graph.CachedDataFetcher")
    @patch("src.api.routes.graph.build_graph")
    def test_default_query_params(
        self, mock_build, mock_fetcher_cls, mock_snapshot_dir, client
    ):
        """Without query params, defaults are include_shadow=True, mutual_only=False, min_followers=0."""
        mock_snapshot_dir.return_value = MagicMock()
        mock_build.return_value = _FakeGraphBuildResult(directed=_make_digraph())

        resp = client.get("/api/graph-data")

        assert resp.status_code == 200
        _, kwargs = mock_build.call_args
        assert kwargs["include_shadow"] is True
        assert kwargs["mutual_only"] is False
        assert kwargs["min_followers"] == 0

    @patch("src.api.routes.graph.get_snapshot_dir")
    @patch("src.api.routes.graph.CachedDataFetcher")
    @patch("src.api.routes.graph.build_graph")
    def test_mutual_only_forces_mutual_true_in_edges(
        self, mock_build, mock_fetcher_cls, mock_snapshot_dir, client
    ):
        """When mutual_only=true, all edges should have mutual=True."""
        mock_snapshot_dir.return_value = MagicMock()
        mock_build.return_value = _FakeGraphBuildResult(directed=_make_digraph())

        resp = client.get("/api/graph-data?mutual_only=true")

        assert resp.status_code == 200
        payload = json.loads(resp.data)
        for edge in payload["edges"]:
            assert edge["mutual"] is True

    @patch("src.api.routes.graph.get_snapshot_dir")
    @patch("src.api.routes.graph.CachedDataFetcher")
    @patch("src.api.routes.graph.build_graph")
    def test_backward_compat_aliases(
        self, mock_build, mock_fetcher_cls, mock_snapshot_dir, client
    ):
        """Response includes directed_nodes and directed_edges aliases."""
        mock_snapshot_dir.return_value = MagicMock()
        mock_build.return_value = _FakeGraphBuildResult(directed=_make_digraph())

        resp = client.get("/api/graph-data")
        payload = json.loads(resp.data)

        assert payload["directed_nodes"] == payload["nodes"]
        assert payload["directed_edges"] == payload["edges"]

    @patch("src.api.routes.graph.get_snapshot_dir")
    @patch("src.api.routes.graph.CachedDataFetcher")
    @patch("src.api.routes.graph.build_graph")
    def test_build_graph_error_returns_500(
        self, mock_build, mock_fetcher_cls, mock_snapshot_dir, graph_app_no_propagate
    ):
        """When build_graph raises, the server returns a 500."""
        mock_snapshot_dir.return_value = MagicMock()
        mock_build.side_effect = RuntimeError("graph build failed")

        client = graph_app_no_propagate.test_client()
        resp = client.get("/api/graph-data")

        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/graph-data -- caching behaviour
# ---------------------------------------------------------------------------

class TestGraphDataCaching:
    """Tests for the caching layer in GET /api/graph-data."""

    @patch("src.api.routes.graph.get_snapshot_dir")
    @patch("src.api.routes.graph.CachedDataFetcher")
    @patch("src.api.routes.graph.build_graph")
    def test_cache_hit_returns_without_building(
        self, mock_build, mock_fetcher_cls, mock_snapshot_dir, graph_app
    ):
        """When the CacheManager has a hit, build_graph is never called."""
        cached_json = json.dumps({"nodes": [], "edges": [], "meta": {}})
        # Cache key is f"{include_shadow}_{mutual_only}_{min_followers}"
        # where include_shadow/mutual_only are Python bools (True/False, capitalized)
        graph_app.config["CACHE_MANAGER"].set_graph_response("True_False_0", cached_json)

        client = graph_app.test_client()
        resp = client.get("/api/graph-data")

        assert resp.status_code == 200
        mock_build.assert_not_called()
        payload = json.loads(resp.data)
        assert payload["nodes"] == []

    @patch("src.api.routes.graph.get_snapshot_dir")
    @patch("src.api.routes.graph.CachedDataFetcher")
    @patch("src.api.routes.graph.build_graph")
    def test_cache_miss_builds_and_caches(
        self, mock_build, mock_fetcher_cls, mock_snapshot_dir, graph_app
    ):
        """On a cache miss, build_graph is called and result is cached."""
        mock_snapshot_dir.return_value = MagicMock()
        mock_build.return_value = _FakeGraphBuildResult(directed=_make_digraph())

        cm = graph_app.config["CACHE_MANAGER"]
        assert cm.graph_cache_size() == 0

        client = graph_app.test_client()
        resp = client.get("/api/graph-data")

        assert resp.status_code == 200
        mock_build.assert_called_once()
        assert cm.graph_cache_size() == 1

    @patch("src.api.routes.graph.get_snapshot_dir")
    @patch("src.api.routes.graph.CachedDataFetcher")
    @patch("src.api.routes.graph.build_graph")
    def test_different_params_create_separate_cache_entries(
        self, mock_build, mock_fetcher_cls, mock_snapshot_dir, graph_app
    ):
        """Different query-param combos produce different cache keys."""
        mock_snapshot_dir.return_value = MagicMock()
        mock_build.return_value = _FakeGraphBuildResult(directed=_make_digraph())

        cm = graph_app.config["CACHE_MANAGER"]
        client = graph_app.test_client()

        client.get("/api/graph-data?include_shadow=true&mutual_only=false&min_followers=0")
        client.get("/api/graph-data?include_shadow=false&mutual_only=true&min_followers=5")

        assert cm.graph_cache_size() == 2
        assert mock_build.call_count == 2


# ---------------------------------------------------------------------------
# GET /api/graph/settings
# ---------------------------------------------------------------------------

class TestGetGraphSettings:
    """Tests for GET /api/graph/settings."""

    @patch("src.api.routes.graph.get_graph_settings")
    def test_returns_current_settings(self, mock_get, client):
        mock_get.return_value = {"layout": "force", "seeds": ["alice"]}

        resp = client.get("/api/graph/settings")

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["layout"] == "force"
        assert payload["seeds"] == ["alice"]


# ---------------------------------------------------------------------------
# POST /api/graph/settings
# ---------------------------------------------------------------------------

class TestUpdateGraphSettings:
    """Tests for POST /api/graph/settings."""

    @patch("src.api.routes.graph.get_graph_settings")
    @patch("src.api.routes.graph.update_graph_settings")
    def test_valid_update(self, mock_update, mock_get, graph_app):
        mock_get.return_value = {"layout": "radial", "min_followers": 5}

        # Pre-populate the graph cache so we can verify it gets cleared
        cm = graph_app.config["CACHE_MANAGER"]
        cm.set_graph_response("some_key", '{"cached": true}')
        assert cm.graph_cache_size() == 1

        client = graph_app.test_client()
        resp = client.post(
            "/api/graph/settings",
            json={"layout": "radial", "min_followers": 5},
        )

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["status"] == "updated"
        assert payload["settings"]["layout"] == "radial"

        # Cache should have been cleared
        assert cm.graph_cache_size() == 0

    @patch("src.api.routes.graph.get_graph_settings")
    @patch("src.api.routes.graph.update_graph_settings")
    def test_update_calls_update_graph_settings_with_body(
        self, mock_update, mock_get, client
    ):
        """The POST body is forwarded to update_graph_settings."""
        mock_get.return_value = {}
        body = {"layout": "force", "mutual_only": True}

        client.post("/api/graph/settings", json=body)

        mock_update.assert_called_once_with(body)

    def test_non_json_body_returns_error(self, error_client):
        """Sending a non-JSON body should return 400 or 415."""
        resp = error_client.post(
            "/api/graph/settings",
            data="not json",
            content_type="text/plain",
        )
        # Flask returns 415 Unsupported Media Type when content_type is wrong
        # and request.json is accessed, or the route may 500 if it doesn't guard.
        # Either 400, 415, or 500 indicates the server rejected bad input.
        assert resp.status_code in (400, 415, 500)

    @patch("src.api.routes.graph.get_graph_settings")
    @patch("src.api.routes.graph.update_graph_settings")
    def test_update_with_empty_object(self, mock_update, mock_get, client):
        """An empty JSON object is a valid (no-op) update."""
        mock_get.return_value = {"layout": "force"}

        resp = client.post("/api/graph/settings", json={})

        assert resp.status_code == 200
        mock_update.assert_called_once_with({})

    @patch("src.api.routes.graph.get_graph_settings")
    @patch("src.api.routes.graph.update_graph_settings")
    def test_update_settings_raises_value_error(
        self, mock_update, mock_get, error_client
    ):
        """If update_graph_settings raises ValueError, server returns 500."""
        mock_update.side_effect = ValueError("settings must be an object")

        resp = error_client.post("/api/graph/settings", json={"bad": "data"})

        # The route does not catch ValueError, so Flask returns 500
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/graph-data -- invalid query params
# ---------------------------------------------------------------------------

class TestGraphDataBadInput:
    """Tests for error handling on bad query params."""

    def test_invalid_min_followers_returns_error(self, error_client):
        """Non-integer min_followers should cause a 400 or 500."""
        resp = error_client.get("/api/graph-data?min_followers=abc")

        # int("abc") raises ValueError; Flask returns 500 without explicit handling
        assert resp.status_code in (400, 500)

    @patch("src.api.routes.graph.get_snapshot_dir")
    @patch("src.api.routes.graph.CachedDataFetcher")
    @patch("src.api.routes.graph.build_graph")
    def test_empty_graph_returns_valid_structure(
        self, mock_build, mock_fetcher_cls, mock_snapshot_dir, client
    ):
        """An empty graph should still return valid JSON with zero counts."""
        mock_snapshot_dir.return_value = MagicMock()
        empty_graph = nx.DiGraph()
        mock_build.return_value = _FakeGraphBuildResult(directed=empty_graph)

        resp = client.get("/api/graph-data")

        assert resp.status_code == 200
        payload = json.loads(resp.data)
        assert payload["nodes"] == []
        assert payload["edges"] == []
        assert payload["meta"]["node_count"] == 0
        assert payload["meta"]["edge_count"] == 0
