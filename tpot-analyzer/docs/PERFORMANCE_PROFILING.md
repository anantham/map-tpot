# Performance Profiling Guide

This document explains how to use the performance profiling system to identify and fix bottlenecks in the graph analysis pipeline.

## Quick Start

### Run Performance Profiling

```bash
# Profile the complete graph rendering pipeline
python -m scripts.profile_graph_rendering

# Include shadow enrichment data
python -m scripts.profile_graph_rendering --include-shadow

# Get detailed phase-by-phase breakdown
python -m scripts.profile_graph_rendering --include-shadow --verbose
```

### Check API Performance Metrics

While the API server is running:

```bash
curl http://localhost:5001/api/metrics/performance | jq
```

This returns:
- **aggregates**: Average, min, max timing for each endpoint
- **recent_requests**: Last 50 requests with durations
- **detailed_reports**: Phase-by-phase breakdown of operations
- **profiler_summary**: Summary statistics across all operations

## Architecture

### Performance Profiler Components

1. **`src/performance_profiler.py`**: Core profiling infrastructure
   - `PerformanceProfiler`: Singleton for collecting metrics
   - `profile_operation()`: Context manager for profiling complete operations
   - `profile_phase()`: Context manager for profiling phases within operations
   - `TimingMetric`: Data class for individual timing measurements
   - `PerformanceReport`: Container for aggregated performance data

2. **Instrumented Modules**:
   - `src/graph/builder.py`: Graph construction timing
   - `src/graph/metrics.py`: PageRank, betweenness, Louvain computation
   - `src/api/server.py`: API endpoint request/response timing

### How It Works

```python
# Profile a complete operation
with profile_operation("build_graph", {"nodes": 1000}) as report:
    # Profile individual phases
    with profile_phase("load_data", "build_graph"):
        data = load_data()

    with profile_phase("create_nodes", "build_graph"):
        graph.add_nodes_from(data)
```

This produces:
- Total operation duration
- Per-phase timing with metadata
- Percentage breakdown showing which phases are slow

## Performance Bottlenecks

### Known Bottlenecks (Updated based on profiling)

Based on `/falsify` analysis, the likely bottlenecks are:

1. **Graph Metrics Computation** (35% prior probability)
   - NetworkX PageRank on 1000+ node graphs
   - Betweenness centrality (O(n³) complexity)
   - Louvain community detection

2. **Data Transformation** (25% prior probability)
   - Pandas DataFrame operations
   - Shadow data injection (when enabled)
   - Edge/node serialization for API responses

3. **Browser Rendering** (20% prior probability)
   - d3-force simulation with many nodes
   - React re-renders on metric updates

4. **Data Loading** (10% prior probability)
   - SQLite cache reads
   - Shadow store queries

### Expected Performance Profile

For a typical graph with 1000 nodes and 5000 edges:

| Operation | Expected Duration | Optimization Priority |
|-----------|-------------------|----------------------|
| Load data from cache | 50-200ms | Low |
| Build graph structure | 100-300ms | Medium |
| Compute PageRank | 500-2000ms | **High** |
| Compute betweenness | 2000-10000ms | **Critical** |
| Compute communities | 200-1000ms | Medium |
| Serialize to JSON | 100-500ms | Low |
| Browser d3-force layout | 1000-3000ms | **High** |

**Critical Path**: Betweenness → PageRank → Browser Rendering

## Optimization Strategies

### 1. NetworkX Algorithm Optimization

**Problem**: Betweenness centrality is O(n³), very slow for large graphs.

**Solutions**:
- Use approximate betweenness with sampling: `nx.betweenness_centrality(G, k=100)`
- Cache computed metrics (only recompute when graph changes)
- Consider parallel computation for independent metrics

**Implementation**:
```python
# In src/graph/metrics.py
def compute_betweenness(graph: nx.Graph, *, normalized: bool = True, sample_size: Optional[int] = None) -> Dict[str, float]:
    """Compute betweenness centrality with optional sampling."""
    if sample_size and graph.number_of_nodes() > 500:
        # Use approximate algorithm for large graphs
        return nx.betweenness_centrality(graph, normalized=normalized, k=sample_size)
    return nx.betweenness_centrality(graph, normalized=normalized)
```

### 2. Caching Strategy

**Problem**: Recomputing metrics on every API call is wasteful.

**Solutions**:
- Cache graph structure and metrics by (include_shadow, mutual_only, min_followers) key
- Use ETags to detect when cache is still valid
- Implement cache warming on startup

**Implementation**:
```python
# In src/api/server.py
from functools import lru_cache

@lru_cache(maxsize=8)
def get_cached_graph(include_shadow: bool, mutual_only: bool, min_followers: int):
    """Cache graph builds."""
    # Build and return graph
    pass
```

### 3. Lazy Computation

**Problem**: Computing all metrics upfront when user might only need PageRank.

**Solutions**:
- Load graph structure first (fast)
- Compute metrics on-demand via separate endpoints
- Stream results as they become available

### 4. Browser Rendering Optimization

**Problem**: d3-force simulation is slow with 1000+ nodes.

**Solutions**:
- Implement graph subsampling (show top N nodes by composite score)
- Use Web Workers for force simulation
- Implement level-of-detail rendering (show fewer edges at high zoom)
- Add quadtree spatial indexing for collision detection

### 5. Data Serialization

**Problem**: JSON serialization of large graphs is slow.

**Solutions**:
- Use MessagePack or protobuf for binary serialization
- Stream JSON output instead of building entire object in memory
- Compress responses with gzip

## Monitoring Performance

### During Development

Run the profiling script after making changes:

```bash
# Before optimization
python -m scripts.profile_graph_rendering --include-shadow --verbose > before.txt

# After optimization
python -m scripts.profile_graph_rendering --include-shadow --verbose > after.txt

# Compare
diff -u before.txt after.txt
```

### In Production

1. Monitor the `/api/metrics/performance` endpoint
2. Set up alerts for slow requests (>5s for graph-data, >10s for compute)
3. Track 95th percentile latencies, not just averages

### Profiling Overhead

The profiling system adds minimal overhead (~1-2% total runtime). To measure baseline without profiling:

```bash
python -m scripts.profile_graph_rendering --disable-profiling
```

## Test Coverage for Performance

When implementing optimizations:

1. **Correctness**: Verify results match original implementation
2. **Performance**: Measure speedup with profiling script
3. **Regression**: Add test to prevent future slowdowns

Example test:
```python
def test_betweenness_performance():
    """Verify betweenness completes in reasonable time."""
    graph = create_test_graph(nodes=1000, edges=5000)

    start = time.time()
    result = compute_betweenness(graph, sample_size=100)
    duration = time.time() - start

    assert duration < 2.0, f"Betweenness took {duration}s, expected <2s"
    assert len(result) == 1000
```

## Performance Targets

### MVP Targets (Current)
- Graph load: < 1s
- Metrics computation: < 5s
- Total page load: < 8s

### Production Targets (Future)
- Graph load: < 500ms
- Metrics computation: < 2s
- Total page load: < 3s

## Related Documentation

- **[/falsify Analysis](../PERFORMANCE_PROFILING.md#falsify-analysis)**: Hypothesis testing for bottlenecks
- **[ADR 002](./adr/002-graph-analysis-foundation.md)**: Graph analysis architecture
- **[Test Coverage Baseline](./test-coverage-baseline.md)**: Performance regression tests

## Debugging Slow Requests

If you encounter a slow request:

1. Check the browser Network tab for the slow request
2. Look at `X-Response-Time` header for server-side timing
3. Query `/api/metrics/performance` for detailed breakdown
4. Run the profiling script locally to reproduce
5. Use the detailed phase breakdown to identify bottleneck

Example debug session:
```bash
# 1. Fetch performance metrics
curl http://localhost:5001/api/metrics/performance | jq '.detailed_reports[-1]'

# 2. Run local profiling
python -m scripts.profile_graph_rendering --include-shadow --verbose

# 3. Focus on slowest phase
# If "compute_betweenness" is 80% of total time, optimize that first
```

## Contributing

When adding new operations:

1. Wrap with `profile_operation()` context manager
2. Break into logical phases with `profile_phase()`
3. Add metadata about input size (nodes, edges, etc.)
4. Document expected performance in this file
