"""Flask routes for hierarchical cluster visualization (expand/collapse)."""
from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

import numpy as np
import pandas as pd
import scipy.sparse as sp
from flask import Blueprint, jsonify, request

from src.graph.clusters import ClusterLabelStore
from src.graph.hierarchy import (
    build_hierarchical_view,
    get_collapse_preview,
    get_expand_preview,
)
from src.graph.spectral import load_spectral_result

logger = logging.getLogger(__name__)

cluster_bp = Blueprint("clusters", __name__, url_prefix="/api/clusters")


@dataclass
class CacheEntry:
    created_at: float
    view: dict


class ClusterCache:
    """Simple LRU cache with TTL for cluster views."""

    def __init__(self, max_entries: int = 20, ttl_seconds: int = 600) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._entries: OrderedDict[Tuple, CacheEntry] = OrderedDict()

    def get(self, key: Tuple) -> Optional[dict]:
        now = time.time()
        entry = self._entries.get(key)
        if not entry:
            return None
        if now - entry.created_at > self.ttl_seconds:
            self._entries.pop(key, None)
            return None
        # refresh LRU
        self._entries.move_to_end(key)
        return entry.view

    def set(self, key: Tuple, view: dict) -> None:
        if key in self._entries:
            self._entries.move_to_end(key)
        self._entries[key] = CacheEntry(created_at=time.time(), view=view)
        if len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)


# Global state
_spectral_result = None
_adjacency = None
_node_metadata: Dict[str, Dict] = {}
_node_id_to_idx: Dict[str, int] = {}  # For in-degree lookups
_louvain_communities: Dict[str, int] = {}  # Louvain community mapping
_label_store: Optional[ClusterLabelStore] = None
_cache = ClusterCache()


def _safe_int(val, default=0) -> int:
    """Convert value to int, handling NaN and None."""
    if val is None:
        return default
    if isinstance(val, float) and np.isnan(val):
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _get_follower_count(node_id: str) -> int:
    """Get follower count with in-degree fallback."""
    meta = _node_metadata.get(str(node_id), {})
    followers = _safe_int(meta.get("num_followers"))
    
    # Fallback to in-degree if followers is 0
    if followers == 0 and _adjacency is not None and _node_id_to_idx:
        idx = _node_id_to_idx.get(str(node_id))
        if idx is not None:
            followers = int(_adjacency[:, idx].sum())
    
    return followers


def _load_metadata(nodes_df: pd.DataFrame) -> Dict[str, Dict]:
    meta = {}
    for _, row in nodes_df.iterrows():
        node_id = str(row["node_id"])
        meta[node_id] = {
            "username": row.get("username"),
            "display_name": row.get("display_name"),
            "num_followers": _safe_int(row.get("num_followers")),
            "num_following": _safe_int(row.get("num_following")),
            "bio": row.get("bio"),
            "location": row.get("location"),
            "profile_image_url": row.get("profile_image_url"),
        }
    return meta


def _load_louvain(data_dir: Path) -> Dict[str, int]:
    lou_path = data_dir / "graph_snapshot.louvain.json"
    if lou_path.exists():
        try:
            return json.loads(lou_path.read_text())
        except Exception:
            return pd.read_json(lou_path, typ="series").to_dict()
    logger.warning("Louvain sidecar not found at %s; hybrid weight will be spectral-only", lou_path)
    return {}


def _build_adjacency(edges_df: pd.DataFrame, node_ids: np.ndarray) -> sp.csr_matrix:
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    rows, cols, data = [], [], []
    for _, row in edges_df.iterrows():
        src = id_to_idx.get(str(row["source"]))
        tgt = id_to_idx.get(str(row["target"]))
        if src is None or tgt is None:
            continue
        rows.append(src)
        cols.append(tgt)
        data.append(1.0)
        if bool(row.get("mutual")):
            rows.append(tgt)
            cols.append(src)
            data.append(1.0)
    adjacency = sp.csr_matrix((data, (rows, cols)), shape=(len(node_ids), len(node_ids)))
    return adjacency


def _make_cache_key(granularity: int, ego: Optional[str], expanded: Set[str], louvain_weight: float = 0.0, expand_depth: float = 0.5) -> Tuple:
    return (granularity, ego or "", ",".join(sorted(expanded)), round(louvain_weight, 2), round(expand_depth, 2))


def init_cluster_routes(app, data_dir: Path = Path("data")) -> None:
    """Initialize and register cluster routes."""
    global _spectral_result, _adjacency, _node_metadata, _node_id_to_idx, _louvain_communities, _label_store

    try:
        base = data_dir / "graph_snapshot"
        _spectral_result = load_spectral_result(base)
        nodes_df = pd.read_parquet(data_dir / "graph_snapshot.nodes.parquet")
        edges_df = pd.read_parquet(data_dir / "graph_snapshot.edges.parquet")
        _node_metadata = _load_metadata(nodes_df)
        node_ids = _spectral_result.node_ids
        _adjacency = _build_adjacency(edges_df, node_ids)
        _label_store = ClusterLabelStore(data_dir / "clusters.db")
        
        # Build node_id -> index mapping for in-degree lookups
        _node_id_to_idx = {str(nid): i for i, nid in enumerate(node_ids)}
        
        # Load Louvain communities
        _louvain_communities = _load_louvain(data_dir)

        if _spectral_result.micro_labels is not None:
            n_micro = len(np.unique(_spectral_result.micro_labels))
            logger.info(
                "Cluster routes initialized (APPROXIMATE mode): %s nodes -> %s micro-clusters, %s edges",
                len(node_ids), n_micro, _adjacency.count_nonzero()
            )
        else:
            logger.info(
                "Cluster routes initialized (EXACT mode): %s nodes, %s edges",
                len(node_ids), _adjacency.count_nonzero()
            )

        app.register_blueprint(cluster_bp)
    except Exception as exc:
        logger.exception("Failed to initialize cluster routes: %s", exc)
        # Do not register blueprint if we failed to load data


@cluster_bp.route("", methods=["GET"])
def get_clusters():
    """Return hierarchical cluster view with expand/collapse support."""
    if _spectral_result is None or _adjacency is None:
        return jsonify({"error": "Cluster data not loaded"}), 503

    granularity = request.args.get("n", 25, type=int)
    granularity = max(5, min(500, granularity))
    ego = request.args.get("ego", None, type=str)
    expanded_arg = request.args.get("expanded", "")
    expanded_ids: Set[str] = set([e for e in expanded_arg.split(",") if e])
    budget = request.args.get("budget", 25, type=int)
    budget = max(5, budget)
    louvain_weight = request.args.get("wl", 0.0, type=float)
    louvain_weight = max(0.0, min(1.0, louvain_weight))
    expand_depth = request.args.get("expand_depth", 0.5, type=float)
    expand_depth = max(0.0, min(1.0, expand_depth))

    cache_key = _make_cache_key(granularity, ego, expanded_ids, louvain_weight, expand_depth)
    cached = _cache.get(cache_key)
    if cached:
        logger.info(
            "clusters cache hit: n=%d budget=%d expanded=%d wl=%.2f depth=%.2f visible=%d budget_rem=%s",
            granularity,
            budget,
            len(expanded_ids),
            louvain_weight,
            expand_depth,
            len((cached or {}).get("clusters", [])),
            (cached or {}).get("meta", {}).get("budget_remaining"),
        )
        return jsonify(cached | {"cache_hit": True})

    start_build = time.time()
    view = build_hierarchical_view(
        linkage_matrix=_spectral_result.linkage_matrix,
        micro_labels=_spectral_result.micro_labels if _spectral_result.micro_labels is not None else np.arange(len(_spectral_result.node_ids)),
        micro_centroids=_spectral_result.micro_centroids if _spectral_result.micro_centroids is not None else _spectral_result.embedding,
        node_ids=_spectral_result.node_ids,
        adjacency=_adjacency,
        node_metadata=_node_metadata,
        base_granularity=granularity,
        expanded_ids=expanded_ids,
        ego_node_id=ego,
        budget=budget,
        label_store=_label_store,
        louvain_communities=_louvain_communities,
        louvain_weight=louvain_weight,
        expand_depth=expand_depth,
    )

    payload = _serialize_hierarchical_view(view)
    logger.info(
        "clusters built: n=%d expanded=%d visible=%d budget_rem=%s wl=%.2f depth=%.2f took=%.3fs",
        granularity,
        len(expanded_ids),
        len(payload.get("clusters", [])),
        payload.get("meta", {}).get("budget_remaining"),
        louvain_weight,
        expand_depth,
        time.time() - start_build,
    )
    _cache.set(cache_key, payload)
    return jsonify(payload)


@cluster_bp.route("/<cluster_id>/members", methods=["GET"])
def get_cluster_members(cluster_id: str):
    """Return members for a cluster from cached view."""
    if _spectral_result is None:
        return jsonify({"error": "Cluster data not loaded"}), 503

    granularity = request.args.get("n", 25, type=int)
    granularity = max(5, min(500, granularity))
    ego = request.args.get("ego", None, type=str)
    expanded_arg = request.args.get("expanded", "")
    expanded_ids: Set[str] = set([e for e in expanded_arg.split(",") if e])
    budget = request.args.get("budget", 25, type=int)
    budget = max(5, budget)
    louvain_weight = request.args.get("wl", 0.0, type=float)
    louvain_weight = max(0.0, min(1.0, louvain_weight))
    expand_depth = request.args.get("expand_depth", 0.5, type=float)
    expand_depth = max(0.0, min(1.0, expand_depth))

    cache_key = _make_cache_key(granularity, ego, expanded_ids, louvain_weight, expand_depth)
    view = _cache.get(cache_key)
    if not view:
        start_build = time.time()
        view_obj = build_hierarchical_view(
            linkage_matrix=_spectral_result.linkage_matrix,
            micro_labels=_spectral_result.micro_labels if _spectral_result.micro_labels is not None else np.arange(len(_spectral_result.node_ids)),
            micro_centroids=_spectral_result.micro_centroids if _spectral_result.micro_centroids is not None else _spectral_result.embedding,
            node_ids=_spectral_result.node_ids,
            adjacency=_adjacency,
            node_metadata=_node_metadata,
            base_granularity=granularity,
            expanded_ids=expanded_ids,
            ego_node_id=ego,
            budget=budget,
            label_store=_label_store,
            louvain_communities=_louvain_communities,
            louvain_weight=louvain_weight,
            expand_depth=expand_depth,
        )
        view = _serialize_hierarchical_view(view_obj)
        logger.info(
            "member view built: n=%d expanded=%d visible=%d wl=%.2f depth=%.2f took=%.3fs",
            granularity,
            len(expanded_ids),
            len(view.get("clusters", [])),
            louvain_weight,
            expand_depth,
            time.time() - start_build,
        )
        _cache.set(cache_key, view)

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
                meta = _node_metadata.get(str(nid), {})
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


@cluster_bp.route("/<cluster_id>/label", methods=["POST"])
def set_cluster_label(cluster_id: str):
    """Set user label."""
    if _label_store is None:
        return jsonify({"error": "Label store unavailable"}), 503
    data = request.get_json(silent=True) or {}
    label = (data.get("label") or "").strip()
    if not label:
        return jsonify({"error": "Label cannot be empty"}), 400
    # Label key independent of granularity (hierarchical IDs are stable)
    key = f"spectral_{cluster_id}"
    _label_store.set_label(key, label)
    return jsonify({"clusterId": cluster_id, "label": label, "labelSource": "user"})


@cluster_bp.route("/<cluster_id>/label", methods=["DELETE"])
def delete_cluster_label(cluster_id: str):
    """Delete user label."""
    if _label_store is None:
        return jsonify({"error": "Label store unavailable"}), 503
    key = f"spectral_{cluster_id}"
    _label_store.delete_label(key)
    return jsonify({"status": "deleted"})


@cluster_bp.route("/<cluster_id>/preview", methods=["GET"])
def preview_cluster(cluster_id: str):
    """Return expand/collapse preview without mutating state."""
    if _spectral_result is None:
        return jsonify({"error": "Cluster data not loaded"}), 503
    granularity = request.args.get("n", 25, type=int)
    granularity = max(5, min(500, granularity))
    expanded_arg = request.args.get("expanded", "")
    expanded_ids: Set[str] = set([e for e in expanded_arg.split(",") if e])
    visible_arg = request.args.get("visible", "")
    visible_ids: Set[str] = set([v for v in visible_arg.split(",") if v])
    budget = request.args.get("budget", 25, type=int)
    budget = max(5, budget)
    expand_depth = request.args.get("expand_depth", 0.5, type=float)
    expand_depth = max(0.0, min(1.0, expand_depth))
    cache_key = _make_cache_key(granularity, None, expanded_ids, 0.0, expand_depth)

    # Try to reuse cached view to avoid recompute during preview
    cached_view = _cache.get(cache_key)
    if cached_view:
        current_visible = len(visible_ids) if visible_ids else len(cached_view.get("clusters", []))
        logger.info(
            "preview cache hit: cluster=%s n=%d expanded=%d visible=%d budget=%d",
            cluster_id, granularity, len(expanded_ids), current_visible, budget
        )
        view_clusters = cached_view.get("clusters", [])
    else:
        current_visible = len(visible_ids) if visible_ids else (len(expanded_ids) + granularity)
        view_clusters = None

    n_micro = _spectral_result.micro_centroids.shape[0] if _spectral_result.micro_centroids is not None else len(_spectral_result.node_ids)

    current_visible = current_visible if cached_view else (len(visible_ids) if visible_ids else (len(expanded_ids) + granularity))
    expand_preview = get_expand_preview(
        _spectral_result.linkage_matrix,
        n_micro,
        cluster_id,
        current_visible,
        budget,
        expand_depth=expand_depth,
    )
    collapse_preview = get_collapse_preview(
        _spectral_result.linkage_matrix,
        n_micro,
        cluster_id,
        visible_ids if visible_ids else expanded_ids,
    )
    # Optionally enrich collapse with cached visible set (if available)
    if cached_view and not visible_ids:
        collapse_preview["visible_count"] = current_visible
    return jsonify({"expand": expand_preview, "collapse": collapse_preview, "cache_hit": bool(cached_view)})


def _serialize_hierarchical_view(view) -> dict:
    """Serialize HierarchicalViewData to JSON-friendly dict."""
    max_conn = max((e.connectivity for e in view.edges), default=1.0)
    if max_conn <= 0:
        max_conn = 1.0

    def serialize_cluster(c):
        return {
            "id": c.id,
            "parentId": c.parent_id,
            "childrenIds": list(c.children_ids) if c.children_ids else [],
            "isLeaf": c.is_leaf,
            "size": c.size,
            "label": c.label,
            "labelSource": c.label_source,
            "representativeHandles": c.representative_handles,
            "containsEgo": c.contains_ego,
            "centroid": c.centroid.tolist(),
            "memberIds": c.member_node_ids,
        }

    payload = {
        "clusters": [serialize_cluster(c) for c in view.clusters],
        "edges": [
            {
                "source": e.source_id,
                "target": e.target_id,
                "rawCount": e.raw_count,
                "connectivity": e.connectivity,
                "opacity": float(min(1.0, e.connectivity / max_conn)),
            }
            for e in view.edges
        ],
        "positions": view.positions or {},
        "ego_cluster_id": view.ego_cluster_id,
        "total_nodes": view.total_nodes,
        "meta": {
            "n_micro_clusters": view.n_micro_clusters,
            "budget": view.budget,
            "budget_remaining": view.budget_remaining,
            "expanded": view.expanded_ids,
        },
        "cache_hit": False,
    }
    return payload
