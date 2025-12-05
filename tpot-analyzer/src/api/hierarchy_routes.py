"""Flask routes for hierarchical cluster navigation."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Set

import numpy as np
import pandas as pd
from flask import Blueprint, jsonify, request

from src.graph.hierarchy import (
    HierarchicalCluster,
    HierarchicalEdge,
    build_hierarchical_view,
    get_collapse_preview,
    get_expand_preview,
)
from src.graph.spectral import load_spectral_result
from src.graph.clusters import ClusterLabelStore

logger = logging.getLogger(__name__)

hierarchy_bp = Blueprint("hierarchy", __name__, url_prefix="/api/hierarchy")

# Global state
_spectral_result = None
_adjacency = None
_node_metadata: Dict[str, Dict] = {}
_label_store: Optional[ClusterLabelStore] = None

MAX_BUDGET = 25
DEFAULT_BASE_GRANULARITY = 12


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
            "profile_image_url": row.get("profile_image_url"),
        }
    return meta


def _build_adjacency(edges_df: pd.DataFrame, node_ids: np.ndarray):
    """Build sparse adjacency matrix."""
    import scipy.sparse as sp
    
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
    return sp.csr_matrix((data, (rows, cols)), shape=(len(node_ids), len(node_ids)))


def init_hierarchy_routes(app, data_dir: Path = Path("data")) -> None:
    """Initialize and register hierarchy routes."""
    global _spectral_result, _adjacency, _node_metadata, _label_store

    try:
        base = data_dir / "graph_snapshot"
        _spectral_result = load_spectral_result(base)
        
        if _spectral_result.micro_labels is None:
            logger.warning("Spectral result has no micro_labels - hierarchy routes disabled")
            return
        
        nodes_df = pd.read_parquet(data_dir / "graph_snapshot.nodes.parquet")
        edges_df = pd.read_parquet(data_dir / "graph_snapshot.edges.parquet")
        _node_metadata = _load_metadata(nodes_df)
        _adjacency = _build_adjacency(edges_df, _spectral_result.node_ids)
        _label_store = ClusterLabelStore(data_dir / "clusters.db")
        
        n_micro = len(np.unique(_spectral_result.micro_labels))
        logger.info(
            "Hierarchy routes initialized: %d nodes, %d micro-clusters",
            len(_spectral_result.node_ids), n_micro
        )
        
        app.register_blueprint(hierarchy_bp)
    except Exception as exc:
        logger.exception("Failed to initialize hierarchy routes: %s", exc)


@hierarchy_bp.route("", methods=["GET"])
def get_hierarchy():
    """Get hierarchical cluster view.
    
    Query params:
        base: Base granularity (default 12)
        expanded: Comma-separated list of expanded cluster IDs (e.g., "d_700,d_500")
        ego: Ego node ID for highlighting
        budget: Max clusters allowed (default 25)
    """
    if _spectral_result is None or _spectral_result.micro_labels is None:
        return jsonify({"error": "Hierarchy data not loaded"}), 503
    
    base = request.args.get("base", DEFAULT_BASE_GRANULARITY, type=int)
    base = max(3, min(100, base))
    
    expanded_str = request.args.get("expanded", "")
    expanded_ids = set(expanded_str.split(",")) if expanded_str else set()
    expanded_ids.discard("")  # Remove empty string if present
    
    ego = request.args.get("ego", None, type=str)
    budget = request.args.get("budget", MAX_BUDGET, type=int)
    budget = max(5, min(50, budget))
    
    try:
        view = build_hierarchical_view(
            linkage_matrix=_spectral_result.linkage_matrix,
            micro_labels=_spectral_result.micro_labels,
            micro_centroids=_spectral_result.micro_centroids,
            node_ids=_spectral_result.node_ids,
            adjacency=_adjacency,
            node_metadata=_node_metadata,
            base_granularity=base,
            expanded_ids=expanded_ids,
            ego_node_id=ego,
            budget=budget,
            label_store=_label_store,
        )
        
        return jsonify(_serialize_view(view))
    except Exception as exc:
        logger.exception("Failed to build hierarchy view: %s", exc)
        return jsonify({"error": str(exc)}), 500


@hierarchy_bp.route("/expand-preview/<cluster_id>", methods=["GET"])
def preview_expand(cluster_id: str):
    """Preview what happens when expanding a cluster."""
    if _spectral_result is None or _spectral_result.micro_labels is None:
        return jsonify({"error": "Hierarchy data not loaded"}), 503
    
    current_count = request.args.get("current", 10, type=int)
    budget = request.args.get("budget", MAX_BUDGET, type=int)
    
    n_micro = len(_spectral_result.micro_centroids)
    preview = get_expand_preview(
        _spectral_result.linkage_matrix,
        n_micro,
        cluster_id,
        current_count,
        budget,
    )
    
    return jsonify(preview)


@hierarchy_bp.route("/collapse-preview/<cluster_id>", methods=["GET"])
def preview_collapse(cluster_id: str):
    """Preview what happens when collapsing a cluster."""
    if _spectral_result is None or _spectral_result.micro_labels is None:
        return jsonify({"error": "Hierarchy data not loaded"}), 503
    
    visible_str = request.args.get("visible", "")
    visible_ids = set(visible_str.split(",")) if visible_str else set()
    visible_ids.discard("")
    
    n_micro = len(_spectral_result.micro_centroids)
    preview = get_collapse_preview(
        _spectral_result.linkage_matrix,
        n_micro,
        cluster_id,
        visible_ids,
    )
    
    return jsonify(preview)


@hierarchy_bp.route("/<cluster_id>/members", methods=["GET"])
def get_members(cluster_id: str):
    """Get members of a cluster."""
    if _spectral_result is None:
        return jsonify({"error": "Data not loaded"}), 503
    
    # Parse cluster ID to get dendrogram node
    try:
        node_idx = int(cluster_id.split("_")[1])
    except (IndexError, ValueError):
        return jsonify({"error": "Invalid cluster ID"}), 400
    
    n_micro = len(_spectral_result.micro_centroids)
    
    # Get micro-cluster leaves under this node
    from src.graph.hierarchy import _get_subtree_leaves
    micro_leaves = _get_subtree_leaves(_spectral_result.linkage_matrix, node_idx, n_micro)
    
    # Get all nodes in these micro-clusters
    micro_to_nodes = {}
    for i, micro_idx in enumerate(_spectral_result.micro_labels):
        if micro_idx not in micro_to_nodes:
            micro_to_nodes[micro_idx] = []
        micro_to_nodes[micro_idx].append(i)
    
    member_indices = []
    for micro_idx in micro_leaves:
        member_indices.extend(micro_to_nodes.get(micro_idx, []))
    
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)
    
    total = len(member_indices)
    slice_indices = member_indices[offset:offset + limit]
    
    members = []
    for idx in slice_indices:
        node_id = str(_spectral_result.node_ids[idx])
        meta = _node_metadata.get(node_id, {})
        members.append({
            "id": node_id,
            "username": meta.get("username"),
            "displayName": meta.get("display_name"),
            "numFollowers": _safe_int(meta.get("num_followers")),
        })
    
    return jsonify({
        "clusterId": cluster_id,
        "members": members,
        "total": total,
        "hasMore": offset + len(members) < total,
    })


@hierarchy_bp.route("/<cluster_id>/label", methods=["POST"])
def set_label(cluster_id: str):
    """Set user label for a cluster."""
    if _label_store is None:
        return jsonify({"error": "Label store unavailable"}), 503
    
    data = request.get_json(silent=True) or {}
    label = (data.get("label") or "").strip()
    if not label:
        return jsonify({"error": "Label cannot be empty"}), 400
    
    _label_store.set_label(cluster_id, label)
    return jsonify({"clusterId": cluster_id, "label": label})


@hierarchy_bp.route("/<cluster_id>/label", methods=["DELETE"])
def delete_label(cluster_id: str):
    """Delete user label for a cluster."""
    if _label_store is None:
        return jsonify({"error": "Label store unavailable"}), 503
    
    _label_store.delete_label(cluster_id)
    return jsonify({"status": "deleted"})


def _serialize_cluster(c: HierarchicalCluster) -> dict:
    return {
        "id": c.id,
        "dendrogramNode": c.dendrogram_node,
        "parentId": c.parent_id,
        "childrenIds": list(c.children_ids) if c.children_ids else None,
        "size": c.size,
        "label": c.label,
        "labelSource": c.label_source,
        "representativeHandles": c.representative_handles,
        "containsEgo": c.contains_ego,
        "isLeaf": c.is_leaf,
        "canExpand": c.children_ids is not None,
        "canCollapse": c.parent_id is not None,
    }


def _serialize_edge(e: HierarchicalEdge) -> dict:
    return {
        "source": e.source_id,
        "target": e.target_id,
        "rawCount": e.raw_count,
        "connectivity": round(e.connectivity, 4),
    }


def _serialize_view(view) -> dict:
    return {
        "clusters": [_serialize_cluster(c) for c in view.clusters],
        "edges": [_serialize_edge(e) for e in view.edges],
        "positions": view.positions,
        "egoClusterId": view.ego_cluster_id,
        "totalNodes": view.total_nodes,
        "nMicroClusters": view.n_micro_clusters,
        "expandedIds": view.expanded_ids,
        "budget": view.budget,
        "budgetRemaining": view.budget_remaining,
        "clusterCount": len(view.clusters),
    }
