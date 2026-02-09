"""Routes for analysis jobs and metrics."""
from __future__ import annotations

import logging
import time
from flask import Blueprint, jsonify, request, current_app

from src.api.services.analysis_manager import AnalysisManager
from src.api.services.cache_manager import CacheManager
from src.api.services.signal_feedback_store import SignalFeedbackStore
from src.graph import (
    compute_betweenness,
    compute_louvain_communities,
    compute_personalized_pagerank,
    compute_engagement_scores,
    normalize_scores,
    load_seed_candidates,
    get_seed_state,
)
from src.config import get_snapshot_dir
from src.data.fetcher import CachedDataFetcher
from src.graph import build_graph

logger = logging.getLogger(__name__)

analysis_bp = Blueprint("analysis", __name__, url_prefix="/api")


@analysis_bp.route("/metrics/compute", methods=["POST"])
def compute_metrics():
    """Compute graph metrics (PageRank, etc.) dynamically based on weights.
    
    Payload:
    {
        "seeds": ["user1", "user2"],
        "weights": [0.4, 0.3, 0.3],  # [PageRank, Betweenness, Engagement]
        "alpha": 0.85,
        "include_shadow": true,
        "mutual_only": false
    }
    """
    data = request.json
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    seeds = data.get("seeds", [])
    weights = data.get("weights", [0.4, 0.3, 0.3]) # PR, BT, ENG
    alpha = float(data.get("alpha", 0.85))
    
    # Optional graph filters
    include_shadow = data.get("include_shadow", True)
    mutual_only = data.get("mutual_only", False)
    min_followers = int(data.get("min_followers", 0))

    # 1. Build/Load Graph (this is fast if cached in memory/disk)
    snapshot_dir = get_snapshot_dir()
    fetcher = CachedDataFetcher(cache_db=snapshot_dir / "cache.db")
    
    graph_result = build_graph(
        fetcher=fetcher,
        include_shadow=include_shadow,
        mutual_only=mutual_only,
        min_followers=min_followers
    )
    G = graph_result.directed
    
    # 2. Compute/Load Metrics
    # PageRank (Dynamic based on seeds)
    pr_scores = compute_personalized_pagerank(G, seeds=seeds, alpha=alpha)
    
    # Betweenness (Static/Cached typically, but computed here for now)
    bt_scores = compute_betweenness(G, sample_size=100) # Approx
    
    # Engagement (Static)
    eng_scores = compute_engagement_scores(G)
    
    # Communities (Static)
    communities = compute_louvain_communities(G)

    # 3. Composite Score
    pr_norm = normalize_scores(pr_scores)
    bt_norm = normalize_scores(bt_scores)
    eg_norm = normalize_scores(eng_scores)
    alpha, beta, gamma = weights
    composite_scores = {
        node: (
            alpha * pr_norm.get(node, 0.0)
            + beta * bt_norm.get(node, 0.0)
            + gamma * eg_norm.get(node, 0.0)
        )
        for node in pr_norm
    }

    # 4. Format Response
    response = {
        "seeds": seeds,
        "resolved_seeds": [s for s in seeds if s in G],
        "metrics": {
            "pagerank": pr_scores,
            "betweenness": bt_scores,
            "engagement": eng_scores,
            "composite": composite_scores,
            "communities": communities
        },
        "top": sorted(
            [{"id": n, "score": s} for n, s in composite_scores.items()],
            key=lambda x: x["score"], 
            reverse=True
        )[:50]
    }
    
    return jsonify(response)


@analysis_bp.route("/metrics/presets", methods=["GET"])
def get_presets():
    """Get seed presets."""
    candidates = load_seed_candidates()
    # Return as dict for extensibility and to match test expectation
    return jsonify({"candidates": list(candidates)})


@analysis_bp.route("/metrics/performance", methods=["GET"])
def get_performance_metrics():
    """Return lightweight backend performance diagnostics for UI status panels."""
    analysis_manager: AnalysisManager = current_app.config["ANALYSIS_MANAGER"]
    cache_manager: CacheManager = current_app.config["CACHE_MANAGER"]
    start_time = float(current_app.config.get("STARTUP_TIME", time.time()))
    uptime_seconds = max(0.0, time.time() - start_time)
    return jsonify(
        {
            "uptime_seconds": round(uptime_seconds, 3),
            "analysis_status": analysis_manager.get_status().get("status", "unknown"),
            "cache": {
                "graph_entries": cache_manager.graph_cache_size(),
                "discovery_entries": cache_manager.discovery_cache_size(),
            },
        }
    )


def _parse_signal_feedback_payload(payload):
    if not isinstance(payload, dict):
        return None, "Request body must be a JSON object"
    account_id = str(payload.get("account_id") or "").strip()
    signal_name = str(payload.get("signal_name") or "").strip()
    user_label = str(payload.get("user_label") or "").strip()
    if not account_id:
        return None, "account_id is required"
    if not signal_name:
        return None, "signal_name is required"
    if user_label not in {"tpot", "not_tpot"}:
        return None, "user_label must be one of: tpot, not_tpot"
    score = payload.get("score", 0.0)
    try:
        parsed_score = float(score)
    except (TypeError, ValueError):
        return None, "score must be numeric"
    context = payload.get("context") or {}
    if not isinstance(context, dict):
        return None, "context must be an object"
    return {
        "account_id": account_id,
        "signal_name": signal_name,
        "user_label": user_label,
        "score": parsed_score,
        "context": context,
    }, None


@analysis_bp.route("/signals/feedback", methods=["POST"])
def submit_signal_feedback():
    """Store user feedback events used for discovery signal-quality diagnostics."""
    parsed, error = _parse_signal_feedback_payload(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400

    feedback_store: SignalFeedbackStore = current_app.config["SIGNAL_FEEDBACK_STORE"]
    feedback_store.add_feedback(**parsed)
    return jsonify(
        {
            "status": "ok",
            "stored": True,
            "total_feedback": feedback_store.event_count(),
        }
    )


@analysis_bp.route("/signals/quality", methods=["GET"])
def get_signal_quality_report():
    """Return aggregate quality metrics over captured signal feedback events."""
    feedback_store: SignalFeedbackStore = current_app.config["SIGNAL_FEEDBACK_STORE"]
    return jsonify(feedback_store.quality_report())


@analysis_bp.route("/analysis/status", methods=["GET"])
def get_analysis_status():
    """Get status of the background analysis job."""
    manager: AnalysisManager = current_app.config["ANALYSIS_MANAGER"]
    return jsonify(manager.get_status())


@analysis_bp.route("/analysis/run", methods=["POST"])
def run_analysis():
    """Start a full analysis run in the background."""
    manager: AnalysisManager = current_app.config["ANALYSIS_MANAGER"]
    
    if manager.is_running():
        return jsonify({"status": "error", "message": "Analysis already running"}), 409

    # Start background task
    started = manager.start_analysis(_run_full_analysis_task)
    
    if started:
        return jsonify({"status": "started"})
    else:
        return jsonify({"status": "error", "message": "Could not start analysis"}), 500


def _run_full_analysis_task(manager: AnalysisManager):
    """The actual analysis logic, running in a thread."""
    manager.log("Starting full analysis...")
    
    # 1. Build Graph
    manager.log("Building graph...")
    snapshot_dir = get_snapshot_dir()
    fetcher = CachedDataFetcher(cache_db=snapshot_dir / "cache.db")
    
    graph_result = build_graph(fetcher=fetcher)
    G = graph_result.directed
    manager.update_status("node_count", len(G.nodes()))
    
    # 2. Communities
    manager.log("Detecting communities (Louvain)...")
    communities = compute_louvain_communities(G)
    manager.update_status("community_count", len(set(communities.values())))
    
    # 3. PageRank
    manager.log("Computing PageRank...")
    pagerank = compute_personalized_pagerank(G)
    
    # 4. Betweenness (expensive!)
    manager.log("Computing Betweenness Centrality...")
    betweenness = compute_betweenness(G, k=100) # Approx for speed
    
    manager.log("Analysis complete.")
    
    # In a real app, we'd save these results to the graph/store
    # For now, we just log completion
