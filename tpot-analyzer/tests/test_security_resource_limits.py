"""Test intent: bounded cache bytes/count/TTL, feedback quota/expiry, rotating
logs, and graph-work admission must hold using only synthetic temporary data.
"""
from __future__ import annotations

import sqlite3
from threading import Event

import pytest
from flask import Flask

from src.api.log_routes import log_bp
from src.api.security_policy import WorkloadGate, install_security_policy
from src.api.services.analysis_manager import AnalysisManager
from src.api.services.cache_manager import CacheManager
from src.api.services.signal_feedback_store import SignalFeedbackStore


def test_cache_evicts_lru_and_rejects_oversized_items():
    cache = CacheManager(discovery_entries=2, graph_entries=1, max_bytes=256)
    cache.set_discovery_result("first", "a")
    cache.set_discovery_result("second", "b")
    assert cache.get_discovery_result("first") == "a"
    cache.set_discovery_result("third", "c")
    assert cache.get_discovery_result("second") is None
    assert cache.discovery_cache_size() == 2
    assert cache.set_graph_response("huge", "x" * 257) is False
    assert cache.graph_cache_size() == 0


def test_cache_expires_without_a_new_write(monkeypatch):
    import src.api.services.bounded_cache as module
    clock = [10.0]
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    cache = CacheManager(ttl_seconds=2)
    cache.set_graph_response("one", "cached")
    clock[0] = 12.0
    assert cache.get_graph_response("one") is None
    assert cache.graph_cache_size() == 0


def _feedback(store, account="synthetic"):
    store.add_feedback(account_id=account, signal_name="fixture", score=.5, user_label="tpot")


def test_feedback_quota_is_transactional_across_store_instances(tmp_path):
    path = tmp_path / "feedback.db"
    first = SignalFeedbackStore(path, max_events=1)
    second = SignalFeedbackStore(path, max_events=1)
    _feedback(first)
    with pytest.raises(OverflowError):
        _feedback(second, "rejected")
    assert SignalFeedbackStore(path, max_events=1).event_count() == 1


def test_new_feedback_expiry_preserves_legacy_rows(tmp_path, monkeypatch):
    import src.api.services.signal_feedback_store as module
    path = tmp_path / "feedback.db"
    clock = [100.0]
    monkeypatch.setattr(module, "time", lambda: clock[0])
    store = SignalFeedbackStore(path, max_events=2, retention_seconds=10)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO feedback_events(account_id,signal_name,score,user_label,context,timestamp) VALUES('legacy','fixture',.5,'tpot','{}',1)")
    _feedback(store)
    clock[0] = 111.0
    assert store.event_count() == 1
    assert store.quality_report()["fixture"]["total_feedback"] == 1
    _feedback(store, "replacement")
    with sqlite3.connect(path) as conn:
        rows = conn.execute("SELECT account_id FROM feedback_events ORDER BY id").fetchall()
    assert rows == [("legacy",), ("replacement",)]
    assert store.event_count() == 2


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -1, 2])
def test_feedback_nonfinite_or_out_of_range_rejected(tmp_path, score):
    store = SignalFeedbackStore(tmp_path / "feedback.db")
    with pytest.raises(ValueError):
        store.add_feedback(account_id="synthetic", signal_name="fixture", score=score, user_label="tpot")
    assert store.event_count() == 0


def test_workload_admission_released_after_error_and_background_completion(monkeypatch, tmp_path):
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", "fixture")
    gate = WorkloadGate(lock_root=tmp_path)
    app = Flask(__name__)
    install_security_policy(app, gate)
    app.add_url_rule("/api/compute", endpoint="discovery.discover", view_func=lambda: ("failure", 500))
    client = app.test_client()
    headers = {"X-TPOT-Curator-Token": "fixture"}
    assert gate.acquire()
    assert client.get("/api/compute", headers=headers).status_code == 429
    gate.release()
    assert client.get("/api/compute", headers=headers).status_code == 500
    assert gate.acquire()
    gate.release()
    done = Event()
    manager = AnalysisManager(workload_gate=gate)
    assert manager.start_analysis(lambda _: done.wait(2))
    try:
        assert client.get("/api/compute", headers=headers).status_code == 429
    finally:
        done.set()
        manager._thread.join(2)
    assert client.get("/api/compute", headers=headers).status_code == 500


def test_frontend_log_rotation_has_finite_disk_ceiling(tmp_path, monkeypatch):
    import src.api.log_routes as module
    monkeypatch.setattr(module, "LOG_FILE", tmp_path / "frontend.log")
    monkeypatch.setattr(module, "MAX_LOG_FILE_BYTES", 400)
    monkeypatch.setattr(module, "LOG_BACKUPS", 2)
    app = Flask(__name__)
    app.register_blueprint(log_bp)
    client = app.test_client()
    for _ in range(20):
        assert client.post("/api/log", json={"message": "x" * 100}).status_code == 200
    files = list(tmp_path.glob("frontend.log*"))
    assert len(files) == 3
    assert all(path.stat().st_size <= 400 for path in files)


def test_cache_snapshots_do_not_allow_later_mutation_to_bypass_byte_caps():
    cache = CacheManager(max_bytes=1024)
    payload = {"items": []}
    cache.set_discovery_result("fixture", payload)
    payload["items"].append("x" * 4096)
    assert cache.get_discovery_result("fixture") == {"items": []}
    read = cache.get_discovery_result("fixture")
    read["items"].append("x" * 4096)
    assert cache.get_discovery_result("fixture") == {"items": []}


def test_discovery_neighborhood_hard_cap_is_enforced():
    import networkx as nx
    from src.api.discovery import extract_subgraph
    graph = nx.DiGraph()
    for branch in range(100):
        child = f"child-{branch}"
        graph.add_edge("synthetic-root", child)
        for leaf in range(100):
            graph.add_edge(child, f"leaf-{branch}-{leaf}")
    subgraph, candidates = extract_subgraph(graph, ["synthetic-root"])
    assert subgraph.number_of_nodes() == 5000
    assert len(candidates) == 4999
