"""In-memory cache for graph metrics computation.

Provides fast caching of expensive graph operations:
- Graph building (from SQLite)
- PageRank computation
- Betweenness centrality
- Engagement scores

Cache keys are based on computation parameters to ensure correctness.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Single cache entry with metadata."""
    key: str
    value: Any
    created_at: float
    access_count: int = 0
    last_accessed: float = 0.0
    computation_time_ms: float = 0.0

    def __post_init__(self):
        """Set last_accessed to created_at if not set."""
        if self.last_accessed == 0.0:
            self.last_accessed = self.created_at


class MetricsCache:
    """LRU cache with TTL and size limits for metrics computation."""

    def __init__(
        self,
        max_size: int = 100,
        ttl_seconds: int = 3600,  # 1 hour default
    ):
        """
        Initialize cache.

        Args:
            max_size: Maximum number of entries (LRU eviction)
            ttl_seconds: Time-to-live for entries (0 = no expiry)
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
            "total_computation_time_ms": 0.0,
        }

    def _make_key(self, prefix: str, params: Dict[str, Any]) -> str:
        """
        Generate cache key from parameters.

        Args:
            prefix: Key prefix (e.g., "graph", "pagerank")
            params: Dictionary of parameters

        Returns:
            Hex digest of key
        """
        # Sort keys for deterministic hashing
        sorted_params = json.dumps(params, sort_keys=True, default=str)
        hash_str = f"{prefix}:{sorted_params}"
        return hashlib.sha256(hash_str.encode()).hexdigest()[:16]

    def get(self, prefix: str, params: Dict[str, Any]) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            prefix: Key prefix
            params: Parameters used to generate key

        Returns:
            Cached value or None if not found/expired
        """
        key = self._make_key(prefix, params)

        if key not in self._cache:
            self._stats["misses"] += 1
            logger.debug(f"Cache MISS: {prefix} (key={key[:8]}...)")
            return None

        entry = self._cache[key]

        # Check TTL
        if self.ttl_seconds > 0:
            age = time.time() - entry.created_at
            if age > self.ttl_seconds:
                logger.debug(f"Cache EXPIRED: {prefix} (age={age:.1f}s, key={key[:8]}...)")
                del self._cache[key]
                self._stats["expirations"] += 1
                self._stats["misses"] += 1
                return None

        # Cache hit - update access stats and move to end (LRU)
        entry.access_count += 1
        entry.last_accessed = time.time()
        self._cache.move_to_end(key)

        self._stats["hits"] += 1
        logger.debug(
            f"Cache HIT: {prefix} (accessed={entry.access_count}x, "
            f"saved={entry.computation_time_ms:.0f}ms, key={key[:8]}...)"
        )

        return entry.value

    def set(
        self,
        prefix: str,
        params: Dict[str, Any],
        value: Any,
        computation_time_ms: float = 0.0,
    ) -> None:
        """
        Store value in cache.

        Args:
            prefix: Key prefix
            params: Parameters used to generate key
            value: Value to cache
            computation_time_ms: Time taken to compute value
        """
        key = self._make_key(prefix, params)

        # Evict oldest entry if at capacity
        if len(self._cache) >= self.max_size and key not in self._cache:
            evicted_key, evicted_entry = self._cache.popitem(last=False)
            self._stats["evictions"] += 1
            logger.debug(
                f"Cache EVICT: {evicted_key[:8]}... "
                f"(accessed={evicted_entry.access_count}x, "
                f"age={time.time() - evicted_entry.created_at:.1f}s)"
            )

        # Store new entry
        entry = CacheEntry(
            key=key,
            value=value,
            created_at=time.time(),
            computation_time_ms=computation_time_ms,
        )
        self._cache[key] = entry
        self._stats["total_computation_time_ms"] += computation_time_ms

        logger.debug(
            f"Cache SET: {prefix} (size={len(self._cache)}/{self.max_size}, "
            f"computed={computation_time_ms:.0f}ms, key={key[:8]}...)"
        )

    def invalidate(self, prefix: Optional[str] = None) -> int:
        """
        Invalidate cache entries.

        Args:
            prefix: If provided, only invalidate entries with this prefix.
                   If None, invalidate all.

        Returns:
            Number of entries invalidated
        """
        if prefix is None:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cache CLEAR: Invalidated all {count} entries")
            return count

        # Invalidate entries matching prefix
        keys_to_remove = [
            key for key, entry in self._cache.items()
            if entry.key.startswith(prefix)
        ]

        for key in keys_to_remove:
            del self._cache[key]

        logger.info(f"Cache INVALIDATE: Removed {len(keys_to_remove)} entries with prefix '{prefix}'")
        return len(keys_to_remove)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with hit rate, size, and timing stats
        """
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0.0

        # Calculate entry stats
        entries_info = []
        for key, entry in self._cache.items():
            age = time.time() - entry.created_at
            entries_info.append({
                "key": key[:12],
                "age_seconds": round(age, 1),
                "access_count": entry.access_count,
                "computation_time_ms": round(entry.computation_time_ms, 1),
            })

        # Sort by access count (most popular first)
        entries_info.sort(key=lambda x: x["access_count"], reverse=True)

        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
            "hit_rate": round(hit_rate, 2),
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "evictions": self._stats["evictions"],
            "expirations": self._stats["expirations"],
            "total_requests": total_requests,
            "total_computation_time_saved_ms": round(
                self._stats["total_computation_time_ms"], 1
            ),
            "entries": entries_info[:10],  # Top 10 most accessed
        }

    def clear_stats(self) -> None:
        """Reset statistics counters."""
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
            "total_computation_time_ms": 0.0,
        }
        logger.info("Cache stats cleared")


# Global cache instance
_global_cache: Optional[MetricsCache] = None


def get_cache(
    max_size: int = 100,
    ttl_seconds: int = 3600,
) -> MetricsCache:
    """
    Get or create global cache instance.

    Args:
        max_size: Maximum cache entries
        ttl_seconds: Time-to-live in seconds

    Returns:
        Global MetricsCache instance
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = MetricsCache(max_size=max_size, ttl_seconds=ttl_seconds)
        logger.info(f"Initialized global cache (max_size={max_size}, ttl={ttl_seconds}s)")
    return _global_cache
