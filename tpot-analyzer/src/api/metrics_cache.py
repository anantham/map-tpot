"""Response caching for expensive metrics computations.

Caches computed metrics responses to avoid recomputation when users
adjust sliders rapidly. Uses in-memory LRU cache with TTL.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with data and metadata."""
    data: Any
    created_at: float
    hits: int = 0


class MetricsCache:
    """In-memory cache for metrics computation responses.

    Features:
    - TTL-based expiration (default: 5 minutes)
    - LRU eviction when max size reached
    - Cache key based on computation parameters
    - Hit/miss statistics
    """

    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        """Initialize cache.

        Args:
            max_size: Maximum number of entries (default: 100)
            ttl_seconds: Time-to-live in seconds (default: 300 = 5 minutes)
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0

    def _create_key(self, **params) -> str:
        """Create cache key from parameters.

        Args:
            **params: Request parameters (seeds, weights, alpha, etc.)

        Returns:
            Hex-encoded SHA256 hash of sorted parameters
        """
        # Sort seeds for consistent hashing
        if "seeds" in params:
            params["seeds"] = tuple(sorted(params["seeds"]))

        # Convert to canonical JSON representation
        canonical = json.dumps(params, sort_keys=True, separators=(',', ':'))

        # Hash to fixed-length key
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def get(self, **params) -> Optional[Any]:
        """Get cached result if available and fresh.

        Args:
            **params: Request parameters

        Returns:
            Cached data or None if not found/expired
        """
        key = self._create_key(**params)
        entry = self._cache.get(key)

        if entry is None:
            self._misses += 1
            logger.debug(f"Cache MISS: {key}")
            return None

        # Check TTL
        age = time.time() - entry.created_at
        if age > self.ttl_seconds:
            logger.debug(f"Cache EXPIRED: {key} (age={age:.1f}s)")
            del self._cache[key]
            self._misses += 1
            return None

        # Hit!
        entry.hits += 1
        self._hits += 1
        logger.debug(f"Cache HIT: {key} (age={age:.1f}s, hits={entry.hits})")
        return entry.data

    def set(self, data: Any, **params) -> None:
        """Store result in cache.

        Args:
            data: Response data to cache
            **params: Request parameters (used for key)
        """
        key = self._create_key(**params)

        # Evict oldest entry if at max size
        if len(self._cache) >= self.max_size:
            oldest_key = min(
                self._cache.keys(),
                key=lambda k: self._cache[k].created_at
            )
            logger.debug(f"Cache EVICT: {oldest_key} (LRU)")
            del self._cache[oldest_key]

        self._cache[key] = CacheEntry(
            data=data,
            created_at=time.time()
        )
        logger.debug(f"Cache SET: {key}")

    def clear(self) -> None:
        """Clear all cache entries."""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cache CLEARED: {count} entries removed")

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with hits, misses, size, hit_rate
        """
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._cache),
            "max_size": self.max_size,
            "hit_rate": round(hit_rate, 3),
            "ttl_seconds": self.ttl_seconds
        }


def cached_response(cache: MetricsCache) -> Callable:
    """Decorator to cache Flask route responses.

    Args:
        cache: MetricsCache instance

    Returns:
        Decorator function

    Example:
        @cached_response(metrics_cache)
        def compute_metrics():
            # expensive computation
            return jsonify(result)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            from flask import request, jsonify

            # Extract cache parameters from request
            data = request.json or {}
            cache_params = {
                "seeds": tuple(sorted(data.get("seeds", []))),
                "weights": tuple(data.get("weights", [0.4, 0.3, 0.3])),
                "alpha": data.get("alpha", 0.85),
                "resolution": data.get("resolution", 1.0),
                "include_shadow": data.get("include_shadow", True),
                "mutual_only": data.get("mutual_only", False),
                "min_followers": data.get("min_followers", 0),
            }

            # Try cache first
            cached = cache.get(**cache_params)
            if cached is not None:
                return jsonify(cached)

            # Cache miss - compute and store
            response = func(*args, **kwargs)

            # Extract data from response (handle both dict and Response objects)
            if hasattr(response, 'get_json'):
                data = response.get_json()
            else:
                data = response

            cache.set(data, **cache_params)
            return response

        return wrapper
    return decorator
