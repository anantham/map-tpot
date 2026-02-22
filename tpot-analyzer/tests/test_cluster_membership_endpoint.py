from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
from flask import Flask
from scipy import sparse

import src.api.cluster_routes as cluster_routes
from src.api.cluster_routes import ClusterCache, cluster_bp
from src.data.account_tags import AccountTagStore


@dataclass
class _MockSpectralResult:
    node_ids: np.ndarray
    embedding: np.ndarray
    micro_labels: np.ndarray
    micro_centroids: np.ndarray
    linkage_matrix: np.ndarray


@pytest.fixture
def membership_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Flask:
    app = Flask(__name__)
    app.register_blueprint(cluster_bp)
    app.config["TESTING"] = True

    node_ids = np.array(["node_0", "node_1", "node_2"], dtype=object)
    adjacency = sparse.csr_matrix(
        [
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 1.0],
            [0.0, 1.0, 0.0],
        ]
    )
    spectral = _MockSpectralResult(
        node_ids=node_ids,
        embedding=np.zeros((3, 2), dtype=np.float64),
        micro_labels=np.array([0, 1, 2]),
        micro_centroids=np.zeros((3, 2), dtype=np.float64),
        linkage_matrix=np.array([[0.0, 1.0, 0.0, 2.0], [2.0, 3.0, 0.0, 3.0]], dtype=np.float64),
    )
    metadata = {
        "node_0": {"username": "pos_anchor", "num_following": 10},
        "node_1": {"username": "candidate", "num_following": 10},
        "node_2": {"username": "neg_anchor", "num_following": 10},
    }
    tag_store = AccountTagStore(tmp_path / "account_tags.db")

    monkeypatch.setattr(cluster_routes, "_spectral_result", spectral, raising=False)
    monkeypatch.setattr(cluster_routes, "_adjacency", adjacency, raising=False)
    monkeypatch.setattr(cluster_routes, "_node_metadata", metadata, raising=False)
    monkeypatch.setattr(cluster_routes, "_node_id_to_idx", {str(v): i for i, v in enumerate(node_ids)}, raising=False)
    monkeypatch.setattr(cluster_routes, "_graph_settings", {"membership_engine": "grf"}, raising=False)
    monkeypatch.setattr(cluster_routes, "_tag_store", tag_store, raising=False)
    monkeypatch.setattr(cluster_routes, "_membership_cache", ClusterCache(), raising=False)
    return app


def test_membership_endpoint_rejects_when_engine_disabled(
    membership_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cluster_routes, "_graph_settings", {"membership_engine": "off"}, raising=False)
    client = membership_app.test_client()
    resp = client.get("/api/clusters/accounts/node_1/membership?ego=ego1")
    assert resp.status_code == 400
    assert "membership_engine" in resp.get_json()["error"]


def test_membership_endpoint_requires_positive_and_negative_anchors(
    membership_app: Flask,
) -> None:
    tag_store = cluster_routes._tag_store
    assert tag_store is not None
    tag_store.upsert_tag(ego="ego1", account_id="node_0", tag="tpot", polarity=1)

    client = membership_app.test_client()
    resp = client.get("/api/clusters/accounts/node_1/membership?ego=ego1")
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["anchorCounts"]["positive"] == 1
    assert payload["anchorCounts"]["negative"] == 0


def test_membership_endpoint_returns_probability_and_uses_cache(
    membership_app: Flask,
) -> None:
    tag_store = cluster_routes._tag_store
    assert tag_store is not None
    tag_store.upsert_tag(ego="ego1", account_id="node_0", tag="tpot", polarity=1)
    tag_store.upsert_tag(ego="ego1", account_id="node_2", tag="not_tpot", polarity=-1)

    client = membership_app.test_client()
    first = client.get("/api/clusters/accounts/node_1/membership?ego=ego1")
    assert first.status_code == 200
    first_payload = first.get_json()
    assert first_payload["engine"] == "grf"
    assert 0.0 <= first_payload["probability"] <= 1.0
    assert first_payload["cacheHit"] is False
    assert first_payload["anchorCounts"]["positive"] == 1
    assert first_payload["anchorCounts"]["negative"] == 1

    second = client.get("/api/clusters/accounts/node_1/membership?ego=ego1")
    assert second.status_code == 200
    second_payload = second.get_json()
    assert second_payload["cacheHit"] is True
