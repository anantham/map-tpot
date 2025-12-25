"""Tests for expansion cache infrastructure."""
import time
import pytest
import scipy.sparse as sp
import numpy as np

from src.graph.hierarchy.expansion_cache import (
    ExpansionCache,
    CachedExpansion,
    get_expansion_cache,
    reset_expansion_cache,
    compute_and_cache_expansion,
    ExpansionPrecomputer,
    trigger_precompute_for_visible_clusters,
)
from src.graph.hierarchy.expansion_scoring import (
    ScoredStrategy,
    StructureScoreBreakdown,
)


class TestExpansionCache:
    """Tests for the ExpansionCache class."""

    def test_put_and_get(self):
        """Should store and retrieve entries."""
        cache = ExpansionCache(max_entries=10)

        strategies = [
            ScoredStrategy(
                strategy_name="louvain",
                sub_clusters=[["a", "b"], ["c", "d"]],
                score=StructureScoreBreakdown(total_score=0.8),
            )
        ]

        cache.put(
            cluster_id="c1",
            member_count=4,
            ranked_strategies=strategies,
            computation_ms=100,
        )

        result = cache.get("c1")
        assert result is not None
        assert result.cluster_id == "c1"
        assert result.member_count == 4
        assert len(result.ranked_strategies) == 1
        assert result.computation_ms == 100

    def test_cache_miss_returns_none(self):
        """Should return None for missing entries."""
        cache = ExpansionCache()
        assert cache.get("nonexistent") is None

    def test_lru_eviction(self):
        """Should evict oldest entries when at capacity."""
        cache = ExpansionCache(max_entries=3)

        for i in range(5):
            cache.put(f"c{i}", i, [], 0)

        # First 2 should be evicted
        assert cache.get("c0") is None
        assert cache.get("c1") is None

        # Last 3 should exist
        assert cache.get("c2") is not None
        assert cache.get("c3") is not None
        assert cache.get("c4") is not None

    def test_lru_access_order(self):
        """Accessing an entry should move it to end of LRU."""
        cache = ExpansionCache(max_entries=3)

        cache.put("c0", 0, [], 0)
        cache.put("c1", 1, [], 0)
        cache.put("c2", 2, [], 0)

        # Access c0 to make it most recently used
        cache.get("c0")

        # Add new entry, should evict c1 (oldest)
        cache.put("c3", 3, [], 0)

        assert cache.get("c0") is not None  # Still there (was accessed)
        assert cache.get("c1") is None  # Evicted
        assert cache.get("c2") is not None
        assert cache.get("c3") is not None

    def test_ttl_expiration(self):
        """Should expire entries after TTL."""
        # Very short TTL for testing
        cache = ExpansionCache(max_entries=10, ttl_seconds=0.05)

        cache.put("c1", 1, [], 0)

        # Should exist immediately
        assert cache.get("c1") is not None

        # Wait for expiry (generous margin)
        time.sleep(0.2)

        # Should be expired
        assert cache.get("c1") is None

    def test_invalidate_single(self):
        """Should remove specific entry."""
        cache = ExpansionCache()

        cache.put("c1", 1, [], 0)
        cache.put("c2", 2, [], 0)

        assert cache.invalidate("c1") is True
        assert cache.get("c1") is None
        assert cache.get("c2") is not None

    def test_invalidate_all(self):
        """Should clear entire cache."""
        cache = ExpansionCache()

        cache.put("c1", 1, [], 0)
        cache.put("c2", 2, [], 0)
        cache.put("c3", 3, [], 0)

        count = cache.invalidate_all()
        assert count == 3
        assert cache.get("c1") is None
        assert cache.get("c2") is None
        assert cache.get("c3") is None

    def test_stats_tracking(self):
        """Should track hits, misses, and evictions."""
        cache = ExpansionCache(max_entries=2)

        cache.put("c1", 1, [], 0)

        # Miss
        cache.get("nonexistent")

        # Hit
        cache.get("c1")
        cache.get("c1")

        # Trigger eviction
        cache.put("c2", 2, [], 0)
        cache.put("c3", 3, [], 0)  # Evicts c1

        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["evictions"] == 1
        assert stats["entries"] == 2


class TestCachedExpansion:
    """Tests for CachedExpansion dataclass."""

    def test_best_strategy(self):
        """Should return first strategy as best."""
        strategies = [
            ScoredStrategy("best", [], StructureScoreBreakdown(total_score=0.9)),
            ScoredStrategy("second", [], StructureScoreBreakdown(total_score=0.7)),
        ]

        entry = CachedExpansion(
            cluster_id="c1",
            member_count=10,
            ranked_strategies=strategies,
            computed_at=time.time(),
            computation_ms=50,
        )

        assert entry.best_strategy is not None
        assert entry.best_strategy.strategy_name == "best"

    def test_alternative_strategies(self):
        """Should return all except first as alternatives."""
        strategies = [
            ScoredStrategy("best", [], StructureScoreBreakdown(total_score=0.9)),
            ScoredStrategy("second", [], StructureScoreBreakdown(total_score=0.7)),
            ScoredStrategy("third", [], StructureScoreBreakdown(total_score=0.5)),
        ]

        entry = CachedExpansion(
            cluster_id="c1",
            member_count=10,
            ranked_strategies=strategies,
            computed_at=time.time(),
            computation_ms=50,
        )

        alts = entry.alternative_strategies
        assert len(alts) == 2
        assert alts[0].strategy_name == "second"
        assert alts[1].strategy_name == "third"

    def test_empty_strategies(self):
        """Should handle empty strategy list."""
        entry = CachedExpansion(
            cluster_id="c1",
            member_count=0,
            ranked_strategies=[],
            computed_at=time.time(),
            computation_ms=0,
        )

        assert entry.best_strategy is None
        assert entry.alternative_strategies == []


class TestGlobalCache:
    """Tests for global cache management."""

    def test_get_creates_singleton(self):
        """get_expansion_cache should return same instance."""
        reset_expansion_cache()

        cache1 = get_expansion_cache()
        cache2 = get_expansion_cache()

        assert cache1 is cache2

    def test_reset_clears_and_recreates(self):
        """reset_expansion_cache should clear and allow new instance."""
        reset_expansion_cache()

        cache1 = get_expansion_cache()
        cache1.put("c1", 1, [], 0)

        reset_expansion_cache()

        cache2 = get_expansion_cache()
        assert cache2.get("c1") is None  # Cleared


class TestComputeAndCache:
    """Tests for compute_and_cache_expansion."""

    @pytest.fixture
    def simple_graph(self):
        """Create a simple test graph."""
        n = 15
        rows, cols = [], []

        # Some edges
        for i in range(n - 1):
            rows.extend([i, i + 1])
            cols.extend([i + 1, i])

        adjacency = sp.csr_matrix(([1.0] * len(rows), (rows, cols)), shape=(n, n))
        node_ids = [f"n{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        return adjacency, node_ids, node_id_to_idx

    def test_computes_and_caches(self, simple_graph):
        """Should compute strategies and cache them."""
        adjacency, node_ids, node_id_to_idx = simple_graph
        cache = ExpansionCache()

        result = compute_and_cache_expansion(
            cluster_id="test_cluster",
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            cache=cache,
        )

        assert result is not None
        assert result.cluster_id == "test_cluster"
        assert result.member_count == len(node_ids)
        assert len(result.ranked_strategies) >= 1

        # Should be cached now
        cached = cache.get("test_cluster")
        assert cached is not None
        assert cached.cluster_id == result.cluster_id

    def test_returns_cached_on_hit(self, simple_graph):
        """Should return cached result on cache hit."""
        adjacency, node_ids, node_id_to_idx = simple_graph
        cache = ExpansionCache()

        # Pre-populate cache
        strategies = [
            ScoredStrategy("cached", [], StructureScoreBreakdown(total_score=0.99))
        ]
        cache.put("test_cluster", 15, strategies, 0)

        result = compute_and_cache_expansion(
            cluster_id="test_cluster",
            member_node_ids=node_ids,
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            cache=cache,
        )

        # Should return cached version (score 0.99)
        assert result.best_strategy.strategy_name == "cached"


class TestExpansionPrecomputer:
    """Tests for background precomputation."""

    @pytest.fixture
    def simple_graph(self):
        """Create a simple test graph."""
        n = 20
        rows, cols = [], []
        rng = np.random.RandomState(42)

        for i in range(n):
            for j in range(i + 1, n):
                if rng.random() < 0.3:
                    rows.extend([i, j])
                    cols.extend([j, i])

        adjacency = sp.csr_matrix(([1.0] * len(rows), (rows, cols)), shape=(n, n))
        node_ids = [f"n{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        return adjacency, node_ids, node_id_to_idx

    def test_enqueue_adds_to_queue(self, simple_graph):
        """Should add requests to queue."""
        adjacency, node_ids, node_id_to_idx = simple_graph
        cache = ExpansionCache()

        precomputer = ExpansionPrecomputer(
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            cache=cache,
        )

        result = precomputer.enqueue("c1", node_ids[:10])
        assert result is True
        assert precomputer.get_queue_size() == 1

    def test_enqueue_skips_cached(self, simple_graph):
        """Should not enqueue already cached clusters."""
        adjacency, node_ids, node_id_to_idx = simple_graph
        cache = ExpansionCache()

        # Pre-cache
        cache.put("c1", 10, [], 0)

        precomputer = ExpansionPrecomputer(
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            cache=cache,
        )

        result = precomputer.enqueue("c1", node_ids[:10])
        assert result is False

    def test_enqueue_skips_duplicate(self, simple_graph):
        """Should not enqueue same cluster twice."""
        adjacency, node_ids, node_id_to_idx = simple_graph
        cache = ExpansionCache()

        precomputer = ExpansionPrecomputer(
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            cache=cache,
        )

        precomputer.enqueue("c1", node_ids[:10])
        result = precomputer.enqueue("c1", node_ids[:10])

        assert result is False
        assert precomputer.get_queue_size() == 1

    def test_priority_ordering(self, simple_graph):
        """Higher priority should be processed first."""
        adjacency, node_ids, node_id_to_idx = simple_graph
        cache = ExpansionCache()

        precomputer = ExpansionPrecomputer(
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            cache=cache,
        )

        precomputer.enqueue("low", node_ids[:5], priority=1)
        precomputer.enqueue("high", node_ids[5:10], priority=10)
        precomputer.enqueue("medium", node_ids[10:15], priority=5)

        # Queue should be ordered: high, medium, low
        request = precomputer._get_next_request()
        assert request.cluster_id == "high"

        request = precomputer._get_next_request()
        assert request.cluster_id == "medium"


class TestTriggerPrecompute:
    """Tests for trigger_precompute_for_visible_clusters."""

    @pytest.fixture
    def simple_graph(self):
        """Create a simple test graph."""
        n = 30
        adjacency = sp.csr_matrix((n, n))
        node_ids = [f"n{i}" for i in range(n)]
        node_id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        return adjacency, node_ids, node_id_to_idx

    def test_queues_visible_clusters(self, simple_graph):
        """Should queue all visible clusters."""
        adjacency, node_ids, node_id_to_idx = simple_graph
        cache = ExpansionCache()

        precomputer = ExpansionPrecomputer(
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            cache=cache,
        )

        cluster_members = {
            "c1": node_ids[:10],
            "c2": node_ids[10:20],
            "c3": node_ids[20:30],
        }

        queued = trigger_precompute_for_visible_clusters(
            visible_cluster_ids=["c1", "c2", "c3"],
            cluster_members=cluster_members,
            precomputer=precomputer,
        )

        assert queued == 3
        assert precomputer.get_queue_size() == 3

    def test_skips_unknown_clusters(self, simple_graph):
        """Should skip clusters not in cluster_members."""
        adjacency, node_ids, node_id_to_idx = simple_graph
        cache = ExpansionCache()

        precomputer = ExpansionPrecomputer(
            adjacency=adjacency,
            node_id_to_idx=node_id_to_idx,
            cache=cache,
        )

        cluster_members = {
            "c1": node_ids[:10],
        }

        queued = trigger_precompute_for_visible_clusters(
            visible_cluster_ids=["c1", "c2", "c3"],  # c2, c3 not in members
            cluster_members=cluster_members,
            precomputer=precomputer,
        )

        assert queued == 1
