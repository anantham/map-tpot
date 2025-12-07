# Performance Monitoring Guide

This guide explains how to interpret the performance logs when using the cluster view.

## Console Log Structure

When you click on the cluster view or expand/collapse clusters, you'll see detailed timing breakdowns in the browser console.

---

## Cluster View Load Sequence

### Stage-by-Stage Breakdown

When loading the cluster view, you'll see these logs in order:

```
[ClusterView] 🚀 Stage 1: Starting cluster view fetch...
[ClusterView] ⏱️  Stage 2: Initiating API call (prep: Xms)
[ClusterView] 📦 Stage 3: API response received (fetch: Xms)
[ClusterView] 🎨 Stage 4: State updated (setState: Xms)
[ClusterView] ✅ COMPLETE - Total time breakdown: {...}
```

### What Each Stage Measures

| Stage | Icon | Description | Expected Time |
|-------|------|-------------|---------------|
| **Stage 1** | 🚀 | Component initialization | <1ms |
| **Stage 2** | ⏱️ | Request preparation (prep) | <5ms |
| **Stage 3** | 📦 | API fetch (network + backend) | 50-500ms |
| **Stage 4** | 🎨 | React state update | <10ms |
| **Render** | 🖼️ | Canvas rendering (separate) | <16ms |

---

## Example Console Output

### ✅ Good Performance (Fast Load)

```javascript
[ClusterView] ✅ COMPLETE - Total time breakdown: {
  1_prep: "1ms",
  2_api_fetch: "120ms",    // ← Backend processing
  3_state_update: "2ms",
  4_render: "1ms",
  TOTAL: "124ms",           // ← Total load time
  expanded: 0,
  visible: 25,
  budget: 25,
  budget_remaining: 0
}
```

**Interpretation**:
- Total 124ms is excellent
- API fetch (120ms) is the dominant cost
- State/render overhead is minimal

---

### ⚠️ Slow Performance (Needs Optimization)

```javascript
[ClusterView] ✅ COMPLETE - Total time breakdown: {
  1_prep: "5ms",
  2_api_fetch: "2500ms",    // ← Backend bottleneck!
  3_state_update: "15ms",
  4_render: "5ms",
  TOTAL: "2525ms",          // ← Slow!
  expanded: 5,
  visible: 150,
  budget: 150
}
```

**Interpretation**:
- API fetch taking 2.5 seconds indicates backend bottleneck
- Likely causes: uncached adjacency matrix, complex graph structure
- Solution: Check if `data/adjacency_matrix_cache.pkl` exists

---

## Canvas Rendering Performance

### Animation Frame Logs

During expand/collapse animations, you'll see:

```
[ClusterCanvas] 🎬 Animation frame: 8ms (progress: 25%)
[ClusterCanvas] 🎬 Animation frame: 7ms (progress: 50%)
[ClusterCanvas] 🎬 Animation frame: 9ms (progress: 75%)
[ClusterCanvas] 🎬 Animation frame: 8ms (progress: 100%)
```

**Expected**: Each frame should be <16ms for smooth 60fps animations

---

### Slow Render Warning

If a single frame takes >16ms, you'll see a warning:

```
[ClusterCanvas] ⚠️  Slow render: 45ms (nodes: 150, edges: 500)
```

**Causes**:
- Too many nodes/edges visible
- Browser DevTools open (slows down canvas)
- Animation overhead during transition

**Solutions**:
- Reduce `budget` parameter (fewer visible nodes)
- Close DevTools for accurate measurements
- Reduce `granularity` to show fewer clusters

---

## Backend API Performance

### Frontend Logs

The frontend logs the API call duration:

```
[API] fetchClusterView: 180.40ms {granularity: 25, ego: "username"}
```

### Backend Logs (Terminal)

Check your backend terminal for detailed server-side timing:

```python
2025-12-07 01:26:36 - src.api.cluster_routes - INFO - Cluster routes initialized: 71761 nodes -> 106 micro-clusters, 295095 edges
```

**Key Metrics**:
- **First startup**: Should show "Building adjacency matrix..." (slow)
- **Subsequent startups**: Should show "Loading cached adjacency..." (fast!)

---

## Performance Targets

| Metric | Target | Good | Needs Work |
|--------|--------|------|-----------|
| **Initial cluster load** | <200ms | <300ms | >500ms |
| **API fetch time** | <100ms | <200ms | >500ms |
| **Canvas render (60fps)** | <16ms | <20ms | >30ms |
| **Animation smoothness** | 60fps | 45fps | <30fps |
| **Expand/collapse** | <700ms | <1s | >1.5s |

---

## Debugging Slow Performance

### 1. Check Backend Cache

```bash
# Check if adjacency cache exists
ls -lh data/adjacency_matrix_cache.pkl

# If missing, backend will be slow on first load
# Wait for it to build and cache (one-time cost)
```

### 2. Check Browser Performance

```javascript
// In browser console, view API stats
window.apiPerformance.getStats()

// Output shows all API calls with timings
{
  fetchClusterView: {
    count: 5,
    avg: "156.20",
    min: "120.00",
    max: "250.00"
  }
}
```

### 3. Check Node/Edge Count

```javascript
// Large graphs impact render performance
[ClusterView] ✅ COMPLETE - Total time breakdown: {
  visible: 150,  // ← If > 100, consider reducing budget
  ...
}
```

---

## Optimization Checklist

When experiencing slow performance:

- [ ] **Backend cache exists**: `data/adjacency_matrix_cache.pkl` should be ~50MB
- [ ] **Reasonable budget**: Try budget=25 instead of 100+
- [ ] **Reasonable granularity**: Try n=25 instead of 200+
- [ ] **Browser DevTools closed**: DevTools slow down canvas rendering
- [ ] **Check backend logs**: Look for "cached adjacency loaded" message
- [ ] **Network tab**: Check API response time vs processing time

---

## Performance Monitoring Tools

### Built-in API Performance Tracker

```javascript
// Get all API call statistics
window.apiPerformance.getStats()

// Clear logs
window.apiPerformance.clear()

// Access raw call history
window.apiPerformance.calls
```

### Chrome DevTools Performance Tab

1. Open DevTools → Performance tab
2. Click Record
3. Expand/collapse a cluster
4. Stop recording
5. Look for:
   - Long tasks (>50ms)
   - Frame drops (<60fps)
   - API call waterfalls

---

## Common Performance Issues

### Issue 1: Slow Initial Load (2-30 seconds)

**Symptoms**:
```
[API] fetchClusterView: 15000ms
[ClusterView] 2_api_fetch: "15000ms"
```

**Cause**: Backend building adjacency matrix from scratch

**Solution**: Wait for cache to build (one-time), then subsequent loads are fast

---

### Issue 2: Choppy Animations (<30fps)

**Symptoms**:
```
[ClusterCanvas] ⚠️  Slow render: 35ms (nodes: 200, edges: 800)
```

**Cause**: Too many nodes/edges to render smoothly

**Solution**:
- Reduce budget: `?budget=25`
- Reduce granularity: `?n=15`
- Close browser DevTools

---

### Issue 3: Long API Calls After Cache Built

**Symptoms**:
```
[API] fetchClusterView: 2000ms
// But backend shows "cached adjacency loaded"
```

**Cause**: Complex hierarchy computation, many expanded clusters

**Solution**:
- Reduce expanded clusters
- Lower expand_depth: `?expand_depth=0.3`
- Check backend Python performance profiling

---

## Next Steps

If performance is still slow after following this guide:

1. Share console logs with the development team
2. Include backend terminal output
3. Note your cluster view URL parameters (n, budget, wl, etc.)
4. Report browser/OS information

Happy debugging! 🚀
