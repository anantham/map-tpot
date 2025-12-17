"""Routes for accounts, search, and user tagging."""
from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, current_app, jsonify, request

from src.api import cluster_routes
from src.config import get_snapshot_dir
from src.data.account_tags import AccountTagStore
from src.graph import (
    save_seed_list,
    set_active_seed_list,
    get_seed_state,
    update_graph_settings,
)
from src.graph.hierarchy.traversal import (
    find_cluster_leaders,
    get_children,
    get_dendrogram_id,
    get_node_idx,
    is_descendant,
)
from scipy.cluster.hierarchy import fcluster

logger = logging.getLogger(__name__)

accounts_bp = Blueprint("accounts", __name__, url_prefix="/api")

_tag_store: Optional[AccountTagStore] = None
_search_index: Optional[List[Tuple[str, str, str]]] = None  # (account_id, username_lc, display_name_lc)
_search_index_graph_id: Optional[int] = None


def _require_ego() -> str:
    ego = (request.args.get("ego") or "").strip()
    if not ego:
        raise ValueError("ego query param is required")
    return ego


def _get_tag_store() -> AccountTagStore:
    global _tag_store
    if _tag_store is not None:
        return _tag_store
    snapshot_dir = get_snapshot_dir()
    db_path = Path(snapshot_dir) / "account_tags.db"
    _tag_store = AccountTagStore(db_path)
    return _tag_store


def _get_node_metadata() -> Dict[str, Dict]:
    meta = getattr(cluster_routes, "_node_metadata", None) or {}
    return meta


def _build_search_index_from_snapshot(graph_result: Any) -> List[Tuple[str, str, str]]:
    global _search_index, _search_index_graph_id
    graph_id = id(graph_result)
    if _search_index is not None and _search_index_graph_id == graph_id:
        return _search_index

    rows: List[Tuple[str, str, str]] = []
    directed = getattr(graph_result, "directed", None)
    if directed is None:
        _search_index = []
        _search_index_graph_id = graph_id
        return _search_index

    for node_id, payload in directed.nodes(data=True):
        username = (payload.get("username") or str(node_id) or "").strip()
        display_name = (payload.get("display_name") or payload.get("displayName") or "").strip()
        rows.append((str(node_id), username.casefold(), display_name.casefold()))

    _search_index = rows
    _search_index_graph_id = graph_id
    return _search_index


@accounts_bp.route("/accounts/<account_id>", methods=["GET"])
def get_account(account_id):
    """Get details for a specific account."""
    meta = _get_node_metadata().get(str(account_id))
    if not meta:
        return jsonify({"error": "Account not found"}), 404
    return jsonify({"id": str(account_id), **meta})


@accounts_bp.route("/accounts/search", methods=["GET"])
def search_accounts():
    """Search accounts in the loaded snapshot by handle/name."""
    q = (request.args.get("q") or "").strip().lstrip("@")
    limit = int(request.args.get("limit") or 20)
    limit = max(1, min(50, limit))
    if not q:
        return jsonify([])

    query = q.casefold()
    graph_result = current_app.config.get("SNAPSHOT_GRAPH")
    if graph_result is None:
        meta = _get_node_metadata()
        index = [(account_id, (payload.get("username") or "").casefold(), (payload.get("display_name") or "").casefold()) for account_id, payload in meta.items()]
        node_lookup = meta
        from_snapshot = False
    else:
        index = _build_search_index_from_snapshot(graph_result)
        directed = getattr(graph_result, "directed", None)
        node_lookup = dict(directed.nodes(data=True)) if directed is not None else {}
        from_snapshot = True

    hits: List[Tuple[int, str]] = []
    for account_id, username_lc, display_lc in index:
        # Tests and UX expect prefix-matching on username/display name.
        if not username_lc.startswith(query) and not display_lc.startswith(query):
            continue
        payload = node_lookup.get(account_id, {}) if isinstance(node_lookup, dict) else {}
        followers = payload.get("num_followers")
        try:
            followers_val = float(followers) if followers is not None else None
        except Exception:
            followers_val = None
        if followers_val is not None and (followers_val != followers_val or followers_val == float("inf") or followers_val == float("-inf")):
            followers_val = None
        # sort: highest followers first; None last
        sort_key = -(followers_val if followers_val is not None else -1.0)
        hits.append((sort_key, account_id))

    hits.sort(key=lambda pair: (pair[0], str(pair[1])))
    results = []
    for _, account_id in hits[:limit]:
        payload = node_lookup.get(account_id, {}) if isinstance(node_lookup, dict) else {}
        username = payload.get("username") or payload.get("username_lc") or account_id
        display_name = payload.get("display_name") or payload.get("displayName") or payload.get("display_name_lc") or ""
        followers = payload.get("num_followers")
        bio = payload.get("bio")
        is_shadow = payload.get("shadow")
        try:
            followers_val = float(followers) if followers is not None else None
        except Exception:
            followers_val = None
        if followers_val is not None and (followers_val != followers_val or followers_val == float("inf") or followers_val == float("-inf")):
            followers_val = None
        if is_shadow is None and not from_snapshot:
            is_shadow = False
        results.append(
            {
                "id": account_id,
                "username": username,
                "displayName": display_name,
                "display_name": display_name,  # backward-compatible alias
                "numFollowers": followers_val,
                "num_followers": followers_val,  # backward-compatible alias
                "isShadow": bool(is_shadow),
                "is_shadow": bool(is_shadow),  # backward-compatible alias
                "bio": bio,
            }
        )
    return jsonify(results)


@accounts_bp.route("/accounts/<account_id>/tags", methods=["GET"])
def get_account_tags(account_id: str):
    """List account tags for an ego."""
    try:
        ego = _require_ego()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    store = _get_tag_store()
    tags = store.list_tags(ego=ego, account_id=str(account_id))
    return jsonify({"ego": ego, "accountId": str(account_id), "tags": [asdict(t) for t in tags]})


@accounts_bp.route("/accounts/<account_id>/tags", methods=["POST"])
def upsert_account_tag(account_id: str):
    """Upsert a tag for an account (scoped by ego)."""
    try:
        ego = _require_ego()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    data = request.get_json(silent=True) or {}
    tag = (data.get("tag") or "").strip()
    polarity_raw = data.get("polarity")
    confidence = data.get("confidence")

    polarity: Optional[int] = None
    if polarity_raw in (1, -1):
        polarity = int(polarity_raw)
    elif isinstance(polarity_raw, str):
        key = polarity_raw.strip().lower()
        if key in ("in", "pos", "positive", "yes", "true"):
            polarity = 1
        elif key in ("not_in", "not-in", "neg", "negative", "no", "false"):
            polarity = -1
    if polarity is None:
        return jsonify({"error": "polarity must be 'in' or 'not_in'"}), 400

    store = _get_tag_store()
    try:
        saved = store.upsert_tag(
            ego=ego,
            account_id=str(account_id),
            tag=tag,
            polarity=polarity,
            confidence=float(confidence) if confidence is not None else None,
        )
    except Exception as exc:
        logger.warning("Tag upsert failed ego=%s account=%s tag=%s: %s", ego, account_id, tag, exc)
        return jsonify({"error": str(exc)}), 400
    return jsonify({"status": "ok", "tag": asdict(saved)})


@accounts_bp.route("/accounts/<account_id>/tags/<tag>", methods=["DELETE"])
def delete_account_tag(account_id: str, tag: str):
    """Delete a tag for an account (scoped by ego)."""
    try:
        ego = _require_ego()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    store = _get_tag_store()
    deleted = store.delete_tag(ego=ego, account_id=str(account_id), tag=tag)
    return jsonify({"status": "deleted" if deleted else "not_found"})


@accounts_bp.route("/tags", methods=["GET"])
def list_tags():
    """List distinct tags for an ego (for autocomplete)."""
    try:
        ego = _require_ego()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    store = _get_tag_store()
    return jsonify({"ego": ego, "tags": store.list_distinct_tags(ego=ego)})


@accounts_bp.route("/accounts/<account_id>/teleport_plan", methods=["GET"])
def get_teleport_plan(account_id: str):
    """Compute a deterministic plan to make an account visible (leaf explode) within budget."""
    spectral = getattr(cluster_routes, "_spectral_result", None)
    node_to_idx = getattr(cluster_routes, "_node_id_to_idx", None) or {}
    if spectral is None or not node_to_idx:
        return jsonify({"error": "Cluster data not loaded"}), 503

    budget = int(request.args.get("budget") or 25)
    budget = max(5, min(500, budget))
    start_visible = request.args.get("visible")
    start_visible_n = int(start_visible) if (start_visible and start_visible.isdigit()) else min(15, budget)
    start_visible_n = max(5, min(budget, start_visible_n))

    idx = node_to_idx.get(str(account_id))
    if idx is None:
        return jsonify({"error": "Account not found in snapshot"}), 404

    # Determine leaf node in dendrogram
    if spectral.micro_labels is None:
        leaf_idx = idx
        n_leaves = len(spectral.node_ids)
    else:
        leaf_idx = int(spectral.micro_labels[idx])
        n_leaves = int(spectral.micro_centroids.shape[0]) if spectral.micro_centroids is not None else int(spectral.micro_labels.max()) + 1

    leaf_cluster_id = get_dendrogram_id(leaf_idx)

    linkage = spectral.linkage_matrix

    def _depth_from_leader(leader_idx: int) -> int:
        depth = 0
        cur = leader_idx
        while cur != leaf_idx:
            children = get_children(linkage, cur, n_leaves)
            if not children:
                break
            left, right = children
            cur = left if is_descendant(linkage, leaf_idx, left, n_leaves) else right
            depth += 1
            if depth > n_leaves:  # safety
                break
        return depth

    chosen_visible = None
    chosen_depth = None
    chosen_leader_id = None

    for base in range(start_visible_n, 4, -1):
        base_labels = fcluster(linkage, t=min(base, n_leaves, budget), criterion="maxclust")
        label_to_leader = find_cluster_leaders(linkage, base_labels, n_leaves)
        leaf_label = int(base_labels[leaf_idx])
        leader_idx = int(label_to_leader.get(leaf_label, leaf_idx))
        depth = _depth_from_leader(leader_idx)
        if base + depth <= budget:
            chosen_visible = base
            chosen_depth = depth
            chosen_leader_id = get_dendrogram_id(leader_idx)
            break

    if chosen_visible is None:
        # fallback: minimum view; may still exceed budget if budget is very small
        base = 5
        base_labels = fcluster(linkage, t=min(base, n_leaves, budget), criterion="maxclust")
        label_to_leader = find_cluster_leaders(linkage, base_labels, n_leaves)
        leaf_label = int(base_labels[leaf_idx])
        leader_idx = int(label_to_leader.get(leaf_label, leaf_idx))
        chosen_visible = base
        chosen_depth = _depth_from_leader(leader_idx)
        chosen_leader_id = get_dendrogram_id(leader_idx)

    return jsonify(
        {
            "accountId": str(account_id),
            "leafClusterId": leaf_cluster_id,
            "targetVisible": int(chosen_visible),
            "budget": budget,
            "pathDepth": int(chosen_depth or 0),
            "leaderClusterId": chosen_leader_id,
            # Caller should clear expanded/collapsed and request clusters with focus_leaf=leafClusterId
            "recommended": {
                "n": int(chosen_visible),
                "expanded": "",
                "collapsed": "",
                "focus_leaf": leaf_cluster_id,
            },
        }
    )


@accounts_bp.route("/seeds", methods=["GET"])
def get_seeds():
    """Return current seed lists + settings state for the frontend."""
    state = get_seed_state()
    return jsonify(state)


@accounts_bp.route("/seeds", methods=["POST"])
def update_seeds():
    """Update seed lists and/or graph settings."""
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    try:
        if "settings" in data:
            next_state = update_graph_settings(data.get("settings") or {})
            return jsonify({"status": "ok", "state": next_state})

        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "name is required"}), 400

        set_active = bool(data.get("set_active", True))
        if "seeds" in data and data.get("seeds") is not None:
            next_state = save_seed_list(name, data.get("seeds") or [], set_active=set_active)
            return jsonify({"status": "ok", "state": next_state})

        if set_active:
            next_state = set_active_seed_list(name)
            return jsonify({"status": "ok", "state": next_state})

        return jsonify({"status": "ok", "state": get_seed_state()})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Failed to update seed settings: %s", exc)
        return jsonify({"error": "Failed to update seed settings"}), 500
