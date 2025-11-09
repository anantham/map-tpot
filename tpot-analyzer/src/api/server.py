"""Flask API server for graph metrics computation."""
from __future__ import annotations

import json
import logging
import math
import subprocess
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, jsonify, request, g, Response
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
    get_graph_settings,
    get_seed_state,
    load_seed_candidates,
    save_seed_list,
    set_active_seed_list,
    update_graph_settings,
)
from src.performance_profiler import profile_operation, profile_phase, get_profiler

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]

analysis_status = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "error": None,
    "log": [],
}
analysis_lock = threading.Lock()
analysis_thread = None


def _append_analysis_log(line: str) -> None:
    with analysis_lock:
        analysis_status.setdefault("log", [])
        analysis_status["log"].append(line)
        if len(analysis_status["log"]) > 200:
            analysis_status["log"] = analysis_status["log"][-200:]


def _analysis_worker(active_list: str, include_shadow: bool, alpha: float) -> None:
    global analysis_thread
    cmd = [
        sys.executable or "python3",
        "scripts/analyze_graph.py",
        "--seed-list",
        active_list,
        "--alpha",
        f"{alpha:.4f}",
        "--global-pagerank",
    ]
    if include_shadow:
        cmd.append("--include-shadow")

    process = None
    try:
        _append_analysis_log(f"Starting analysis: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
        )
        assert process.stdout is not None
        for line in process.stdout:
            _append_analysis_log(line.rstrip())
        process.wait()
        exit_code = process.returncode
        with analysis_lock:
            analysis_status["finished_at"] = datetime.utcnow().isoformat() + "Z"
            if exit_code == 0:
                analysis_status["status"] = "succeeded"
                analysis_status["error"] = None
                _append_analysis_log("Analysis completed successfully.")
            else:
                analysis_status["status"] = "failed"
                analysis_status["error"] = f"Process exited with code {exit_code}"
                _append_analysis_log(f"Analysis failed with exit code {exit_code}.")
    except Exception as exc:
        logger.exception("Analysis job failed")
        with analysis_lock:
            analysis_status["status"] = "failed"
            analysis_status["error"] = str(exc)
            analysis_status["finished_at"] = datetime.utcnow().isoformat() + "Z"
            _append_analysis_log(f"Analysis failed: {exc}")
    finally:
        if process and process.poll() is None:
            process.kill()
        with analysis_lock:
            analysis_thread = None


class SafeJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles NaN and Infinity values."""

    def encode(self, o):
        """Recursively sanitize NaN/Inf values before encoding."""
        def sanitize(obj):
            if isinstance(obj, dict):
                return {k: sanitize(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [sanitize(item) for item in obj]
            elif isinstance(obj, float):
                if math.isnan(obj) or math.isinf(obj):
                    return None
            return obj

        return super().encode(sanitize(o))


def safe_jsonify(data):
    """Create a JSON response with NaN/Inf handling."""
    return Response(
        json.dumps(data, cls=SafeJSONEncoder),
        mimetype='application/json'
    )


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
    # Enable CORS for frontend and expose custom headers
    CORS(app, expose_headers=['X-Response-Time'])

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

                return safe_jsonify({
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

                return safe_jsonify({
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

    @app.route("/api/accounts/search", methods=["GET"])
    def search_accounts():
        """
        Search for accounts by username prefix.

        Query params:
            q: Search query (username prefix)
            limit: Max results (default 10)
        """
        try:
            query = request.args.get('q', '').lower().strip()
            limit = min(int(request.args.get('limit', '10')), 50)

            if not query or len(query) < 1:
                return safe_jsonify([])

            # Load graph from cache
            snapshot_loader = app.config["SNAPSHOT_LOADER"]
            graph = snapshot_loader.load_graph()

            if graph is None:
                # Fall back to loading from cache
                cache_path = app.config["CACHE_DB_PATH"]
                with CachedDataFetcher(cache_db=cache_path) as fetcher:
                    shadow_store = get_shadow_store(fetcher.engine)
                    graph = build_graph(
                        fetcher=fetcher,
                        mutual_only=False,
                        min_followers=0,
                        include_shadow=True,
                        shadow_store=shadow_store,
                    )

            # Search for matching usernames and deduplicate
            matches_by_username = {}  # username -> best match
            for node, data in graph.directed.nodes(data=True):
                username = data.get('username', '')
                if username and username.lower().startswith(query):
                    # Use num_followers if available, otherwise use graph in-degree
                    num_followers = data.get('num_followers')
                    # Check if num_followers is missing, NaN, or infinity
                    if num_followers is None or (isinstance(num_followers, float) and (math.isnan(num_followers) or math.isinf(num_followers))):
                        # Fallback to graph in-degree for shadow accounts
                        num_followers = graph.directed.in_degree(node)

                    match = {
                        'username': username,
                        'display_name': data.get('account_display_name') or data.get('display_name', ''),
                        'num_followers': num_followers,
                        'is_shadow': data.get('shadow', False),
                        'bio': (data.get('bio', '') or '')[:100]  # First 100 chars of bio
                    }

                    # Deduplicate: prefer non-shadow accounts, or the one with more followers
                    username_lower = username.lower()
                    if username_lower not in matches_by_username:
                        matches_by_username[username_lower] = match
                    else:
                        existing = matches_by_username[username_lower]
                        # Prefer non-shadow over shadow
                        if match['is_shadow'] and not existing['is_shadow']:
                            continue  # Keep existing (non-shadow)
                        elif not match['is_shadow'] and existing['is_shadow']:
                            matches_by_username[username_lower] = match  # Replace with non-shadow
                        else:
                            # Both shadow or both non-shadow: prefer higher follower count
                            if (match['num_followers'] or 0) > (existing['num_followers'] or 0):
                                matches_by_username[username_lower] = match

            # Convert to list, sort by followers (descending) and limit
            matches = list(matches_by_username.values())
            matches.sort(key=lambda x: x['num_followers'] or 0, reverse=True)
            matches = matches[:limit]

            return safe_jsonify(matches)

        except Exception as e:
            logger.exception("Error in account search")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/seeds", methods=["GET", "POST"])
    def seed_collections():
        """List or update Discovery seed collections."""
        if request.method == "GET":
            return safe_jsonify(get_seed_state())

        data = request.json or {}
        name = data.get("name") or "discovery_active"
        seeds = data.get("seeds")
        set_active = data.get("set_active", True)
        settings_payload = data.get("settings")

        try:
            if settings_payload is not None:
                if not isinstance(settings_payload, dict):
                    return safe_jsonify({"error": "settings must be an object"}), 400
                state = update_graph_settings(settings_payload)
            elif seeds is None:
                state = set_active_seed_list(name)
            else:
                if not isinstance(seeds, list):
                    return safe_jsonify({"error": "seeds must be an array"}), 400
                state = save_seed_list(name, seeds, set_active=set_active)
            return safe_jsonify({"ok": True, "state": state})
        except ValueError as exc:
            return safe_jsonify({"error": str(exc)}), 400

    @app.route("/api/analysis/status", methods=["GET"])
    def analysis_status_endpoint():
        with analysis_lock:
            payload = {
                "status": analysis_status.get("status"),
                "started_at": analysis_status.get("started_at"),
                "finished_at": analysis_status.get("finished_at"),
                "error": analysis_status.get("error"),
                "log": list(analysis_status.get("log", []))[-50:],
            }
        return safe_jsonify(payload)

    @app.route("/api/analysis/run", methods=["POST"])
    def run_analysis():
        global analysis_thread
        graph_state = get_graph_settings()
        active_list = graph_state.get("active_list") or "adi_tpot"
        settings = graph_state.get("settings", {})
        include_shadow = settings.get("auto_include_shadow", True)
        alpha = settings.get("alpha", 0.85)

        with analysis_lock:
            if analysis_status.get("status") == "running":
                return safe_jsonify({"error": "Analysis already running", "status": analysis_status}), 409
            analysis_status["status"] = "running"
            analysis_status["started_at"] = datetime.utcnow().isoformat() + "Z"
            analysis_status["finished_at"] = None
            analysis_status["error"] = None
            analysis_status["log"] = []

            analysis_thread = threading.Thread(
                target=_analysis_worker,
                args=(active_list, include_shadow, alpha),
                daemon=True,
            )
            analysis_thread.start()

        return safe_jsonify({"ok": True, "status": analysis_status})

    @app.route("/api/ego-network", methods=["POST"])
    def get_ego_network():
        """
        Get ego network for a specific user - their immediate network + top recommendations.

        This is much faster than loading the entire graph.

        Request body:
        {
            "username": "twitter_handle",
            "depth": 2,               // How many hops out (default: 2, max: 3)
            "top_recommendations": 20 // Deprecated alias for limit
            "limit": 50,              // Batch size (default: 50, max: 200 here / 500 overall)
            "offset": 0,              // Pagination offset
            "weights": {...},         // Optional scoring weights
            "filters": {...}          // Optional filters
        }
        """
        try:
            data = request.json or {}

            # Validate username
            username = data.get('username', '').strip()
            if not username:
                return safe_jsonify({"error": "username is required"}), 400

            depth = min(data.get('depth', 2), 5)  # Max 5 hops

            raw_limit = data.get('limit', data.get('top_recommendations', 50))
            try:
                limit = int(raw_limit)
            except (TypeError, ValueError):
                limit = 50
            limit = max(10, min(limit, 500))

            try:
                offset = int(data.get('offset', 0))
            except (TypeError, ValueError):
                offset = 0
            offset = max(0, offset)

            logger.info(f"[EGO-NETWORK] Starting for user '{username}', depth={depth}, limit={limit}, offset={offset}")

            # Load graph
            snapshot_loader = app.config["SNAPSHOT_LOADER"]
            graph = snapshot_loader.load_graph()

            # Resolve username to account ID
            resolved_seeds = _resolve_seeds(graph, [username])
            if not resolved_seeds:
                logger.warning(f"[EGO-NETWORK] User '{username}' not found in graph")
                return safe_jsonify({"error": f"User '{username}' not found in graph"}), 404

            account_id = resolved_seeds[0]  # Should only have one seed
            logger.info(f"[EGO-NETWORK] Resolved '{username}' to account ID: {account_id}")

            # Create discovery request with account ID as seed
            discovery_data = {
                'seeds': [account_id],
                'weights': data.get('weights', {}),
                'filters': data.get('filters', {}),
                'limit': limit,
                'offset': offset,
                'use_cache': True,  # Enable caching for ego-network
                'debug': False
            }
            parsed_request, errors = validate_request(discovery_data)
            if errors:
                return safe_jsonify({"error": "Invalid weights or filters", "details": errors}), 400

            # Load PageRank scores (same logic as discovery endpoint)
            pagerank_scores = {}
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
                logger.info("[EGO-NETWORK] Computing PageRank scores (no precomputed scores found)")
                from src.api.graph_metrics import compute_personalized_pagerank
                pagerank_scores = compute_personalized_pagerank(
                    graph.directed,
                    seeds=[account_id],  # Use the resolved account ID
                    alpha=0.85
                )

            logger.info(f"[EGO-NETWORK] Extracting {depth}-hop subgraph around '{username}'")

            # Extract k-hop neighborhood using account ID
            from src.api.discovery import extract_subgraph
            subgraph, candidates = extract_subgraph(graph.directed, [account_id], depth=depth)

            logger.info(f"[EGO-NETWORK] Extracted subgraph: {len(subgraph.nodes())} nodes, {len(candidates)} candidates")

            # Run discovery to get top recommendations
            logger.info(f"[EGO-NETWORK] Computing top {limit} recommendations")
            from src.api.discovery import discover_subgraph

            discovery_result = discover_subgraph(graph.directed, parsed_request, pagerank_scores)

            # Combine ego network nodes + recommendations
            logger.info(f"[EGO-NETWORK] Building response with network + recommendations")

            # Get all nodes in subgraph
            network_nodes = set(subgraph.nodes())

            # Add recommendation nodes
            recommendation_nodes = set()
            for rec in discovery_result.get('recommendations', []):
                recommendation_nodes.add(rec['handle'])

            # Combine unique nodes
            all_nodes = network_nodes | recommendation_nodes
            logger.info(f"[EGO-NETWORK] Total nodes: {len(all_nodes)} (network: {len(network_nodes)}, recs: {len(recommendation_nodes)})")

            # Serialize nodes
            nodes = {}
            for node in all_nodes:
                if node in graph.directed:
                    node_data = graph.directed.nodes[node]
                    nodes[node] = {
                        "account_id": node,
                        "username": node_data.get("username"),
                        "display_name": node_data.get("account_display_name") or node_data.get("display_name"),
                        "num_followers": node_data.get("num_followers"),
                        "num_following": node_data.get("num_following"),
                        "bio": node_data.get("bio"),
                        "shadow": node_data.get("shadow", False),
                        "is_ego": node == account_id,
                        "is_recommendation": node in recommendation_nodes and node not in network_nodes
                    }

            # Serialize edges (only between nodes we're including)
            edges = []
            for u, v in subgraph.edges():
                if u in all_nodes and v in all_nodes:
                    edges.append({
                        "source": u,
                        "target": v,
                        "mutual": subgraph.has_edge(v, u)
                    })

            # Add edges to/from recommendation nodes
            for rec_node in recommendation_nodes:
                if rec_node in graph.directed:
                    # Add edges between rec_node and network nodes
                    for neighbor in graph.directed.neighbors(rec_node):
                        if neighbor in all_nodes and {"source": rec_node, "target": neighbor, "mutual": graph.directed.has_edge(neighbor, rec_node)} not in edges:
                            edges.append({
                                "source": rec_node,
                                "target": neighbor,
                                "mutual": graph.directed.has_edge(neighbor, rec_node)
                            })
                    for predecessor in graph.directed.predecessors(rec_node):
                        if predecessor in all_nodes and {"source": predecessor, "target": rec_node, "mutual": graph.directed.has_edge(rec_node, predecessor)} not in edges:
                            edges.append({
                                "source": predecessor,
                                "target": rec_node,
                                "mutual": graph.directed.has_edge(rec_node, predecessor)
                            })

            logger.info(f"[EGO-NETWORK] Serialized {len(nodes)} nodes, {len(edges)} edges")

            # Build response
            ego_details = nodes.get(account_id, {}).copy()
            ego_details.setdefault("account_id", account_id)
            ego_details.setdefault("username", username)

            response = {
                "ego": ego_details,
                "network": {
                    "nodes": nodes,
                    "edges": edges
                },
                "recommendations": discovery_result.get('recommendations', []),
                "stats": {
                    "total_nodes": len(nodes),
                    "total_edges": len(edges),
                    "network_nodes": len(network_nodes),
                    "recommendation_nodes": len(recommendation_nodes),
                    "depth": depth,
                    "computation_time_ms": discovery_result.get('meta', {}).get('computation_time_ms', 0)
                },
                "meta": discovery_result.get('meta', {})
            }

            logger.info(f"[EGO-NETWORK] Completed successfully for '{username}'")
            return safe_jsonify(response)

        except Exception as e:
            logger.exception("Error in ego-network endpoint")
            return safe_jsonify({"error": str(e)}), 500

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
                result_response = safe_jsonify(result)
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
