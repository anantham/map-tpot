"""Shared state, initialization, and helper functions for cluster routes."""
from __future__ import annotations

import functools
import json
import logging
import os
import pickle  # used for cached adjacency matrix (local files only, not user input)
import time
import hashlib
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

import numpy as np
import pandas as pd
import scipy.sparse as sp
from flask import Blueprint, jsonify, request

from src.data.account_tags import AccountTagStore
from src.graph.clusters import ClusterLabelStore
from src.graph.hierarchy import (
    build_hierarchical_view,
    get_collapse_preview,
    get_expand_preview,
)
from src.graph.observation_model import (
    ObservationWeightingConfig,
    build_binary_adjacency_from_edges,
    build_ipw_adjacency_from_edges,
    compute_observation_completeness,
    summarize_completeness,
)
from src.graph.membership_grf import GRFMembershipConfig, compute_grf_membership
from src.graph.seeds import get_graph_settings
from src.communities.cluster_colors import (
    PropagationData,
    compute_cluster_community,
    load_propagation,
)
from src.graph.spectral import load_spectral_result

logger = logging.getLogger(__name__)
_log_level_name = os.getenv("CLUSTER_LOG_LEVEL", os.getenv("API_LOG_LEVEL", "INFO")).upper()
_log_level = getattr(logging, _log_level_name, logging.INFO)
logger.setLevel(_log_level)

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
        self._inflight: Dict[Tuple, "concurrent.futures.Future"] = {}
        self._inflight: Dict[Tuple, "asyncio.Future"] = {}

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

    def inflight_get(self, key: Tuple):
        return self._inflight.get(key)

    def inflight_set(self, key: Tuple, future) -> None:
        self._inflight[key] = future

    def inflight_clear(self, key: Tuple) -> None:
        self._inflight.pop(key, None)


# Global state
_spectral_result = None
_adjacency = None
_node_metadata: Dict[str, Dict] = {}
_node_id_to_idx: Dict[str, int] = {}  # For in-degree lookups
_louvain_communities: Dict[str, int] = {}  # Louvain community mapping
_label_store: Optional[ClusterLabelStore] = None
_tag_store: Optional[AccountTagStore] = None
_data_dir: Optional[Path] = None
_propagation_data: Optional[PropagationData] = None
_spectral_presets: Dict[float, object] = {}  # alpha -> SpectralResult
_alpha_presets: list = []  # sorted list of available alpha values
_tpot_spectral = None  # SpectralResult for TPOT-focused lens
_tpot_node_metadata: Dict[str, Dict] = {}  # Metadata for TPOT subgraph nodes only
_tpot_adjacency = None  # Adjacency for TPOT subgraph
_tpot_stats: Dict[str, object] = {}  # n_core, n_halo, tau from mapping
_available_lenses: list = ["full"]  # Available graph lenses
_observation_config = ObservationWeightingConfig()
_observation_stats: Dict[str, object] = {}
_graph_settings: Dict[str, object] = {}
_cache = ClusterCache()
_membership_cache = ClusterCache(max_entries=16, ttl_seconds=300)


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


def _build_adjacency(
    edges_df: pd.DataFrame,
    node_ids: np.ndarray,
    *,
    obs_config: ObservationWeightingConfig,
    expected_following: Optional[Dict[str, float]] = None,
) -> Tuple[sp.csr_matrix, Dict[str, object]]:
    """Build adjacency matrix with optional observation-aware weighting."""
    if obs_config.mode == "ipw":
        completeness = compute_observation_completeness(
            edges_df,
            node_ids,
            expected_following=expected_following,
            completeness_floor=obs_config.completeness_floor,
        )
        adjacency, ipw_stats = build_ipw_adjacency_from_edges(
            edges_df,
            node_ids,
            completeness,
            p_min=obs_config.p_min,
        )
        stats: Dict[str, object] = {
            **ipw_stats,
            "completeness": summarize_completeness(completeness),
            "p_min": obs_config.p_min,
            "completeness_floor": obs_config.completeness_floor,
        }
        return adjacency, stats

    adjacency = build_binary_adjacency_from_edges(edges_df, node_ids)
    stats = {
        "mode": "off",
        "observed_edges": int(len(edges_df)),
        "weighted_edges": int(adjacency.count_nonzero()),
        "p_min": obs_config.p_min,
        "completeness_floor": obs_config.completeness_floor,
    }
    return adjacency, stats


def _load_or_build_adjacency(
    edges_df: pd.DataFrame,
    node_ids: np.ndarray,
    cache_path: Path,
    *,
    obs_config: ObservationWeightingConfig,
    expected_following: Optional[Dict[str, float]] = None,
) -> Tuple[sp.csr_matrix, Dict[str, object]]:
    """Load adjacency matrix from cache or build it (with caching)."""
    if cache_path.exists():
        try:
            logger.info("Loading cached adjacency matrix from %s", cache_path)
            with open(cache_path, 'rb') as f:
                cached_payload = pickle.load(f)  # noqa: S301 — local cache files only
                if isinstance(cached_payload, dict) and "adjacency" in cached_payload:
                    adjacency = cached_payload["adjacency"]
                    stats = cached_payload.get("stats", {})
                else:
                    # Backward compatibility: old cache contained only CSR matrix.
                    adjacency = cached_payload
                    stats = {
                        "mode": obs_config.mode,
                        "cache_format": "legacy",
                    }
                logger.info("Cached adjacency loaded: %s edges", adjacency.count_nonzero())
                if isinstance(stats, dict):
                    stats["cache_hit"] = True
                return adjacency, stats
        except Exception as e:
            logger.warning("Failed to load adjacency cache (%s), rebuilding...", e)

    # Build fresh adjacency matrix
    logger.info("Building adjacency matrix from %s edges...", len(edges_df))
    start_time = time.time()
    adjacency, stats = _build_adjacency(
        edges_df,
        node_ids,
        obs_config=obs_config,
        expected_following=expected_following,
    )
    duration = time.time() - start_time
    logger.info("Adjacency matrix built in %.2fs: %s edges", duration, adjacency.count_nonzero())
    if isinstance(stats, dict):
        stats["build_seconds"] = round(duration, 4)
        stats["cache_hit"] = False

    # Save to cache
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, 'wb') as f:
            pickle.dump({"adjacency": adjacency, "stats": stats}, f)
        logger.info("Adjacency matrix cached to %s", cache_path)
    except Exception as e:
        logger.warning("Failed to cache adjacency matrix: %s", e)

    return adjacency, stats


def _make_cache_key(
    granularity: int,
    ego: Optional[str],
    expanded: Set[str],
    collapsed: Set[str] = None,
    louvain_weight: float = 0.0,
    expand_depth: float = 0.5,
    focus_leaf: Optional[str] = None,
    alpha: float = 0.0,
    lens: str = "full",
) -> Tuple:
    collapsed = collapsed or set()
    return (
        granularity,
        ego or "",
        ",".join(sorted(expanded)),
        ",".join(sorted(collapsed)),
        round(louvain_weight, 2),
        round(expand_depth, 2),
        focus_leaf or "",
        round(alpha, 2),
        lens,
    )

def _get_tag_store() -> AccountTagStore:
    global _tag_store
    if _tag_store is not None:
        return _tag_store
    if _data_dir is None:
        raise RuntimeError("cluster routes not initialized (missing data_dir)")
    db_path = _data_dir / "account_tags.db"
    _tag_store = AccountTagStore(db_path)
    return _tag_store


def _membership_engine_enabled() -> bool:
    engine = str(_graph_settings.get("membership_engine", "off")).strip().lower()
    return engine == "grf"


def _resolve_anchor_indices(ego: str) -> Tuple[list[int], list[int], Dict[str, int]]:
    store = _get_tag_store()
    anchor_rows = store.list_anchor_polarities(ego=ego)
    positive: list[int] = []
    negative: list[int] = []
    dropped = 0
    for account_id, polarity in anchor_rows:
        idx = _node_id_to_idx.get(str(account_id))
        if idx is None:
            dropped += 1
            continue
        if polarity > 0:
            positive.append(int(idx))
        elif polarity < 0:
            negative.append(int(idx))
    stats = {
        "anchor_rows": int(len(anchor_rows)),
        "anchors_in_graph": int(len(positive) + len(negative)),
        "anchors_dropped": int(dropped),
    }
    return positive, negative, stats


def _anchor_digest(positive: list[int], negative: list[int]) -> str:
    payload = f"p:{','.join(map(str, sorted(set(positive))))}|n:{','.join(map(str, sorted(set(negative))))}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _estimate_account_coverage(account_id: str) -> Dict[str, float]:
    meta = _node_metadata.get(account_id, {})
    expected_following = _safe_int(meta.get("num_following"), default=0)
    observed_following = 0
    idx = _node_id_to_idx.get(account_id)
    if idx is not None and _adjacency is not None:
        observed_following = int(_adjacency.getrow(idx).count_nonzero())

    if expected_following <= 0:
        base_floor = max(1e-4, _observation_config.completeness_floor)
        coverage = 1.0 if observed_following > 0 else base_floor
    else:
        coverage = observed_following / float(expected_following)
        coverage = max(_observation_config.completeness_floor, min(1.0, coverage))

    return {
        "value": float(coverage),
        "observedFollowing": float(observed_following),
        "expectedFollowing": float(expected_following),
    }


def _require_loaded(f):
    """Decorator: return 503 if cluster data hasn't been initialized."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if _spectral_result is None or _adjacency is None:
            return jsonify({"error": "Cluster data not loaded"}), 503
        return f(*args, **kwargs)
    return wrapper


def _parse_lens() -> str:
    """Extract and validate the lens query parameter."""
    lens = request.args.get("lens", "full", type=str)
    if lens not in _available_lenses:
        lens = "full"
    return lens


def _require_ego() -> str:
    """Extract ego query param, raising ValueError if missing."""
    ego = (request.args.get("ego") or "").strip()
    if not ego:
        raise ValueError("ego query param is required")
    return ego


def init_cluster_routes(data_dir: Path = Path("data")) -> None:
    """Initialize cluster routes state (data load + caches).

    Note: Blueprint registration is handled by the Flask app factory.
    """
    global _spectral_result, _adjacency, _node_metadata, _node_id_to_idx, _louvain_communities, _label_store
    global _data_dir, _propagation_data, _spectral_presets, _alpha_presets
    global _tpot_spectral, _tpot_node_metadata, _tpot_adjacency, _tpot_stats, _available_lenses
    global _observation_config, _observation_stats, _graph_settings

    try:
        _data_dir = data_dir
        base = data_dir / "graph_snapshot"
        spectral_sidecar = data_dir / "graph_snapshot.spectral.npz"
        if not spectral_sidecar.exists():
            logger.warning("Spectral sidecar not found at %s; skipping cluster routes init", spectral_sidecar)
            return
        _spectral_result = load_spectral_result(base)
        nodes_df = pd.read_parquet(data_dir / "graph_snapshot.nodes.parquet")
        edges_df = pd.read_parquet(data_dir / "graph_snapshot.edges.parquet")
        _node_metadata = _load_metadata(nodes_df)
        node_ids = _spectral_result.node_ids

        settings_payload = get_graph_settings().get("settings", {})
        if not isinstance(settings_payload, dict):
            settings_payload = {}
        _graph_settings = dict(settings_payload)
        _observation_config = ObservationWeightingConfig.from_settings(settings_payload)

        expected_following: Dict[str, float] = {}
        if "node_id" in nodes_df.columns and "num_following" in nodes_df.columns:
            node_following = nodes_df[["node_id", "num_following"]].copy()
            node_following["node_id"] = node_following["node_id"].astype(str)
            expected_following = dict(
                zip(
                    node_following["node_id"].tolist(),
                    node_following["num_following"].tolist(),
                )
            )

        # Use cached adjacency matrix (saves ~12 seconds on startup)
        if _observation_config.mode == "off":
            adjacency_cache_path = data_dir / "adjacency_matrix_cache.pkl"
        else:
            p_tag = f"{_observation_config.p_min:.4f}".replace(".", "p")
            adjacency_cache_path = data_dir / f"adjacency_matrix_cache.{_observation_config.mode}.{p_tag}.pkl"
        _adjacency, _observation_stats = _load_or_build_adjacency(
            edges_df,
            node_ids,
            adjacency_cache_path,
            obs_config=_observation_config,
            expected_following=expected_following,
        )
        _membership_cache._entries.clear()
        _membership_cache._inflight.clear()

        _label_store = ClusterLabelStore(data_dir / "clusters.db")

        # Build node_id -> index mapping for in-degree lookups
        _node_id_to_idx = {str(nid): i for i, nid in enumerate(node_ids)}

        # Load Louvain communities
        _louvain_communities = _load_louvain(data_dir)

        # Load community propagation data (optional — degrades gracefully)
        prop_path = data_dir / "community_propagation.npz"
        _propagation_data = load_propagation(prop_path)
        if _propagation_data is not None:
            logger.info("Community propagation loaded: %d nodes, %d communities",
                        _propagation_data.memberships.shape[0],
                        len(_propagation_data.community_names))
        else:
            logger.warning("Community propagation not found at %s — community colors disabled", prop_path)

        # Load spectral alpha presets (e.g. graph_snapshot.a15.spectral.npz)
        _spectral_presets = {0.0: _spectral_result}
        for alpha_pct in [15, 30]:
            alpha_val = alpha_pct / 100.0
            preset_base = data_dir / f"graph_snapshot.a{alpha_pct}"
            preset_sidecar = data_dir / f"graph_snapshot.a{alpha_pct}.spectral.npz"
            if preset_sidecar.exists():
                try:
                    _spectral_presets[alpha_val] = load_spectral_result(preset_base)
                    logger.info("Loaded spectral preset alpha=%.2f from %s", alpha_val, preset_base)
                except Exception:
                    logger.warning("Failed to load spectral preset alpha=%.2f", alpha_val, exc_info=True)
        _alpha_presets = sorted(_spectral_presets.keys())

        # Load TPOT-focused lens (optional — degrades gracefully)
        _available_lenses = ["full"]
        tpot_spectral_path = data_dir / "graph_snapshot_tpot.spectral.npz"
        if tpot_spectral_path.exists():
            try:
                tpot_base = data_dir / "graph_snapshot_tpot"
                _tpot_spectral = load_spectral_result(tpot_base)

                # Load TPOT node metadata (subset of full metadata)
                tpot_nodes_path = data_dir / "graph_snapshot_tpot.nodes.parquet"
                if tpot_nodes_path.exists():
                    tpot_nodes_df = pd.read_parquet(tpot_nodes_path)
                    _tpot_node_metadata = _load_metadata(tpot_nodes_df)

                    # Build TPOT adjacency from edges
                    tpot_edges_path = data_dir / "graph_snapshot_tpot.edges.parquet"
                    if tpot_edges_path.exists():
                        tpot_edges_df = pd.read_parquet(tpot_edges_path)
                        tpot_node_ids = _tpot_spectral.node_ids
                        tpot_adj_cache = data_dir / "adjacency_matrix_cache.tpot.pkl"
                        _tpot_adjacency, _tpot_obs_stats = _load_or_build_adjacency(
                            tpot_edges_df, tpot_node_ids, tpot_adj_cache,
                            obs_config=ObservationWeightingConfig(),  # default for TPOT
                        )

                # Load TPOT mapping stats (n_core, n_halo, tau)
                tpot_mapping_path = data_dir / "graph_snapshot_tpot.mapping.json"
                if tpot_mapping_path.exists():
                    mapping = json.loads(tpot_mapping_path.read_text())
                    _tpot_stats = {
                        "n_core": mapping.get("n_core", 0),
                        "n_halo": mapping.get("n_halo", 0),
                        "n_total": mapping.get("n_tpot_subgraph", 0),
                        "tau": mapping.get("tau", 0),
                    }

                _available_lenses.append("tpot")
                logger.info("TPOT lens loaded: %d nodes", len(_tpot_spectral.node_ids))
            except Exception:
                logger.warning("Failed to load TPOT lens", exc_info=True)
                _tpot_spectral = None
        else:
            logger.info("TPOT lens not available (no %s)", tpot_spectral_path)

        if _spectral_result.micro_labels is not None:
            n_micro = len(np.unique(_spectral_result.micro_labels))
            logger.info(
                "Cluster routes initialized (APPROXIMATE mode): %s nodes -> %s micro-clusters, %s edges, obs_mode=%s",
                len(node_ids), n_micro, _adjacency.count_nonzero(), _observation_config.mode
            )
        else:
            logger.info(
                "Cluster routes initialized (EXACT mode): %s nodes, %s edges, obs_mode=%s",
                len(node_ids), _adjacency.count_nonzero(), _observation_config.mode
            )
    except Exception as exc:
        logger.exception("Failed to initialize cluster routes: %s", exc)
        # Do not register blueprint if we failed to load data


def _serialize_hierarchical_view(view) -> dict:
    """Serialize HierarchicalViewData to JSON-friendly dict."""
    max_conn = max((e.connectivity for e in view.edges), default=1.0)
    if max_conn <= 0:
        max_conn = 1.0

    def serialize_cluster(c):
        result = {
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

        # Community color fields — ADR-013 probabilistic contract.
        # communityChroma is the canonical rendering signal (replaces old communityIntensity).
        if _propagation_data is not None and c.member_node_ids:
            ci = compute_cluster_community(_propagation_data, c.member_node_ids)
            result["communityColor"] = ci.dominant_color
            result["communityName"] = ci.dominant_name
            result["communityId"] = ci.dominant_id
            result["communityChroma"] = ci.chroma            # ADR-013: use this for fill
            result["signalStrength"] = ci.signal_strength
            result["purity"] = ci.purity
            result["ambiguity"] = ci.ambiguity
            result["coverage"] = ci.coverage
            result["confidence"] = ci.confidence
            result["secondaryCommunityColor"] = ci.secondary_color
            result["secondaryCommunityWeight"] = ci.secondary_weight
            result["communityBreakdown"] = ci.breakdown
        else:
            result["communityColor"] = None
            result["communityName"] = None
            result["communityId"] = None
            result["communityChroma"] = 0.0
            result["signalStrength"] = 0.0
            result["purity"] = 0.0
            result["ambiguity"] = 0.0
            result["coverage"] = 0.0
            result["confidence"] = 0.0
            result["secondaryCommunityColor"] = None
            result["secondaryCommunityWeight"] = 0.0
            result["communityBreakdown"] = []

        return result

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
            "collapsed": view.collapsed_ids,
            "observation": {
                "mode": _observation_config.mode,
                "stats": _observation_stats,
            },
            "communities": _build_communities_meta(),
            "alphaPresets": _alpha_presets if len(_alpha_presets) > 1 else [],
            "activeAlpha": 0.0,  # Will be overridden per-request in get_clusters
            "availableLenses": _available_lenses,
            "activeLens": "full",  # Will be overridden per-request in get_clusters
            "tpotStats": _tpot_stats if _tpot_stats else None,
        },
        "cache_hit": False,
    }
    return payload


def _build_communities_meta() -> list:
    """Build communities list for meta response."""
    if _propagation_data is None:
        return []
    return [
        {
            "id": _propagation_data.community_ids[i],
            "name": _propagation_data.community_names[i],
            "color": _propagation_data.community_colors[i],
        }
        for i in range(len(_propagation_data.community_names))
    ]
