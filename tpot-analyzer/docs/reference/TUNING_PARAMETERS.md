# Tuning Parameters Reference

Magic numbers and tunable constants across the TPOT Analyzer codebase.
When changing a value, update this table and note the rationale.

Last updated: 2026-03-08

---

## Backend

| Constant | File | Line | Value | Description | Rationale |
|----------|------|------|-------|-------------|-----------|
| `QUEUE_ENTROPY_WEIGHT` | `src/data/golden/constants.py` | 7 | `0.7` | Weight given to label-distribution entropy when scoring the active-learning queue | Prioritizes uncertain examples; tuned empirically |
| `QUEUE_DISAGREEMENT_WEIGHT` | `src/data/golden/constants.py` | 8 | `0.3` | Weight given to annotator disagreement when scoring the active-learning queue | Complements entropy weight (must sum to 1.0 with entropy weight) |

## Frontend — Cluster Visualization

| Constant | File | Line | Value | Description | Rationale |
|----------|------|------|-------|-------------|-----------|
| `OKLCH_L` | `graph-explorer/src/ClusterCanvas.jsx` | 13 | `0.68` | Fixed OKLCH lightness for all community cluster nodes | ADR-013: uniform perceived brightness across hues |
| `OKLCH_MAX_CHROMA` | `graph-explorer/src/ClusterCanvas.jsx` | 14 | `0.26` | Maximum chroma in OKLCH color space | ADR-013: keeps colors vivid but within sRGB gamut |
| `OKLCH_GRAY_L` | `graph-explorer/src/ClusterCanvas.jsx` | 15 | `0.60` | OKLCH lightness for abstain / no-signal nodes | ADR-013: visually distinct from colored nodes |
| `jerkThreshold` (prop default) | `graph-explorer/src/ClusterCanvas.jsx` | 133 | `50` | Threshold for detecting sudden movement changes in force simulation | Needs documentation |
| `velocityThreshold` (prop default) | `graph-explorer/src/ClusterCanvas.jsx` | 134 | `30` | Threshold for detecting excessive node velocity in force simulation | Needs documentation |
| `POSITION_SCALE` | `graph-explorer/src/ClusterView.jsx` | 373 | `300` | Multiplier to scale normalized backend positions (~[-1,+1]) to world coordinates | Needs documentation |
| `n` (URL param default) | `graph-explorer/src/ClusterView.jsx` | 89 | `25` | Default number of clusters to request when `?n=` is omitted | Sensible starting resolution for the cluster explorer |

## Frontend — Discovery

| Constant | File | Line | Value | Description | Rationale |
|----------|------|------|-------|-------------|-----------|
| `DEFAULT_BATCH_SIZE` | `graph-explorer/src/Discovery.jsx` | 12 | `50` | Default number of recommendations fetched per batch | Needs documentation |
| `MIN_BATCH_SIZE` | `graph-explorer/src/Discovery.jsx` | 13 | `10` | Minimum allowed batch size | Needs documentation |
| `MAX_BATCH_SIZE` | `graph-explorer/src/Discovery.jsx` | 14 | `500` | Maximum allowed batch size | Needs documentation |

## Frontend — Caching

| Constant | File | Line | Value | Description | Rationale |
|----------|------|------|-------|-------------|-----------|
| `maxAgeMs` (constructor default) | `graph-explorer/src/cache/IndexedDBCache.js` | 13 | `300000` (5 min) | Default TTL for IndexedDB cache entries before they become stale | Balances freshness vs. API load; callers can override |
