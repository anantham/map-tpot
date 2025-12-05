"""Flask routes for spectral cluster visualization."""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import json
import numpy as np
import pandas as pd
import scipy.sparse as sp
from flask import Blueprint, jsonify, request

from src.graph.clusters import (
    ClusterInfo,
    ClusterLabelStore,
    ClusterViewData,
    build_cluster_view,
)
from src.graph.spectral import load_spectral_result

logger = logging.getLogger(__name__)

cluster_bp = Blueprint("clusters", __name__, url_prefix="/api/clusters")


@dataclass
class CacheEntry:
    created_at: float
    view: ClusterViewData


class ClusterCache:
    """Simple LRU cache with TTL for cluster views."""

    def __init__(self, max_entries: int = 20, ttl_seconds: int = 600) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._entries: OrderedDict[Tuple, CacheEntry] = OrderedDict()

    def get(self, key: Tuple) -> Optional[ClusterViewData]:
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

    def set(self, key: Tuple, view: ClusterViewData) -> None:
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
_louvain_map: Dict[str, int] = {}
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
            # fallback to pandas if JSON parsing fails
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
        # If mutual flag is set, add reverse edge weight
        if bool(row.get("mutual")):
            rows.append(tgt)
            cols.append(src)
            data.append(1.0)
    adjacency = sp.csr_matrix((data, (rows, cols)), shape=(len(node_ids), len(node_ids)))
    return adjacency


def _positions_from_pca(clusters, dims: int = 2) -> Dict[str, list]:
    """Project cluster centroids to 2D via PCA (simple SVD-based)."""
    if not clusters:
        logger.warning("_positions_from_pca: no clusters provided")
        return {}
    
    centroids = np.stack([c.centroid for c in clusters])
    centroids = centroids.astype(np.float64)
    
    # Check for NaN/Inf
    if np.any(~np.isfinite(centroids)):
        logger.warning("_positions_from_pca: centroids contain NaN/Inf, replacing with 0")
        centroids = np.nan_to_num(centroids, nan=0.0, posinf=0.0, neginf=0.0)
    
    centroids -= centroids.mean(axis=0, keepdims=True)
    
    if centroids.shape[0] == 1:
        return {clusters[0].id: [0.0, 0.0]}

    # SVD for PCA
    try:
        U, S, Vt = np.linalg.svd(centroids, full_matrices=False)
        comps = Vt[:dims].T  # (d x 2)
        coords = centroids @ comps
    except Exception as e:
        logger.error("_positions_from_pca: SVD failed: %s", e)
        # Fallback: random positions
        coords = np.random.randn(len(clusters), dims) * 100
    
    positions = {}
    for cluster, pos in zip(clusters, coords):
        x = float(pos[0]) if np.isfinite(pos[0]) else 0.0
        y = float(pos[1]) if np.isfinite(pos[1]) else 0.0
        positions[cluster.id] = [x, y]
    
    logger.info(
        "_positions_from_pca: %d clusters, position range x=[%.2f, %.2f] y=[%.2f, %.2f]",
        len(positions),
        min(p[0] for p in positions.values()),
        max(p[0] for p in positions.values()),
        min(p[1] for p in positions.values()),
        max(p[1] for p in positions.values()),
    )
    return positions


def _make_cache_key(granularity: int, ego: Optional[str], weight_bucket: float, focus: Optional[str]) -> Tuple:
    return (granularity, ego or "", weight_bucket, focus or "")


def init_cluster_routes(app, data_dir: Path = Path("data")) -> None:
    """Initialize and register cluster routes."""
    global _spectral_result, _adjacency, _node_metadata, _label_store, _louvain_map

    try:
        base = data_dir / "graph_snapshot"
        _spectral_result = load_spectral_result(base)
        nodes_df = pd.read_parquet(data_dir / "graph_snapshot.nodes.parquet")
        edges_df = pd.read_parquet(data_dir / "graph_snapshot.edges.parquet")
        _node_metadata = _load_metadata(nodes_df)
        node_ids = _spectral_result.node_ids
        _adjacency = _build_adjacency(edges_df, node_ids)
        _louvain_map = _load_louvain(data_dir)
        _label_store = ClusterLabelStore(data_dir / "clusters.db")
        
        # Log approximate mode info
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
    """Return cluster view for given granularity and weights."""
    if _spectral_result is None or _adjacency is None:
        return jsonify({"error": "Cluster data not loaded"}), 503

    granularity = request.args.get("n", 25, type=int)
    granularity = max(5, min(500, granularity))
    ego = request.args.get("ego", None, type=str)
    focus = request.args.get("focus", None, type=str)
    wl = request.args.get("wl", 0.0, type=float)
    wl = min(1.0, max(0.0, wl))
    ws = round(1.0 - wl, 1)
    wl_bucket = round(wl, 1)

    cache_key = _make_cache_key(granularity, ego, wl_bucket, focus)
    cached = _cache.get(cache_key)
    if cached:
        return jsonify(_serialize_view(cached, {"spectral": ws, "louvain": wl_bucket}, True))

    weights = {"spectral": ws, "louvain": wl_bucket}
    view = build_cluster_view(
        embedding=_spectral_result.embedding,
        linkage_matrix=_spectral_result.linkage_matrix,
        node_ids=_spectral_result.node_ids,
        adjacency=_adjacency,
        node_metadata=_node_metadata,
        granularity=granularity,
        ego_node_id=ego,
        label_store=_label_store,
        louvain_communities=_louvain_map,
        signal_weights=weights,
        # Pass approximate mode data
        micro_labels=_spectral_result.micro_labels,
        micro_centroids=_spectral_result.micro_centroids,
    )

    positions = _positions_from_pca(view.clusters)
    view.positions = positions
    _cache.set(cache_key, view)

    return jsonify(_serialize_view(view, weights, False))


@cluster_bp.route("/<cluster_id>/members", methods=["GET"])
def get_cluster_members(cluster_id: str):
    """Return members for a cluster from cached view."""
    if _spectral_result is None:
        return jsonify({"error": "Cluster data not loaded"}), 503

    granularity = request.args.get("n", 25, type=int)
    granularity = max(5, min(500, granularity))
    wl = request.args.get("wl", 0.0, type=float)
    wl = min(1.0, max(0.0, wl))
    wl_bucket = round(wl, 1)
    ws = round(1.0 - wl_bucket, 1)
    ego = request.args.get("ego", None, type=str)
    focus = request.args.get("focus", None, type=str)
    cache_key = _make_cache_key(granularity, ego, wl_bucket, focus)

    view = _cache.get(cache_key)
    if not view:
        weights = {"spectral": ws, "louvain": wl_bucket}
        view = build_cluster_view(
            embedding=_spectral_result.embedding,
            linkage_matrix=_spectral_result.linkage_matrix,
            node_ids=_spectral_result.node_ids,
            adjacency=_adjacency,
            node_metadata=_node_metadata,
            granularity=granularity,
            ego_node_id=ego,
            label_store=_label_store,
            louvain_communities=_louvain_map,
            signal_weights=weights,
            micro_labels=_spectral_result.micro_labels,
            micro_centroids=_spectral_result.micro_centroids,
        )
        positions = _positions_from_pca(view.clusters)
        view.positions = positions
        _cache.set(cache_key, view)

    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)

    members = []
    total = 0
    for cluster in view.clusters:
        if cluster.id == cluster_id:
            total = len(cluster.member_ids)
            slice_ids = cluster.member_ids[offset : offset + limit]
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
    granularity = request.args.get("n", 25, type=int)
    wl = request.args.get("wl", 0.0, type=float)
    wl = min(1.0, max(0.0, wl))
    ws = round(1.0 - round(wl, 1), 1)
    key = f"spectral_w{ws:.1f}_l{round(wl,1):.1f}_n{granularity}_c{cluster_id.replace('cluster_', '')}"
    _label_store.set_label(key, label)
    return jsonify({"clusterId": cluster_id, "label": label, "labelSource": "user"})


@cluster_bp.route("/<cluster_id>/label", methods=["DELETE"])
def delete_cluster_label(cluster_id: str):
    """Delete user label."""
    if _label_store is None:
        return jsonify({"error": "Label store unavailable"}), 503
    granularity = request.args.get("n", 25, type=int)
    wl = request.args.get("wl", 0.0, type=float)
    wl = min(1.0, max(0.0, wl))
    ws = round(1.0 - round(wl, 1), 1)
    key = f"spectral_w{ws:.1f}_l{round(wl,1):.1f}_n{granularity}_c{cluster_id.replace('cluster_', '')}"
    _label_store.delete_label(key)
    return jsonify({"status": "deleted"})


def _serialize_cluster(cluster: ClusterInfo) -> dict:
    return {
        "id": cluster.id,
        "size": cluster.size,
        "label": cluster.label,
        "labelSource": cluster.label_source,
        "representativeHandles": cluster.representative_handles,
        "containsEgo": cluster.contains_ego,
        "centroid": cluster.centroid.tolist(),
    }


def _serialize_view(view: ClusterViewData, weights: Dict[str, float], cache_hit: bool) -> dict:
    max_w = max((e.weight for e in view.edges), default=1.0)
    if max_w <= 0:
        max_w = 1.0
    return {
        "clusters": [_serialize_cluster(c) for c in view.clusters],
        "individual_nodes": view.individual_nodes,
        "edges": [
            {
                "source": e.source_id,
                "target": e.target_id,
                "weight": e.weight,
                "rawCount": e.raw_count,
                "opacity": float(min(1.0, e.weight / max_w)),
            }
            for e in view.edges
        ],
        "positions": view.positions or {},
        "ego_cluster_id": view.ego_cluster_id,
        "granularity": view.granularity,
        "total_nodes": view.total_nodes,
        "weights": weights,
        "cache_hit": cache_hit,
        "meta": {
            "spectral_dims": view.clusters[0].centroid.shape[0] if view.clusters else 0,
            "approximate_mode": view.approximate_mode if hasattr(view, 'approximate_mode') else False,
        },
    }
