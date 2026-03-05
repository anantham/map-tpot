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

---

*The sections below cover Phase 4+ features added after the initial snapshot/clustering pipeline.*

## Golden curation and active learning (Phase 4, ADR-009/010)

- **Human-in-the-loop labeling**: Tweets get deterministic train/dev/test splits (SHA256 hash mod 100) so the same tweet always lands in the same split regardless of when or where the assignment runs. This ensures Brier score comparisons across evaluation runs are meaningful.
- **Soft labels over hard classes**: Labels are probability distributions over L1–L4, not single-class. This captures genuine ambiguity (most simulacrum tweets blend levels) and lets Brier scoring measure distributional accuracy rather than accuracy on a forced choice.
- **Active learning queue**: Predictions are ranked by `0.7 × entropy + 0.3 × disagreement`. Entropy is weighted higher because self-uncertainty is a stronger signal for labeling ROI than cross-model disagreement; the 70/30 split is an empirical prior pending calibration data.
- **Mixin composition for store decomposition**: `GoldenStore` is composed from `BaseGoldenStore + PredictionMixin + EvaluationMixin` so each file stays under 200 LOC. The tradeoff is that methods are spread across three files, but single-responsibility is preserved.
- **Brier score is per-label normalized**: The implementation uses `mean(sum((pred_k − label_k)² / K))` rather than standard Brier (which divides by N only). This is deliberate — it makes scores scale-invariant across different numbers of classes. The ≤0.18 acceptance target was calibrated against this variant.
- **Interpret endpoint is loopback-only by default**: The `/api/golden/interpret` endpoint calls an external LLM (OpenRouter). It is restricted to localhost to prevent unauthorized remote spend. Override with `GOLDEN_INTERPRET_ALLOW_REMOTE=1`.

## Shadow enrichment and acquisition scoring (Phase 4, ADR-009)

- **Hybrid Selenium + X API**: Browser automation is required because Twitter's follower lists require JavaScript execution and authenticated sessions. The X API is used as a fallback for profile-only lookups where full list scraping isn't needed or is rate-limited.
- **Active learning acquisition scorer**: With hundreds of unscraped candidates, scraping time is the bottleneck. The acquisition scorer ranks by expected information gain per unit scrape time — combining entropy (35%), boundary score (25%), influence (20%), novelty (15%), and coverage boost (5%). Dividing by expected scrape time makes fast, informative accounts more attractive than slow ones even if equally uncertain.
- **MMR diversity pass**: After acquisition scoring, a greedy Maximal Marginal Relevance pass (λ=0.7) prevents near-duplicate batches — without it, the top-k would be dominated by accounts from the same community cluster.
- **Graceful pause**: Ctrl+C during enrichment triggers a pause menu rather than aborting, so operators can inspect progress and decide whether to continue, skip the current seed, or shut down cleanly.

## Community label propagation (Phase 4+, ADR-012)

- **Harmonic label propagation over Laplacian**: Community labels assigned by humans or NMF clustering are propagated to unlabeled nodes via the Gaussian Random Field (GRF) harmonic solution. This respects graph structure — nodes with strong connections to labeled anchors converge toward their labels.
- **Anchor polarity**: Account tags with polarity (+1 / −1) serve as anchors for GRF propagation. The net polarity per account (`sign(sum(polarity))`) determines the anchor value. This lets a human draw a semantic boundary ("these accounts are core TPOT, these are adjacent") that then diffuses through the graph.
- **Observation-aware weighting (IPW)**: Follow-graphs are incomplete — not every account has been fully scraped. Inverse probability weighting (`w_uv = 1 / (c_u × c_v / mean_c)`) upweights edges where both endpoints are well-observed, preventing observed hub-and-spoke structure from dominating the embedding. Assumes edges are missing at random given node completeness.

## TPOT relevance lens (Phase 4+)

- **Four-factor relevance score**: `r_i = (1 − p_none) × (1 − H_norm) × convergence_confidence × degree_gate`. Each factor captures a different failure mode: `p_none` filters noise, `H_norm` filters unfocused bridging accounts, convergence confidence filters uncertain propagation results, and degree gating prevents isolated nodes from scoring high.
- **Continuous reweighting over hard pruning**: The adjacency is reweighted by `D_r^{1/2} W D_r^{1/2}` rather than removing low-relevance nodes. This preserves downstream graph computations (PageRank, spectral embedding) while downweighting irrelevant structure.
- **Core/halo mask**: A binary mask identifies "core" accounts (r_i ≥ threshold) plus their 1-hop halo. The halo prevents isolated core islands — accounts that are relevant but surrounded by low-relevance neighbors remain connected to context.
