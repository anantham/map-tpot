"""Backward-compatibility shim — real code lives in src/api/cluster/."""
from src.api.cluster import (  # noqa: F401
    cluster_bp,
    init_cluster_routes,
    ClusterCache,
    CacheEntry,
    _make_cache_key,
    _safe_int,
    _serialize_hierarchical_view,
)
