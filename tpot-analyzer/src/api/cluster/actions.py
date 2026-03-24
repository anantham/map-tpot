"""Label CRUD and cluster preview routes."""
from __future__ import annotations

import logging
from typing import Set

from flask import jsonify, request

from src.api.cluster.state import (
    cluster_bp,
    _require_loaded,
    _parse_lens,
    _make_cache_key,
)
from src.api.cluster import state
from src.graph.hierarchy import get_expand_preview, get_collapse_preview

logger = logging.getLogger(__name__)


@cluster_bp.route("/<cluster_id>/label", methods=["POST"])
def set_cluster_label(cluster_id: str):
    """Set user label."""
    if state._label_store is None:
        return jsonify({"error": "Label store unavailable"}), 503
    data = request.get_json(silent=True) or {}
    label = (data.get("label") or "").strip()
    if not label:
        return jsonify({"error": "Label cannot be empty"}), 400
    # Label key independent of granularity (hierarchical IDs are stable)
    key = f"spectral_{cluster_id}"
    state._label_store.set_label(key, label)
    return jsonify({"clusterId": cluster_id, "label": label, "labelSource": "user"})


@cluster_bp.route("/<cluster_id>/label", methods=["DELETE"])
def delete_cluster_label(cluster_id: str):
    """Delete user label."""
    if state._label_store is None:
        return jsonify({"error": "Label store unavailable"}), 503
    key = f"spectral_{cluster_id}"
    state._label_store.delete_label(key)
    return jsonify({"status": "deleted"})


@cluster_bp.route("/<cluster_id>/preview", methods=["GET"])
@_require_loaded
def preview_cluster(cluster_id: str):
    """Return expand/collapse preview without mutating state."""
    granularity = request.args.get("n", 25, type=int)
    granularity = max(5, min(500, granularity))
    expanded_arg = request.args.get("expanded", "")
    expanded_ids: Set[str] = set([e for e in expanded_arg.split(",") if e])
    collapsed_arg = request.args.get("collapsed", "")
    collapsed_ids: Set[str] = set([c for c in collapsed_arg.split(",") if c])
    visible_arg = request.args.get("visible", "")
    visible_ids: Set[str] = set([v for v in visible_arg.split(",") if v])
    budget = request.args.get("budget", 25, type=int)
    budget = max(5, budget)
    expand_depth = request.args.get("expand_depth", 0.5, type=float)
    expand_depth = max(0.0, min(1.0, expand_depth))
    lens = _parse_lens()

    active_spectral = state._spectral_result
    if lens == "tpot" and state._tpot_spectral is not None:
        active_spectral = state._tpot_spectral

    cache_key = _make_cache_key(granularity, None, expanded_ids, collapsed_ids, 0.0, expand_depth, lens=lens)

    # Try to reuse cached view to avoid recompute during preview
    cached_view = state._cache.get(cache_key)
    if cached_view:
        current_visible = len(visible_ids) if visible_ids else len(cached_view.get("clusters", []))
        logger.info(
            "preview cache hit: cluster=%s n=%d expanded=%d visible=%d budget=%d lens=%s",
            cluster_id, granularity, len(expanded_ids), current_visible, budget, lens
        )
        view_clusters = cached_view.get("clusters", [])
    else:
        current_visible = len(visible_ids) if visible_ids else (len(expanded_ids) + granularity)
        view_clusters = None

    n_micro = active_spectral.micro_centroids.shape[0] if active_spectral.micro_centroids is not None else len(active_spectral.node_ids)

    current_visible = current_visible if cached_view else (len(visible_ids) if visible_ids else (len(expanded_ids) + granularity))
    expand_preview = get_expand_preview(
        active_spectral.linkage_matrix,
        n_micro,
        cluster_id,
        current_visible,
        budget,
        expand_depth=expand_depth,
    )
    collapse_preview = get_collapse_preview(
        active_spectral.linkage_matrix,
        n_micro,
        cluster_id,
        visible_ids if visible_ids else expanded_ids,
    )
    # Optionally enrich collapse with cached visible set (if available)
    if cached_view and not visible_ids:
        collapse_preview["visible_count"] = current_visible
    return jsonify({"expand": expand_preview, "collapse": collapse_preview, "cache_hit": bool(cached_view)})
