"""Routes for graph data retrieval."""
from __future__ import annotations

import logging
import json
from flask import Blueprint, jsonify, request, current_app, Response

from src.graph import (
    build_graph,
    get_graph_settings,
    update_graph_settings,
)
from src.data.fetcher import CachedDataFetcher
from src.api.services.cache_manager import CacheManager
from src.config import get_snapshot_dir

logger = logging.getLogger(__name__)

graph_bp = Blueprint("graph", __name__, url_prefix="/api")


@graph_bp.route("/graph-data", methods=["GET"])
def get_graph_data():
    """Return the current graph structure for visualization."""
    include_shadow = request.args.get("include_shadow", "true").lower() == "true"
    mutual_only = request.args.get("mutual_only", "false").lower() == "true"
    min_followers = int(request.args.get("min_followers", "0"))

    cache_key = f"{include_shadow}_{mutual_only}_{min_followers}"
    
    # Access CacheManager via current_app
    cache_manager: CacheManager = current_app.config["CACHE_MANAGER"]
    cached_data = cache_manager.get_graph_response(cache_key)

    if cached_data:
        # If it's a pre-serialized Response object or string, return it directly
        if isinstance(cached_data, (str, bytes)):
             return Response(cached_data, mimetype='application/json')
        return jsonify(cached_data)

    # Build the graph
    snapshot_dir = get_snapshot_dir()
    fetcher = CachedDataFetcher(cache_db=snapshot_dir / "cache.db")
    
    graph_result = build_graph(
        fetcher=fetcher,
        include_shadow=include_shadow,
        min_followers=min_followers,
        mutual_only=mutual_only
    )
    G = graph_result.directed

    # Convert to JSON-serializable format

    # Convert to JSON-serializable format
    nodes = []
    for n, data in G.nodes(data=True):
        nodes.append({
            "id": str(n),
            "label": data.get("username", str(n)),
            "group": data.get("community", 0),
            "value": data.get("pagerank", 1.0) * 100,  # Scale for visibility
            **data
        })

    links = []
    for u, v, data in G.edges(data=True):
        links.append({
            "source": str(u),
            "target": str(v),
            "value": data.get("weight", 1.0),
            "mutual": True if mutual_only else data.get("mutual", False)
        })

    response_data = {
        "nodes": nodes,
        "edges": links,
        "directed_nodes": nodes,  # Alias for backward compatibility if needed
        "directed_edges": links,  # Alias for backward compatibility if needed
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(links),
            "generated_at": str(current_app.config.get("STARTUP_TIME"))
        }
    }
    
    # Serialize once and cache
    json_str = json.dumps(response_data)
    cache_manager.set_graph_response(cache_key, json_str)

    return Response(json_str, mimetype='application/json')


@graph_bp.route("/graph/settings", methods=["GET"])
def get_settings():
    """Get current graph settings."""
    return jsonify(get_graph_settings())


@graph_bp.route("/graph/settings", methods=["POST"])
def update_settings():
    """Update graph settings."""
    data = request.json
    update_graph_settings(data)
    
    # Invalidate cache on settings change
    cache_manager: CacheManager = current_app.config["CACHE_MANAGER"]
    cache_manager.clear_graph_cache()
    
    return jsonify({"status": "updated", "settings": get_graph_settings()})
