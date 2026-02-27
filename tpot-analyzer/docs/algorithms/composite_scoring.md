# Composite Scoring Specification

<!-- staleness-marker: src/graph/metrics.py:compute_composite_score -->
<!-- staleness-marker: src/graph/scoring.py:compute_composite_score -->
<!-- staleness-marker: src/graph/scoring.py:score_candidate -->
<!-- last-verified: 2026-02-27 -->

## Overview

TPOT uses two composite scoring systems for different purposes:

1. **Base Composite** (`metrics.py`): 3-metric weighted combination for graph visualization
2. **Discovery Composite** (`scoring.py`): 4-metric weighted combination for account recommendations

Both normalize individual metrics to [0, 1] and compute a weighted sum.

## 1. Base Composite Score (Visualization)

**Source:** `src/graph/metrics.py:338-359`

### Formula

```
composite(v) = α * PR_norm(v) + β * BT_norm(v) + γ * EG_norm(v)
```

Where:
- `PR_norm` = min-max normalized PageRank
- `BT_norm` = min-max normalized betweenness centrality
- `EG_norm` = min-max normalized engagement score
- `(α, β, γ)` = user-adjustable weights, default `(0.4, 0.3, 0.3)`

### Default Weights

| Metric | Weight | Rationale |
|--------|--------|-----------|
| PageRank | 0.4 (40%) | Primary signal: influence relative to seeds |
| Betweenness | 0.3 (30%) | Bridge importance across communities |
| Engagement | 0.3 (30%) | Activity level relative to audience size |

### Engagement Score Formula

```python
engagement(v) = (likes + tweets) / max(followers, 1)
```

- `likes` = node attribute `num_likes` (default: 0)
- `tweets` = node attribute `num_tweets` (default: 0)
- `followers` = node attribute `num_followers` (default: 0)
- Denominator capped at 1 to avoid division by zero

**Source:** `src/graph/metrics.py:311-322`

**Limitations:** This is a heuristic proxy. It does not account for:
- Content quality or relevance
- Recency of activity
- Different engagement patterns (lurkers vs. posters)

### Normalization (Min-Max)

Each input metric is independently normalized:

```python
normalized(v) = (score(v) - min) / (max - min)
# If max == min: returns 0.5 for all nodes
```

**Source:** `src/graph/metrics.py:325-335`

## 2. Discovery Composite Score (Recommendations)

**Source:** `src/graph/scoring.py:296-316`

### Formula

```
discovery(v) = w₁ * NO(v) + w₂ * PR(v) + w₃ * CA(v) + w₄ * PD(v)
```

Where all component scores are already normalized to [0, 1]:
- `NO` = Neighbor Overlap score
- `PR` = PageRank score (95th-percentile normalized)
- `CA` = Community Affinity score
- `PD` = Path Distance score

### Default Weights

```python
DEFAULT_WEIGHTS = {
    "neighbor_overlap": 0.4,
    "pagerank": 0.3,
    "community": 0.2,
    "path_distance": 0.1
}
```

| Metric | Weight | Rationale |
|--------|--------|-----------|
| Neighbor Overlap | 0.4 (40%) | Strongest signal: shared connections with seeds |
| PageRank | 0.3 (30%) | Influence within the subgraph |
| Community Affinity | 0.2 (20%) | Same-community membership |
| Path Distance | 0.1 (10%) | Proximity (weakest signal, supplementary) |

### Component Algorithms

#### Neighbor Overlap

**Source:** `src/graph/scoring.py:26-92`

```
overlap(v) = |seeds_following ∩ candidate_followers| / |seeds_following|
```

- Computes the set of all accounts seeds follow
- Intersects with accounts that follow the candidate
- Normalizes by total accounts seeds follow
- Capped at 1.0

#### Community Affinity

**Source:** `src/graph/scoring.py:95-143`

```
affinity(v) = |seeds in same community as v| / |seeds|
```

- Looks up Louvain community assignment for candidate and each seed
- Fraction of seeds sharing the candidate's community
- Requires `community` node attribute (from Louvain detection)

#### Path Distance Score

**Source:** `src/graph/scoring.py:146-215`

```
if min_distance ≤ max_distance:
    score = 1.0 - (min_distance - 1) * (0.9 / (max_distance - 1))
else:
    score = 0.0
```

- Uses shortest path on the **undirected** graph
- Linear decay: distance 1 → score 1.0, distance max_distance → score 0.1
- Beyond max_distance (default: 3) → score 0.0
- Uses `min_distance` across all seeds

| Distance | Score (max_distance=3) |
|----------|----------------------|
| 1 hop | 1.0 |
| 2 hops | 0.55 |
| 3 hops | 0.1 |
| >3 hops | 0.0 |

#### PageRank Score (Discovery normalization)

**Source:** `src/graph/scoring.py:218-261`

```
p95 = scores[int(N * 0.95)]
normalized = min(1.0, raw_score / p95)
```

- Uses the 95th percentile value as the normalization ceiling
- Avoids outlier influence (top accounts don't compress everyone else to near-zero)
- Different from the min-max normalization used in base composite

### Weight Processing

**Source:** `src/graph/scoring.py:264-293`

User-provided weights are processed:

1. Start with `DEFAULT_WEIGHTS`
2. Override with user values (each clamped to [0, 1])
3. If all weights are zero, revert to defaults
4. Normalize to sum to 1.0 (rounded to 4 decimal places)

```python
# Example: user provides partial weights
input:  {"neighbor_overlap": 0.8, "pagerank": 0.2}
result: {"neighbor_overlap": 0.5333, "pagerank": 0.1333, "community": 0.2000, "path_distance": 0.0667}
# (Missing keys keep defaults, all normalized to sum=1.0)
```

## Candidate Scoring Pipeline

**Source:** `src/graph/scoring.py:319-371`

The full pipeline for scoring a single candidate:

```
score_candidate(graph, candidate, seeds, pagerank_scores, weights)
    │
    ├── compute_neighbor_overlap(directed_graph, candidate, seeds)
    ├── compute_community_affinity(directed_graph, candidate, seeds)
    ├── compute_path_distance_score(undirected_graph, candidate, seeds)
    ├── compute_pagerank_score(candidate, pagerank_scores)
    │
    ├── Collect normalized scores into dict
    └── compute_composite_score(scores, weights)
```

Returns:
```json
{
    "candidate": "account_id",
    "composite_score": 0.7234,
    "scores": {
        "neighbor_overlap": 0.85,
        "pagerank": 0.62,
        "community": 1.0,
        "path_distance": 0.55
    },
    "details": {
        "overlap": {"normalized": 0.85, "raw_count": 12, ...},
        "community": {"normalized": 1.0, "community_id": 4, ...},
        "distance": {"normalized": 0.55, "min_distance": 2, ...},
        "pagerank": {"normalized": 0.62, "raw": 0.00034, ...}
    }
}
```

## Configuration Constants

### Discovery Module (`src/api/discovery.py:25-32`)

| Constant | Value | Purpose |
|----------|-------|---------|
| `SUBGRAPH_MAX_DEPTH` | 2 | BFS hops from seeds for candidate extraction |
| `SUBGRAPH_MAX_NODES` | 5000 | Safety limit to prevent memory exhaustion |
| `MAX_NEIGHBORS_PER_NODE` | 100 | Cap on neighbors expanded per BFS step |
| `MAX_SEEDS` | 20 | Maximum seed accounts per request |
| `MAX_LIMIT` | 500 | Maximum recommendations returned |
| `MAX_OFFSET` | 10000 | Maximum pagination offset |

## Performance

| Operation | Typical Time | Factors |
|-----------|-------------|---------|
| Subgraph extraction | 50-200ms | Graph size, depth, neighbor cap |
| Scoring all candidates | 500-2000ms | Candidate count, path computation |
| Filtering + sorting | 10-50ms | Filter complexity, candidate count |
| **Total discovery** | 600-2500ms | Sum of above |

**Cache:** Discovery results cached in `DiscoveryCache` with 1-hour TTL.

## Related

- **PageRank** (`pagerank.md`): Input to both scoring systems
- **Betweenness** (`betweenness.md`): Input to base composite only
- **Louvain Communities** (`src/graph/metrics.py:266-280`): Generates community assignments used by Community Affinity
