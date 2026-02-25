"""Expansion cache for precomputed strategy evaluations.

This module provides caching infrastructure for expansion strategies.
When a cluster becomes visible in the UI, we precompute all viable
expansion strategies and their scores so the user can:

1. See instant expansions (no waiting)
2. Choose from ranked alternatives
3. Understand WHY a particular strategy was recommended

The cache uses LRU eviction and TTL-based expiry to manage memory.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Callable

import numpy as np
from scipy import sparse

logger = logging.getLogger(__name__)

# Cache configuration
MAX_CACHE_ENTRIES = 100  # Maximum clusters to cache
CACHE_TTL_SECONDS = 3600  # 1 hour TTL
PRECOMPUTE_BATCH_SIZE = 5  # How many clusters to precompute at once


@dataclass
class CachedExpansion:
    """Cached expansion result for a cluster."""

    cluster_id: str
    member_count: int
    ranked_strategies: List["ScoredStrategy"]  # Best first
    computed_at: float  # time.time() when computed
    computation_ms: int  # How long it took to compute

    def is_expired(self, ttl_seconds: float = CACHE_TTL_SECONDS) -> bool:
        """Check if this cache entry has expired.

        Args:
            ttl_seconds: TTL to check against (defaults to global setting)
        """
        return time.time() - self.computed_at > ttl_seconds

    @property
    def best_strategy(self) -> Optional["ScoredStrategy"]:
        """Get the top-ranked strategy."""
        return self.ranked_strategies[0] if self.ranked_strategies else None

    @property
    def alternative_strategies(self) -> List["ScoredStrategy"]:
        """Get all strategies except the best."""
        return self.ranked_strategies[1:] if len(self.ranked_strategies) > 1 else []


class ExpansionCache:
    """LRU cache for precomputed expansion strategies.

    Thread-safe cache that stores ranked expansion strategies for clusters.
    Supports both synchronous lookup and async precomputation.
    """

    def __init__(
        self,
        max_entries: int = MAX_CACHE_ENTRIES,
        ttl_seconds: float = CACHE_TTL_SECONDS,
    ):
        self._cache: OrderedDict[str, CachedExpansion] = OrderedDict()
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._lock = threading.RLock()

        # Stats for monitoring
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, cluster_id: str) -> Optional[CachedExpansion]:
        """Get cached expansion for a cluster.

        Args:
            cluster_id: The cluster ID to look up

        Returns:
            CachedExpansion if found and not expired, None otherwise
        """
        with self._lock:
            if cluster_id not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[cluster_id]

            # Check TTL using instance's configured TTL
            if entry.is_expired(self._ttl_seconds):
                del self._cache[cluster_id]
                self._misses += 1
                return None

            # Move to end (LRU)
            self._cache.move_to_end(cluster_id)
            self._hits += 1

            return entry

    def put(
        self,
        cluster_id: str,
        member_count: int,
        ranked_strategies: List["ScoredStrategy"],
        computation_ms: int = 0,
    ) -> None:
        """Store expansion result in cache.

        Args:
            cluster_id: The cluster ID
            member_count: Number of members in the cluster
            ranked_strategies: Strategies ranked by score (best first)
            computation_ms: How long the computation took
        """
        with self._lock:
            # Evict if at capacity
            while len(self._cache) >= self._max_entries:
                self._cache.popitem(last=False)  # Remove oldest
                self._evictions += 1

            self._cache[cluster_id] = CachedExpansion(
                cluster_id=cluster_id,
                member_count=member_count,
                ranked_strategies=ranked_strategies,
                computed_at=time.time(),
                computation_ms=computation_ms,
            )

    def invalidate(self, cluster_id: str) -> bool:
        """Remove a specific cluster from cache.

        Args:
            cluster_id: The cluster ID to invalidate

        Returns:
            True if entry was removed, False if not found
        """
        with self._lock:
            if cluster_id in self._cache:
                del self._cache[cluster_id]
                return True
            return False

    def invalidate_all(self) -> int:
        """Clear entire cache.

        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def get_stats(self) -> Dict:
        """Get cache statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0

            return {
                "entries": len(self._cache),
                "max_entries": self._max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "evictions": self._evictions,
            }

    def get_cached_cluster_ids(self) -> List[str]:
        """Get list of currently cached cluster IDs."""
        with self._lock:
            return list(self._cache.keys())


# Global cache instance
_expansion_cache: Optional[ExpansionCache] = None
_cache_lock = threading.Lock()


def get_expansion_cache() -> ExpansionCache:
    """Get or create the global expansion cache."""
    global _expansion_cache

    with _cache_lock:
        if _expansion_cache is None:
            _expansion_cache = ExpansionCache()
        return _expansion_cache


def reset_expansion_cache() -> None:
    """Reset the global expansion cache (useful for testing)."""
    global _expansion_cache

    with _cache_lock:
        if _expansion_cache is not None:
            _expansion_cache.invalidate_all()
        _expansion_cache = None


@dataclass
class PrecomputeRequest:
    """Request to precompute expansion for a cluster."""

    cluster_id: str
    member_node_ids: List[str]
    priority: int = 0  # Higher = more urgent
    requested_at: float = field(default_factory=time.time)


class ExpansionPrecomputer:
    """Background precomputation of expansion strategies.

    When clusters become visible, add them to the precompute queue.
    This runs in a background thread to prepare expansions before
    the user clicks.
    """

    def __init__(
        self,
        adjacency: sparse.spmatrix,
        node_id_to_idx: Dict[str, int],
        node_tags: Optional[Dict[str, Set[str]]] = None,
        cache: Optional[ExpansionCache] = None,
    ):
        self._adjacency = adjacency
        self._node_id_to_idx = node_id_to_idx
        self._node_tags = node_tags
        self._cache = cache or get_expansion_cache()

        self._queue: List[PrecomputeRequest] = []
        self._queue_lock = threading.Lock()

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def enqueue(
        self,
        cluster_id: str,
        member_node_ids: List[str],
        priority: int = 0,
    ) -> bool:
        """Add a cluster to the precompute queue.

        Args:
            cluster_id: The cluster ID
            member_node_ids: Members of the cluster
            priority: Higher priority = computed sooner

        Returns:
            True if added, False if already cached or queued
        """
        # Skip if already cached
        if self._cache.get(cluster_id) is not None:
            return False

        with self._queue_lock:
            # Skip if already queued
            if any(r.cluster_id == cluster_id for r in self._queue):
                return False

            self._queue.append(PrecomputeRequest(
                cluster_id=cluster_id,
                member_node_ids=member_node_ids,
                priority=priority,
            ))

            # Sort by priority (highest first)
            self._queue.sort(key=lambda r: r.priority, reverse=True)

            return True

    def start(self) -> None:
        """Start the background precomputation thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Expansion precomputer started")

    def stop(self) -> None:
        """Stop the background precomputation thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        logger.info("Expansion precomputer stopped")

    def _run(self) -> None:
        """Background thread main loop."""
        from src.graph.hierarchy.expansion_strategy import evaluate_all_strategies

        while self._running:
            request = self._get_next_request()

            if request is None:
                # No work, sleep briefly
                time.sleep(0.1)
                continue

            try:
                start = time.time()

                ranked = evaluate_all_strategies(
                    member_node_ids=request.member_node_ids,
                    adjacency=self._adjacency,
                    node_id_to_idx=self._node_id_to_idx,
                    node_tags=self._node_tags,
                    max_sub_clusters=50,
                )

                elapsed_ms = int((time.time() - start) * 1000)

                self._cache.put(
                    cluster_id=request.cluster_id,
                    member_count=len(request.member_node_ids),
                    ranked_strategies=ranked,
                    computation_ms=elapsed_ms,
                )

                logger.debug(
                    "Precomputed expansion for cluster %s (%d members) in %dms, "
                    "found %d strategies",
                    request.cluster_id,
                    len(request.member_node_ids),
                    elapsed_ms,
                    len(ranked),
                )

            except Exception as e:
                logger.warning(
                    "Failed to precompute expansion for cluster %s: %s",
                    request.cluster_id,
                    e,
                )

    def _get_next_request(self) -> Optional[PrecomputeRequest]:
        """Get the next request from the queue."""
        with self._queue_lock:
            if not self._queue:
                return None
            return self._queue.pop(0)

    def get_queue_size(self) -> int:
        """Get number of pending precompute requests."""
        with self._queue_lock:
            return len(self._queue)


def compute_and_cache_expansion(
    cluster_id: str,
    member_node_ids: List[str],
    adjacency: sparse.spmatrix,
    node_id_to_idx: Dict[str, int],
    node_tags: Optional[Dict[str, Set[str]]] = None,
    weights: Optional["StructureScoreWeights"] = None,
    cache: Optional[ExpansionCache] = None,
) -> CachedExpansion:
    """Compute expansion strategies and cache the result.

    This is a synchronous helper for computing and caching expansions
    on-demand (when cache miss occurs).

    Args:
        cluster_id: The cluster ID
        member_node_ids: Members of the cluster
        adjacency: Full graph adjacency
        node_id_to_idx: Node ID to index mapping
        node_tags: Optional tag data
        weights: Optional scoring weights
        cache: Optional cache instance (uses global if not provided)

    Returns:
        CachedExpansion with ranked strategies
    """
    from src.graph.hierarchy.expansion_strategy import evaluate_all_strategies
    from src.graph.hierarchy.expansion_scoring import StructureScoreWeights

    if cache is None:
        cache = get_expansion_cache()

    # Check cache first
    cached = cache.get(cluster_id)
    if cached is not None:
        return cached

    # Compute
    start = time.time()

    ranked = evaluate_all_strategies(
        member_node_ids=member_node_ids,
        adjacency=adjacency,
        node_id_to_idx=node_id_to_idx,
        node_tags=node_tags,
        weights=weights,
        max_sub_clusters=50,
    )

    elapsed_ms = int((time.time() - start) * 1000)
    best = ranked[0] if ranked else None
    logger.info(
        "expansion_cache computed cluster=%s members=%d strategies=%d best=%s score=%.3f elapsed_ms=%d",
        cluster_id,
        len(member_node_ids),
        len(ranked),
        best.strategy_name if best else "none",
        best.score.total_score if best else 0.0,
        elapsed_ms,
    )

    # Cache
    cache.put(
        cluster_id=cluster_id,
        member_count=len(member_node_ids),
        ranked_strategies=ranked,
        computation_ms=elapsed_ms,
    )

    return cache.get(cluster_id)


def trigger_precompute_for_visible_clusters(
    visible_cluster_ids: List[str],
    cluster_members: Dict[str, List[str]],
    precomputer: ExpansionPrecomputer,
) -> int:
    """Trigger precomputation for clusters that become visible.

    Call this when the view changes and new clusters become visible.

    Args:
        visible_cluster_ids: IDs of clusters currently visible
        cluster_members: Mapping from cluster ID to member node IDs
        precomputer: The precomputer instance

    Returns:
        Number of clusters queued for precomputation
    """
    queued = 0

    for i, cluster_id in enumerate(visible_cluster_ids):
        if cluster_id in cluster_members:
            # Higher priority for clusters visible earlier (top of list)
            priority = len(visible_cluster_ids) - i

            if precomputer.enqueue(
                cluster_id=cluster_id,
                member_node_ids=cluster_members[cluster_id],
                priority=priority,
            ):
                queued += 1

    return queued
