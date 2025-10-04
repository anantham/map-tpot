# Roadmap & Idea Log

A living document capturing future enhancements, testing gaps, and quality-of-life ideas. Add new items liberally—prioritization happens later.

## Testing Coverage
- [ ] Add fixture-based tests for `CachedDataFetcher` to cover caching, expiry, and HTTP error handling without hitting Supabase.
- [ ] Expand metric tests with deterministic graphs (e.g., known PageRank outputs, community assignments) to guard against regressions.
- [ ] Create integration tests for `scripts/analyze_graph.py` (run CLI on small fixture dataset, verify JSON structure and parameter handling).
- [ ] Add seed-resolution tests ensuring usernames map to account IDs in graph nodes (integration of builder + seed parser).
- [ ] Consider optional test matrix (with/without SciPy) to ensure fallback pathways remain healthy.

## Features & Analysis
- [ ] Implement heat-diffusion and temporal metrics once core graph UI is stable.
- [ ] Investigate likes/retweets ingestion for deeper engagement analysis (e.g., “bangers” detection, lurker identification).
- [ ] Add filter for “active in last N days” using tweet metadata.
- [ ] Seed preset management UI (save/load multiple seed sets).
- [ ] Comparative views (side-by-side parameter configs, rank change visualizations).
- [ ] Shadow enrichment job queue with progress API so the explorer can launch/monitor scraping without manual CLI calls.
- [ ] Extend trust propagation heuristics (personalized PageRank threshold, depth controls) to govern which shadow nodes get enqueued automatically.

## UI & Visualization
- [ ] Wrap `src/ui/graph-explorer.jsx` into a runnable frontend (Next.js or Vite), with data loading from CLI output or live fetcher.
- [ ] Node tooltips with profile info, engagement stats, and seed markers.
- [ ] Ego network view (focus + highlight on click).
- [ ] Export controls (PNG snapshot, CSV of current rankings, shareable config link).
- [ ] Add seed selector UI (drop-down or multi-select list populated from presets + fetched data).

## Dev Experience & Infrastructure
- [ ] Provide Makefile or CLI entrypoint for common commands (`make verify`, `make analyze SEEDS=...`).
- [ ] CI pipeline to run tests and lint checks (once repo is private/public as needed).
- [ ] Document expected dataset growth and how to refresh caches when new accounts upload.
- [ ] Add local fixtures/bundles for offline experimentation (small subset of Community Archive).
- [ ] Package Selenium/X API credentials handling (config templates, secrets management) and add smoke tests for enrichment pipeline.

## Documentation
- [ ] Architecture diagrams for data pipeline and graph analysis flow.
- [ ] Tutorial-style notebook showing how to use CLI outputs for custom analysis.
- [ ] Inline code comments where logic is non-obvious (e.g., seed normalization).

*Last updated: 2025-10-04*
