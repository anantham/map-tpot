# API Reference

<!-- staleness-marker: src/api/server.py -->
<!-- staleness-marker: src/api/discovery.py -->
<!-- staleness-marker: src/api/cache.py -->
<!-- staleness-marker: src/api/metrics_cache.py -->
<!-- staleness-marker: src/api/snapshot_loader.py -->
<!-- last-verified: 2026-02-27 -->

**Base URL:** `http://localhost:5001`
**CORS:** Enabled globally
**Content-Type:** `application/json`

All responses include:
- `X-Response-Time` header (milliseconds)
- `X-Cache-Status: HIT|MISS` header (on cacheable endpoints)

---

## Table of Contents

1. [Health & Status](#1-health--status)
2. [Graph Data](#2-graph-data)
3. [Metrics](#3-metrics)
4. [Cache Management](#4-cache-management)
5. [Account Search](#5-account-search)
6. [Seeds](#6-seeds)
7. [Discovery](#7-discovery)
8. [Analysis Jobs](#8-analysis-jobs)
9. [Signal Quality](#9-signal-quality)
10. [Error Handling](#error-handling)
11. [Cache Architecture](#cache-architecture)

---

## 1. Health & Status

### `GET /health`

Health check endpoint.

**Response:** `200 OK`
```json
{
  "status": "ok",
  "cache": {
    "size": 15,
    "hit_rate": 78.5
  }
}
```

---

## 2. Graph Data

### `GET /api/graph-data`

Load graph structure (nodes and edges). Prefers precomputed snapshot if available and parameters are compatible (include_shadow=true, mutual_only=false, min_followers=0).

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include_shadow` | boolean | true | Include shadow-enriched nodes |
| `mutual_only` | boolean | false | Only include mutual follow edges |
| `min_followers` | integer | 0 | Minimum in-degree (followers) to include node |
| `force_rebuild` | boolean | false | Skip snapshot, rebuild from SQLite |

**Cache:** `MetricsCache` prefix `"graph"`, TTL 1 hour

**Response:** `200 OK`
```json
{
  "nodes": {
    "12345": {
      "username": "alice",
      "display_name": "Alice",
      "num_followers": 1200,
      "num_following": 350,
      "num_likes": 5000,
      "num_tweets": 800,
      "bio": "Building things",
      "location": "SF",
      "website": "https://example.com",
      "profile_image_url": "https://...",
      "provenance": "archive",
      "shadow": false,
      "shadow_scrape_stats": null,
      "fetched_at": null
    }
  },
  "edges": [
    {
      "source": "12345",
      "target": "67890",
      "mutual": true,
      "provenance": "archive",
      "shadow": false,
      "metadata": null,
      "direction_label": null,
      "fetched_at": null
    }
  ],
  "directed_nodes": 7981,
  "directed_edges": 18497,
  "undirected_edges": 9248,
  "source": "snapshot"
}
```

**Source field:** `"snapshot"` if loaded from Parquet, `"live_build"` if rebuilt from SQLite.

**Errors:** `500` on graph build failure

---

## 3. Metrics

### `POST /api/metrics/base`

Compute base metrics (PageRank, betweenness, engagement) **without** composite scores. Designed for client-side reweighting.

**Cache:** `MetricsCache` prefix `"base_metrics"`, TTL 1 hour

**Request:**
```json
{
  "seeds": ["alice", "bob"],
  "alpha": 0.85,
  "resolution": 1.0,
  "include_shadow": true,
  "mutual_only": false,
  "min_followers": 0
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `seeds` | string[] | required | Usernames or account IDs |
| `alpha` | float | 0.85 | PageRank damping factor |
| `resolution` | float | 1.0 | Louvain community resolution |
| `include_shadow` | boolean | true | Include shadow nodes |
| `mutual_only` | boolean | false | Mutual edges only |
| `min_followers` | integer | 0 | Minimum follower filter |

**Response:** `200 OK`
```json
{
  "seeds": ["alice", "bob"],
  "resolved_seeds": ["12345", "67890"],
  "metrics": {
    "pagerank": {"12345": 0.00045, "67890": 0.00035},
    "betweenness": {"12345": 0.0012, "67890": 0.0008},
    "engagement": {"12345": 0.67, "67890": 0.54},
    "communities": {"12345": 0, "67890": 1}
  }
}
```

### `POST /api/metrics/compute`

Compute full metrics with composite scores and discovery recommendations.

**Cache:** Response cache (`metrics_cache.py`), TTL 5 minutes

**Request:**
```json
{
  "seeds": ["alice", "bob"],
  "weights": [0.4, 0.3, 0.3],
  "alpha": 0.85,
  "resolution": 1.0,
  "include_shadow": true,
  "mutual_only": false,
  "min_followers": 0
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `seeds` | string[] | required | Usernames or account IDs |
| `weights` | float[3] | [0.4, 0.3, 0.3] | [PageRank, Betweenness, Engagement] weights |
| `alpha` | float | 0.85 | PageRank damping factor |
| `resolution` | float | 1.0 | Louvain resolution |
| `include_shadow` | boolean | true | Include shadow nodes |
| `mutual_only` | boolean | false | Mutual edges only |
| `min_followers` | integer | 0 | Minimum follower filter |

**Response:** `200 OK`
```json
{
  "seeds": ["alice", "bob"],
  "resolved_seeds": ["12345", "67890"],
  "metrics": {
    "pagerank": {"12345": 0.00045},
    "betweenness": {"12345": 0.0012},
    "engagement": {"12345": 0.67},
    "composite": {"12345": 0.723},
    "communities": {"12345": 0},
    "discovery": {
      "config": {"weights": {}, "filters": {}, "limit": 100},
      "scores": {"99999": 0.85},
      "components": {"99999": {}},
      "ranks": {"99999": 1},
      "recommendations": [],
      "meta": {},
      "warnings": null
    }
  },
  "top": {
    "pagerank": [["12345", 0.00045]],
    "betweenness": [["12345", 0.0012]],
    "composite": [["12345", 0.723]]
  }
}
```

### `GET /api/metrics/presets`

Get predefined seed collections.

**Response:** `200 OK`
```json
{
  "adi_tpot": ["nosilverv", "tszzl", "visakanv"]
}
```

**Data Source:** `docs/seed_presets.json`, falls back to "adi_tpot" preset.

### `GET /api/metrics/performance`

Get performance metrics and profiling data.

**Response:** `200 OK`
```json
{
  "aggregates": {
    "POST /api/metrics/compute": {
      "count": 50,
      "avg_ms": 1234.5,
      "min_ms": 45.2,
      "max_ms": 2500.0,
      "total_time_s": 61.7
    }
  },
  "recent_requests": [],
  "total_requests": 200,
  "detailed_reports": [],
  "profiler_summary": {}
}
```

---

## 4. Cache Management

### `GET /api/cache/stats`

Get graph cache (MetricsCache) statistics.

**Response:** `200 OK`
```json
{
  "size": 15,
  "max_size": 100,
  "ttl_seconds": 3600,
  "hit_rate": 78.5,
  "hits": 157,
  "misses": 43,
  "evictions": 2,
  "expirations": 5,
  "total_requests": 200,
  "total_computation_time_saved_ms": 235800.5,
  "entries": [
    {
      "key": "base_metrics_12ab",
      "age_seconds": 245.3,
      "access_count": 23,
      "computation_time_ms": 1523.4
    }
  ]
}
```

### `POST /api/cache/invalidate`

Invalidate graph cache entries.

**Request:**
```json
{
  "prefix": "base_metrics"
}
```

Set `prefix` to `null` to invalidate all entries. Valid prefixes: `"graph"`, `"base_metrics"`, `"pagerank"`, `"betweenness"`, `"engagement"`.

**Response:** `200 OK`
```json
{
  "invalidated": 12,
  "prefix": "base_metrics"
}
```

### `GET /api/metrics/cache/stats`

Get response cache (metrics_cache.py) statistics.

**Response:** `200 OK`
```json
{
  "hits": 45,
  "misses": 12,
  "size": 8,
  "max_size": 100,
  "hit_rate": 0.789,
  "ttl_seconds": 300
}
```

### `POST /api/metrics/cache/clear`

Clear all response cache entries.

**Response:** `200 OK`
```json
{
  "status": "cleared",
  "message": "Metrics cache cleared successfully"
}
```

---

## 5. Account Search

### `GET /api/accounts/search`

Search accounts by username prefix (autocomplete).

**Query Parameters:**

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `q` | string | required | - | Username prefix |
| `limit` | integer | 10 | 50 | Max results |

**Response:** `200 OK`
```json
[
  {
    "username": "alice",
    "display_name": "Alice",
    "num_followers": 1200,
    "is_shadow": false,
    "bio": "Building things"
  }
]
```

**Notes:**
- Case-insensitive prefix matching
- Deduplicates by username (prefers non-shadow accounts)
- Sorted by follower count (descending)

---

## 6. Seeds

### `GET /api/seeds`

Get current seed collection state and settings.

**Response:** `200 OK`
```json
{
  "seeds": {
    "discovery_active": ["alice", "bob"]
  },
  "active_list": "discovery_active",
  "settings": {
    "alpha": 0.85,
    "resolution": 1.0,
    "auto_include_shadow": true,
    "discovery_weights": {"neighbor_overlap": 0.4, "pagerank": 0.3, "community": 0.2, "path_distance": 0.1},
    "limit": 100,
    "max_distance": 3
  }
}
```

### `POST /api/seeds`

Create/update seed collections or update graph settings.

**Request (Seeds):**
```json
{
  "name": "my_seeds",
  "seeds": ["alice", "bob", "charlie"],
  "set_active": true
}
```

**Request (Settings):**
```json
{
  "settings": {
    "alpha": 0.90,
    "discovery_weights": {"neighbor_overlap": 0.5}
  }
}
```

**Response:** `200 OK`
```json
{
  "ok": true,
  "state": {}
}
```

---

## 7. Discovery

### `POST /api/subgraph/discover`

Main discovery/recommendation engine. Finds accounts similar to your seed set using a 4-component scoring algorithm.

**Rate Limit:** 30 requests/minute per IP

**Request:**
```json
{
  "seeds": ["alice", "bob"],
  "weights": {
    "neighbor_overlap": 0.4,
    "pagerank": 0.3,
    "community": 0.2,
    "path_distance": 0.1
  },
  "filters": {
    "max_distance": 3,
    "min_overlap": 0,
    "min_followers": 100,
    "max_followers": 50000,
    "include_communities": [1, 4],
    "exclude_communities": [6],
    "include_shadow": true,
    "exclude_following": false
  },
  "limit": 100,
  "offset": 0,
  "use_cache": true,
  "debug": false
}
```

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `seeds` | string[] | required | 1-20, each ≤50 chars | Seed account handles |
| `weights` | object | DEFAULT_WEIGHTS | Each [0, 1], auto-normalized | Scoring weights |
| `filters.max_distance` | integer | 3 | 1-4 | Max graph hops |
| `filters.min_overlap` | integer | 0 | ≥0 | Min shared connections |
| `filters.min_followers` | integer | - | ≥0 | Min follower count |
| `filters.max_followers` | integer | - | ≥0 | Max follower count |
| `filters.include_communities` | int[] | - | - | Whitelist community IDs |
| `filters.exclude_communities` | int[] | - | - | Blacklist community IDs |
| `filters.include_shadow` | boolean | true | - | Include shadow-enriched accounts |
| `filters.exclude_following` | boolean | false | - | Exclude accounts ego already follows |
| `limit` | integer | 100 | 1-500 | Max recommendations |
| `offset` | integer | 0 | 0-10000 | Pagination offset |
| `use_cache` | boolean | true | - | Use cached results |
| `debug` | boolean | false | - | Include debug timing info |

**Cache:** `DiscoveryCache`, TTL 1 hour, key includes snapshot version.

**Response:** `200 OK`
```json
{
  "recommendations": [
    {
      "account_id": "99999",
      "handle": "99999",
      "username": "recommended_user",
      "display_name": "Recommended User",
      "composite_score": 0.8523,
      "scores": {
        "neighbor_overlap": 0.95,
        "pagerank": 0.72,
        "community": 1.0,
        "path_distance": 0.55
      },
      "explanation": {
        "overlapping_seeds": ["alice"],
        "overlap_count": 8,
        "community_id": 4,
        "community_name": "AI/ML",
        "min_distance": 2
      },
      "metadata": {
        "username": "recommended_user",
        "num_followers": 3500,
        "num_following": 800,
        "follower_following_ratio": 4.4,
        "is_shadow": false,
        "bio": "ML researcher",
        "location": "NYC"
      },
      "edges_to_seeds": [
        {"seed": "alice", "mutual": true}
      ]
    }
  ],
  "meta": {
    "request_id": "a1b2c3d4e5f67890",
    "timestamp": "2026-02-27T10:00:00Z",
    "seed_count": 2,
    "recommendation_count": 50,
    "total_candidates": 1250,
    "computation_time_ms": 1523,
    "cache_hit": false,
    "cache_key": null,
    "snapshot_version": "2026-02-27T08:00:00",
    "snapshot_age_hours": 2.0,
    "pagination": {
      "limit": 100,
      "offset": 0,
      "total_candidates": 1250,
      "has_more": true
    }
  },
  "warnings": ["Unknown handles ignored: unknown_user"],
  "debug": null
}
```

**Rate Limit Headers:**
- `X-RateLimit-Limit: 30`
- `X-RateLimit-Remaining: 28`
- `X-RateLimit-Reset: 1709035200`

**Errors:**
- `400` - Validation error (bad seeds, invalid filters)
- `429` - Rate limit exceeded
- `500` - Internal error

### `POST /api/ego-network`

Get ego network: user + immediate neighborhood + recommendations.

**Request:**
```json
{
  "username": "alice",
  "depth": 2,
  "limit": 50,
  "offset": 0,
  "weights": {},
  "filters": {}
}
```

| Field | Type | Default | Constraints |
|-------|------|---------|-------------|
| `username` | string | required | - |
| `depth` | integer | 2 | max 5 |
| `limit` | integer | 50 | max 200 |
| `offset` | integer | 0 | - |

**Response:** `200 OK`
```json
{
  "ego": {
    "account_id": "12345",
    "username": "alice",
    "display_name": "Alice",
    "num_followers": 1200,
    "num_following": 350,
    "bio": "Building things",
    "shadow": false,
    "is_ego": true,
    "is_recommendation": false
  },
  "network": {
    "nodes": {},
    "edges": []
  },
  "recommendations": [],
  "stats": {
    "total_nodes": 250,
    "total_edges": 800,
    "network_nodes": 200,
    "recommendation_nodes": 50,
    "depth": 2,
    "computation_time_ms": 1200
  },
  "meta": {}
}
```

**Errors:** `400` (bad request), `404` (user not found), `500` (internal error)

---

## 8. Analysis Jobs

### `GET /api/analysis/status`

Get background analysis job status.

**Response:** `200 OK`
```json
{
  "status": "idle",
  "started_at": null,
  "finished_at": null,
  "error": null,
  "log": []
}
```

Status values: `"idle"`, `"running"`, `"succeeded"`, `"failed"`

### `POST /api/analysis/run`

Start background graph analysis job. Runs `scripts/analyze_graph.py` in a background thread.

**Request:** `{}` (empty body)

**Response:** `200 OK`
```json
{
  "ok": true,
  "status": {
    "status": "running",
    "started_at": "2026-02-27T10:00:00Z",
    "finished_at": null,
    "error": null,
    "log": ["Starting analysis..."]
  }
}
```

**Errors:** `409 Conflict` if analysis is already running.

**Side effects:** Clears metrics cache on successful completion.

---

## 9. Signal Quality

### `POST /api/signals/feedback`

Submit user feedback on signal quality.

**Request:**
```json
{
  "account_id": "12345",
  "signal_name": "composite_score",
  "score": 0.85,
  "user_label": "tpot",
  "context": {}
}
```

| Field | Type | Required | Values |
|-------|------|----------|--------|
| `account_id` | string | yes | - |
| `signal_name` | string | yes | - |
| `score` | float | yes | - |
| `user_label` | string | yes | `"tpot"` or `"not_tpot"` |
| `context` | object | no | - |

**Response:** `200 OK` `{"ok": true}`

### `GET /api/signals/quality`

Get signal quality report based on feedback.

**Query Parameters:** `signal` (optional, filter by signal name)

**Response:** `200 OK`
```json
{
  "signals": {
    "composite_score": {
      "positive_feedback": 45,
      "negative_feedback": 5,
      "total_feedback": 50,
      "positive_rate": 0.9,
      "confidence": 0.85,
      "recommendation": {}
    }
  }
}
```

### `GET /api/signals/events`

Get recent signal computation events.

**Query Parameters:**

| Parameter | Type | Default | Max |
|-----------|------|---------|-----|
| `signal` | string | - | - |
| `candidate` | string | - | - |
| `phase` | string | - | - |
| `limit` | integer | 100 | 1000 |

**Response:** `200 OK`
```json
{
  "events": [
    {
      "signal_name": "composite_score",
      "candidate_id": "99999",
      "score": 0.85,
      "phase": "scoring",
      "timestamp": "2026-02-27T10:00:00Z",
      "metadata": {},
      "warnings": []
    }
  ],
  "count": 42
}
```

### `POST /api/signals/explain`

Explain why a candidate received a specific signal score.

**Request:**
```json
{
  "candidate_id": "99999",
  "seeds": ["alice", "bob"],
  "signal_name": "composite_score"
}
```

**Response:** `200 OK`
```json
{
  "candidate_id": "99999",
  "signal_name": "composite_score",
  "score": 0.85,
  "explanations": ["High neighbor overlap with seeds (8 shared connections)"],
  "metadata": {},
  "warnings": []
}
```

**Errors:** `400` (missing fields), `404` (no recent computation), `500` (internal error)

---

## Error Handling

### Error Format

The API uses multiple error formats (standardization pending):

**Discovery endpoint:**
```json
{
  "error": {
    "code": "NO_VALID_SEEDS",
    "message": "None of the provided seeds exist in graph",
    "unknown_handles": ["unknown_user"]
  }
}
```

**Other endpoints:**
```json
{
  "error": "Description of what went wrong"
}
```

### Status Codes

| Code | Meaning | Used By |
|------|---------|---------|
| 200 | Success | All endpoints |
| 400 | Bad Request | Discovery, signals, seeds |
| 404 | Not Found | Ego network, signal explain |
| 409 | Conflict | Analysis (already running) |
| 429 | Rate Limited | Discovery (30/min) |
| 500 | Internal Error | All endpoints |

### NaN/Infinity Handling

The API uses a custom `SafeJSONEncoder` that converts `NaN` and `Infinity` values to `null` in JSON responses.

---

## Cache Architecture

The API uses a three-layer caching system:

### Layer 1: Graph Building Cache (`src/api/cache.py`)

- **Purpose:** Cache expensive graph construction + base metric computation
- **Implementation:** `MetricsCache` class, LRU + TTL
- **Config:** max_size=100, TTL=3600s (1 hour)
- **Key:** SHA256 hash of `"{prefix}:{json(params)}"`, truncated to 16 chars
- **Prefixes:** `"graph"`, `"base_metrics"`, `"pagerank"`, `"betweenness"`, `"engagement"`
- **Endpoints:** `/api/graph-data`, `/api/metrics/base`
- **Stats:** Hit count, miss count, evictions, expirations, computation time saved
- **Invalidation:** `POST /api/cache/invalidate` (by prefix or all)

### Layer 2: Response Cache (`src/api/metrics_cache.py`)

- **Purpose:** Cache full HTTP JSON responses for rapid slider adjustments
- **Implementation:** `MetricsCache` class (different from Layer 1), LRU
- **Config:** max_size=100, TTL=300s (5 minutes)
- **Key:** SHA256 hash of canonical JSON (seeds sorted, separators compact), truncated to 16 chars
- **Params:** seeds, weights, alpha, resolution, include_shadow, mutual_only, min_followers
- **Endpoints:** `/api/metrics/compute` (via `@cached_response` decorator)
- **Invalidation:** `POST /api/metrics/cache/clear`

### Layer 3: Discovery Cache (`src/api/discovery.py`)

- **Purpose:** Cache discovery/recommendation results
- **Implementation:** `DiscoveryCache` class, LRU + TTL
- **Config:** max_size=100, TTL=3600s (1 hour)
- **Key:** MD5 hash of canonical JSON (includes snapshot_version from manifest)
- **Endpoints:** `/api/subgraph/discover`, `/api/ego-network`
- **Invalidation:** TTL-based only (no manual endpoint)

### Layer 4: Snapshot Cache (`src/api/snapshot_loader.py`)

- **Purpose:** Precomputed graph loaded from Parquet files
- **Implementation:** `SnapshotLoader` class, in-memory singleton
- **Staleness detection:** Age-based (24h) + row-count-based (100 new accounts or 10% follower increase)
- **Fallback:** Live SQLite rebuild if stale
- **Files:** `data/graph_snapshot.{nodes,edges}.parquet`, `data/graph_snapshot.meta.json`

### Why Two MetricsCache Classes?

The codebase has two classes both named `MetricsCache` serving different purposes:

| | Graph Cache (`cache.py`) | Response Cache (`metrics_cache.py`) |
|-|--------------------------|-------------------------------------|
| **Caches** | Intermediate computation results | Final HTTP response JSON |
| **TTL** | 1 hour (expensive to recompute) | 5 minutes (fast to recompute from cached intermediates) |
| **Key includes** | Prefix + graph params | Seeds + weights + all params |
| **Use case** | Same graph, different metrics | Same request, rapid re-fire |
| **Stats** | Detailed (computation time, per-entry) | Simple (hits, misses, size) |

The separation allows weight-slider changes to be served from the response cache (5 min) while the underlying graph stays cached for 1 hour. When only weights change, the base metrics don't need recomputation.
