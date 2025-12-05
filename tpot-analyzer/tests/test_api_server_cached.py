"""Integration tests for cached API endpoints.

Verifies that:
- /api/metrics/base endpoint caching works correctly
- Cache hit/miss headers are accurate
- /api/cache/stats endpoint returns correct statistics
- /api/cache/invalidate endpoint clears cache entries
- Concurrent requests share cache properly
- TTL expiration works in realistic scenarios
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from src.api.cache import MetricsCache
from src.api.server import app


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def client():
    """Flask test client with fresh cache."""
    app.config['TESTING'] = True

    # Get and clear cache
    from src.api.server import metrics_cache
    metrics_cache.invalidate()

    with app.test_client() as client:
        yield client


@pytest.fixture
def sample_request_payload():
    """Standard request payload for base metrics."""
    return {
        "seeds": ["alice", "bob"],
        "alpha": 0.85,
        "resolution": 1.0,
        "include_shadow": True,
        "mutual_only": False,
        "min_followers": 0,
    }


# ==============================================================================
# /api/metrics/base Endpoint Tests
# ==============================================================================

@pytest.mark.integration
def test_base_metrics_cache_miss_then_hit(client, sample_request_payload):
    """First request should be cache miss, second should be cache hit."""
    # First request - cache miss
    response1 = client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )

    assert response1.status_code == 200
    assert response1.headers.get('X-Cache-Status') == 'MISS'

    data1 = response1.get_json()
    assert 'metrics' in data1
    assert 'pagerank' in data1['metrics']
    assert 'betweenness' in data1['metrics']
    assert 'engagement' in data1['metrics']

    # Second request - cache hit
    response2 = client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )

    assert response2.status_code == 200
    assert response2.headers.get('X-Cache-Status') == 'HIT'

    # Data should be identical
    data2 = response2.get_json()
    assert data1 == data2


@pytest.mark.integration
def test_base_metrics_different_seeds_different_cache(client):
    """Different seeds should not hit same cache entry."""
    payload1 = {
        "seeds": ["alice"],
        "alpha": 0.85,
        "resolution": 1.0,
    }

    payload2 = {
        "seeds": ["bob"],
        "alpha": 0.85,
        "resolution": 1.0,
    }

    # First request
    response1 = client.post(
        '/api/metrics/base',
        data=json.dumps(payload1),
        content_type='application/json'
    )
    assert response1.headers.get('X-Cache-Status') == 'MISS'

    # Second request with different seeds - should also be miss
    response2 = client.post(
        '/api/metrics/base',
        data=json.dumps(payload2),
        content_type='application/json'
    )
    assert response2.headers.get('X-Cache-Status') == 'MISS'

    # Third request same as first - should be hit
    response3 = client.post(
        '/api/metrics/base',
        data=json.dumps(payload1),
        content_type='application/json'
    )
    assert response3.headers.get('X-Cache-Status') == 'HIT'


@pytest.mark.integration
def test_base_metrics_different_alpha_different_cache(client):
    """Different alpha values should not hit same cache entry."""
    payload1 = {
        "seeds": ["alice"],
        "alpha": 0.85,
        "resolution": 1.0,
    }

    payload2 = {
        "seeds": ["alice"],
        "alpha": 0.90,  # Different alpha
        "resolution": 1.0,
    }

    # First request
    response1 = client.post(
        '/api/metrics/base',
        data=json.dumps(payload1),
        content_type='application/json'
    )
    assert response1.headers.get('X-Cache-Status') == 'MISS'

    # Second request with different alpha - should also be miss
    response2 = client.post(
        '/api/metrics/base',
        data=json.dumps(payload2),
        content_type='application/json'
    )
    assert response2.headers.get('X-Cache-Status') == 'MISS'


@pytest.mark.integration
def test_base_metrics_cache_hit_faster_than_miss(client, sample_request_payload):
    """Cache hit should be significantly faster than cache miss."""
    # First request - cache miss (slow)
    response1 = client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )
    time1 = float(response1.headers.get('X-Response-Time', '0').replace('ms', ''))

    # Second request - cache hit (fast)
    response2 = client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )
    time2 = float(response2.headers.get('X-Response-Time', '0').replace('ms', ''))

    # Cache hit should be at least 5x faster
    assert time2 < time1 / 5, f"Cache hit ({time2}ms) not significantly faster than miss ({time1}ms)"


@pytest.mark.integration
def test_base_metrics_missing_seeds_returns_error(client):
    """Request without seeds should return error."""
    payload = {
        "alpha": 0.85,
        "resolution": 1.0,
    }

    response = client.post(
        '/api/metrics/base',
        data=json.dumps(payload),
        content_type='application/json'
    )

    # Should fail validation
    assert response.status_code in [400, 422]


@pytest.mark.integration
def test_base_metrics_empty_seeds_returns_error(client):
    """Request with empty seeds should return error."""
    payload = {
        "seeds": [],
        "alpha": 0.85,
        "resolution": 1.0,
    }

    response = client.post(
        '/api/metrics/base',
        data=json.dumps(payload),
        content_type='application/json'
    )

    # Should fail validation
    assert response.status_code in [400, 422]


# ==============================================================================
# /api/cache/stats Endpoint Tests
# ==============================================================================

@pytest.mark.integration
def test_cache_stats_initial_state(client):
    """Cache stats should show empty cache initially."""
    response = client.get('/api/cache/stats')

    assert response.status_code == 200

    data = response.get_json()
    assert data['size'] == 0
    assert data['hits'] == 0
    assert data['misses'] == 0
    assert data['hit_rate'] == 0.0


@pytest.mark.integration
def test_cache_stats_after_requests(client, sample_request_payload):
    """Cache stats should update after requests."""
    # Make some requests
    client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )  # Miss

    client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )  # Hit

    client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )  # Hit

    # Check stats
    response = client.get('/api/cache/stats')
    data = response.get_json()

    assert data['size'] == 1  # One unique cache entry
    assert data['hits'] == 2
    assert data['misses'] == 1
    assert data['hit_rate'] == pytest.approx(66.7, abs=0.1)


@pytest.mark.integration
def test_cache_stats_includes_entries(client, sample_request_payload):
    """Cache stats should include entry details."""
    # Make a request
    client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )

    # Check stats
    response = client.get('/api/cache/stats')
    data = response.get_json()

    assert 'entries' in data
    assert len(data['entries']) == 1

    entry = data['entries'][0]
    assert 'key' in entry
    assert 'age_seconds' in entry
    assert 'access_count' in entry
    assert 'computation_time_ms' in entry
    assert entry['access_count'] == 1


@pytest.mark.integration
def test_cache_stats_tracks_computation_time_saved(client, sample_request_payload):
    """Cache stats should track total time saved by caching."""
    # First request (miss)
    response1 = client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )

    # Second request (hit)
    client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )

    # Check stats
    response = client.get('/api/cache/stats')
    data = response.get_json()

    assert 'total_computation_time_saved_ms' in data
    # Should have saved time equal to original computation
    assert data['total_computation_time_saved_ms'] > 0


# ==============================================================================
# /api/cache/invalidate Endpoint Tests
# ==============================================================================

@pytest.mark.integration
def test_cache_invalidate_all(client, sample_request_payload):
    """Invalidating without prefix should clear all cache."""
    # Populate cache
    client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )

    # Verify cache has entries
    stats = client.get('/api/cache/stats').get_json()
    assert stats['size'] > 0

    # Invalidate all
    response = client.post(
        '/api/cache/invalidate',
        data=json.dumps({"prefix": None}),
        content_type='application/json'
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data['invalidated'] > 0

    # Verify cache is empty
    stats = client.get('/api/cache/stats').get_json()
    assert stats['size'] == 0


@pytest.mark.integration
def test_cache_invalidate_forces_recomputation(client, sample_request_payload):
    """After invalidation, next request should be cache miss."""
    # First request (miss)
    response1 = client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )
    assert response1.headers.get('X-Cache-Status') == 'MISS'

    # Second request (hit)
    response2 = client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )
    assert response2.headers.get('X-Cache-Status') == 'HIT'

    # Invalidate
    client.post(
        '/api/cache/invalidate',
        data=json.dumps({"prefix": None}),
        content_type='application/json'
    )

    # Third request (miss again after invalidation)
    response3 = client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )
    assert response3.headers.get('X-Cache-Status') == 'MISS'


@pytest.mark.integration
def test_cache_invalidate_with_prefix(client, sample_request_payload):
    """Invalidating with prefix should clear matching entries."""
    # Populate cache
    client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )

    # Invalidate with prefix
    response = client.post(
        '/api/cache/invalidate',
        data=json.dumps({"prefix": "base_metrics"}),
        content_type='application/json'
    )

    assert response.status_code == 200
    data = response.get_json()
    assert 'invalidated' in data
    assert data['prefix'] == 'base_metrics'


# ==============================================================================
# Concurrent Request Tests
# ==============================================================================

@pytest.mark.integration
def test_concurrent_requests_share_cache(client, sample_request_payload):
    """Multiple concurrent requests should benefit from shared cache."""
    # Prime the cache
    client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )

    # Make 10 concurrent requests
    def make_request():
        response = client.post(
            '/api/metrics/base',
            data=json.dumps(sample_request_payload),
            content_type='application/json'
        )
        return response.headers.get('X-Cache-Status')

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(make_request) for _ in range(10)]
        results = [future.result() for future in as_completed(futures)]

    # All should be cache hits
    assert all(status == 'HIT' for status in results)


@pytest.mark.integration
def test_concurrent_different_seeds_no_collision(client):
    """Concurrent requests with different seeds should not collide."""
    payloads = [
        {"seeds": ["alice"], "alpha": 0.85, "resolution": 1.0},
        {"seeds": ["bob"], "alpha": 0.85, "resolution": 1.0},
        {"seeds": ["charlie"], "alpha": 0.85, "resolution": 1.0},
    ]

    def make_request(payload):
        response = client.post(
            '/api/metrics/base',
            data=json.dumps(payload),
            content_type='application/json'
        )
        return response.get_json()

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(make_request, p) for p in payloads]
        results = [future.result() for future in as_completed(futures)]

    # All should succeed
    assert len(results) == 3

    # Check cache has 3 entries
    stats = client.get('/api/cache/stats').get_json()
    assert stats['size'] == 3


# ==============================================================================
# TTL Expiration Tests
# ==============================================================================

@pytest.mark.integration
@pytest.mark.slow
def test_cache_ttl_expiration_integration(sample_request_payload):
    """Cache entries should expire after TTL in realistic scenario."""
    # Create app with short TTL for testing
    app.config['TESTING'] = True

    # Create cache with short TTL
    short_ttl_cache = MetricsCache(max_size=100, ttl_seconds=2)

    # Temporarily replace app cache
    from src.api import server
    original_cache = server.metrics_cache
    server.metrics_cache = short_ttl_cache

    try:
        with app.test_client() as client:
            # First request (miss)
            response1 = client.post(
                '/api/metrics/base',
                data=json.dumps(sample_request_payload),
                content_type='application/json'
            )
            assert response1.headers.get('X-Cache-Status') == 'MISS'

            # Second request immediately (hit)
            response2 = client.post(
                '/api/metrics/base',
                data=json.dumps(sample_request_payload),
                content_type='application/json'
            )
            assert response2.headers.get('X-Cache-Status') == 'HIT'

            # Wait for TTL expiration
            time.sleep(2.5)

            # Third request after TTL (miss)
            response3 = client.post(
                '/api/metrics/base',
                data=json.dumps(sample_request_payload),
                content_type='application/json'
            )
            assert response3.headers.get('X-Cache-Status') == 'MISS'

    finally:
        # Restore original cache
        server.metrics_cache = original_cache


@pytest.mark.integration
def test_cache_stats_tracks_expirations(sample_request_payload):
    """Cache stats should track TTL expirations."""
    # Create cache with short TTL
    short_ttl_cache = MetricsCache(max_size=100, ttl_seconds=1)

    from src.api import server
    original_cache = server.metrics_cache
    server.metrics_cache = short_ttl_cache

    try:
        with app.test_client() as client:
            # Add entry
            client.post(
                '/api/metrics/base',
                data=json.dumps(sample_request_payload),
                content_type='application/json'
            )

            # Wait for expiration
            time.sleep(1.5)

            # Try to access (will detect expiration)
            client.post(
                '/api/metrics/base',
                data=json.dumps(sample_request_payload),
                content_type='application/json'
            )

            # Check stats
            stats = client.get('/api/cache/stats').get_json()
            assert stats['expirations'] >= 1

    finally:
        server.metrics_cache = original_cache


# ==============================================================================
# Edge Cases
# ==============================================================================

@pytest.mark.integration
def test_cache_with_invalid_seeds(client):
    """Request with invalid seeds should handle gracefully."""
    payload = {
        "seeds": ["nonexistent_user_12345"],
        "alpha": 0.85,
        "resolution": 1.0,
    }

    response = client.post(
        '/api/metrics/base',
        data=json.dumps(payload),
        content_type='application/json'
    )

    # Should either return empty results or error gracefully
    # (specific behavior depends on implementation)
    assert response.status_code in [200, 400, 404]


# Category C test deleted (Phase 1, Task 1.4):
# - test_cache_stats_endpoint_always_available (too generic: just checks 200 + fields exist)

@pytest.mark.integration
def test_base_metrics_response_structure(client, sample_request_payload):
    """Base metrics response should have expected structure."""
    response = client.post(
        '/api/metrics/base',
        data=json.dumps(sample_request_payload),
        content_type='application/json'
    )

    assert response.status_code == 200
    data = response.get_json()

    # Required fields
    assert 'seeds' in data
    assert 'resolved_seeds' in data
    assert 'metrics' in data

    # Metrics should have all base components
    metrics = data['metrics']
    assert 'pagerank' in metrics
    assert 'betweenness' in metrics
    assert 'engagement' in metrics
    assert 'communities' in metrics

    # Should NOT have composite (that's client-side)
    assert 'composite' not in metrics


@pytest.mark.integration
def test_cache_hit_rate_calculation_accuracy(client, sample_request_payload):
    """Cache hit rate should be calculated accurately."""
    # Make pattern of requests: MISS, HIT, HIT, MISS, HIT
    # Expected: 3 hits, 2 misses, 60% hit rate

    payload1 = {"seeds": ["alice"], "alpha": 0.85, "resolution": 1.0}
    payload2 = {"seeds": ["bob"], "alpha": 0.85, "resolution": 1.0}

    # Request 1: MISS (payload1)
    client.post('/api/metrics/base', data=json.dumps(payload1), content_type='application/json')

    # Request 2: HIT (payload1)
    client.post('/api/metrics/base', data=json.dumps(payload1), content_type='application/json')

    # Request 3: HIT (payload1)
    client.post('/api/metrics/base', data=json.dumps(payload1), content_type='application/json')

    # Request 4: MISS (payload2)
    client.post('/api/metrics/base', data=json.dumps(payload2), content_type='application/json')

    # Request 5: HIT (payload2)
    client.post('/api/metrics/base', data=json.dumps(payload2), content_type='application/json')

    # Check stats
    stats = client.get('/api/cache/stats').get_json()

    assert stats['hits'] == 3
    assert stats['misses'] == 2
    assert stats['hit_rate'] == pytest.approx(60.0, abs=0.1)
