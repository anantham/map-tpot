"""Cluster routes package — split from monolithic cluster_routes.py."""
from src.api.cluster.state import (
    cluster_bp,
    init_cluster_routes,
    ClusterCache,
    CacheEntry,
    _make_cache_key,
    _safe_int,
    _serialize_hierarchical_view,
)

# Register routes from sub-modules onto the shared blueprint.
# These imports have side effects (decorator registration).
import src.api.cluster.views      # noqa: F401
import src.api.cluster.sidebar    # noqa: F401
import src.api.cluster.membership # noqa: F401
import src.api.cluster.actions    # noqa: F401
