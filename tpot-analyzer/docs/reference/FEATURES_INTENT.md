# Feature Intent & Motivations

This document captures the “why” behind current features and supporting behaviors across the snapshot pipeline, clustering, metrics, and the explorer UI. It complements the ADRs and specs by keeping motivations close to the implemented surfaces.

## Data pipeline and snapshots
- **Precomputed snapshots (ADR 004)**: Compute-intensive steps (graph build, embeddings, communities) are done offline to keep the UI responsive and avoid recomputation per request. A relaxed staleness window (~4 months) trades freshness for stability and avoids accidental churn of long-running jobs.
- **Single source of truth**: `SNAPSHOT_DIR` (default `tpot-analyzer/data`) is shared by refresh scripts and the API loader so generation and serving always read the same files; startup logs emit the resolved path for drift detection.
- **Logging to disk**: API logs and per-metrics timing CSVs are written under `logs/` to preserve failures and latency breakdowns outside the console.

## Clustering, hierarchy, and budgets
- **Spectral + dendrogram**: We keep a spectral embedding and dendrogram so cluster views can be cut at variable granularities without re-running heavy math; soft memberships and centroids come from those artifacts (see `docs/specs/spectral-clustering-spec.md`).
- **Hierarchy view (budgeted)**: Expand/collapse uses the dendrogram lineage while enforcing a visual budget (default 25 clusters) to keep the canvas legible. Budget is enforced server-side to prevent oversized responses and UI overload.
- **Approximate vs exact**: Approximate mode reuses precomputed micro-clusters for speed; exact mode can be enabled when fidelity is required. Connectivity metrics (edge counts, normalized connectivity) drive edge opacity on the canvas.
- **Previews reuse cache**: Cluster previews (`/api/clusters/{id}/preview`) reuse the cluster cache when possible so hover/peek actions do not rebuild the view.

## Metrics and discovery
- **Metrics pipeline**: PageRank (and other metrics) run on demand against the snapshot graph; timing and convergence stats are logged for observability. Fast paths use prebuilt adjacency if available.
- **Discovery flow**: Seeds → `/api/subgraph/discover` (server filters/limits) → client-side filters → cluster view → metrics overlay. Caching (IndexedDB) avoids refetching unchanged graph data; retries with timeouts/backoff prevent hung requests from blocking the UI.
- **Budget and granularity in UI**: Granularity slider and budget metadata are surfaced so users understand why expand/collapse might be blocked; URL sync preserves the view for sharing.

## Member listing and counts
- **Member slices**: Member lists page through cluster membership rather than loading everything to keep responses small; logging records total available vs slice returned.
- **Counts and fallbacks**: `num_followers` is read from snapshot metadata and, if missing, falls back to in-degree from the loaded adjacency. Zeros typically indicate stale snapshot or adjacency unavailable.

## Frontend UX patterns
- **Selection and multi-collapse**: Marquee selection and “collapse selected” exist to reduce clicks when freeing budget; budget and visibility totals are logged to explain why visible counts may not drop.
- **Error visibility**: Backend availability checks gate UI behavior; retries/backoff avoid immediate hard-failures, and the intent is to surface clear banners instead of silent failures.
- **Disk-friendly E2E**: Playwright prefers a system-installed browser (Brave/Chrome) via `graph-explorer/playwright.config.ts` to avoid Playwright browser downloads; set `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` for restricted-network installs.

## Observability and performance goals
- Favor cached data (snapshot, cluster cache, graph data cache) before recomputing expensive pieces (metrics, cluster builds).
- Emit structured logs with timings and request ids for long-running endpoints (`/api/metrics/compute`, `/api/subgraph/discover`, `/api/clusters`) so slow paths are diagnosable without repro.
- Keep the visual budget explicit and enforced server-side to prevent the UI from degrading when users expand aggressively.
