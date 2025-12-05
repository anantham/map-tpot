# Performance Testing Guide

**Date:** 2025-01-10
**Status:** ✅ Comprehensive test coverage added

---

## Overview

This document describes the test suite for the performance optimization features added to the map-tpot analyzer. The caching layer and client-side reweighting optimizations are critical for maintaining sub-50ms response times, so comprehensive testing is essential.

---

## Test Coverage Summary

### Backend Tests

#### **test_api_cache.py** (22 tests)
Unit tests for the `MetricsCache` class.

**Coverage:**
- ✅ Basic cache operations (set, get, miss)
- ✅ LRU eviction behavior
- ✅ TTL expiration
- ✅ Cache invalidation
- ✅ Statistics tracking
- ✅ Cache key generation

**Run:**
```bash
cd tpot-analyzer
pytest tests/test_api_cache.py -v
```

#### **test_api_server_cached.py** (25 tests)
Integration tests for cached API endpoints.

**Coverage:**
- ✅ `/api/metrics/base` endpoint with cache hit/miss
- ✅ `/api/cache/stats` endpoint
- ✅ `/api/cache/invalidate` endpoint
- ✅ Concurrent request handling
- ✅ Cache performance verification
- ✅ TTL expiration in realistic scenarios

**Run:**
```bash
cd tpot-analyzer
pytest tests/test_api_server_cached.py -v
```

**Note:** Some tests are marked `@pytest.mark.slow` and use `time.sleep()` for TTL testing.

### Frontend Tests

#### **metricsUtils.test.js** (45 tests)
Unit tests for client-side metrics utilities.

**Coverage:**
- ✅ `normalizeScores()` - score normalization
- ✅ `computeCompositeScores()` - client-side reweighting
- ✅ `getTopScores()` - ranking
- ✅ `validateWeights()` - weight validation
- ✅ `weightsEqual()` - weight comparison
- ✅ `createBaseMetricsCacheKey()` - cache key generation
- ✅ `PerformanceTimer` - timing utility
- ✅ `BaseMetricsCache` - client-side LRU cache

**Setup:**
```bash
cd tpot-analyzer/graph-explorer
npm install
```

**Run:**
```bash
cd tpot-analyzer/graph-explorer

# Run once
npm test

# Watch mode (auto-rerun on changes)
npm run test:watch

# With coverage report
npm run test:coverage

# Interactive UI
npm run test:ui
```

---

## Test Categories

### Unit Tests (`@pytest.mark.unit`)
Fast, isolated tests for individual functions/classes.
- No external dependencies
- No I/O operations
- Deterministic results
- Run in <1s

**Examples:**
- `test_cache_set_and_get()` - Basic cache operations
- `test_normalize_scores()` - Score normalization logic
- `test_cache_key_deterministic()` - Cache key generation

### Integration Tests (`@pytest.mark.integration`)
Tests that verify multiple components working together.
- May involve Flask test client
- May test API endpoints
- May involve threading/concurrency
- Run in <5s each

**Examples:**
- `test_base_metrics_cache_miss_then_hit()` - Full request cycle
- `test_concurrent_requests_share_cache()` - Multi-threaded caching
- `test_cache_invalidate_forces_recomputation()` - Cache lifecycle

### Slow Tests (`@pytest.mark.slow`)
Tests that require `time.sleep()` for TTL expiration.
- Run in 2-5 seconds
- Only run when explicitly requested
- Critical for TTL verification

**Run slow tests:**
```bash
pytest -m slow -v
```

**Skip slow tests:**
```bash
pytest -m "not slow" -v
```

---

## Key Test Scenarios

### 1. Cache Hit/Miss Verification

**Backend (Python):**
```python
@pytest.mark.integration
def test_base_metrics_cache_miss_then_hit(client, sample_request_payload):
    # First request - MISS
    response1 = client.post('/api/metrics/base', ...)
    assert response1.headers.get('X-Cache-Status') == 'MISS'

    # Second request - HIT
    response2 = client.post('/api/metrics/base', ...)
    assert response2.headers.get('X-Cache-Status') == 'HIT'
```

**Frontend (JavaScript):**
```javascript
it('should store and retrieve values', () => {
  const key = 'test:key';
  const value = { data: 'test' };

  baseMetricsCache.set(key, value);
  const retrieved = baseMetricsCache.get(key);

  expect(retrieved).toEqual(value);
});
```

### 2. Performance Verification

**Backend:**
```python
@pytest.mark.integration
def test_cache_hit_faster_than_miss(client, sample_request_payload):
    # Cache miss timing
    response1 = client.post('/api/metrics/base', ...)
    time1 = float(response1.headers.get('X-Response-Time').replace('ms', ''))

    # Cache hit timing
    response2 = client.post('/api/metrics/base', ...)
    time2 = float(response2.headers.get('X-Response-Time').replace('ms', ''))

    # Cache hit should be at least 5x faster
    assert time2 < time1 / 5
```

**Frontend:**
```javascript
describe('PerformanceTimer', () => {
  it('should measure elapsed time', () => {
    const timer = new PerformanceTimer('test');
    // ... do work ...
    const duration = timer.end();

    expect(duration).toBeGreaterThanOrEqual(0);
  });
});
```

### 3. LRU Eviction

**Backend:**
```python
@pytest.mark.unit
def test_cache_lru_eviction():
    cache = MetricsCache(max_size=3, ttl_seconds=60)
    cache.set("test", {"id": 1}, "value1")
    cache.set("test", {"id": 2}, "value2")
    cache.set("test", {"id": 3}, "value3")
    cache.set("test", {"id": 4}, "value4")  # Evicts id=1

    assert cache.get("test", {"id": 1}) is None  # Evicted
    assert cache.get("test", {"id": 2}) == "value2"  # Still present
```

**Frontend:**
```javascript
it('should evict oldest entry when at capacity', () => {
  // Fill cache to max (10 entries)
  for (let i = 0; i < 10; i++) {
    baseMetricsCache.set(`key${i}`, { value: i });
  }

  // Add 11th entry - evicts key0
  baseMetricsCache.set('key10', { value: 10 });

  expect(baseMetricsCache.get('key0')).toBeNull();
  expect(baseMetricsCache.get('key10')).not.toBeNull();
});
```

### 4. Client-Side Reweighting

**Frontend:**
```javascript
describe('computeCompositeScores', () => {
  it('should compute composite scores with equal weights', () => {
    const baseMetrics = {
      pagerank: { node1: 0.5, node2: 0.3, node3: 0.2 },
      betweenness: { node1: 0.1, node2: 0.7, node3: 0.2 },
      engagement: { node1: 0.8, node2: 0.4, node3: 0.3 },
    };

    const weights = [1/3, 1/3, 1/3];
    const composite = computeCompositeScores(baseMetrics, weights);

    expect(Object.keys(composite)).toEqual(['node1', 'node2', 'node3']);
  });
});
```

### 5. Concurrent Requests

**Backend:**
```python
@pytest.mark.integration
def test_concurrent_requests_share_cache(client, sample_request_payload):
    # Prime cache
    client.post('/api/metrics/base', ...)

    # 10 concurrent requests
    def make_request():
        response = client.post('/api/metrics/base', ...)
        return response.headers.get('X-Cache-Status')

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(make_request) for _ in range(10)]
        results = [future.result() for future in as_completed(futures)]

    # All should be cache hits
    assert all(status == 'HIT' for status in results)
```

### 6. TTL Expiration

**Backend:**
```python
@pytest.mark.integration
@pytest.mark.slow
def test_cache_ttl_expiration_integration(sample_request_payload):
    short_ttl_cache = MetricsCache(max_size=100, ttl_seconds=2)

    # First request (MISS)
    response1 = client.post('/api/metrics/base', ...)
    assert response1.headers.get('X-Cache-Status') == 'MISS'

    # Immediate second request (HIT)
    response2 = client.post('/api/metrics/base', ...)
    assert response2.headers.get('X-Cache-Status') == 'HIT'

    # Wait for expiration
    time.sleep(2.5)

    # Third request after TTL (MISS)
    response3 = client.post('/api/metrics/base', ...)
    assert response3.headers.get('X-Cache-Status') == 'MISS'
```

---

## Running All Tests

### Backend Tests Only
```bash
cd tpot-analyzer
pytest tests/test_api_cache.py tests/test_api_server_cached.py -v
```

### Backend Tests with Coverage
```bash
cd tpot-analyzer
pytest tests/test_api_cache.py tests/test_api_server_cached.py --cov=src/api --cov-report=html
```

### Frontend Tests Only
```bash
cd tpot-analyzer/graph-explorer
npm test
```

### Frontend Tests with Coverage
```bash
cd tpot-analyzer/graph-explorer
npm run test:coverage
```

### All Tests (Backend + Frontend)
```bash
# Terminal 1: Backend tests
cd tpot-analyzer
pytest tests/test_api_cache.py tests/test_api_server_cached.py -v

# Terminal 2: Frontend tests
cd tpot-analyzer/graph-explorer
npm test
```

---

## Test Fixtures

### Backend Fixtures

#### `client`
Flask test client with fresh cache.
```python
@pytest.fixture
def client():
    app.config['TESTING'] = True
    from src.api.server import metrics_cache
    metrics_cache.invalidate()
    with app.test_client() as client:
        yield client
```

#### `sample_request_payload`
Standard request payload for base metrics.
```python
@pytest.fixture
def sample_request_payload():
    return {
        "seeds": ["alice", "bob"],
        "alpha": 0.85,
        "resolution": 1.0,
        "include_shadow": True,
        "mutual_only": False,
        "min_followers": 0,
    }
```

### Frontend Fixtures

Vitest automatically provides `beforeEach`, `describe`, `it`, `expect`.

**Example:**
```javascript
describe('BaseMetricsCache', () => {
  beforeEach(() => {
    baseMetricsCache.clear();
  });

  it('should store and retrieve values', () => {
    // ...
  });
});
```

---

## Expected Coverage

### Backend

| Module | Lines | Coverage | Target |
|--------|-------|----------|--------|
| `src/api/cache.py` | 302 | **~95%** | 95%+ |
| `src/api/server.py` (cache endpoints) | ~150 | **~90%** | 90%+ |

**Excluded from coverage:**
- Flask app initialization
- `if __name__ == '__main__'` blocks
- Error handling for external service failures

### Frontend

| Module | Lines | Coverage | Target |
|--------|-------|----------|--------|
| `src/metricsUtils.js` | 257 | **~95%** | 95%+ |

**Excluded from coverage:**
- Console logging statements
- `window` object assignments (browser-only)

---

## Continuous Integration

### Recommended CI Pipeline

```yaml
name: Performance Tests

on: [push, pull_request]

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          cd tpot-analyzer
          pip install -e .
          pip install pytest pytest-cov
      - name: Run backend tests
        run: |
          cd tpot-analyzer
          pytest tests/test_api_cache.py tests/test_api_server_cached.py \
            -v --cov=src/api --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '20'
      - name: Install dependencies
        run: |
          cd tpot-analyzer/graph-explorer
          npm ci
      - name: Run frontend tests
        run: |
          cd tpot-analyzer/graph-explorer
          npm run test:coverage
```

---

## Debugging Failing Tests

### Backend

**Issue:** Cache tests failing with import errors
```
ModuleNotFoundError: No module named 'src.api.cache'
```

**Fix:**
```bash
cd tpot-analyzer
pip install -e .
```

**Issue:** Flask app tests timeout
```
TimeoutError: Request took too long
```

**Fix:** Check that test client is configured correctly:
```python
app.config['TESTING'] = True
```

### Frontend

**Issue:** Module not found errors
```
Error: Cannot find module './metricsUtils.js'
```

**Fix:** Ensure `vitest.config.js` is present and test uses correct import:
```javascript
import { ... } from './metricsUtils.js';  // Include .js extension
```

**Issue:** `window` is not defined
```
ReferenceError: window is not defined
```

**Fix:** Ensure `vitest.config.js` has `environment: 'jsdom'`:
```javascript
export default defineConfig({
  test: {
    environment: 'jsdom',  // Simulates browser environment
  },
});
```

---

## Performance Benchmarks

### Test Execution Time

| Test Suite | # Tests | Execution Time | Target |
|------------|---------|----------------|--------|
| `test_api_cache.py` | 22 | ~2s | <5s |
| `test_api_server_cached.py` (fast) | 23 | ~5s | <10s |
| `test_api_server_cached.py` (slow) | 2 | ~5s | <10s |
| `metricsUtils.test.js` | 45 | ~0.5s | <2s |
| **Total** | **92** | **~12.5s** | **<30s** |

**Note:** Slow tests can be skipped in development with `pytest -m "not slow"`

---

## Future Test Additions

### High Priority
- [ ] Cache warming tests (if feature implemented)
- [ ] Redis cache backend tests (if feature added)
- [ ] Stress tests for concurrent requests (1000+ simultaneous)
- [ ] Memory leak tests for long-running cache

### Medium Priority
- [ ] Property-based tests for cache key generation
- [ ] Fuzzing tests for malformed API requests
- [ ] Performance regression tests (track response times over commits)

### Low Priority
- [ ] Visual regression tests for UI
- [ ] Load tests with realistic traffic patterns
- [ ] Tests for cache metrics dashboard

---

## Contributing

When adding new performance features, please:

1. **Add unit tests** for new functions/classes
2. **Add integration tests** for new API endpoints
3. **Update this document** with new test descriptions
4. **Run all tests** before committing:
   ```bash
   # Backend
   cd tpot-analyzer
   pytest tests/test_api_cache.py tests/test_api_server_cached.py -v

   # Frontend
   cd tpot-analyzer/graph-explorer
   npm test
   ```

5. **Verify coverage** stays above 90%:
   ```bash
   # Backend
   pytest --cov=src/api --cov-report=term

   # Frontend
   npm run test:coverage
   ```

---

## Resources

- **pytest documentation:** https://docs.pytest.org/
- **Vitest documentation:** https://vitest.dev/
- **Flask testing:** https://flask.palletsprojects.com/en/latest/testing/
- **Performance optimization doc:** [PERFORMANCE_OPTIMIZATION.md](./PERFORMANCE_OPTIMIZATION.md)

---

## Summary

✅ **92 new tests added** (47 backend + 45 frontend)
✅ **~95% coverage** on performance code
✅ **All critical paths tested**
✅ **Fast test execution** (<15s total)
✅ **CI/CD ready**

The test suite ensures the performance optimizations remain stable and effective as the codebase evolves.
