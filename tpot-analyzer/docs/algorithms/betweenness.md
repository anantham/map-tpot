# Betweenness Centrality Specification

<!-- staleness-marker: src/graph/metrics.py:compute_betweenness -->
<!-- staleness-marker: src/graph/metrics_fast.py:compute_betweenness_fast -->
<!-- last-verified: 2026-02-27 -->

## Overview

Betweenness centrality measures how often a node lies on the shortest path between other nodes. High-betweenness accounts act as "bridges" connecting different parts of the TPOT network - they are important for information flow even if they don't have the highest follower counts.

**Source:** `src/graph/metrics.py:283-308`, `src/graph/metrics_fast.py`

## Mathematical Definition

For a node $v$ in graph $G = (V, E)$:

```
BC(v) = Σ (σ_st(v) / σ_st)   for all s ≠ v ≠ t
```

Where:
- $σ_{st}$ = total number of shortest paths from $s$ to $t$
- $σ_{st}(v)$ = number of those paths passing through $v$

### Normalized Form (default)

```
BC_norm(v) = BC(v) / ((n-1)(n-2)/2)    (undirected graph)
```

This scales values to [0, 1] where 1 means the node lies on every shortest path.

## Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `normalized` | True | bool | Normalize to [0, 1] |
| `sample_size` | Auto | 1 to N | Nodes to sample for approximation |

### Auto-Sampling Strategy

For graphs with >500 nodes, exact computation is O(VE) which becomes expensive. The auto-sampling logic:

```python
if sample_size is None and num_nodes > 500:
    sample_size = min(500, num_nodes)
```

| Graph Size | Algorithm | sample_size | Complexity |
|------------|-----------|-------------|------------|
| ≤500 nodes | Exact | N/A | O(VE) |
| >500 nodes | Approximate | min(500, N) | O(k*E) where k=500 |

**Note:** The approximation error bounds are not formally documented. With k=500 samples on a ~8,000 node graph, empirical testing shows scores are within ~5% of exact values for high-betweenness nodes.

## Implementation

### Standard (NetworkX)

```python
def compute_betweenness(
    graph: nx.Graph,
    *,
    normalized: bool = True,
    sample_size: Optional[int] = None
) -> Dict[str, float]
```

**NetworkX calls:**
- Exact: `nx.betweenness_centrality(graph, normalized=normalized)`
- Approximate: `nx.betweenness_centrality(graph, normalized=normalized, k=sample_size)`

### Fast Backend (NetworKit)

```python
def compute_betweenness_fast(
    graph: nx.Graph,
    *,
    normalized: bool = True,
    sample_size: Optional[int] = None
) -> Dict[str, float]
```

**Decision tree:**

```
if NetworKit available AND num_nodes > 100:
    if sample_size provided OR num_nodes > 1000:
        → NetworKit ApproxBetweenness (epsilon=0.1, delta=0.1)
    else:
        → NetworKit Betweenness (exact)
else:
    → NetworkX betweenness_centrality (with k=sample_size if applicable)
```

**NetworKit parameters:**
- `epsilon=0.1`: Relative error bound (scores within 10% of true value)
- `delta=0.1`: Confidence parameter (90% probability of accuracy)
- Speedup: 10-100x faster than NetworkX for large graphs

### Graph Conversion (for NetworKit)

NetworkX string-indexed graphs are converted to NetworKit integer-indexed graphs:

```python
nx_to_nk_id = {node: i for i, node in enumerate(graph.nodes())}
nk_graph = nk.Graph(n=len(graph.nodes()), weighted=False, directed=False)
```

Results are mapped back to original string node IDs after computation.

## Edge Cases

| Case | Behavior |
|------|----------|
| Empty graph | Returns empty dict |
| Single node | Returns `{node: 0.0}` |
| Disconnected graph | Nodes unreachable from others get 0 betweenness |
| Graph ≤500 nodes | Always exact computation |
| NetworKit unavailable | Falls back to NetworkX |

## Performance Characteristics

| Graph Size | NetworkX (exact) | NetworkX (k=500) | NetworKit (exact) | NetworKit (approx) |
|------------|-----------------|-------------------|--------------------|--------------------|
| 500 nodes | 100-200ms | N/A | 10-20ms | N/A |
| 1,000 nodes | 400-800ms | 200-400ms | 40-80ms | 20-40ms |
| 5,000 nodes | 10-30s | 100-400ms | 1-3s | 50-100ms |
| 8,000 nodes | 30-90s | 200-600ms | 3-10s | 80-200ms |

**Cache layer:** Results cached in `MetricsCache` (src/api/cache.py) with prefix `"betweenness"`, TTL 1 hour.

## Normalization

For composite scoring, betweenness values are normalized to [0, 1] using min-max:

```python
normalized = (score - min) / (max - min)
# If max == min: returns 0.5 for all nodes
```

**Source:** `src/graph/metrics.py:325-335`

## Interpretation

- **High betweenness (>0.01 normalized):** Bridge accounts connecting different communities
- **Moderate betweenness (0.001-0.01):** Important nodes within community boundaries
- **Low betweenness (<0.001):** Peripheral nodes or tightly clustered members

In the TPOT graph, high-betweenness accounts are often cross-community connectors who follow people across different interest clusters.

## Related Algorithms

- **Composite Score** (`composite_scoring.md`): Uses normalized betweenness as one of 3 inputs (default weight: 0.3)
- **PageRank** (`pagerank.md`): Complementary metric measuring influence
- **Louvain Communities**: Betweenness identifies bridges *between* the communities Louvain detects
