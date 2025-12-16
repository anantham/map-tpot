from __future__ import annotations

import pytest
from flask import Flask

import src.api.cluster_routes as cluster_routes


@pytest.fixture
def cluster_app(monkeypatch, tmp_path) -> Flask:
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(cluster_routes.cluster_bp)

    # Minimal global state for this route.
    monkeypatch.setattr(cluster_routes, "_spectral_result", object(), raising=False)
    monkeypatch.setattr(cluster_routes, "_data_dir", tmp_path, raising=False)
    cluster_routes._tag_store = None

    # Avoid cross-test cache pollution.
    monkeypatch.setattr(cluster_routes, "_cache", cluster_routes.ClusterCache(), raising=False)
    return app


@pytest.mark.unit
def test_cluster_tag_summary_counts_and_suggestion(cluster_app) -> None:
    client = cluster_app.test_client()

    ego = "adityaarpitha"
    cluster_id = "d_123"
    member_ids = ["1", "2", "3"]

    cache_key = cluster_routes._make_cache_key(  # type: ignore[attr-defined]
        11,
        ego,
        set(),
        set(),
        0.0,
        0.5,
        None,
    )
    cluster_routes._cache.set(cache_key, {"clusters": [{"id": cluster_id, "memberIds": member_ids}]})  # type: ignore[attr-defined]

    store = cluster_routes._get_tag_store()  # type: ignore[attr-defined]
    store.upsert_tag(ego=ego, account_id="1", tag="AI alignment", polarity=1)
    store.upsert_tag(ego=ego, account_id="2", tag="AI alignment", polarity=1)
    store.upsert_tag(ego=ego, account_id="2", tag="Gender wars", polarity=-1)

    resp = client.get(
        f"/api/clusters/{cluster_id}/tag_summary?ego={ego}&n=11&budget=25&wl=0.00&expand_depth=0.50"
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["clusterId"] == cluster_id
    assert payload["ego"] == ego
    assert payload["totalMembers"] == 3
    assert payload["taggedMembers"] == 2
    assert payload["tagAssignments"] == 3

    counts = {row["tag"]: row for row in payload["tagCounts"]}
    assert counts["AI alignment"]["inCount"] == 2
    assert counts["AI alignment"]["notInCount"] == 0
    assert counts["AI alignment"]["score"] == 2
    assert counts["Gender wars"]["inCount"] == 0
    assert counts["Gender wars"]["notInCount"] == 1
    assert counts["Gender wars"]["score"] == -1

    assert payload["suggestedLabel"]["tag"] == "AI alignment"
    assert payload["suggestedLabel"]["score"] > 0


@pytest.mark.unit
def test_cluster_tag_summary_requires_ego(cluster_app) -> None:
    client = cluster_app.test_client()
    resp = client.get("/api/clusters/d_1/tag_summary")
    assert resp.status_code == 400

