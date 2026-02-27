# Personalized PageRank Specification

<!-- staleness-marker: src/graph/metrics.py:compute_personalized_pagerank -->
<!-- last-verified: 2026-02-27 -->

## Overview

Personalized PageRank (PPR) measures node influence relative to a set of seed accounts. Unlike standard PageRank which models a "random surfer" across the entire graph, PPR biases the random walk to restart at seed nodes, producing scores that reflect proximity and connectivity to the user's chosen accounts.

**Source:** `src/graph/metrics.py:161-263`

## Mathematical Definition

### Standard PageRank

For a directed graph $G = (V, E)$ with adjacency matrix $A$:

```
PR(v) = (1 - α) / N + α * Σ(PR(u) / deg(u))  for all u → v
```

Where:
- $α$ = damping factor (probability of following a link vs teleporting)
- $N$ = total number of nodes
- $deg(u)$ = out-degree of node $u$

### Personalized PageRank Extension

The personalization vector $p$ replaces the uniform teleport distribution:

```
p[seed] = 1.0 / |seeds|    for each seed in seeds
p[node] = 0.0              for all other nodes
```

The iteration becomes:

```
PPR(v) = (1 - α) * p[v] + α * Σ(PPR(u) / deg(u))  for all u → v
```

This causes the random surfer to teleport back to seed nodes (uniformly weighted) rather than random nodes, concentrating score mass near the seed set.

## Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `alpha` | 0.85 | (0, 1) | Damping factor. Higher = more exploration away from seeds |
| `tol` | 1.0e-6 | (0, 1) | Convergence tolerance |
| `max_iter` | Auto | > 0 | Maximum power iterations |
| `weight` | None | string | Edge weight attribute name |
| `seeds` | required | non-empty | Seed nodes for personalization |

### Auto-Scaling `max_iter`

When `max_iter` is not explicitly set, it scales with `alpha` to ensure convergence:

| Alpha Range | max_iter | Rationale |
|-------------|----------|-----------|
| α >= 0.99 | 500 | Very slow convergence at high damping |
| α >= 0.95 | 300 | Slow convergence |
| α >= 0.90 | 200 | Moderate convergence |
| α < 0.90 | 100 | Fast convergence (default range) |

**Warning:** Values of `alpha > 0.95` trigger a log warning. High alpha increases the "exploration radius" but slows convergence significantly.

## Implementation

```python
def compute_personalized_pagerank(
    graph: nx.DiGraph,
    *,
    seeds: Iterable[str],
    alpha: float = 0.85,
    weight: Optional[str] = None,
    max_iter: Optional[int] = None,
    tol: float = 1.0e-6,
) -> Dict[str, float]
```

**NetworkX call:** `nx.pagerank(graph, alpha=alpha, personalization=personalization, weight=weight, max_iter=max_iter, tol=tol)`

### Personalization Setup

```python
personalization = {node: 0.0 for node in graph.nodes}
for seed in seeds:
    if seed in personalization:
        personalization[seed] = 1.0 / len(seeds)
```

Seeds not found in the graph are silently skipped. If no seeds are found, standard (non-personalized) PageRank is computed.

## Edge Cases

| Case | Behavior |
|------|----------|
| Empty seeds | Falls back to standard PageRank (uniform teleport) |
| Seeds not in graph | Silently skipped; uses valid seeds only |
| All seeds missing | Standard PageRank (no personalization) |
| Convergence failure | Raises `PowerIterationFailedConvergence` with diagnostic info |
| Disconnected graph | Scores may be zero for unreachable components |

### Convergence Failure Recovery

When `PowerIterationFailedConvergence` is raised, the error message includes:
1. Lower alpha (try 0.90 or 0.85)
2. Increase `max_iter`
3. Increase tolerance (try 1e-5 or 1e-4)
4. Check for disconnected components or dead ends

## Score Distribution Properties

After computation, scores are logged with distribution analysis:
- **Gini coefficient**: Measures inequality (0 = equal, 1 = concentrated)
- **Shannon entropy**: Measures dispersal (higher = more uniform)
- **Concentration**: What % of total mass is held by top 1%, 5%, 10%, 25%
- **Percentile thresholds**: Minimum score to be in top X%

Typical TPOT graph (~8k nodes): Gini ~0.85-0.95 (highly concentrated around seeds).

## Performance Characteristics

| Graph Size | Cache Miss | Cache Hit | Notes |
|------------|-----------|-----------|-------|
| <1,000 nodes | 100-300ms | <50ms | Standard NetworkX |
| 1,000-5,000 nodes | 300-800ms | <50ms | Default graph range |
| 5,000-10,000 nodes | 500-2000ms | <50ms | Consider fast backend |

**Cache layer:** Results cached in `MetricsCache` (src/api/cache.py) with prefix `"pagerank"`, TTL 1 hour.

## Fast Backend

`src/graph/metrics_fast.py:compute_pagerank_fast()` always delegates to NetworkX because NetworKit does not easily support personalized PageRank. The "fast" variant exists for API parity but uses the same algorithm.

## Normalization

For downstream use in composite scoring, PageRank values are normalized to [0, 1]:

```python
normalized = (score - min) / (max - min)
# If max == min: returns 0.5 for all nodes
```

**Source:** `src/graph/metrics.py:325-335` (`normalize_scores()`)

## Related Algorithms

- **Composite Score** (`composite_scoring.md`): Uses normalized PageRank as one of 3 inputs (default weight: 0.4)
- **Discovery PageRank** (`src/graph/scoring.py`): Normalizes raw PageRank using 95th percentile instead of min-max
- **Betweenness Centrality** (`betweenness.md`): Complementary metric measuring bridge importance
