# Roadmap & Idea Log

A living document capturing future enhancements, testing gaps, and quality-of-life ideas. Add new items liberally—prioritization happens later.

## Testing Coverage
- [x] Add `tests/conftest.py` with shared fixtures (temp SQLite store, path setup) to eliminate `sys.path` hacks. ✅ **2025-10-05**
- [x] Adopt pytest markers (`unit`, `integration`, `selenium`) and configure default runs to exclude slow suites unless requested. ✅ **2025-10-05**
- [x] Wire in `pytest-cov` and capture baseline coverage (54% overall, documented in `docs/test-coverage-baseline.md`). ✅ **2025-10-05**
  - pytest-cov installed in requirements.txt ✓
  - Can run coverage with `pytest --cov=src --cov-report=term-missing` ✓
  - Created `docs/test-coverage-baseline.md` with detailed module breakdown ✓
- [ ] Add fixture-based tests for `CachedDataFetcher` to cover caching, expiry, and HTTP error handling without hitting Supabase.
- [ ] Expand metric tests with deterministic graphs (e.g., known PageRank outputs, community assignments) to guard against regressions.
- [ ] Create integration tests for `scripts/analyze_graph.py` (run CLI on small fixture dataset, verify JSON structure and parameter handling).
- [ ] Add seed-resolution tests ensuring usernames map to account IDs in graph nodes (integration of builder + seed parser).
- [ ] Consider optional test matrix (with/without SciPy) to ensure fallback pathways remain healthy.
- [ ] **HIGH PRIORITY**: Add tests for `x_api_client.py` (currently 28% coverage, 0 tests) - rate limiting, persistent state, HTTP error handling
- [ ] **HIGH PRIORITY**: Add direct unit tests for `shadow_store.py` (currently 39% coverage) - COALESCE upsert behavior, edge summary aggregation
- [ ] Introduce regression tests for JSON-LD fallback using saved profile fixtures (ensure counts remain accurate when headers fail).
- [x] Add policy-driven tests covering cache-skipping logic (profile-only refresh, list skipping, delta-triggered rescrapes). ✅ **2025-10-05**
  - 14 integration tests for policy refresh logic (age/delta triggers, skip logic, confirmation behavior)
  - Tests refactored to follow behavioral testing principles (test through public API, verify observable outcomes)
  - Tests use complete seeds with realistic ScrapeRunMetrics fixtures

## Metrics & Observability
- [x] Add error tracking to ScrapeRunMetrics (error_type, error_details) ✅ **2025-10-06**
- [x] Create metrics summary CLI (`python -m scripts.summarize_metrics`) to aggregate success rates, error breakdowns, and performance ✅ **2025-10-06**
- [ ] Add structured JSON event logging for real-time monitoring
- [ ] Create web dashboard for live enrichment progress (success rate, error breakdown, ETA)
- [ ] Add alerting for error rate thresholds (e.g., >20% failures)

## Features & Analysis
- [ ] Implement heat-diffusion and temporal metrics once core graph UI is stable.
- [ ] Investigate likes/retweets ingestion for deeper engagement analysis (e.g., "bangers" detection, lurker identification).
- [ ] Add filter for "active in last N days" using tweet metadata.
- [ ] Seed preset management UI (save/load multiple seed sets).
- [ ] Comparative views (side-by-side parameter configs, rank change visualizations).
- [ ] Shadow enrichment job queue with progress API so the explorer can launch/monitor scraping without manual CLI calls.
- [ ] Extend trust propagation heuristics (personalized PageRank threshold, depth controls) to govern which shadow nodes get enqueued automatically.
- [x] Refactor `HybridShadowEnricher.enrich` into composable helpers (`_should_skip_seed`, `_refresh_profile`, `_refresh_following`, `_refresh_followers`) for testability and cache-aware skipping ✅ **2025-10-05**
- [x] Implement enrichment refresh policy with percentage-based delta thresholds (default 50%) and auto-confirm for unattended runs ✅ **2025-10-05**
  - Policy-driven refresh logic: `age_days > 180 OR pct_delta > 50%` triggers refresh for ALL seeds (complete or incomplete)
  - Fixed architectural issue where policy was bypassed for complete seeds (commit 81e3137)
  - Non-blocking default (auto-confirm), opt-in to prompts via `--require-confirmation` flag
  - Config file: `config/enrichment_policy.json`
  - Added `get_last_scrape_metrics()` to ShadowStore for historical data queries
  - Skipped runs marked `skipped=True` to preserve baseline metrics (no corruption)
  - 91 unit tests passing (14 tests for policy logic, skip behavior, and confirmation flows)
- [ ] **FUTURE**: Temporal graph analysis - persist enrichment diffs (edge add/remove events with timestamps) to support:
  - Follower/following churn analysis over time
  - Reconstruction of graph state at any historical point
  - Growth pattern detection and community evolution tracking
  - Schema: `shadow_edge_history` table with `(seed_id, shadow_id, direction, change_type, effective_at)`

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
- [ ] Document enrichment policy knobs (default freshness, delta thresholds) and expose CLI flag to override policy file.

## Documentation
- [ ] Architecture diagrams for data pipeline and graph analysis flow.
- [ ] Tutorial-style notebook showing how to use CLI outputs for custom analysis.
- [ ] Inline code comments where logic is non-obvious (e.g., seed normalization).

*Last updated: 2025-10-05*
