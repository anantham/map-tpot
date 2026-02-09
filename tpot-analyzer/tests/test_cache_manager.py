"""Unit tests for CacheManager behavior."""
from __future__ import annotations

from src.api.services.cache_manager import CacheManager


def test_cache_manager_stores_and_reads_graph_and_discovery_entries():
    cache = CacheManager()
    cache.set_graph_response("graph:key", {"nodes": 3})
    cache.set_discovery_result("disc:key", {"recommendations": []})

    assert cache.get_graph_response("graph:key") == {"nodes": 3}
    assert cache.get_discovery_result("disc:key") == {"recommendations": []}
    assert cache.graph_cache_size() == 1
    assert cache.discovery_cache_size() == 1


def test_cache_manager_clear_all_clears_both_caches():
    cache = CacheManager()
    cache.set_graph_response("graph:key", {"nodes": 3})
    cache.set_discovery_result("disc:key", {"recommendations": []})

    cache.clear_all()

    assert cache.get_graph_response("graph:key") is None
    assert cache.get_discovery_result("disc:key") is None
    assert cache.graph_cache_size() == 0
    assert cache.discovery_cache_size() == 0
