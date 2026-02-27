# Discovery API Algorithm Specification

<!-- staleness-marker: src/api/discovery.py -->
<!-- staleness-marker: src/graph/scoring.py -->
<!-- last-verified: 2026-02-27 -->

## Overview

The discovery API (`POST /api/subgraph/discover`) recommends accounts similar to a user's seed set. It extracts a k-hop subgraph around the seeds, scores all candidate nodes using 4 metrics, applies filters, and returns paginated results.

**Source:** `src/api/discovery.py`, `src/graph/scoring.py`

## Pipeline

```
Request (seeds, weights, filters)
    │
    ▼
1. Validate Request ──→ errors? return 400
    │
    ▼
2. Check Cache ──→ hit? return cached result
    │
    ▼
3. Extract Subgraph (BFS, 2-hop, max 5000 nodes)
    │
    ▼
4. Score Candidates (4-metric composite per candidate)
    │
    ▼
5. Apply Filters (distance, overlap, followers, community, shadow)
    │
    ▼
6. Sort by composite_score DESC
    │
    ▼
7. Paginate (offset + limit)
    │
    ▼
8. Build Recommendations (metadata, explanation, edges)
    │
    ▼
9. Cache Result (1 hour TTL)
    │
    ▼
Response (recommendations, meta, warnings)
```

## Step 3: Subgraph Extraction

**Source:** `src/api/discovery.py:210-261`

```
Input: directed graph G, seeds S, depth=2
Output: subgraph H, candidate_nodes C

Algorithm:
  subgraph_nodes = set(valid_seeds)
  current_layer = set(valid_seeds)

  for hop in range(depth):
    next_layer = {}
    for node in current_layer:
      predecessors = list(G.predecessors(node))[:MAX_NEIGHBORS_PER_NODE]  # cap at 100
      successors = list(G.successors(node))[:MAX_NEIGHBORS_PER_NODE]     # cap at 100
      next_layer += predecessors + successors

    subgraph_nodes += next_layer

    if |subgraph_nodes| > SUBGRAPH_MAX_NODES:  # 5000
      stop early with warning

    current_layer = next_layer - subgraph_nodes

  H = G.subgraph(subgraph_nodes)
  C = subgraph_nodes - valid_seeds
```

### Extraction Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `SUBGRAPH_MAX_DEPTH` | 2 | BFS hops from seeds |
| `SUBGRAPH_MAX_NODES` | 5000 | Safety limit for memory |
| `MAX_NEIGHBORS_PER_NODE` | 100 | Prevents hub-node explosion |

**Rationale for depth=2:** In the TPOT graph (~8k nodes), 2-hop neighborhoods cover most relevant accounts. 3-hop would expand to ~50k+ nodes on hub-heavy seeds, making scoring prohibitively expensive.

**Rationale for 5000 node cap:** A 5000-node NetworkX graph uses ~50MB of memory. Scoring all candidates requires O(N*S) shortest-path computations, which becomes expensive beyond this threshold.

## Step 4: Candidate Scoring

Each candidate (non-seed node in the subgraph) is scored with 4 metrics. See `docs/algorithms/composite_scoring.md` for detailed formulas.

**Default weights:**
```
neighbor_overlap: 0.4  (shared connections with seeds)
pagerank:         0.3  (influence in personalized PageRank)
community:        0.2  (same Louvain community as seeds)
path_distance:    0.1  (graph proximity to seeds)
```

## Step 5: Filtering

**Source:** `src/api/discovery.py:264-335`

Filters applied sequentially:

1. **exclude_following:** Remove accounts the ego node already follows (single-seed mode only)
2. **max_distance:** Remove candidates beyond N hops from any seed
3. **min_overlap:** Require at least N shared connections with seeds
4. **min_followers / max_followers:** Follower count range filter
5. **include_communities / exclude_communities:** Whitelist/blacklist Louvain community IDs
6. **include_shadow:** Optionally exclude shadow-enriched accounts

**Note:** `min_overlap` is auto-capped at `len(seeds)` to prevent impossible filters.

## Community Labels

**Source:** `src/api/discovery.py:36-51`

Manually curated labels for Louvain community IDs:

| ID | Label |
|----|-------|
| 0 | General |
| 1 | Tech/Engineering |
| 2 | Philosophy |
| 3 | Rationalist |
| 4 | AI/ML |
| 5 | Builder/Indie |
| 6 | Politics |
| 7 | Art/Creative |
| 8 | Science |
| 9 | Economics |
| 10 | Education |
| 11 | Media/Journalism |
| 12 | AI Safety |

**Caveat:** These labels are hardcoded and may drift as Louvain community detection produces different partitions on graph changes. They should be verified after each graph snapshot regeneration.

## Rate Limiting

- 30 requests/minute per IP address
- In-memory counter (resets on server restart)
- Response headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

## Performance

| Phase | Typical Time | Bottleneck |
|-------|-------------|------------|
| Validation | <1ms | - |
| Cache check | <1ms | - |
| Subgraph extraction | 50-200ms | BFS traversal |
| Candidate scoring | 500-2000ms | Shortest path computation |
| Filtering + sorting | 10-50ms | - |
| Recommendation building | 10-30ms | - |
| **Total (cache miss)** | **600-2500ms** | Scoring phase |
| **Total (cache hit)** | **<5ms** | Cache lookup |

## Related

- **Composite Scoring** (`composite_scoring.md`): Detailed algorithm formulas
- **API Reference** (`docs/API.md`): Full request/response schemas
- **PageRank** (`pagerank.md`): One of the 4 scoring components
