"""Admission intent through public HTTP APIs with synthetic graph/store fixtures:
- Every hierarchy/GRF/whole-graph scan route shares the process-wide slot pool.
- Cold/warm caches and automatic HEAD aliases cannot bypass busy admission.
- Auth precedes admission; ordinary private reads and health remain available.
- Completion releases the lease and restores successful authenticated reads.
"""
from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse
from scipy.cluster.hierarchy import linkage

from src.api.cluster import ClusterCache
from src.api.cluster import state
from src.api.server import create_app
from src.data.account_tags import AccountTagStore

AUTH = {"X-TPOT-Curator-Token": "synthetic-admission-token"}


def _synthetic_state(root, setter=setattr):
    centroids = np.array([[0, 0], [1, 0], [0, 2], [2, 2], [3, 1], [4, 4]], dtype=float)
    node_ids = np.array([f"node_{i}" for i in range(6)])
    spectral = SimpleNamespace(node_ids=node_ids, embedding=centroids,
                               micro_labels=np.arange(6), micro_centroids=centroids,
                               linkage_matrix=linkage(centroids, method="ward"))
    adjacency = sparse.diags([np.ones(5), np.ones(5)], [-1, 1], shape=(6, 6), format="csr")
    store = AccountTagStore(Path(root) / "synthetic-tags.db")
    store.upsert_tag(ego="fixture", account_id="node_0", tag="tpot", polarity=1)
    store.upsert_tag(ego="fixture", account_id="node_5", tag="not_tpot", polarity=-1)
    values = {
        "_spectral_result": spectral, "_adjacency": adjacency,
        "_node_metadata": {str(n): {"username": str(n), "num_following": 5} for n in node_ids},
        "_node_id_to_idx": {str(n): i for i, n in enumerate(node_ids)},
        "_cache": ClusterCache(), "_membership_cache": ClusterCache(),
        "_tag_store": store, "_label_store": None, "_louvain_communities": {},
        "_graph_settings": {"membership_engine": "grf"}, "_tpot_spectral": None,
        "_spectral_presets": {}, "_alpha_presets": [], "_available_lenses": ["full"],
    }
    for name, value in values.items():
        setter(state, name, value)


def _paths(cluster_id):
    suffix = "?n=5&budget=10&ego=fixture"
    return [
        "/api/clusters" + suffix,
        f"/api/clusters/{cluster_id}/members" + suffix,
        f"/api/clusters/{cluster_id}/tag_summary" + suffix,
        "/api/clusters/accounts/node_1/membership?ego=fixture",
        f"/api/clusters/{cluster_id}/preview?n=5&budget=10",
        "/api/accounts/node_1/teleport_plan?budget=10&visible=5",
        "/api/accounts/search?q=node&limit=2",
    ]


@pytest.fixture
def analyst_app(temp_snapshot_dir, monkeypatch):
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", AUTH["X-TPOT-Curator-Token"])
    monkeypatch.setattr("src.api.server.init_cluster_routes", lambda _: None)
    _synthetic_state(temp_snapshot_dir, monkeypatch.setattr)
    app = create_app({"TESTING": True})
    response = app.test_client().get("/api/clusters?n=5&budget=10&ego=fixture", headers=AUTH)
    assert response.status_code == 200
    cluster_id = response.get_json()["clusters"][0]["id"]
    return app, _paths(cluster_id), temp_snapshot_dir


def _hold_http_hierarchy(root, started, release, results):
    """An independent Flask worker holds its lease while building a tiny view."""
    import src.api.server as server
    import src.api.cluster.views as views
    os.environ["SNAPSHOT_DIR"] = str(root)
    os.environ["TPOT_LOG_DIR"] = str(Path(root) / "worker-logs")
    os.environ["TPOT_CURATOR_TOKEN"] = AUTH["X-TPOT-Curator-Token"]
    server.init_cluster_routes = lambda _: None
    _synthetic_state(root)
    app = server.create_app({"TESTING": True})
    original = views.build_hierarchical_view
    def blocked(**kwargs):
        started.set()
        if not release.wait(15):
            raise RuntimeError("synthetic worker release timed out")
        return original(**kwargs)
    views.build_hierarchical_view = blocked
    response = app.test_client().get("/api/clusters?n=5&budget=10", headers=AUTH)
    results.put((response.status_code, response.get_json()))


@pytest.mark.parametrize("warm", [False, True], ids=["cold-cache", "warm-cache"])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_all_hierarchy_aliases_share_cross_process_admission(analyst_app, monkeypatch, warm, method):
    app, paths, root = analyst_app
    client = app.test_client()
    if warm:
        for path in paths:
            assert client.get(path, headers=AUTH).status_code == 200
        assert client.get(paths[0], headers=AUTH).get_json()["cache_hit"] is True
        assert client.get(paths[3], headers=AUTH).get_json()["cacheHit"] is True
    else:
        monkeypatch.setattr(state, "_cache", ClusterCache())
        monkeypatch.setattr(state, "_membership_cache", ClusterCache())
    ctx = mp.get_context("spawn")
    started, release, results = ctx.Event(), ctx.Event(), ctx.Queue()
    worker = ctx.Process(target=_hold_http_hierarchy, args=(str(root), started, release, results))
    worker.start()
    try:
        assert started.wait(10), "synthetic HTTP worker did not enter its hierarchy build"
        responses = []
        for path in paths:
            if not warm:
                monkeypatch.setattr(state, "_cache", ClusterCache())
                monkeypatch.setattr(state, "_membership_cache", ClusterCache())
            responses.append(client.open(path, method=method, headers=AUTH))
        assert [r.status_code for r in responses] == [429] * len(paths)
        if method == "GET":
            assert all("capacity busy" in r.get_json()["error"] for r in responses)
        assert client.get(paths[1]).status_code == 401
        assert client.get("/api/accounts/node_1", headers=AUTH).status_code == 200
        assert client.get("/api/health").status_code == 200
        assert all(client.options(path).status_code == 200 for path in paths)
    finally:
        release.set()
        worker.join(10)
        if worker.is_alive():
            worker.terminate()
            worker.join()
    assert worker.exitcode == 0
    status, payload = results.get(timeout=5)
    assert status == 200 and payload["clusters"]
    for path in paths:
        assert client.get(path, headers=AUTH).status_code == 200


def test_coordination_failure_is_closed_for_hierarchy_aliases(analyst_app):
    app, paths, root = analyst_app
    root.chmod(0o777)
    try:
        responses = [app.test_client().get(path, headers=AUTH) for path in paths]
        assert [r.status_code for r in responses] == [503] * len(paths)
        assert all("coordination unavailable" in r.get_json()["error"] for r in responses)
    finally:
        root.chmod(0o700)
