"""Tests for the discovery API routes.

Covers:
- POST /api/subgraph/discover — validation, seed resolution, error paths
- GET /api/ego-network — parameter validation, placeholder response
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest
from flask import Flask

from src.api.routes.discovery import discovery_bp
from src.api.services.cache_manager import CacheManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_test_graph() -> nx.DiGraph:
    """Build a small directed graph with username attributes for seed resolution."""
    G = nx.DiGraph()
    G.add_node("acct_001", username="alice", num_followers=500, num_following=200)
    G.add_node("acct_002", username="Bob", num_followers=1200, num_following=300)
    G.add_node("acct_003", username="charlie", num_followers=50, num_following=10)
    G.add_edge("acct_001", "acct_002")
    G.add_edge("acct_002", "acct_003")
    G.add_edge("acct_003", "acct_001")
    return G


def _graph_result_from(directed: nx.DiGraph) -> SimpleNamespace:
    """Wrap a DiGraph in a namespace that mimics GraphBuildResult."""
    return SimpleNamespace(directed=directed)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def discovery_app(monkeypatch, tmp_path) -> Flask:
    """Create a minimal Flask app with the discovery blueprint registered.

    The snapshot loader is patched so _load_graph_result returns our small
    test graph without touching any real files on disk.
    """
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path))

    app = Flask(__name__)
    app.testing = True
    app.config["CACHE_MANAGER"] = CacheManager()

    # Pre-inject the test graph so _load_graph_result returns it immediately.
    app.config["SNAPSHOT_GRAPH"] = _graph_result_from(_build_test_graph())

    app.register_blueprint(discovery_bp)
    return app


@pytest.fixture
def discovery_app_no_graph(monkeypatch, tmp_path) -> Flask:
    """App without a preloaded graph — forces _load_graph_result to fall through.

    Both the snapshot loader and CachedDataFetcher are patched to simulate
    a fresh environment with no graph data available.
    """
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path))

    app = Flask(__name__)
    app.testing = True
    app.config["CACHE_MANAGER"] = CacheManager()
    # Deliberately do NOT set SNAPSHOT_GRAPH — forces the loader path.

    app.register_blueprint(discovery_bp)
    return app


# ===========================================================================
# POST /api/subgraph/discover — validation tests
# ===========================================================================

class TestDiscoverValidation:
    """Request validation (400-level errors)."""

    @pytest.mark.unit
    def test_missing_seeds_returns_400(self, discovery_app: Flask) -> None:
        client = discovery_app.test_client()
        resp = client.post("/api/subgraph/discover", json={})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == "VALIDATION_ERROR"
        assert "seeds" in body["details"][0]

    @pytest.mark.unit
    def test_empty_seeds_list_returns_400(self, discovery_app: Flask) -> None:
        client = discovery_app.test_client()
        resp = client.post("/api/subgraph/discover", json={"seeds": []})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == "VALIDATION_ERROR"
        assert any("seeds" in d for d in body["details"])

    @pytest.mark.unit
    def test_seeds_not_a_list_returns_400(self, discovery_app: Flask) -> None:
        client = discovery_app.test_client()
        resp = client.post("/api/subgraph/discover", json={"seeds": "alice"})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == "VALIDATION_ERROR"

    @pytest.mark.unit
    def test_too_many_seeds_returns_400(self, discovery_app: Flask) -> None:
        client = discovery_app.test_client()
        seeds = [f"seed_{i}" for i in range(25)]
        resp = client.post("/api/subgraph/discover", json={"seeds": seeds})
        assert resp.status_code == 400
        body = resp.get_json()
        assert "maximum" in body["details"][0].lower() or "seeds" in body["details"][0].lower()

    @pytest.mark.unit
    def test_non_string_seed_returns_400(self, discovery_app: Flask) -> None:
        client = discovery_app.test_client()
        resp = client.post("/api/subgraph/discover", json={"seeds": [123]})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == "VALIDATION_ERROR"

    @pytest.mark.unit
    def test_seed_too_long_returns_400(self, discovery_app: Flask) -> None:
        client = discovery_app.test_client()
        resp = client.post("/api/subgraph/discover", json={"seeds": ["x" * 51]})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == "VALIDATION_ERROR"
        assert any("long" in d.lower() for d in body["details"])

    @pytest.mark.unit
    def test_non_json_body_returns_400(self, discovery_app: Flask) -> None:
        client = discovery_app.test_client()
        resp = client.post(
            "/api/subgraph/discover",
            data="not json",
            content_type="text/plain",
        )
        # Non-parseable body → silent=True → req_data={} → seeds missing → 400
        assert resp.status_code == 400

    @pytest.mark.unit
    def test_json_array_body_returns_400(self, discovery_app: Flask) -> None:
        """Body must be a JSON *object*, not an array."""
        client = discovery_app.test_client()
        resp = client.post("/api/subgraph/discover", json=["alice"])
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == "VALIDATION_ERROR"
        assert "JSON object" in body["error"]

    @pytest.mark.unit
    def test_invalid_filter_max_distance_returns_400(self, discovery_app: Flask) -> None:
        client = discovery_app.test_client()
        resp = client.post(
            "/api/subgraph/discover",
            json={"seeds": ["alice"], "filters": {"max_distance": 10}},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert any("max_distance" in d for d in body["details"])

    @pytest.mark.unit
    def test_negative_min_overlap_returns_400(self, discovery_app: Flask) -> None:
        client = discovery_app.test_client()
        resp = client.post(
            "/api/subgraph/discover",
            json={"seeds": ["alice"], "filters": {"min_overlap": -1}},
        )
        assert resp.status_code == 400

    @pytest.mark.unit
    def test_negative_max_followers_returns_400(self, discovery_app: Flask) -> None:
        client = discovery_app.test_client()
        resp = client.post(
            "/api/subgraph/discover",
            json={"seeds": ["alice"], "filters": {"max_followers": -5}},
        )
        assert resp.status_code == 400


# ===========================================================================
# POST /api/subgraph/discover — seed resolution tests
# ===========================================================================

class TestDiscoverSeedResolution:
    """Seed resolution: case-insensitive handle matching, @ stripping, missing handles."""

    @pytest.mark.unit
    def test_case_insensitive_username_resolves(self, discovery_app: Flask) -> None:
        """'Alice', 'ALICE', 'alice' should all resolve to acct_001."""
        client = discovery_app.test_client()
        with patch("src.api.routes.discovery.compute_personalized_pagerank", return_value={}):
            with patch("src.api.routes.discovery.discover_subgraph", return_value={"recommendations": []}):
                resp = client.post("/api/subgraph/discover", json={"seeds": ["ALICE"]})
        assert resp.status_code == 200
        body = resp.get_json()
        # Should NOT trigger NO_VALID_SEEDS since ALICE resolves.
        assert body.get("code") != "NO_VALID_SEEDS"

    @pytest.mark.unit
    def test_at_prefix_stripped(self, discovery_app: Flask) -> None:
        """'@alice' should resolve the same as 'alice'."""
        client = discovery_app.test_client()
        with patch("src.api.routes.discovery.compute_personalized_pagerank", return_value={}):
            with patch("src.api.routes.discovery.discover_subgraph", return_value={"recommendations": []}):
                resp = client.post("/api/subgraph/discover", json={"seeds": ["@alice"]})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get("code") != "NO_VALID_SEEDS"

    @pytest.mark.unit
    def test_unknown_handles_return_no_valid_seeds(self, discovery_app: Flask) -> None:
        """All seeds missing from graph → NO_VALID_SEEDS (HTTP 422)."""
        client = discovery_app.test_client()
        resp = client.post("/api/subgraph/discover", json={"seeds": ["nobody", "ghost"]})
        assert resp.status_code == 422
        body = resp.get_json()
        assert body["code"] == "NO_VALID_SEEDS"
        assert set(body["unknown_handles"]) == {"nobody", "ghost"}

    @pytest.mark.unit
    def test_partial_resolution_warns_about_unresolved(self, discovery_app: Flask) -> None:
        """Some seeds resolve, others don't → result includes warnings."""
        client = discovery_app.test_client()
        with patch("src.api.routes.discovery.compute_personalized_pagerank", return_value={}):
            with patch(
                "src.api.routes.discovery.discover_subgraph",
                return_value={"recommendations": []},
            ):
                resp = client.post(
                    "/api/subgraph/discover",
                    json={"seeds": ["alice", "nonexistent"]},
                )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "warnings" in body
        assert any("nonexistent" in w for w in body["warnings"])

    @pytest.mark.unit
    def test_direct_node_id_resolves(self, discovery_app: Flask) -> None:
        """Passing raw account IDs (acct_001) should also resolve."""
        client = discovery_app.test_client()
        with patch("src.api.routes.discovery.compute_personalized_pagerank", return_value={}):
            with patch("src.api.routes.discovery.discover_subgraph", return_value={"recommendations": []}):
                resp = client.post("/api/subgraph/discover", json={"seeds": ["acct_001"]})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get("code") != "NO_VALID_SEEDS"


# ===========================================================================
# POST /api/subgraph/discover — error paths
# ===========================================================================

class TestDiscoverErrorPaths:
    """Internal errors and graph-unavailable scenarios."""

    @pytest.mark.unit
    def test_internal_exception_returns_500(self, discovery_app: Flask) -> None:
        """If discover_subgraph blows up, the route catches it and returns 500."""
        client = discovery_app.test_client()
        with patch(
            "src.api.routes.discovery.compute_personalized_pagerank",
            side_effect=RuntimeError("kaboom"),
        ):
            resp = client.post("/api/subgraph/discover", json={"seeds": ["alice"]})
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["code"] == "INTERNAL_ERROR"
        assert "kaboom" in body["error"]

    @pytest.mark.unit
    def test_graph_not_loaded_falls_through_to_error(
        self, discovery_app_no_graph: Flask, monkeypatch
    ) -> None:
        """When no graph is available and loader returns None, build_graph is called.

        We patch build_graph to raise, simulating the 'no data' scenario.
        """
        client = discovery_app_no_graph.test_client()

        mock_loader = MagicMock()
        mock_loader.load_graph.return_value = None

        with patch(
            "src.api.routes.discovery.snapshot_loader.get_snapshot_loader",
            return_value=mock_loader,
        ):
            with patch(
                "src.api.routes.discovery.build_graph",
                side_effect=Exception("no cache.db"),
            ):
                resp = client.post(
                    "/api/subgraph/discover",
                    json={"seeds": ["alice"]},
                )
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["code"] == "INTERNAL_ERROR"

    @pytest.mark.unit
    def test_cached_result_returned_without_graph_access(self, discovery_app: Flask) -> None:
        """When CacheManager has a cached result, graph loading is skipped entirely."""
        client = discovery_app.test_client()
        cache_mgr: CacheManager = discovery_app.config["CACHE_MANAGER"]

        cached_payload = {"recommendations": [], "meta": {"cache_hit": True}}
        # Pre-populate the cache with the exact key the route will compute.
        import json as _json

        req_body = {"seeds": ["alice"]}
        cache_key = f"discovery:{_json.dumps(req_body, sort_keys=True)}"
        cache_mgr.set_discovery_result(cache_key, cached_payload)

        resp = client.post("/api/subgraph/discover", json=req_body)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["meta"]["cache_hit"] is True


# ===========================================================================
# GET /api/ego-network — placeholder endpoint
# ===========================================================================

class TestEgoNetwork:
    """Tests for the /api/ego-network endpoint."""

    @pytest.mark.unit
    def test_missing_center_id_returns_400(self, discovery_app: Flask) -> None:
        client = discovery_app.test_client()
        resp = client.get("/api/ego-network")
        assert resp.status_code == 400
        body = resp.get_json()
        assert "center_id" in body["error"]

    @pytest.mark.unit
    def test_valid_center_id_returns_200(self, discovery_app: Flask) -> None:
        client = discovery_app.test_client()
        resp = client.get("/api/ego-network?center_id=acct_001")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["center_id"] == "acct_001"
        assert body["radius"] == 1
        assert isinstance(body["nodes"], list)
        assert isinstance(body["links"], list)

    @pytest.mark.unit
    def test_custom_radius(self, discovery_app: Flask) -> None:
        client = discovery_app.test_client()
        resp = client.get("/api/ego-network?center_id=acct_001&radius=3")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["radius"] == 3
