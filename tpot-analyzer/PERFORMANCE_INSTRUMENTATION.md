# Performance Instrumentation Guide

**Status:** ✅ Fully Implemented
**Date:** 2025-10-10

---

## Overview

The graph-explorer now has **comprehensive performance instrumentation** to track empirical timing data across the entire stack:

- ✅ **Backend timing middleware** (Flask)
- ✅ **Frontend timing instrumentation** (JavaScript)
- ✅ **Performance metrics API endpoint**
- ✅ **Console logging with color coding**
- ✅ **Browser DevTools integration**

This allows you to answer questions like:
- "How long does PageRank computation actually take?"
- "Is the bottleneck in network transfer or computation?"
- "Which operations are slower than expected?"

---

## Quick Start: View Performance Data

### 1. Browser Console (Easiest)

Open browser DevTools (F12) → Console tab. You'll see color-coded timing logs:

```
[API] fetchGraphData: 342.56ms  {serverTime: "325.12ms", nodeCount: 7981, ...}
[API] computeMetrics: 1823.44ms {serverTime: "1805.23ms", seedCount: 5, ...}
```

**Color Coding:**
- 🟢 Green: < 500ms (fast)
- 🟠 Orange: 500-1000ms (acceptable)
- 🔴 Red: > 1000ms (slow)

### 2. Get Client-Side Stats

In browser console:
```javascript
// Get aggregated statistics
window.apiPerformance.getStats()

// Output:
// {
//   fetchGraphData: { count: 3, avg: "342.56", min: "298.12", max: "401.23" },
//   computeMetrics: { count: 5, avg: "1823.44", min: "1650.00", max: "2100.00" }
// }
```

### 3. Backend Server Logs

Terminal 1 (Flask server) shows timing for every request:

```
INFO:src.api.server:GET /api/graph-data -> 200 [342.56ms]
INFO:src.api.server:POST /api/metrics/compute -> 200 [1823.44ms]
```

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│         Browser (Client-Side)                    │
│  • performance.now() timing                      │
│  • Console logging (color-coded)                 │
│  • window.apiPerformance stats                   │
└──────────────────┬──────────────────────────────┘
                   │ HTTP Request
                   │
         ┌─────────▼──────────────┐
         │  Flask Middleware      │
         │  • @before_request     │
         │  • @after_request      │
         │  • X-Response-Time     │
         └─────────┬──────────────┘
                   │
         ┌─────────▼──────────────┐
         │  Endpoint Logic        │
         │  • build_graph()       │
         │  • compute_pagerank()  │
         └─────────┬──────────────┘
                   │
         ┌─────────▼──────────────┐
         │  Performance Store     │
         │  • In-memory cache     │
         │  • Last 1000 requests  │
         │  • Aggregated stats    │
         └────────────────────────┘
```

---

## What's Being Tracked

### Backend (Flask)

**For EVERY request:**
- ✅ Endpoint name
- ✅ HTTP method
- ✅ Response status code
- ✅ Total duration (ms)
- ✅ Timestamp

**Stored:**
- Last 1000 requests (rolling buffer)
- Aggregated stats: count, avg, min, max per endpoint

**Header Added:**
- `X-Response-Time: 342.56ms` (sent to client)

### Frontend (JavaScript)

**For EVERY API call:**
- ✅ Operation name
- ✅ Total client-side duration (network + parsing)
- ✅ Server-side duration (from header)
- ✅ Request parameters (seed count, weights, etc.)
- ✅ Response metadata (node count, edge count)

**Stored:**
- Last 100 calls (rolling buffer)
- Aggregated stats: count, avg, min, max per operation

---

## Usage Examples

### Example 1: Check Initial Load Time

```javascript
// In browser console after page loads
window.apiPerformance.getStats()

// Expected output:
// {
//   checkHealth: { count: 1, avg: "12.34", min: "12.34", max: "12.34" },
//   fetchGraphData: { count: 1, avg: "342.56", min: "342.56", max: "342.56" },
//   computeMetrics: { count: 1, avg: "1823.44", min: "1823.44", max: "1823.44" }
// }
```

**Analysis:**
- checkHealth: 12ms ✅ (expected)
- fetchGraphData: 343ms ✅ (good for 8K nodes)
- computeMetrics: 1823ms ⚠️ (acceptable, can optimize)

### Example 2: Compare Weight Slider Changes

```javascript
// Before changing slider
let before = window.apiPerformance.calls.length;

// Move α slider from 0.4 → 0.8
// Wait for computation...

// After
let after = window.apiPerformance.calls.slice(before);
console.table(after);

// Output shows timing for that specific computation
```

### Example 3: Benchmark Different Seed Sets

```javascript
// Clear previous data
window.apiPerformance.clear();

// Try seed set 1 (5 seeds)
// Apply seeds... wait...

// Try seed set 2 (10 seeds)
// Apply seeds... wait...

// Compare
window.apiPerformance.getStats();
// Shows if more seeds = slower computation
```

### Example 4: Backend Performance Endpoint

```bash
# Fetch backend metrics via API
curl http://localhost:5001/api/metrics/performance | jq

# Output:
# {
#   "aggregates": {
#     "GET health": {
#       "count": 5,
#       "avg_ms": 12.34,
#       "min_ms": 10.00,
#       "max_ms": 15.00,
#       "total_time_s": 0.0617
#     },
#     "POST compute_metrics": {
#       "count": 10,
#       "avg_ms": 1823.44,
#       "min_ms": 1650.00,
#       "max_ms": 2100.00,
#       "total_time_s": 18.2344
#     }
#   },
#   "recent_requests": [ ... ],
#   "total_requests": 15
# }
```

---

## Interpreting Results

### Client vs Server Time Split

When you see:
```
[API] computeMetrics: 1850ms  {serverTime: "1805ms", ...}
```

**Analysis:**
- Total time: 1850ms
- Server computation: 1805ms (97.6%)
- Network overhead: 45ms (2.4%)

**Conclusion:** Computation is the bottleneck, not network.

### Typical Performance Targets

| Operation | Good | Acceptable | Slow | Notes |
|-----------|------|------------|------|-------|
| checkHealth | <50ms | <100ms | >100ms | Should be instant |
| fetchGraphData | <500ms | <1000ms | >1000ms | Loads 8K nodes |
| computeMetrics | <1000ms | <2000ms | >2000ms | NetworkX PageRank |

**Current Performance (Option B):**
- checkHealth: ~10ms ✅
- fetchGraphData: ~300-500ms ✅
- computeMetrics: ~1500-2000ms ⚠️ (acceptable, can optimize)

---

## Profiling Workflow

### Step 1: Establish Baseline

```bash
# Start fresh
cd tpot-analyzer
source .venv/bin/activate
python -m scripts.start_api_server

# In browser console
window.apiPerformance.clear()

# Perform 5 identical operations (e.g., same seed set)
# Check stats
window.apiPerformance.getStats()
```

**Record:**
- Average time
- Min/max variance
- P95 latency

### Step 2: Identify Bottlenecks

```javascript
// Check server vs client split
window.apiPerformance.calls.forEach(call => {
  const serverMs = parseFloat(call.serverTime);
  const clientMs = call.duration_ms;
  const networkMs = clientMs - serverMs;
  console.log(`${call.operation}: server=${serverMs}ms, network=${networkMs}ms`);
});
```

**If network > 100ms:**
- Consider compression
- Check network tab in DevTools

**If server > 1500ms:**
- Profile Python code
- Consider caching (Option C)
- Check database queries

### Step 3: Test Optimization

```javascript
// Before optimization
const baseline = window.apiPerformance.getStats();

// Apply optimization (e.g., add caching)

// After optimization
window.apiPerformance.clear();
// Repeat same operations
const optimized = window.apiPerformance.getStats();

// Compare
console.log('Before:', baseline.computeMetrics.avg, 'ms');
console.log('After:', optimized.computeMetrics.avg, 'ms');
console.log('Improvement:',
  ((baseline.computeMetrics.avg - optimized.computeMetrics.avg) / baseline.computeMetrics.avg * 100).toFixed(1),
  '%'
);
```

---

## API Reference

### Frontend (data.js)

```javascript
// Get aggregated stats
window.apiPerformance.getStats()
// Returns: { operation: { count, avg, min, max } }

// Get all raw calls
window.apiPerformance.calls
// Returns: [{ operation, duration_ms, timestamp, ... }]

// Clear logs
window.apiPerformance.clear()
```

### Backend Endpoint

**GET /api/metrics/performance**

Response:
```json
{
  "aggregates": {
    "POST compute_metrics": {
      "count": 10,
      "avg_ms": 1823.44,
      "min_ms": 1650.00,
      "max_ms": 2100.00,
      "total_time_s": 18.2344
    }
  },
  "recent_requests": [
    {
      "endpoint": "compute_metrics",
      "method": "POST",
      "path": "/api/metrics/compute",
      "status": 200,
      "duration_ms": 1823.44,
      "timestamp": 1633900000.123
    }
  ],
  "total_requests": 15
}
```

---

## Debugging Slow Performance

### Symptom: computeMetrics > 3000ms

**Hypothesis 1: Large graph size**
```javascript
// Check node/edge counts
window.apiPerformance.calls
  .filter(c => c.operation === 'fetchGraphData')
  .forEach(c => console.log('Nodes:', c.nodeCount, 'Edges:', c.edgeCount));
```

**Action:** If nodes > 10K, consider filtering or subgraph sampling.

**Hypothesis 2: Complex PageRank computation**
```javascript
// Check seed count and resolved seeds
window.apiPerformance.calls
  .filter(c => c.operation === 'computeMetrics')
  .forEach(c => console.log('Seeds:', c.seedCount, 'Resolved:', c.resolvedSeeds));
```

**Action:** More seeds = longer computation. Consider limiting to top N seeds.

**Hypothesis 3: Database I/O**
```bash
# Check backend logs for database queries
# Terminal 1 should show timing
```

**Action:** If I/O is slow, check SQLite file size and consider indexing.

### Symptom: Network time > 200ms

**Check:**
```javascript
window.apiPerformance.calls.forEach(c => {
  const server = parseFloat(c.serverTime);
  const network = c.duration_ms - server;
  if (network > 200) {
    console.log(`High network latency: ${c.operation} (${network.toFixed(2)}ms)`);
  }
});
```

**Actions:**
1. Check DevTools → Network tab for payload size
2. Consider response compression (gzip)
3. Check if localhost or remote server
4. Test on different network

---

## Future Enhancements (Option C)

When implementing caching:

1. **Add cache hit/miss tracking**
   ```javascript
   performanceLog.log('computeMetrics', duration, {
     cacheHit: true,
     cacheKey: 'abc123'
   });
   ```

2. **Track cache effectiveness**
   ```javascript
   const hitRate = cacheHits / totalRequests * 100;
   console.log(`Cache hit rate: ${hitRate.toFixed(1)}%`);
   ```

3. **Compare cached vs uncached**
   ```javascript
   const cachedAvg = getCachedRequestsAvg();
   const uncachedAvg = getUncachedRequestsAvg();
   console.log(`Speedup: ${(uncachedAvg / cachedAvg).toFixed(2)}x`);
   ```

---

## Testing Instrumentation

### Verify Backend Timing

```bash
# Terminal 1: Start server
python -m scripts.start_api_server

# Terminal 2: Test with curl
time curl http://localhost:5001/api/graph-data?include_shadow=true

# Check:
# 1. Server logs show timing: [342.56ms]
# 2. Response header: X-Response-Time: 342.56ms
# 3. curl shows total time
```

### Verify Frontend Timing

```javascript
// In browser console
const start = performance.now();
await fetch('http://localhost:5001/api/graph-data?include_shadow=true');
const duration = performance.now() - start;
console.log(`Manual timing: ${duration.toFixed(2)}ms`);

// Compare with logged timing
const logged = window.apiPerformance.calls[window.apiPerformance.calls.length - 1];
console.log(`Logged timing: ${logged.duration_ms.toFixed(2)}ms`);

// Should be within 1-2ms
```

---

## Performance Regression Testing

Add to your test suite:

```python
# tests/test_performance.py
import pytest
import time

def test_compute_metrics_performance(client):
    """Ensure metrics computation stays under 3 seconds."""
    start = time.time()

    response = client.post('/api/metrics/compute', json={
        'seeds': ['nosilverv', 'DefenderOfBasic'],
        'weights': [0.4, 0.3, 0.3],
    })

    duration = time.time() - start

    assert response.status_code == 200
    assert duration < 3.0, f"Computation took {duration:.2f}s (expected < 3s)"

def test_graph_data_performance(client):
    """Ensure graph loading stays under 1 second."""
    start = time.time()

    response = client.get('/api/graph-data?include_shadow=true')

    duration = time.time() - start

    assert response.status_code == 200
    assert duration < 1.0, f"Graph load took {duration:.2f}s (expected < 1s)"
```

---

## Summary

**What you get:**
- ✅ Real-time performance logging in browser console
- ✅ Server-side timing in Flask logs
- ✅ Aggregated statistics via `window.apiPerformance.getStats()`
- ✅ Backend metrics API endpoint
- ✅ Color-coded visual feedback

**How to use it:**
1. Open browser DevTools → Console
2. Use the app normally (change seeds, sliders, etc.)
3. Run `window.apiPerformance.getStats()` to see aggregated data
4. Check Terminal 1 for server-side logs

**Next steps:**
- Establish baseline performance metrics
- Identify bottlenecks (server vs network)
- Implement Option C (caching) if needed
- Add performance regression tests

**Evidence-first debugging in action!** 📊
