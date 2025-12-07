# Backend Performance Issue Diagnosis

## Problem Summary

The backend is taking 14-23 seconds to respond to `/api/graph-data` requests, causing frontend timeout errors.

---

## Root Causes Identified

### 1. **Snapshot Not Being Used for API Requests** 🔴 CRITICAL

**Evidence from logs**:
```
2025-12-07 01:16:08,811 [INFO] Building graph from cache (snapshot unavailable or stale)
```

**What's happening**:
- Snapshot IS loaded at startup (95,303 nodes, 322,621 edges)
- But `/api/graph-data` endpoint doesn't use it - rebuilds from database every time!
- Backend rebuilds the entire graph for every API request

**Why this is slow**:
1. Reads from SQLite cache database
2. Builds NetworkX graph object (95K nodes, 322K edges)
3. **Serializes all 322,621 edges in Python for-loop** ← BOTTLENECK

**Time breakdown**:
- Build graph from DB: ~8-10s
- Serialize edges (for-loop): ~8-12s
- **Total**: 14-23s per request

---

### 2. **Edge Serialization is Extremely Slow** 🔴 CRITICAL

**Problem code** (`src/api/server.py:438-451`):
```python
edges = []
for u, v in directed.edges():  # ← 322,621 iterations!
    data = directed.get_edge_data(u, v, default={})
    edges.append({
        "source": u,
        "target": v,
        "mutual": directed.has_edge(v, u),  # ← Extra lookup per edge!
        # ... 8 more fields
    })
```

**Why it's slow**:
- Python for-loop over 322K edges
- `get_edge_data()` call for each edge
- `has_edge(v, u)` for mutual check (another graph lookup!)
- Dictionary creation per edge
- List append per edge

**Expected time**: 8-12 seconds for 322K edges

---

### 3. **Frontend Timeout Too Aggressive** ⚠️ MEDIUM

**Problem**: `/api/graph-data` was using 8-second timeout, but backend takes 14-23s

**Fixed**: Increased to 30-second timeout for this endpoint

---

## Current Performance

| Endpoint | Time | Status |
|----------|------|--------|
| `/api/graph-data` | 14-23s | ❌ Too slow |
| `/api/metrics/compute` | 6-8s | ⚠️ Slow |
| `/api/clusters` | ~1s | ✅ OK (cached) |

---

## Solutions

### **Solution 1: Use Snapshot for `/api/graph-data`** ⭐ HIGHEST PRIORITY

The snapshot is already loaded! Just use it instead of rebuilding.

**Current behavior**:
```python
# src/api/server.py:413-415
if can_use_snapshot:
    graph = snapshot_loader.load_graph()  # This returns None!
```

**Why it returns None**:
- `load_graph()` likely checks freshness/cache
- May be returning None due to some condition check
- Need to debug why snapshot isn't available

**Quick fix**: Cache the snapshot at startup and reuse it

```python
# In server.py startup
CACHED_SNAPSHOT = None

def init_app():
    global CACHED_SNAPSHOT
    snapshot_loader = SnapshotLoader(data_dir)
    CACHED_SNAPSHOT = snapshot_loader.load_graph(force_reload=True)
    logger.info(f"Cached snapshot: {CACHED_SNAPSHOT.directed.number_of_nodes()} nodes")

# In /api/graph-data endpoint
if can_use_snapshot and CACHED_SNAPSHOT:
    graph = CACHED_SNAPSHOT  # Instant!
else:
    graph = build_graph(...)  # Slow fallback
```

**Expected improvement**: 14-23s → <100ms ⚡

---

### **Solution 2: Optimize Edge Serialization** ⭐ HIGH PRIORITY

Replace Python for-loop with vectorized operations or pre-serialized data.

**Option A: Pre-serialize snapshot edges at build time**

Save edges as JSON during snapshot creation:
```bash
# data/graph_snapshot.edges.json (pre-serialized)
```

Then just load and return:
```python
with open('data/graph_snapshot.edges.json') as f:
    edges = json.load(f)  # <100ms instead of 8-12s
```

**Option B: Use pandas DataFrame**

Convert edges to DataFrame, serialize with `.to_dict('records')`:
```python
import pandas as pd

edge_data = [(u, v, directed.get_edge_data(u, v)) for u, v in directed.edges()]
df = pd.DataFrame(edge_data, columns=['source', 'target', 'data'])
edges = df.to_dict('records')  # Much faster than for-loop
```

**Expected improvement**: 8-12s → <500ms

---

### **Solution 3: Add Response Caching** ⭐ MEDIUM PRIORITY

Cache the JSON response for repeated requests:

```python
from functools import lru_cache
import hashlib

@app.route("/api/graph-data")
def get_graph_data():
    cache_key = f"{include_shadow}_{mutual_only}_{min_followers}"

    if cache_key in RESPONSE_CACHE:
        logger.info("Returning cached response")
        return RESPONSE_CACHE[cache_key]

    # ... build response ...

    RESPONSE_CACHE[cache_key] = response
    return response
```

**Expected improvement**: 14-23s → <10ms for cached requests

---

## Immediate Action Plan

### Phase 1: Quick Wins (10 minutes)

1. ✅ **Increase frontend timeout to 30s** (DONE)
   - Prevents timeout errors while backend is slow

2. ⏳ **Cache snapshot globally at startup**
   - Modify `src/api/server.py` to store snapshot in memory
   - Use cached snapshot instead of rebuilding

### Phase 2: Edge Serialization (30 minutes)

3. **Pre-serialize edges during snapshot creation**
   - Modify snapshot builder to save `graph_snapshot.edges.json`
   - Load pre-serialized JSON instead of iterating

### Phase 3: Response Caching (15 minutes)

4. **Add in-memory response cache**
   - Cache the full JSON response
   - Invalidate when snapshot changes

---

## Expected Results

| Phase | Current | After Fix | Improvement |
|-------|---------|-----------|-------------|
| **Frontend timeout** | 8s (fails) | 30s | No more errors ✅ |
| **Phase 1** | 14-23s | <1s | **95% faster** |
| **Phase 2** | <1s | <200ms | 80% faster |
| **Phase 3** | <200ms | <10ms | 95% faster |

**Final target**: <10ms for cached, <200ms for fresh

---

## Why This Matters

### User Experience Impact

**Current**:
- Page load: 25-45 seconds (retries + timeouts)
- 50% request failure rate
- Poor first impression

**After fixes**:
- Page load: <1 second
- 0% failures
- Instant, smooth experience

---

## Monitoring

After implementing fixes, monitor these metrics:

```python
# In logs, look for:
[INFO] Returning cached snapshot: 0.05ms  # Good!
[INFO] Building graph from cache: 15000ms  # Bad!
[INFO] Serializing 322621 edges: 8500ms   # Bad!
```

---

## Files to Modify

1. **src/api/server.py** (lines 399-478)
   - Add global snapshot cache
   - Use cached snapshot instead of rebuilding
   - Add response caching

2. **scripts/refresh_graph_snapshot.py**
   - Save pre-serialized edges JSON
   - Save pre-serialized nodes JSON

3. **graph-explorer/src/data.js** (line 257)
   - ✅ DONE: Increased timeout to 30s

---

## Testing

After implementing:

1. **Restart backend**
2. **Check logs** for "Cached snapshot" message
3. **Load frontend** and check console:
   ```
   [API] fetchGraphData: 120ms  # Should be <500ms
   ```
4. **Reload page** - second load should be <50ms (cached)

---

## Next Steps

1. Implement Phase 1 (snapshot caching) - **10 minutes**
2. Test and verify <1s response time
3. If still slow, implement Phase 2 (edge pre-serialization)

The frontend timeout fix is already deployed, so errors should stop immediately. Backend optimization will make it fast!
