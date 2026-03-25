"""Sidebar routes: cluster members and tag summary."""
from __future__ import annotations

import logging
import time
from typing import Dict, Set

import numpy as np
from flask import jsonify, request

from src.api.responses import error_response

from src.api.cluster.state import (
    cluster_bp,
    _require_loaded,
    _parse_lens,
    _require_ego,
    _make_cache_key,
    _get_follower_count,
    _get_tag_store,
    _serialize_hierarchical_view,
)
from src.api.cluster import state
from src.graph.hierarchy import build_hierarchical_view

logger = logging.getLogger(__name__)


@cluster_bp.route("/<cluster_id>/members", methods=["GET"])
@_require_loaded
def get_cluster_members(cluster_id: str):
    """Return members for a cluster from cached view."""

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
    lens = _parse_lens()

    # Select spectral/adjacency/metadata based on lens
    active_spectral = state._spectral_result
    active_adjacency = state._adjacency
    active_metadata = state._node_metadata
    if lens == "tpot" and state._tpot_spectral is not None:
        active_spectral = state._tpot_spectral
        active_adjacency = state._tpot_adjacency if state._tpot_adjacency is not None else state._adjacency
        active_metadata = state._tpot_node_metadata if state._tpot_node_metadata else state._node_metadata

    cache_key = _make_cache_key(granularity, ego, expanded_ids, collapsed_ids, louvain_weight, expand_depth, focus_leaf, lens=lens)
    view = state._cache.get(cache_key)
    if not view:
        start_build = time.time()
        view_obj = build_hierarchical_view(
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
        view = _serialize_hierarchical_view(view_obj)
        logger.info(
            "member view built: n=%d expanded=%d visible=%d wl=%.2f depth=%.2f lens=%s took=%.3fs",
            granularity,
            len(expanded_ids),
            len(view.get("clusters", [])),
            louvain_weight,
            expand_depth,
            lens,
            time.time() - start_build,
        )
        state._cache.set(cache_key, view)

    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)

    members = []
    total = 0
    found_cluster = None
    for cluster in view["clusters"]:
        if cluster["id"] == cluster_id:
            total = len(cluster.get("memberIds", []))
            slice_ids = cluster.get("memberIds", [])[offset : offset + limit]
            for nid in slice_ids:
                meta = active_metadata.get(str(nid), {})
                members.append(
                    {
                        "id": str(nid),
                        "username": meta.get("username"),
                        "displayName": meta.get("display_name"),
                        "numFollowers": _get_follower_count(nid),
                    }
                )
            found_cluster = {"size": cluster.get("size"), "memberIds_len": len(cluster.get("memberIds", []))}
            break
    logger.info(
        "members fetched: cluster=%s found=%s total=%d slice=%d offset=%d limit=%d expanded=%d n=%d budget=%d",
        cluster_id,
        bool(found_cluster),
        total,
        len(members),
        offset,
        limit,
        len(expanded_ids),
        granularity,
        budget,
    )

    return jsonify(
        {
            "clusterId": cluster_id,
            "members": members,
            "total": total,
            "hasMore": offset + len(members) < total,
        }
    )


@cluster_bp.route("/<cluster_id>/tag_summary", methods=["GET"])
@_require_loaded
def get_cluster_tag_summary(cluster_id: str):
    """Return per-tag counts (IN/NOT IN) for a cluster's members (scoped by ego)."""

    try:
        ego = _require_ego()
    except ValueError as exc:
        return error_response(str(exc))

    granularity = request.args.get("n", 25, type=int)
    granularity = max(5, min(500, granularity))
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
    lens = _parse_lens()

    # Select spectral/adjacency/metadata based on lens
    active_spectral = state._spectral_result
    active_adjacency = state._adjacency
    active_metadata = state._node_metadata
    if lens == "tpot" and state._tpot_spectral is not None:
        active_spectral = state._tpot_spectral
        active_adjacency = state._tpot_adjacency if state._tpot_adjacency is not None else state._adjacency
        active_metadata = state._tpot_node_metadata if state._tpot_node_metadata else state._node_metadata

    cache_key = _make_cache_key(granularity, ego, expanded_ids, collapsed_ids, louvain_weight, expand_depth, focus_leaf, lens=lens)
    view = state._cache.get(cache_key)
    if not view:
        start_build = time.time()
        view_obj = build_hierarchical_view(
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
        view = _serialize_hierarchical_view(view_obj)
        state._cache.set(cache_key, view)
        logger.info(
            "tag_summary view built: cluster=%s n=%d expanded=%d visible=%d lens=%s took=%.3fs",
            cluster_id,
            granularity,
            len(expanded_ids),
            len(view.get("clusters", [])),
            lens,
            time.time() - start_build,
        )

    found = None
    for cluster in view.get("clusters", []):
        if cluster.get("id") == cluster_id:
            found = cluster
            break
    if not found:
        return error_response("Cluster not found", status=404)

    member_ids = [str(v) for v in (found.get("memberIds") or [])]
    total_members = len(member_ids)

    t0 = time.time()
    store = _get_tag_store()
    assignments = store.list_tags_for_accounts(ego=ego, account_ids=member_ids)
    tagged_accounts = set()
    counts: Dict[str, Dict[str, int]] = {}
    for tag in assignments:
        tagged_accounts.add(tag.account_id)
        entry = counts.get(tag.tag)
        if entry is None:
            entry = {"inCount": 0, "notInCount": 0}
            counts[tag.tag] = entry
        if tag.polarity == 1:
            entry["inCount"] += 1
        elif tag.polarity == -1:
            entry["notInCount"] += 1

    tag_counts = []
    for tag_name, entry in counts.items():
        in_count = int(entry.get("inCount") or 0)
        not_in_count = int(entry.get("notInCount") or 0)
        tag_counts.append(
            {
                "tag": tag_name,
                "inCount": in_count,
                "notInCount": not_in_count,
                "score": in_count - not_in_count,
            }
        )
    tag_counts.sort(key=lambda row: (row["score"], row["inCount"]), reverse=True)
    suggested = next((row for row in tag_counts if row["score"] > 0), None)

    compute_ms = int((time.time() - t0) * 1000)
    logger.info(
        "tag_summary computed: cluster=%s ego=%s members=%d tagged_members=%d tags=%d suggested=%s took_ms=%d",
        cluster_id,
        ego,
        total_members,
        len(tagged_accounts),
        len(tag_counts),
        (suggested or {}).get("tag") if suggested else None,
        compute_ms,
    )
    return jsonify(
        {
            "clusterId": cluster_id,
            "ego": ego,
            "totalMembers": total_members,
            "taggedMembers": len(tagged_accounts),
            "tagAssignments": len(assignments),
            "tagCounts": tag_counts,
            "suggestedLabel": suggested,
            "computeMs": compute_ms,
        }
    )
