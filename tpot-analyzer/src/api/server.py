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

from src.api.discovery import (
    discover_subgraph,
    validate_request,
)
from src.api.snapshot_loader import get_snapshot_loader
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
from src.performance_profiler import profile_operation, profile_phase, get_profiler

logger = logging.getLogger(__name__)

# Performance metrics storage (in-memory for now)
performance_metrics = {
    "requests": [],  # List of request timing data
    "aggregates": defaultdict(lambda: {"count": 0, "total_time": 0.0, "min": float('inf'), "max": 0.0}),
}

# Rate limiting storage (in-memory, resets on restart)
rate_limits = defaultdict(lambda: {"count": 0, "reset_time": 0})


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

    # Initialize snapshot loader
    snapshot_loader = get_snapshot_loader()
    app.config["SNAPSHOT_LOADER"] = snapshot_loader

    # Try to load snapshot on startup
    logger.info("Checking for graph snapshot...")
    should_use, reason = snapshot_loader.should_use_snapshot()
    if should_use:
        logger.info(f"Loading snapshot: {reason}")
        graph = snapshot_loader.load_graph()
        if graph:
            logger.info(f"Snapshot loaded successfully: {graph.directed.number_of_nodes()} nodes, {graph.directed.number_of_edges()} edges")
        else:
            logger.warning("Failed to load snapshot, will rebuild on first request")
    else:
        logger.warning(f"Snapshot not available: {reason}")
        logger.info("Graph will be rebuilt from cache on first request")

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

        Returns aggregated timing data for all endpoints plus detailed profiling data.
        """
        try:
            # Calculate averages from request tracking
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

            # Get detailed profiling data
            profiler = get_profiler()
            detailed_reports = []
            for report in profiler.get_all_reports()[-20:]:  # Last 20 detailed reports
                detailed_reports.append({
                    "operation": report.operation,
                    "total_ms": report.total_duration_ms,
                    "metadata": report.metadata,
                    "phases": [
                        {
                            "name": phase.name,
                            "duration_ms": phase.duration_ms,
                            "metadata": phase.metadata
                        }
                        for phase in report.phases
                    ],
                    "breakdown": report.get_phase_breakdown()
                })

            # Get profiler summary
            profiler_summary = profiler.get_summary()

            return jsonify({
                "aggregates": aggregates,
                "recent_requests": recent,
                "total_requests": sum(data["count"] for data in performance_metrics["aggregates"].values()),
                "detailed_reports": detailed_reports,
                "profiler_summary": profiler_summary,
            })

        except Exception as e:
            logger.exception("Error getting performance metrics")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/graph-data", methods=["GET"])
    def get_graph_data():
        """
        Load raw graph structure (nodes and edges).

        Prefers snapshot if available and fresh, falls back to live build.

        Query params:
            include_shadow: bool (default: true)
            mutual_only: bool (default: false)
            min_followers: int (default: 0)
            force_rebuild: bool (default: false) - skip snapshot, rebuild from cache
        """
        try:
            include_shadow = request.args.get("include_shadow", "true").lower() == "true"
            mutual_only = request.args.get("mutual_only", "false").lower() == "true"
            min_followers = int(request.args.get("min_followers", "0"))
            force_rebuild = request.args.get("force_rebuild", "false").lower() == "true"

            with profile_operation("api_get_graph_data", {
                "include_shadow": include_shadow,
                "mutual_only": mutual_only,
                "min_followers": min_followers,
                "force_rebuild": force_rebuild
            }, verbose=False) as report:

                graph = None
                source = "snapshot"

                # Try snapshot first unless force_rebuild
                # NOTE: Snapshot is always built with include_shadow=True, mutual_only=False, min_followers=0
                # If client requests different parameters, we must rebuild
                snapshot_loader = app.config["SNAPSHOT_LOADER"]
                can_use_snapshot = (
                    not force_rebuild
                    and include_shadow  # Snapshot always has shadow data
                    and not mutual_only  # Snapshot is built without mutual_only filter
                    and min_followers == 0  # Snapshot has no follower filter
                )

                if can_use_snapshot:
                    with profile_phase("load_snapshot", "api_get_graph_data"):
                        graph = snapshot_loader.load_graph()

                # Fall back to live build if snapshot unavailable or incompatible
                if graph is None:
                    source = "live_build"
                    logger.info("Building graph from cache (snapshot unavailable or stale)")

                    cache_path = app.config["CACHE_DB_PATH"]

                    with profile_phase("build_graph", "api_get_graph_data"):
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
                with profile_phase("serialize_edges", "api_get_graph_data", {"edge_count": directed.number_of_edges()}):
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
                with profile_phase("serialize_nodes", "api_get_graph_data", {"node_count": directed.number_of_nodes()}):
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
                    "source": source,  # Indicates if from snapshot or live build
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

            with profile_operation("api_compute_metrics", {
                "seed_count": len(seeds),
                "include_shadow": include_shadow
            }, verbose=False) as report:

                # Load default seeds if none provided
                if not seeds:
                    with profile_phase("load_default_seeds", "api_compute_metrics"):
                        seeds = sorted(load_seed_candidates())

                # Try snapshot first
                graph = None
                snapshot_loader = app.config["SNAPSHOT_LOADER"]

                # Check if snapshot parameters match request
                can_use_snapshot = (
                    include_shadow
                    and not mutual_only
                    and min_followers == 0
                )

                if can_use_snapshot:
                    with profile_phase("load_graph", "api_compute_metrics"):
                        graph = snapshot_loader.load_graph()

                # Fall back to live build if snapshot unavailable or incompatible
                if graph is None:
                    logger.info("Building graph from cache for metrics (snapshot unavailable)")
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
                undirected = graph.undirected

                # Resolve seeds (usernames -> account IDs)
                with profile_phase("resolve_seeds", "api_compute_metrics"):
                    resolved_seeds = _resolve_seeds(graph, seeds)

                # Compute metrics
                pagerank = compute_personalized_pagerank(
                    directed,
                    seeds=resolved_seeds,
                    alpha=alpha
                )
                betweenness = compute_betweenness(undirected)

                with profile_phase("compute_engagement", "api_compute_metrics"):
                    engagement = compute_engagement_scores(undirected)

                with profile_phase("compute_composite", "api_compute_metrics"):
                    composite = compute_composite_score(
                        pagerank=pagerank,
                        betweenness=betweenness,
                        engagement=engagement,
                        weights=weights,
                    )

                communities = compute_louvain_communities(undirected, resolution=resolution)

                # Get top accounts
                with profile_phase("sort_top_accounts", "api_compute_metrics"):
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

    @app.route("/api/subgraph/discover", methods=["POST"])
    def discover():
        """
        Discover personalized recommendations based on seed accounts.

        Request body:
        {
            "seeds": ["handle1", "handle2"],  // Required: 1-20 seed handles
            "weights": {  // Optional: scoring weights (will be normalized)
                "neighbor_overlap": 0.4,
                "pagerank": 0.3,
                "community": 0.2,
                "path_distance": 0.1
            },
            "filters": {  // Optional: filtering criteria
                "max_distance": 3,  // Max graph distance from seeds (1-4)
                "min_overlap": 2,  // Min seed connections required
                "min_followers": 100,  // Min follower count
                "max_followers": 50000,  // Max follower count
                "include_communities": [1, 2],  // Community IDs to include
                "exclude_communities": [7],  // Community IDs to exclude
                "include_shadow": true  // Include shadow-enriched accounts
            },
            "limit": 100,  // Results per page (max 500)
            "offset": 0,  // Pagination offset
            "use_cache": true,  // Use cached results if available
            "debug": false  // Include debug information
        }

        Response:
        {
            "recommendations": [...],  // Ranked list of recommendations
            "meta": {...},  // Request metadata
            "warnings": [...]  // Any warnings
        }
        """
        try:
            # Rate limiting (30 req/min per IP)
            client_ip = request.remote_addr
            now = time.time()
            minute_window = int(now / 60)

            rate_key = f"{client_ip}:{minute_window}"
            rate_info = rate_limits[rate_key]

            if rate_info["reset_time"] < now:
                rate_info["count"] = 0
                rate_info["reset_time"] = now + 60

            rate_info["count"] += 1

            if rate_info["count"] > 30:
                logger.warning(f"Rate limit exceeded for {client_ip}")
                return jsonify({
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many requests. Max 30 per minute.",
                        "retry_after": int(rate_info["reset_time"] - now)
                    }
                }), 429

            # Validate request
            data = request.json or {}
            parsed_request, errors = validate_request(data)

            if errors:
                return jsonify({
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Invalid request parameters",
                        "details": errors
                    }
                }), 400

            with profile_operation("api_discover", {
                "seed_count": len(parsed_request.seeds),
                "limit": parsed_request.limit,
                "has_filters": bool(parsed_request.filters)
            }, verbose=False) as report:

                # Load graph (prefer snapshot)
                graph = None
                snapshot_loader = app.config["SNAPSHOT_LOADER"]

                # Try snapshot first
                with profile_phase("load_graph", "api_discover"):
                    graph = snapshot_loader.load_graph()

                    # Fall back to live build if needed
                    if graph is None:
                        logger.info("Building graph from cache for discovery (snapshot unavailable)")
                        cache_path = app.config["CACHE_DB_PATH"]

                        with CachedDataFetcher(cache_db=cache_path) as fetcher:
                            # Always include shadow for discovery
                            shadow_store = get_shadow_store(fetcher.engine)
                            graph = build_graph(
                                fetcher=fetcher,
                                mutual_only=False,
                                min_followers=0,
                                include_shadow=True,
                                shadow_store=shadow_store,
                            )

                # Load precomputed PageRank scores
                with profile_phase("load_pagerank", "api_discover"):
                    # Try to load from snapshot metadata first
                    pagerank_scores = {}

                    # Check if we have frontend analysis output with precomputed scores
                    frontend_path = Path("graph-explorer/public/analysis_output.json")
                    if frontend_path.exists():
                        try:
                            import json
                            with open(frontend_path) as f:
                                analysis_data = json.load(f)
                                pagerank_scores = analysis_data.get("metrics", {}).get("pagerank", {})
                        except Exception as e:
                            logger.warning(f"Failed to load precomputed PageRank: {e}")

                    # Fallback: compute PageRank if not available
                    if not pagerank_scores:
                        logger.info("Computing PageRank scores (no precomputed scores found)")
                        with profile_phase("compute_pagerank_fallback", "api_discover"):
                            # Use default seeds for PageRank if none provided
                            pr_seeds = parsed_request.seeds if parsed_request.seeds else sorted(load_seed_candidates())
                            resolved_pr_seeds = _resolve_seeds(graph, pr_seeds)
                            pagerank_scores = compute_personalized_pagerank(
                                graph.directed,
                                seeds=resolved_pr_seeds,
                                alpha=0.85
                            )

                # Resolve seeds (usernames -> account IDs)
                with profile_phase("resolve_seeds", "api_discover"):
                    resolved_seeds = _resolve_seeds(graph, parsed_request.seeds)

                    # Update the request with resolved seeds
                    parsed_request.seeds = resolved_seeds

                # Run discovery
                with profile_phase("discover_subgraph", "api_discover"):
                    result = discover_subgraph(
                        graph.directed,
                        parsed_request,
                        pagerank_scores
                    )

                # Add rate limit headers
                result_response = jsonify(result)
                result_response.headers['X-RateLimit-Limit'] = '30'
                result_response.headers['X-RateLimit-Remaining'] = str(30 - rate_info["count"])
                result_response.headers['X-RateLimit-Reset'] = str(int(rate_info["reset_time"]))

                return result_response

        except Exception as e:
            logger.exception("Error in discovery endpoint")
            return jsonify({
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(e)
                }
            }), 500

    return app


def run_dev_server(host: str = "localhost", port: int = 5001):
    """Run development server."""
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    logger.info(f"Starting Flask server on {host}:{port}")
    app.run(host=host, port=port, debug=True)


if __name__ == "__main__":
    run_dev_server()
