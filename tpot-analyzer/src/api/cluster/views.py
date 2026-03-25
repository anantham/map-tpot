"""Main cluster view endpoint."""
from __future__ import annotations

import json
import logging
import time
from typing import Set
from uuid import uuid4

import numpy as np
from flask import jsonify, request

from src.api.responses import error_response

from src.api.cluster.state import (
    cluster_bp,
    _require_loaded,
    _parse_lens,
    _make_cache_key,
    _serialize_hierarchical_view,
)
from src.api.cluster import state
from src.graph.hierarchy import build_hierarchical_view

logger = logging.getLogger(__name__)


@cluster_bp.route("", methods=["GET"])
@_require_loaded
def get_clusters():
    """Return hierarchical cluster view with expand/collapse support."""
    req_arg = request.args.get("reqId", type=str)
    req_id = req_arg if req_arg else uuid4().hex[:8]
    start_total = time.time()
    import concurrent.futures

    granularity = request.args.get("n", 25, type=int)
    granularity = max(5, min(500, granularity))
    ego = request.args.get("ego", None, type=str)
    expanded_arg = request.args.get("expanded", "")
    expanded_ids: Set[str] = set([e for e in expanded_arg.split(",") if e])
    collapsed_arg = request.args.get("collapsed", "")
    collapsed_ids: Set[str] = set([c for c in collapsed_arg.split(",") if c])
    focus_leaf = request.args.get("focus_leaf", "", type=str) or None
    budget = request.args.get("budget", 25, type=int)
    budget = max(5, budget)
    louvain_weight = request.args.get("wl", 0.0, type=float)
    louvain_weight = max(0.0, min(1.0, louvain_weight))
    expand_depth = request.args.get("expand_depth", 0.5, type=float)
    expand_depth = max(0.0, min(1.0, expand_depth))
    alpha = request.args.get("alpha", 0.0, type=float)
    alpha = max(0.0, min(1.0, alpha))
    lens = _parse_lens()

    # Select spectral + adjacency + metadata based on lens
    active_spectral = state._spectral_result
    active_adjacency = state._adjacency
    active_metadata = state._node_metadata
    active_alpha = 0.0

    if lens == "tpot" and state._tpot_spectral is not None:
        active_spectral = state._tpot_spectral
        active_adjacency = state._tpot_adjacency if state._tpot_adjacency is not None else state._adjacency
        active_metadata = state._tpot_node_metadata if state._tpot_node_metadata else state._node_metadata
    elif alpha > 0 and state._spectral_presets:
        # Select spectral preset for this alpha (snap to nearest available)
        best_alpha = min(state._alpha_presets, key=lambda a: abs(a - alpha))
        if best_alpha in state._spectral_presets:
            active_spectral = state._spectral_presets[best_alpha]
            active_alpha = best_alpha

    logger.info(
        "clusters start req=%s n=%d budget=%d expanded=%d collapsed=%d wl=%.2f depth=%.2f alpha=%.2f",
        req_id,
        granularity,
        budget,
        len(expanded_ids),
        len(collapsed_ids),
        louvain_weight,
        expand_depth,
        active_alpha,
    )

    cache_key = _make_cache_key(granularity, ego, expanded_ids, collapsed_ids, louvain_weight, expand_depth, focus_leaf, active_alpha, lens)

    # Deduplicate identical in-flight builds
    inflight = state._cache.inflight_get(cache_key)
    if inflight:
        logger.info(
            "clusters inflight hit req=%s waiting_for=%s",
            req_id,
            getattr(inflight, "req_id", "unknown"),
        )
        wait_start = time.time()
        try:
            payload = inflight.result()
            if not isinstance(payload, dict):
                logger.info("clusters inflight payload not dict; serializing req=%s type=%s", req_id, type(payload))
                payload = _serialize_hierarchical_view(payload)
            wait_ms = int((time.time() - wait_start) * 1000)
            total_ms = int((time.time() - start_total) * 1000)
            server_timing = (payload.get("server_timing") or {}).copy()
            server_timing.update(
                {
                    "req_id": req_id,
                    "source_req_id": getattr(inflight, "req_id", None),
                    "served_from": "inflight",
                    "inflight_wait_ms": wait_ms,
                    "t_total_ms": total_ms,
                }
            )
            payload = {**payload, "server_timing": server_timing}
            logger.info(
                "clusters inflight resolved req=%s waited_ms=%d visible=%d budget_rem=%s total_ms=%d",
                req_id,
                wait_ms,
                len((payload or {}).get("clusters", [])),
                (payload or {}).get("meta", {}).get("budget_remaining"),
                total_ms,
            )
            return jsonify(payload | {"cache_hit": True, "deduped": True, "inflight_wait_ms": wait_ms})
        except Exception as exc:  # pragma: no cover
            logger.warning("clusters inflight failed req=%s err=%s", req_id, exc)
            # fall through to rebuild
    cached = state._cache.get(cache_key)
    if cached:
        server_timing = (cached.get("server_timing") or {}).copy()
        total_ms = int((time.time() - start_total) * 1000)
        server_timing.update(
            {
                "req_id": req_id,
                "served_from": "cache",
                "t_total_ms": total_ms,
            }
        )
        payload = {**cached, "server_timing": server_timing}
        logger.info(
            "clusters cache hit req=%s n=%d budget=%d expanded=%d wl=%.2f depth=%.2f visible=%d budget_rem=%s total_ms=%d",
            req_id,
            granularity,
            budget,
            len(expanded_ids),
            louvain_weight,
            expand_depth,
            len((payload or {}).get("clusters", [])),
            (payload or {}).get("meta", {}).get("budget_remaining"),
            total_ms,
        )
        return jsonify(payload | {"cache_hit": True})

    start_build = time.time()

    def _compute_view():
        return build_hierarchical_view(
            linkage_matrix=active_spectral.linkage_matrix,
            micro_labels=active_spectral.micro_labels if active_spectral.micro_labels is not None else np.arange(len(active_spectral.node_ids)),
            micro_centroids=active_spectral.micro_centroids if active_spectral.micro_centroids is not None else active_spectral.embedding,
            node_ids=active_spectral.node_ids,
            adjacency=active_adjacency,
            node_metadata=active_metadata,
            base_granularity=granularity,
                expanded_ids=expanded_ids,
                collapsed_ids=collapsed_ids,
                focus_leaf_id=focus_leaf,
                ego_node_id=ego,
                budget=budget,
                label_store=state._label_store,
            louvain_communities=state._louvain_communities,
            louvain_weight=louvain_weight,
            expand_depth=expand_depth,
        )

    future = concurrent.futures.Future()
    future.req_id = req_id  # type: ignore[attr-defined]
    state._cache.inflight_set(cache_key, future)

    build_duration = serialize_duration = total_duration = None
    try:
        view = _compute_view()
        build_duration = time.time() - start_build

        start_serialize = time.time()
        payload = _serialize_hierarchical_view(view)
        # Patch per-request values into meta
        if "meta" in payload:
            payload["meta"]["activeAlpha"] = active_alpha
            payload["meta"]["activeLens"] = lens
        serialize_duration = time.time() - start_serialize
        total_duration = time.time() - start_total

        future.set_result(payload)
    except Exception as exc:
        logger.exception("clusters build failed req=%s expanded=%s collapsed=%s: %s", req_id, expanded_ids, collapsed_ids, exc)
        state._cache.inflight_clear(cache_key)
        return error_response("cluster build failed", status=500, details={"req_id": req_id})
    finally:
        state._cache.inflight_clear(cache_key)

    server_timing = {
        "req_id": req_id,
        "served_from": "build",
        "t_build_ms": int(build_duration * 1000) if build_duration is not None else None,
        "t_serialize_ms": int(serialize_duration * 1000) if serialize_duration is not None else None,
        "t_total_ms": int(total_duration * 1000) if total_duration is not None else None,
    }
    payload = {**payload, "server_timing": server_timing}

    logger.info(
        "clusters built req=%s n=%d expanded=%d visible=%d budget_rem=%s wl=%.2f depth=%.2f "
        "t_build=%.3fs t_serialize=%.3fs t_total=%.3fs",
        req_id,
        granularity,
        len(expanded_ids),
        len(payload.get("clusters", [])),
        payload.get("meta", {}).get("budget_remaining"),
        louvain_weight,
        expand_depth,
        build_duration,
        serialize_duration,
        total_duration,
    )
    try:
        logger.info(
            "clusters response req=%s clusters=%d cache_hit=%s expanded=%d collapsed=%d budget=%d body_bytes=%d",
            req_id,
            len(payload.get("clusters", [])),
            payload.get("cache_hit"),
            len(expanded_ids),
            len(collapsed_ids),
            budget,
            len(json.dumps(payload)),
        )
    except Exception:
        logger.warning("clusters response logging failed for req=%s", req_id)
    state._cache.set(cache_key, payload)
    return jsonify(payload)
