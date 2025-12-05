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


def _make_cache_key(granularity: int, ego: Optional[str], expanded: Set[str]) -> Tuple:
    return (granularity, ego or "", ",".join(sorted(expanded)))


def init_cluster_routes(app, data_dir: Path = Path("data")) -> None:
    """Initialize and register cluster routes."""
    global _spectral_result, _adjacency, _node_metadata, _label_store

    try:
        base = data_dir / "graph_snapshot"
        _spectral_result = load_spectral_result(base)
        nodes_df = pd.read_parquet(data_dir / "graph_snapshot.nodes.parquet")
        edges_df = pd.read_parquet(data_dir / "graph_snapshot.edges.parquet")
        _node_metadata = _load_metadata(nodes_df)
        node_ids = _spectral_result.node_ids
        _adjacency = _build_adjacency(edges_df, node_ids)
        _label_store = ClusterLabelStore(data_dir / "clusters.db")

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

    cache_key = _make_cache_key(granularity, ego, expanded_ids)
    cached = _cache.get(cache_key)
    if cached:
        return jsonify(cached | {"cache_hit": True})

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
    )

    payload = _serialize_hierarchical_view(view)
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

    cache_key = _make_cache_key(granularity, ego, expanded_ids)
    view = _cache.get(cache_key)
    if not view:
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
        )
        view = _serialize_hierarchical_view(view_obj)
        _cache.set(cache_key, view)

    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)

    members = []
    total = 0
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
                        "numFollowers": _safe_int(meta.get("num_followers")),
                    }
                )
            break

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
    budget = request.args.get("budget", 25, type=int)
    budget = max(5, budget)

    n_micro = _spectral_result.micro_centroids.shape[0] if _spectral_result.micro_centroids is not None else len(_spectral_result.node_ids)

    current_visible = len(expanded_ids) + granularity  # rough upper bound, refined client-side
    expand_preview = get_expand_preview(
        _spectral_result.linkage_matrix,
        n_micro,
        cluster_id,
        current_visible,
        budget,
    )
    collapse_preview = get_collapse_preview(
        _spectral_result.linkage_matrix,
        n_micro,
        cluster_id,
        expanded_ids,
    )
    return jsonify({"expand": expand_preview, "collapse": collapse_preview})


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
