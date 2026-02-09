"""Routes for discovery and ego-network exploration."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from flask import Blueprint, current_app, jsonify, request

from src.api import snapshot_loader
from src.api.discovery import discover_subgraph, validate_request
from src.api.services.cache_manager import CacheManager
from src.config import get_snapshot_dir
from src.data.fetcher import CachedDataFetcher
from src.graph import build_graph, compute_personalized_pagerank

logger = logging.getLogger(__name__)

discovery_bp = Blueprint("discovery", __name__, url_prefix="/api")


def _load_graph_result() -> Any:
    """Load graph from in-memory snapshot, snapshot files, or cache.db fallback."""
    graph_result = current_app.config.get("SNAPSHOT_GRAPH")
    if graph_result is not None:
        return graph_result

    loader = snapshot_loader.get_snapshot_loader()
    graph_result = loader.load_graph()
    if graph_result is not None:
        current_app.config["SNAPSHOT_GRAPH"] = graph_result
        return graph_result

    snapshot_dir = get_snapshot_dir()
    cache_path = snapshot_dir / "cache.db"
    with CachedDataFetcher(cache_db=cache_path) as fetcher:
        return build_graph(
            fetcher=fetcher,
            include_shadow=True,
            mutual_only=False,
            min_followers=0,
        )


def _resolve_seed_handles(directed_graph: Any, seeds: List[str]) -> tuple[List[str], List[str]]:
    """Resolve incoming seed handles (username/account_id) to graph node ids.

    Returns:
        (resolved_ids, unresolved_inputs)
    """
    node_id_lookup: Dict[str, str] = {}
    username_lookup: Dict[str, str] = {}

    for node_id, payload in directed_graph.nodes(data=True):
        node_id_str = str(node_id)
        node_id_lookup[node_id_str] = node_id_str
        username = (payload.get("username") or "").strip().casefold()
        if username and username not in username_lookup:
            username_lookup[username] = node_id_str

    resolved: List[str] = []
    seen = set()
    for seed in seeds:
        candidate = str(seed).strip().lstrip("@")
        if not candidate:
            continue
        resolved_id = node_id_lookup.get(candidate) or username_lookup.get(candidate.casefold())
        if resolved_id is None or resolved_id in seen:
            continue
        seen.add(resolved_id)
        resolved.append(resolved_id)
    unresolved = []
    for seed in seeds:
        candidate = str(seed).strip().lstrip("@")
        if not candidate:
            continue
        if candidate in node_id_lookup or candidate.casefold() in username_lookup:
            continue
        unresolved.append(seed)
    return resolved, unresolved


@discovery_bp.route("/subgraph/discover", methods=["POST"])
def discover():
    """Discovery endpoint for finding relevant subgraphs."""
    req_data = request.get_json(silent=True)
    if req_data is None:
        req_data = {}
    elif not isinstance(req_data, dict):
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "Request body must be a JSON object"}}), 400

    parsed_request, errors = validate_request(req_data)
    if errors:
        return jsonify({
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request parameters",
                "details": errors,
            }
        }), 400

    cache_manager: CacheManager = current_app.config["CACHE_MANAGER"]
    cache_key = f"discovery:{json.dumps(req_data, sort_keys=True)}"

    cached = cache_manager.get_discovery_result(cache_key)
    if cached:
        return jsonify(cached)

    try:
        graph_result = _load_graph_result()
        directed_graph = getattr(graph_result, "directed", graph_result)

        seed_inputs = list(parsed_request.seeds)
        resolved_seeds, unresolved_seeds = _resolve_seed_handles(directed_graph, seed_inputs)
        parsed_request.seeds = resolved_seeds
        logger.info(
            "Discovery seed resolution complete: provided=%d resolved=%d",
            len(seed_inputs),
            len(resolved_seeds),
        )

        if not resolved_seeds:
            return jsonify(
                {
                    "error": {
                        "code": "NO_VALID_SEEDS",
                        "message": "None of the provided seeds exist in graph",
                        "unknown_handles": unresolved_seeds,
                    }
                }
            ), 200

        pagerank_scores = compute_personalized_pagerank(
            directed_graph,
            seeds=resolved_seeds,
            alpha=0.85,
        )
        result = discover_subgraph(directed_graph, parsed_request, pagerank_scores)
        if unresolved_seeds:
            result.setdefault("warnings", [])
            warning_text = f"Unknown handles ignored: {', '.join(unresolved_seeds)}"
            if warning_text not in result["warnings"]:
                result["warnings"].append(warning_text)
        cache_manager.set_discovery_result(cache_key, result)
        return jsonify(result)
    except Exception as exc:
        logger.exception("Discovery failed: %s", exc)
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": str(exc)}}), 500


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
