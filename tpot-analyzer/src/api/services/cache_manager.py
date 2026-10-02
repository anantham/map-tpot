"""Bounded ephemeral caches for graph responses and discovery outputs."""
from __future__ import annotations

from src.api.services.bounded_cache import BoundedCache


class CacheManager:
    """TTL/LRU eviction and byte ceilings prevent arbitrary-key memory growth."""

    def __init__(self, *, graph_entries=8, discovery_entries=64, max_bytes=16 * 1024 * 1024, ttl_seconds=300):
        self._graph_response_cache = BoundedCache(graph_entries, max_bytes, ttl_seconds)
        self._discovery_cache = BoundedCache(discovery_entries, max_bytes, ttl_seconds)

    def get_graph_response(self, key):
        return self._graph_response_cache.get(key)

    def set_graph_response(self, key, data):
        return self._graph_response_cache.set(key, data)

    def clear_graph_cache(self):
        self._graph_response_cache.clear()

    def get_discovery_result(self, key):
        return self._discovery_cache.get(key)

    def set_discovery_result(self, key, data):
        return self._discovery_cache.set(key, data)

    def clear_discovery_cache(self):
        self._discovery_cache.clear()

    def graph_cache_size(self):
        return len(self._graph_response_cache)

    def discovery_cache_size(self):
        return len(self._discovery_cache)

    def clear_all(self):
        self.clear_graph_cache()
        self.clear_discovery_cache()
