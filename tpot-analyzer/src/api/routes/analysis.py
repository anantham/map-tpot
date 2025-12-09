"""Routes for analysis jobs and metrics."""
from __future__ import annotations

import logging
import time
from flask import Blueprint, jsonify, request, current_app

from src.api.services.analysis_manager import AnalysisManager
from src.graph import (
    compute_betweenness,
    compute_louvain_communities,
    compute_personalized_pagerank,
    compute_composite_score,
    compute_engagement_scores,
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
    composite_scores = compute_composite_score(
        pagerank=pr_scores,
        betweenness=bt_scores,
        engagement=eng_scores,
        weights=weights,
    )

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
