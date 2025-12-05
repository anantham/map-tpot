"""Flask API server for graph metrics computation."""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, jsonify, request, g
from flask_cors import CORS

from src.config import get_cache_settings
from src.data.fetcher import CachedDataFetcher
from src.data.shadow_store import get_shadow_store
from src.graph import (
    build_graph,
    compute_betweenness,
    compute_composite_score,
    compute_engagement_scores,
    compute_louvain_communities,
    compute_personalized_pagerank,
    load_seed_candidates,
)

logger = logging.getLogger(__name__)

# Performance metrics storage (in-memory for now)
performance_metrics = {
    "requests": [],  # List of request timing data
    "aggregates": defaultdict(lambda: {"count": 0, "total_time": 0.0, "min": float('inf'), "max": 0.0}),
}


def _serialize_datetime(value) -> str | None:
    """Serialize datetime objects to ISO format."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _resolve_seeds(graph_result, seeds: List[str]) -> List[str]:
    """Resolve username/handle seeds to account IDs."""
    directed = graph_result.directed
    id_seeds = {seed for seed in seeds if seed in directed}

    username_to_id = {
        data.get("username", "").lower(): node
        for node, data in directed.nodes(data=True)
        if data.get("username")
    }

    for seed in seeds:
        lower = seed.lower()
        if lower in username_to_id:
            id_seeds.add(username_to_id[lower])

    return sorted(id_seeds)


def create_app(cache_db_path: Path | None = None) -> Flask:
    """Create and configure Flask app."""
    app = Flask(__name__)
    CORS(app)  # Enable CORS for frontend

    # Store cache path in app config
    if cache_db_path is None:
        cache_db_path = get_cache_settings().path
    app.config["CACHE_DB_PATH"] = cache_db_path

    # Performance tracking middleware
    @app.before_request
    def before_request():
        """Start timing the request."""
        g.start_time = time.time()

    @app.after_request
    def after_request(response):
        """Log request duration and collect metrics."""
        if hasattr(g, 'start_time'):
            duration = time.time() - g.start_time
            endpoint = request.endpoint or "unknown"
            method = request.method

            # Log the request
            logger.info(
                f"{method} {request.path} -> {response.status_code} "
                f"[{duration*1000:.2f}ms]"
            )

            # Store metrics
            metric_key = f"{method} {endpoint}"
            performance_metrics["requests"].append({
                "endpoint": endpoint,
                "method": method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration * 1000,
                "timestamp": time.time(),
            })

            # Update aggregates
            agg = performance_metrics["aggregates"][metric_key]
            agg["count"] += 1
            agg["total_time"] += duration
            agg["min"] = min(agg["min"], duration)
            agg["max"] = max(agg["max"], duration)

            # Keep only last 1000 requests
            if len(performance_metrics["requests"]) > 1000:
                performance_metrics["requests"] = performance_metrics["requests"][-1000:]

            # Add timing header for client-side tracking
            response.headers['X-Response-Time'] = f"{duration*1000:.2f}ms"

        return response

    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok"})

    @app.route("/api/metrics/performance", methods=["GET"])
    def get_performance_metrics():
        """
        Get performance metrics for API endpoints.

        Returns aggregated timing data for all endpoints.
        """
        try:
            # Calculate averages
            aggregates = {}
            for key, data in performance_metrics["aggregates"].items():
                if data["count"] > 0:
                    aggregates[key] = {
                        "count": data["count"],
                        "avg_ms": (data["total_time"] / data["count"]) * 1000,
                        "min_ms": data["min"] * 1000,
                        "max_ms": data["max"] * 1000,
                        "total_time_s": data["total_time"],
                    }

            # Get recent requests (last 50)
            recent = performance_metrics["requests"][-50:]

            return jsonify({
                "aggregates": aggregates,
                "recent_requests": recent,
                "total_requests": sum(data["count"] for data in performance_metrics["aggregates"].values()),
            })

        except Exception as e:
            logger.exception("Error getting performance metrics")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/graph-data", methods=["GET"])
    def get_graph_data():
        """
        Load raw graph structure (nodes and edges) from SQLite cache.

        Query params:
            include_shadow: bool (default: true)
            mutual_only: bool (default: false)
            min_followers: int (default: 0)
        """
        try:
            include_shadow = request.args.get("include_shadow", "true").lower() == "true"
            mutual_only = request.args.get("mutual_only", "false").lower() == "true"
            min_followers = int(request.args.get("min_followers", "0"))

            cache_path = app.config["CACHE_DB_PATH"]

            with CachedDataFetcher(cache_db=cache_path) as fetcher:
                shadow_store = get_shadow_store(fetcher.engine) if include_shadow else None
                graph = build_graph(
                    fetcher=fetcher,
                    mutual_only=mutual_only,
                    min_followers=min_followers,
                    include_shadow=include_shadow,
                    shadow_store=shadow_store,
                )

            directed = graph.directed

            # Serialize edges
            edges = []
            for u, v in directed.edges():
                data = directed.get_edge_data(u, v, default={})
                edges.append({
                    "source": u,
                    "target": v,
                    "mutual": directed.has_edge(v, u),
                    "provenance": data.get("provenance", "archive"),
                    "shadow": data.get("shadow", False),
                    "metadata": data.get("metadata"),
                    "direction_label": data.get("direction_label"),
                    "fetched_at": _serialize_datetime(data.get("fetched_at")),
                })

            # Serialize nodes
            nodes = {}
            for node, data in directed.nodes(data=True):
                nodes[node] = {
                    "username": data.get("username"),
                    "display_name": data.get("account_display_name") or data.get("display_name"),
                    "num_followers": data.get("num_followers"),
                    "num_following": data.get("num_following"),
                    "num_likes": data.get("num_likes"),
                    "num_tweets": data.get("num_tweets"),
                    "bio": data.get("bio"),
                    "location": data.get("location"),
                    "website": data.get("website"),
                    "profile_image_url": data.get("profile_image_url"),
                    "provenance": data.get("provenance", "archive"),
                    "shadow": data.get("shadow", False),
                    "shadow_scrape_stats": data.get("shadow_scrape_stats"),
                    "fetched_at": _serialize_datetime(data.get("fetched_at")),
                }

            return jsonify({
                "nodes": nodes,
                "edges": edges,
                "directed_nodes": directed.number_of_nodes(),
                "directed_edges": directed.number_of_edges(),
                "undirected_edges": graph.undirected.number_of_edges(),
            })

        except Exception as e:
            logger.exception("Error loading graph data")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/metrics/compute", methods=["POST"])
    def compute_metrics():
        """
        Compute graph metrics with custom seeds and weights.

        Request body:
        {
            "seeds": ["username1", "account_id2"],
            "weights": [0.4, 0.3, 0.3],  // [alpha, beta, gamma] for PR, BT, ENG
            "alpha": 0.85,  // PageRank damping factor
            "resolution": 1.0,  // Louvain resolution
            "include_shadow": true,
            "mutual_only": false,
            "min_followers": 0
        }
        """
        try:
            data = request.json or {}

            # Extract parameters with defaults
            seeds = data.get("seeds", [])
            weights = tuple(data.get("weights", [0.4, 0.3, 0.3]))
            alpha = data.get("alpha", 0.85)
            resolution = data.get("resolution", 1.0)
            include_shadow = data.get("include_shadow", True)
            mutual_only = data.get("mutual_only", False)
            min_followers = data.get("min_followers", 0)

            # Load default seeds if none provided
            if not seeds:
                seeds = sorted(load_seed_candidates())

            cache_path = app.config["CACHE_DB_PATH"]

            # Build graph
            with CachedDataFetcher(cache_db=cache_path) as fetcher:
                shadow_store = get_shadow_store(fetcher.engine) if include_shadow else None
                graph = build_graph(
                    fetcher=fetcher,
                    mutual_only=mutual_only,
                    min_followers=min_followers,
                    include_shadow=include_shadow,
                    shadow_store=shadow_store,
                )

            directed = graph.directed
            undirected = graph.undirected

            # Resolve seeds (usernames -> account IDs)
            resolved_seeds = _resolve_seeds(graph, seeds)

            # Compute metrics
            pagerank = compute_personalized_pagerank(
                directed,
                seeds=resolved_seeds,
                alpha=alpha
            )
            betweenness = compute_betweenness(undirected)
            engagement = compute_engagement_scores(undirected)
            composite = compute_composite_score(
                pagerank=pagerank,
                betweenness=betweenness,
                engagement=engagement,
                weights=weights,
            )
            communities = compute_louvain_communities(undirected, resolution=resolution)

            # Get top accounts
            top_pagerank = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)[:20]
            top_betweenness = sorted(betweenness.items(), key=lambda x: x[1], reverse=True)[:20]
            top_composite = sorted(composite.items(), key=lambda x: x[1], reverse=True)[:20]

            return jsonify({
                "seeds": seeds,
                "resolved_seeds": resolved_seeds,
                "metrics": {
                    "pagerank": pagerank,
                    "betweenness": betweenness,
                    "engagement": engagement,
                    "composite": composite,
                    "communities": communities,
                },
                "top": {
                    "pagerank": top_pagerank,
                    "betweenness": top_betweenness,
                    "composite": top_composite,
                },
            })

        except Exception as e:
            logger.exception("Error computing metrics")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/metrics/presets", methods=["GET"])
    def get_presets():
        """Get available seed presets."""
        try:
            # Load from docs/seed_presets.json if it exists
            presets_path = Path("docs/seed_presets.json")
            if presets_path.exists():
                import json
                with open(presets_path) as f:
                    presets = json.load(f)
                return jsonify(presets)

            # Fallback to default
            return jsonify({
                "adi_tpot": sorted(load_seed_candidates())
            })

        except Exception as e:
            logger.exception("Error loading presets")
            return jsonify({"error": str(e)}), 500

    return app


def run_dev_server(host: str = "localhost", port: int = 5001):
    """Run development server."""
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    logger.info(f"Starting Flask server on {host}:{port}")
    app.run(host=host, port=port, debug=True)


if __name__ == "__main__":
    run_dev_server()
