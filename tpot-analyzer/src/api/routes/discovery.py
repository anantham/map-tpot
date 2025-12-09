"""Routes for discovery and ego-network exploration."""
from __future__ import annotations

import logging
from flask import Blueprint, jsonify, request, current_app

from src.api.services.cache_manager import CacheManager
from src.api.discovery import discover_subgraph, validate_request
from src.graph import get_graph_settings

logger = logging.getLogger(__name__)

discovery_bp = Blueprint("discovery", __name__, url_prefix="/api")


@discovery_bp.route("/subgraph/discover", methods=["POST"])
def discover():
    """Discovery endpoint for finding relevant subgraphs."""
    req_data = request.json
    
    try:
        discovery_req = validate_request(req_data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Check cache
    cache_manager: CacheManager = current_app.config["CACHE_MANAGER"]
    # Simple cache key based on serialized request
    import json
    cache_key = f"discovery:{json.dumps(req_data, sort_keys=True)}"
    
    cached = cache_manager.get_discovery_result(cache_key)
    if cached:
        return jsonify(cached)

    # Execute discovery
    # Note: discover_subgraph likely needs refactoring to accept 'G' or build it internally
    # For now, assuming it works as is or builds its own graph
    try:
        result = discover_subgraph(discovery_req)
        cache_manager.set_discovery_result(cache_key, result)
        return jsonify(result)
    except Exception as e:
        logger.exception("Discovery failed")
        return jsonify({"error": str(e)}), 500


@discovery_bp.route("/ego-network", methods=["GET"])
def get_ego_network():
    """Get ego network for a specific node."""
    center_id = request.args.get("center_id")
    radius = int(request.args.get("radius", 1))
    
    if not center_id:
        return jsonify({"error": "center_id required"}), 400

    # Reuse discovery logic or build custom
    # ... placeholder implementation ...
    return jsonify({
        "center_id": center_id,
        "radius": radius,
        "nodes": [],
        "links": []
    })
