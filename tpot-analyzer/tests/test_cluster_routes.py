"""Tests for src/api/cluster_routes.py - Flask cluster API endpoints.

These tests verify:
1. Endpoint behavior (request/response contracts)
2. Parameter validation and bounds checking
3. Cache behavior (LRU + TTL)
4. Error handling for uninitialized state
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from flask import Flask
from scipy import sparse
from scipy.cluster.hierarchy import linkage

from src.api.cluster_routes import (
    ClusterCache,
    CacheEntry,
    _make_cache_key,
    _safe_int,
    _serialize_hierarchical_view,
    cluster_bp,
)
from src.graph.clusters import ClusterLabelStore
from src.graph.hierarchy.models import (
    HierarchicalCluster,
    HierarchicalEdge,
    HierarchicalViewData,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def app():
    """Create Flask test app with cluster blueprint."""
    app = Flask(__name__)
    app.register_blueprint(cluster_bp)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def mock_spectral_result():
    """Mock spectral clustering result."""
    n_micro = 4
    n_nodes = 8
    micro_centroids = np.array([
        [0.0, 0.0],
        [1.0, 0.0],
        [0.0, 1.0],
        [1.0, 1.0],
    ])

    @dataclass
    class MockSpectralResult:
        node_ids: np.ndarray
        embedding: np.ndarray
        micro_labels: np.ndarray
        micro_centroids: np.ndarray
        linkage_matrix: np.ndarray

    return MockSpectralResult(
        node_ids=np.array([f"node_{i}" for i in range(n_nodes)]),
        embedding=np.random.randn(n_nodes, 2),
        micro_labels=np.repeat(np.arange(n_micro), 2),
        micro_centroids=micro_centroids,
        linkage_matrix=linkage(micro_centroids, method="ward"),
    )


@pytest.fixture
def mock_adjacency():
    """Mock adjacency matrix."""
    return sparse.csr_matrix((8, 8))


@pytest.fixture
def mock_node_metadata():
    """Mock node metadata."""
    return {
        f"node_{i}": {
            "username": f"user_{i}",
            "display_name": f"User {i}",
            "num_followers": i * 100,
        }
        for i in range(8)
    }


def _make_mock_view(n_clusters: int = 2) -> HierarchicalViewData:
    """Create a mock HierarchicalViewData for testing."""
    clusters = []
    for i in range(n_clusters):
        clusters.append(HierarchicalCluster(
            id=f"d_{i}",
            dendrogram_node=i,
            parent_id=None,
            children_ids=None,
            member_micro_indices=[i],
            member_node_ids=[f"node_{i * 2}", f"node_{i * 2 + 1}"],
            centroid=np.array([float(i), 0.0]),
            size=2,
            label=f"Cluster {i}",
            label_source="auto",
            representative_handles=[f"user_{i * 2}"],
            contains_ego=i == 0,
            is_leaf=True,
        ))

    edges = [
        HierarchicalEdge(
            source_id="d_0",
            target_id="d_1",
            raw_count=5,
            connectivity=0.5,
        )
    ] if n_clusters >= 2 else []

    return HierarchicalViewData(
        clusters=clusters,
        edges=edges,
        ego_cluster_id="d_0",
        total_nodes=n_clusters * 2,
        n_micro_clusters=n_clusters,
        positions={f"d_{i}": [float(i), 0.0] for i in range(n_clusters)},
        expanded_ids=[],
        collapsed_ids=[],
        budget=25,
        budget_remaining=25 - n_clusters,
    )


# =============================================================================
# ClusterCache Tests
# =============================================================================

class TestClusterCache:
    """Tests for the LRU + TTL cache."""

    def test_get_returns_none_for_missing_key(self):
        """Missing key returns None."""
        cache = ClusterCache()
        assert cache.get(("nonexistent",)) is None

    def test_set_and_get_retrieves_value(self):
        """Set then get returns the value."""
        cache = ClusterCache()
        key = ("test", "key")
        value = {"data": "test"}

        cache.set(key, value)
        assert cache.get(key) == value

    def test_ttl_expires_old_entries(self):
        """Entries older than TTL are not returned."""
        cache = ClusterCache(ttl_seconds=1)
        key = ("test",)
        cache.set(key, {"data": "old"})

        # Artificially age the entry
        cache._entries[key] = CacheEntry(
            created_at=time.time() - 2,  # 2 seconds ago
            view={"data": "old"}
        )

        assert cache.get(key) is None

    def test_lru_eviction(self):
        """Oldest entries evicted when max_entries exceeded."""
        cache = ClusterCache(max_entries=2)

        cache.set(("a",), {"a": 1})
        cache.set(("b",), {"b": 2})
        cache.set(("c",), {"c": 3})  # Should evict "a"

        assert cache.get(("a",)) is None
        assert cache.get(("b",)) is not None
        assert cache.get(("c",)) is not None

    def test_get_refreshes_lru_order(self):
        """Getting an entry moves it to end (prevents eviction)."""
        cache = ClusterCache(max_entries=2)

        cache.set(("a",), {"a": 1})
        cache.set(("b",), {"b": 2})
        cache.get(("a",))  # Refresh "a"
        cache.set(("c",), {"c": 3})  # Should evict "b" (oldest now)

        assert cache.get(("a",)) is not None
        assert cache.get(("b",)) is None
        assert cache.get(("c",)) is not None

    def test_inflight_tracking(self):
        """Inflight futures can be tracked."""
        cache = ClusterCache()
        key = ("test",)
        future = MagicMock()

        cache.inflight_set(key, future)
        assert cache.inflight_get(key) is future

        cache.inflight_clear(key)
        assert cache.inflight_get(key) is None


# =============================================================================
# Helper Function Tests
# =============================================================================

class TestSafeInt:
    """Tests for _safe_int helper."""

    def test_none_returns_default(self):
        assert _safe_int(None) == 0
        assert _safe_int(None, default=42) == 42

    def test_nan_returns_default(self):
        assert _safe_int(float("nan")) == 0

    def test_valid_int_returns_int(self):
        assert _safe_int(42) == 42
        assert _safe_int(42.9) == 42

    def test_string_returns_default(self):
        assert _safe_int("not a number") == 0


class TestMakeCacheKey:
    """Tests for cache key generation."""

    def test_consistent_key_for_same_params(self):
        """Same parameters produce same key."""
        key1 = _make_cache_key(25, "ego", {"d_0", "d_1"})
        key2 = _make_cache_key(25, "ego", {"d_1", "d_0"})  # Different order
        assert key1 == key2

    def test_different_params_different_keys(self):
        """Different parameters produce different keys."""
        key1 = _make_cache_key(25, "ego1", set())
        key2 = _make_cache_key(25, "ego2", set())
        assert key1 != key2

    def test_none_ego_handled(self):
        """None ego doesn't crash."""
        key = _make_cache_key(25, None, set())
        assert key[1] == ""


class TestSerializeHierarchicalView:
    """Tests for view serialization."""

    def test_serializes_clusters(self):
        """Clusters are serialized correctly."""
        view = _make_mock_view(2)
        payload = _serialize_hierarchical_view(view)

        assert "clusters" in payload
        assert len(payload["clusters"]) == 2

        cluster = payload["clusters"][0]
        assert "id" in cluster
        assert "size" in cluster
        assert "label" in cluster
        assert "memberIds" in cluster

    def test_serializes_edges(self):
        """Edges are serialized with opacity."""
        view = _make_mock_view(2)
        payload = _serialize_hierarchical_view(view)

        assert "edges" in payload
        assert len(payload["edges"]) == 1

        edge = payload["edges"][0]
        assert "source" in edge
        assert "target" in edge
        assert "rawCount" in edge
        assert "opacity" in edge
        assert 0 <= edge["opacity"] <= 1

    def test_serializes_metadata(self):
        """Meta fields are included."""
        view = _make_mock_view(2)
        payload = _serialize_hierarchical_view(view)

        assert "meta" in payload
        assert "budget" in payload["meta"]
        assert "budget_remaining" in payload["meta"]

    def test_handles_empty_edges(self):
        """Empty edge list doesn't crash."""
        view = _make_mock_view(1)  # Single cluster = no edges
        payload = _serialize_hierarchical_view(view)
        assert payload["edges"] == []


# =============================================================================
# Endpoint Tests (with mocked global state)
# =============================================================================

class TestGetClustersEndpoint:
    """Tests for GET /api/clusters."""

    def test_503_when_not_initialized(self, client):
        """Returns 503 when spectral data not loaded."""
        with patch("src.api.cluster_routes._spectral_result", None):
            resp = client.get("/api/clusters")
            assert resp.status_code == 503
            assert "error" in resp.get_json()

    def test_returns_clusters_when_initialized(
        self, client, mock_spectral_result, mock_adjacency, mock_node_metadata
    ):
        """Returns cluster data when properly initialized."""
        with patch("src.api.cluster_routes._spectral_result", mock_spectral_result), \
             patch("src.api.cluster_routes._adjacency", mock_adjacency), \
             patch("src.api.cluster_routes._node_metadata", mock_node_metadata), \
             patch("src.api.cluster_routes._label_store", None), \
             patch("src.api.cluster_routes._louvain_communities", {}), \
             patch("src.api.cluster_routes._cache", ClusterCache()):

            resp = client.get("/api/clusters?n=2&budget=10")
            assert resp.status_code == 200

            data = resp.get_json()
            assert "clusters" in data
            assert "edges" in data
            assert "positions" in data

    def test_granularity_bounded(self, client, mock_spectral_result, mock_adjacency, mock_node_metadata):
        """Granularity parameter is bounded to valid range."""
        with patch("src.api.cluster_routes._spectral_result", mock_spectral_result), \
             patch("src.api.cluster_routes._adjacency", mock_adjacency), \
             patch("src.api.cluster_routes._node_metadata", mock_node_metadata), \
             patch("src.api.cluster_routes._label_store", None), \
             patch("src.api.cluster_routes._louvain_communities", {}), \
             patch("src.api.cluster_routes._cache", ClusterCache()):

            # Very low granularity gets bounded to 5
            resp = client.get("/api/clusters?n=1&budget=10")
            assert resp.status_code == 200

            # Very high granularity gets bounded to 500
            resp = client.get("/api/clusters?n=9999&budget=10")
            assert resp.status_code == 200

    def test_cache_hit_returns_cached(
        self, client, mock_spectral_result, mock_adjacency, mock_node_metadata
    ):
        """Second request with same params returns cached result."""
        cache = ClusterCache()

        with patch("src.api.cluster_routes._spectral_result", mock_spectral_result), \
             patch("src.api.cluster_routes._adjacency", mock_adjacency), \
             patch("src.api.cluster_routes._node_metadata", mock_node_metadata), \
             patch("src.api.cluster_routes._label_store", None), \
             patch("src.api.cluster_routes._louvain_communities", {}), \
             patch("src.api.cluster_routes._cache", cache):

            # First request - builds view
            resp1 = client.get("/api/clusters?n=2&budget=10")
            assert resp1.status_code == 200
            data1 = resp1.get_json()

            # Second request - should hit cache
            resp2 = client.get("/api/clusters?n=2&budget=10")
            assert resp2.status_code == 200
            data2 = resp2.get_json()

            assert data2.get("cache_hit") is True
            assert data1["clusters"] == data2["clusters"]
            assert data1["edges"] == data2["edges"]
            assert data1["positions"] == data2["positions"]
            assert data1["meta"]["budget"] == data2["meta"]["budget"]


class TestGetClusterMembersEndpoint:
    """Tests for GET /api/clusters/<id>/members."""

    def test_503_when_not_initialized(self, client):
        """Returns 503 when spectral data not loaded."""
        with patch("src.api.cluster_routes._spectral_result", None):
            resp = client.get("/api/clusters/d_0/members")
            assert resp.status_code == 503

    def test_returns_members_list(
        self, client, mock_spectral_result, mock_adjacency, mock_node_metadata
    ):
        """Returns paginated members list."""
        cache = ClusterCache()

        with patch("src.api.cluster_routes._spectral_result", mock_spectral_result), \
             patch("src.api.cluster_routes._adjacency", mock_adjacency), \
             patch("src.api.cluster_routes._node_metadata", mock_node_metadata), \
             patch("src.api.cluster_routes._label_store", None), \
             patch("src.api.cluster_routes._louvain_communities", {}), \
             patch("src.api.cluster_routes._node_id_to_idx", {}), \
             patch("src.api.cluster_routes._cache", cache):

            cluster_resp = client.get("/api/clusters?n=2&budget=10")
            assert cluster_resp.status_code == 200
            cluster_data = cluster_resp.get_json()
            cluster_id = cluster_data["clusters"][0]["id"]

            resp = client.get(f"/api/clusters/{cluster_id}/members?n=2&budget=10")
            assert resp.status_code == 200

            data = resp.get_json()
            assert "members" in data
            assert "total" in data
            assert "hasMore" in data


class TestClusterLabelEndpoints:
    """Tests for POST/DELETE /api/clusters/<id>/label."""

    def test_post_label_503_when_no_store(self, client):
        """Returns 503 when label store not initialized."""
        with patch("src.api.cluster_routes._label_store", None):
            resp = client.post(
                "/api/clusters/d_0/label",
                json={"label": "Test Label"}
            )
            assert resp.status_code == 503

    def test_post_label_400_when_empty(self, client, tmp_path):
        """Returns 400 when label is empty."""
        store = ClusterLabelStore(tmp_path / "clusters.db")
        with patch("src.api.cluster_routes._label_store", store):
            resp = client.post(
                "/api/clusters/d_0/label",
                json={"label": "   "}
            )
            assert resp.status_code == 400

    def test_post_label_success(self, client, tmp_path):
        """Successfully sets cluster label."""
        store = ClusterLabelStore(tmp_path / "clusters.db")
        with patch("src.api.cluster_routes._label_store", store):
            resp = client.post(
                "/api/clusters/d_0/label",
                json={"label": "My Label"}
            )
            assert resp.status_code == 200

            data = resp.get_json()
            assert data["label"] == "My Label"
            assert data["labelSource"] == "user"
            labels = store.get_all_labels()
            assert labels.get("spectral_d_0") == "My Label"

    def test_delete_label_success(self, client, tmp_path):
        """Successfully deletes cluster label."""
        store = ClusterLabelStore(tmp_path / "clusters.db")
        store.set_label("spectral_d_0", "My Label")
        with patch("src.api.cluster_routes._label_store", store):
            resp = client.delete("/api/clusters/d_0/label")
            assert resp.status_code == 200
            labels = store.get_all_labels()
            assert "spectral_d_0" not in labels


class TestPreviewEndpoint:
    """Tests for GET /api/clusters/<id>/preview."""

    def test_503_when_not_initialized(self, client):
        """Returns 503 when spectral data not loaded."""
        with patch("src.api.cluster_routes._spectral_result", None):
            resp = client.get("/api/clusters/d_0/preview")
            assert resp.status_code == 503

    def test_returns_expand_and_collapse_previews(
        self, client, mock_spectral_result
    ):
        """Returns both expand and collapse preview data."""
        with patch("src.api.cluster_routes._spectral_result", mock_spectral_result), \
             patch("src.api.cluster_routes._cache", ClusterCache()):

            resp = client.get("/api/clusters/d_4/preview?n=2&budget=10")
            assert resp.status_code == 200

            data = resp.get_json()
            assert "expand" in data
            assert "collapse" in data
            assert "can_expand" in data["expand"]
            assert "can_collapse" in data["collapse"]


class TestTagSummaryEndpoint:
    """Tests for GET /api/clusters/<id>/tag_summary."""

    def test_503_when_not_initialized(self, client):
        """Returns 503 when spectral data not loaded."""
        with patch("src.api.cluster_routes._spectral_result", None):
            resp = client.get("/api/clusters/d_0/tag_summary")
            assert resp.status_code == 503

    def test_400_when_ego_missing(self, client, mock_spectral_result):
        """Returns 400 when ego parameter is missing."""
        with patch("src.api.cluster_routes._spectral_result", mock_spectral_result):
            resp = client.get("/api/clusters/d_0/tag_summary")
            assert resp.status_code == 400
            assert "ego" in resp.get_json().get("error", "").lower()
