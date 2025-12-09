"""Service for managing application-level caches."""
from __future__ import annotations

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class CacheManager:
    """Centralized manager for in-memory caches."""

    def __init__(self):
        # Cache for /api/graph-data responses
        # Key: "{include_shadow}_{mutual_only}_{min_followers}"
        self._graph_response_cache: Dict[str, Any] = {}
        
        # Cache for subgraph discovery results
        # Key: query hash
        self._discovery_cache: Dict[str, Any] = {}

    def get_graph_response(self, key: str) -> Optional[Any]:
        """Retrieve a cached graph data response."""
        return self._graph_response_cache.get(key)

    def set_graph_response(self, key: str, data: Any) -> None:
        """Cache a graph data response."""
        self._graph_response_cache[key] = data

    def clear_graph_cache(self) -> None:
        """Invalidate the entire graph response cache."""
        self._graph_response_cache.clear()
        logger.info("Graph response cache cleared")

    def get_discovery_result(self, key: str) -> Optional[Any]:
        """Retrieve a cached discovery result."""
        return self._discovery_cache.get(key)

    def set_discovery_result(self, key: str, data: Any) -> None:
        """Cache a discovery result."""
        self._discovery_cache[key] = data
        
    def clear_discovery_cache(self) -> None:
        """Invalidate discovery cache."""
        self._discovery_cache.clear()
        logger.info("Discovery cache cleared")

    def clear_all(self) -> None:
        """Clear all caches."""
        self.clear_graph_cache()
        self.clear_discovery_cache()
