# WORKLOG

## 2025-12-07T12:35:00Z — Cluster request timing surfaced to frontend
- `src/api/cluster_routes.py`: added server_timing metadata (served_from/build/cache/inflight, wait_ms, total_ms, build/serialize ms, req ids) to `/api/clusters` responses and expanded inflight/cache logs to include totals for slow-request diagnosis.
- `graph-explorer/src/ClusterView.jsx`: Stage 3/complete logs now include backend `server_timing` so dev console shows server vs client timings.
- Logging config: `API_LOG_LEVEL`/`CLUSTER_LOG_LEVEL` env vars raise file logging to INFO/DEBUG so cluster timing logs persist to `logs/api.log` behind rotation.
- `StartGraphExplorer.command`: start API with `API_LOG_LEVEL=DEBUG CLUSTER_LOG_LEVEL=DEBUG` so timing logs always hit disk during local dev.
- `graph-explorer/src/ClusterView.jsx`: added request guards (drop stale/empty payloads), attached `req_id`, and emit render readiness logs (cluster/position counts) to spot spinner causes without manual inspection.
- Rationale: make it obvious in logs whether cluster fetch delays come from backend build, inflight waits, or client retries; keep timing visible in both `api.log` and browser console.

## 2025-12-07T13:10:00Z — Collapse-upward & leaf explosion UX
- `src/graph/hierarchy.py` + `src/api/cluster_routes.py`: plumbed `collapsed_ids` through cache keys, previews, meta; added `_is_descendant` so collapsing shows parent even if it wasn’t previously expanded.
- `graph-explorer/src/ClusterView.jsx`: track `collapsed` state in URL/requests, cancel in-flight fetches on param change, and add leaf “explode” path that fetches members and renders them as satellites; stale/empty payloads now dropped; readiness log includes lastGoodReq.
- `graph-explorer/src/data.js`: propagate `collapsed` through cluster, preview, and member requests; retry/abort logging now respects external AbortSignals to avoid noisy errors.
- `graph-explorer/src/ClusterCanvas.jsx`: draw exploded member dots with hover tooltip; hover/cursor handling respects member nodes.
- Scripts: added `scripts/start_dev.sh`, `wait_for_backend.sh`, and `verify_cluster_layout.py` for repeatable startup and layout checks.

## 2025-12-07T10:15:00Z — Cluster layout continuity + budget headroom
- `graph-explorer/src/ClusterView.jsx`: added Procrustes alignment for successive layouts (lines ~1-170), decoupled base cut from max budget with headroom defaults (lines ~10-120, ~320-370), and propagated aligned positions/meta through fetch/rename flows.
- `graph-explorer/src/ClusterCanvas.jsx`: smoothed persistent node movement with position tweening and parent/child seeding (lines ~90-320, ~300-500), stabilized autofit to avoid camera jumps, and interpolated edges/labels during transitions.
- `scripts/verify_cluster_layout.py`: new verification script for budget headroom and layout alignment metrics.
- Rationale: reduce visual teleports on expand/collapse and keep initial visible count below max budget for user-driven expansion.

## 2025-12-07T11:10:00Z — Cluster inflight dedupe fix
- `src/api/cluster_routes.py`: inflight dedupe now stores serialized payloads (not HierarchicalViewData) to avoid `unsupported operand type(s) for |`, logs inflight wait time/visible counts, and serializes non-dict inflight payloads defensively so deduped responses stay consistent.
- Rationale: client retries were hitting inflight futures returning non-dict objects; dedupe now returns cached payload cleanly.

## 2025-12-07T11:25:00Z — Frontend diagnostics for cluster fetches
- `graph-explorer/src/data.js`: added per-attempt fetch logging with durations, abort detection, retry delays, total wall time, and attached timing metadata on responses for downstream logs.
- `graph-explorer/src/ClusterView.jsx`: added request IDs and richer Stage logs (cache/dedup flags, inflight wait, meta, per-attempt timings now propagated) plus context for rename/delete flows to trace delays end-to-end in the console.

## 2025-12-07T11:40:00Z — Mocked cluster e2e scaffold
- `graph-explorer/e2e/cluster_mock.spec.ts`: Playwright test that mocks cluster API responses to verify ClusterView renders and respects expanded param (visible count changes 3→4 with expanded root). Useful for fast, backend-free coverage.
- Note: `PW_NO_SERVER=1` allows running against an already-started dev server; automatic webServer can still fail in restricted sandboxes (EPERM on binding 127.0.0.1:5173).

## 2025-12-07T01:45:00Z — Feature intent & motivations doc
- `docs/FEATURES_INTENT.md`: captured motivations for snapshots, hierarchy/budgets, metrics/discovery flow, member counts, UI selection/error handling, and perf/logging goals; ties behavior to ADRs/specs and current UX constraints.
- Verification: documentation only.

## 2025-12-07T02:05:00Z — Reduce initial API fan-out and timeout aborts
- `graph-explorer/src/App.jsx`: switched from hidden mounted views to conditional rendering so Discovery/Graph/Cluster mount only when selected; removes background preload and prevents 7 concurrent API calls on page load.
- `graph-explorer/src/data.js`: set `/api/metrics/compute` to use slow timeout (30s) to match backend runtime; reduces 8s abort/retry cascades.
- Verification: not run (frontend logic only); expect fewer AbortError logs and fewer concurrent requests on load.

## 2025-12-07T03:55:00Z — Cluster view dedup + timing instrumentation
- `src/api/cluster_routes.py`: added per-request ids and timing logs (build/serialize/total) plus in-flight deduplication so identical `/api/clusters` requests reuse the same build instead of running in parallel.
- `graph-explorer/src/data.js`: deduplicate identical `fetchClusterView` calls to reuse the same promise.
- `graph-explorer/src/ClusterView.jsx`: skip refetch when params unchanged (n/wl/expandDepth/ego/expanded/budget), reducing re-loads when navigating away and back.
- Verification: `npm run test:e2e` (all 6 tests passed); cluster fetch ~48s, cache hit, no aborts.

## 2025-12-07T04:15:00Z — Docs re-org and index
- Moved root docs into `docs/ui/` and `docs/diagnostics/`; added `docs/index.md` to explain doc intent/timing.
- Files:
  - `docs/ui/cluster_animations.md`
  - `docs/diagnostics/performance_monitoring.md`
  - `docs/diagnostics/performance_optimizations.md`
  - `docs/diagnostics/slow_backend_diagnosis.md`
- Verification: documentation only.

## 2025-12-07T11:10:00Z — Theme toggle and contrast variables
- `graph-explorer/src/App.css`: introduced light/dark CSS variables and swapped hard-coded colors to use vars for panel backgrounds, text, borders, buttons, sliders, textarea, and select; body now uses theme tokens.
- `graph-explorer/src/App.jsx`: added theme toggle (persisted in localStorage, applies `data-theme` on html) and header button to switch light/dark.
- Verification: not run (UI change only).

## 2025-12-06T00:10:00Z — Cluster canvas marquee selection
- `graph-explorer/src/ClusterCanvas.jsx`: added selection-mode box drag with overlay, shared selected set highlighting, and click-to-toggle selection so multiple clusters can be marked at once.
- `graph-explorer/src/ClusterView.jsx`: added selection mode toggle, synced collapse selection to marquee picks, and passed selection state into the canvas; collapse button now works with drag-selected clusters.
- Verification: not run (UI-only changes).

## 2025-12-06T12:20:00Z — Snapshot dir config unification
- `src/config.py`: added SNAPSHOT_DIR env + resolver (defaults to `tpot-analyzer/data`).
- `src/api/snapshot_loader.py`: loader now uses shared snapshot dir, logs path, and exposes `snapshot_info` to fix metrics access.
- `src/api/server.py`: logs resolved snapshot dir on startup and wires cluster routes/loader to it.
- `scripts/refresh_graph_snapshot.py`: default output dir now uses SNAPSHOT_DIR; logs reflect resolved path.
- Verification: not run (config only).

## 2025-12-06T13:45:00Z — Playwright browser normalization
- `graph-explorer/playwright.config.ts`: force bundled `chromium` (no Chrome channel) to avoid repeated Chrome-for-Testing installs; keeps disk usage down and removes the need for system Chrome.
- Verification: not run (config only).

## 2025-12-06T14:45:00Z — Metrics timing instrumentation
- `src/api/server.py`: added request_id for metrics compute, per-phase timing (pagerank/betweenness/engagement/composite/communities), CSV timing output (`logs/metrics_timing.csv`), and structured metadata in responses.
- Logging: snapshot dir and usage already emitted; metrics timing now recorded with `fast_used` and snapshot generation time.
- Verification: pending API restart to exercise new logging.

## 2025-12-05T16:20:00Z — GraphExplorer preload fix
- `graph-explorer/src/GraphExplorer.jsx`: moved `graphSettings`/related state initializers and `availablePresets` memo above dependent effects to resolve TDZ runtime errors (“Cannot access 'graphSettings' before initialization” / “availablePresets before initialization”) seen during background preload.
- `graph-explorer/src/ClusterCanvas.jsx`: avoid calling `preventDefault` on non-cancelable wheel events to silence passive listener warnings during canvas zoom/granularity scroll.
- Verification: manual UI repro fixed; no automated tests run in this step.

## 2025-12-05T17:05:00Z — API log persistence
- `src/api/server.py`: added rotating file handler (`logs/api.log`, 5MB x5) during app creation so backend 500s are captured to disk for easier debugging.
- Verification: not run (logging config only).

## 2025-12-05T17:20:00Z — Verify script approx-mode fix
- `scripts/verify_clusters.py`: pass `micro_labels`/`micro_centroids` when present so approximate spectral artifacts validate without mask/shape errors.
- Verification: not run (script change only).

## 2025-12-05T20:10:00Z — Hierarchical cluster API scaffold
- `src/api/cluster_routes.py`: switched to hierarchical view with expand/collapse params (`expanded`, `budget`), returning parent/child lineage, connectivity metrics, and budget fields; caching now keys on expanded set.
- `src/graph/hierarchy.py`: capped base granularity by budget and skipped expansions that exceed budget; uses precomputed dendrogram tree for lineage.
- Verification: not run yet (API change pending UI wiring).

## 2025-12-05T20:20:00Z — Cluster UI expand/collapse state
- `graph-explorer/src/ClusterView.jsx`: added expanded set + budget guard (URL-synced), pane buttons for expand/collapse, and per-request budget metadata handling; fetches include expanded/budget params.
- `graph-explorer/src/ClusterCanvas.jsx`: uses connectivity/opacity from API edges.
- `graph-explorer/src/data.js`: cluster API calls now support expanded/budget; member fetch includes expanded state.
- Verification: not run (UI wiring only).

## 2025-12-04T21:14:56Z — Cluster canvas, stability, tests
- `src/graph/spectral.py`: added stability ARI metrics, tiny-graph fallback, k-safeguards; metadata now records stability; eigenvalue gap unchanged; linkage kept float64.
- `src/graph/clusters.py`: fixed weight key scoping, Louvain fusion helper reuse, label-key bucket logic stable with weights defined once.
- `src/api/cluster_routes.py`: opacity normalized per-view max weight.
- Frontend: new canvas renderer `graph-explorer/src/ClusterCanvas.jsx` (pan/zoom, edge gradients) and upgraded `ClusterView.jsx` with URL sync, Louvain slider, semantic wheel → granularity, member fetch/rename, and cache hints; added cluster API helpers in `graph-explorer/src/data.js`; navigation already wired in `App.jsx`.
- Tests: added `tests/test_spectral.py` and `tests/test_clusters.py` (pass); workflow `.github/workflows/test.yml` runs verify scripts + unit tests.
- Fixtures: medium fixture already in place; README retains cluster quickstart.

## 2025-12-04T20:27:56Z — Spectral precompute scaffolding
- Added `src/graph/spectral.py`:1-170 with spectral embedding/Laplacian helpers, eigen solve, linkage, save/load.
- Added `src/graph/clusters.py`:1-210 covering cluster cuts, soft memberships, edge aggregation, label store, view builder with weight-bucketed label keys.
- Added `scripts/build_spectral.py`:1-120 to generate spectral artifacts and Louvain sidecar from graph snapshots (optional node limiting for fixtures).
- Added `scripts/verify_clusters.py`:1-90 verification script emitting ✓/✗ for spectral artifacts and cluster build sanity.
- Added `src/api/cluster_routes.py`:1-260 blueprint for `/api/clusters` with cache, weight-bucketed fusion, PCA positions, member lookup; registered in `server.py`.
- Updated `docs/specs/spectral-clustering-spec.md`: caching, hybrid weights, data schemas, performance scope, layout decisions.
- Built 500-node fixture artifacts (`data/graph_snapshot.spectral.*`, `.louvain.json`) and ran `scripts/verify_clusters.py` (all ✓; granularity=25).
- Added `graph-explorer/src/ClusterView.jsx` and navigation button in `App.jsx` to fetch/render clustered view (granularity + Louvain weight sliders, cluster/edge summaries, positions, ego input) via new `/api/clusters`.
- Generated medium fixture (`tests/fixtures/medium_graph/graph_snapshot.*`) with 2000 nodes/61k edges; verify script ✓ at granularity 40.

## 2025-10-04T10:26:07Z — Phase 1.1 Kickoff
- Established project scaffold for TPOT Community Graph Analyzer (docs/, src/, tests/, scripts/ directories).
- Captured ADR 001 choosing API-first + SQLite cache architecture.
- Pending: implement Supabase config module and cached data fetcher (src/config.py, src/data/fetcher.py).

## 2025-10-04T00:00:00Z — Phase 1.2 Planning
- Drafted ADR 002 proposing graph construction + baseline metrics (PageRank, Louvain, betweenness).
- Identified deliverables: graph builder utilities, metrics module, CLI analysis script, unit tests.
- Awaiting stakeholder sign-off before implementation.

## 2025-10-04T12:00:00Z — Phase 1.2 Implementation (in progress)
- Added graph builder/metrics/seed modules and CLI (`scripts/analyze_graph.py`).
- Drafted React+d3 explorer stub for interactive parameter tuning (data expected from CLI output).
- Introduced tests for graph construction, metrics, and seed parsing (local run hit macOS numpy segfault; needs manual verification on adopter machine).

## 2025-10-04T17:53:16Z — Phase 1.4 Shadow Enrichment Bootstrapping
- `src/data/shadow_store.py`:1-163 — created dedicated SQLite tables for shadow accounts/edges with provenance metadata and timestamps.
- `src/shadow/enricher.py`:1-210, `src/shadow/selenium_worker.py`:1-144, `src/shadow/x_api_client.py`:1-184 — ported hybrid Selenium + X API enrichment pipeline with caching and rate-limit resilience.
- `scripts/enrich_shadow_graph.py`:1-94, `scripts/verify_shadow_graph.py`:1-64 — added CLI for enrichment runs and verification script emitting ✓/✗ status.
- `scripts/setup_cookies.py`:1-67 — interactive helper to capture login cookies into `secrets/twitter_cookies.pkl`.
- `scripts/analyze_graph.py`:1-191 — added `--include-shadow` flag, serialised provenance/shadow metadata in output, and wired builder to new store.
- `src/graph/builder.py`:1-198 — injected shadow nodes/edges into directed graph and rebuilt undirected view post-augmentation.
- `graph-explorer/src/GraphExplorer.jsx`:1-820 & `src/App.css`:1-220 — surfaced shadow toggle, legend updates, provenance tooltips, and adjusted rendering for shadow-only filtering.
- `requirements.txt`:1-11 — recorded Selenium/requests dependencies for enrichment subsystem.
- Verification: `npm run lint` (graph-explorer).

## 2025-10-04T18:04:51Z — Legacy data sanity tests
- `tests/test_shadow_store_migration.py`:1-119 — load slices from legacy `social_graph.db` to assert shadow store upserts/fetches behave idempotently and preserve provenance metadata.
- Verification pending: `pytest tests/test_shadow_store_migration.py -q` (fails locally until Python deps such as `pytest`, `pandas`, `sqlalchemy` are installed in the active environment).

## 2025-10-05T02:40:00Z — Enrichment ergonomics & pacing
- `src/shadow/selenium_worker.py`:1-190 — default to visible Chrome, add action jitter (4–9 s), optional browser override, and richer scroll logging.
- `src/shadow/enricher.py`:1-240 — skip seeds with existing shadow edges, emit edge summaries, and expose new delay/headless settings.
- `scripts/enrich_shadow_graph.py`:1-140 — CLI gains `--chrome-binary`, `--headless`, delay tuning, structured logging, and graceful interrupt handling.
- `README.md`:86-132 — document the interactive workflow and new flags.
- Verification pending: `python -m pytest ../tests/test_shadow_store_migration.py -q` (run via project venv) and a manual enrichment dry-run with `--log-level DEBUG`.

## 2025-10-05T03:15:00Z — Selector drift guard + human confirmation
- `src/shadow/selenium_worker.py`:119-210 — broadened user cell selector to `[data-testid="UserCell"]`, added resilient handle parsing for relative profile links, `_handle_from_href` helper, and new DEBUG logging for cell discovery/link inspection (first 500 chars of HTML samples).
- `src/shadow/enricher.py`:36-215 — added `confirm_first_scrape` config flag, interactive preview/confirmation for the first scraped profile, and graceful abort handling.
- `scripts/enrich_shadow_graph.py`:48-170 — surfaced `--auto-confirm-first` flag, wired confirmation config, and mapped runtime aborts to structured CLI output.
- Verification pending: manual enrichment dry-run to validate new selector + prompt (requires Twitter session cookies & Selenium setup).

- `src/shadow/selenium_worker.py`:30-260 — introduced `CapturedUser`/`UserListCapture`/`ProfileOverview` dataclasses, captured claimed totals from profile tabs, scraped optional bios/websites/avatars, and added dedicated fetch for `followers_you_follow`.
- `src/shadow/enricher.py`:26-430 — reworked enrichment to consume structured captures, merge multi-list memberships, compute coverage ratios, present richer confirmation previews (top N, seed metadata), and persist profile overview details alongside summary stats (including websites + profile images).
- `scripts/enrich_shadow_graph.py`:20-170 — added `--preview-count` and `--no-followers-you-follow` flags, plumbed preview/sample sizing, and defaulted reciprocal follower scraping on.
- `src/data/shadow_store.py`:26-210 — promoted `website` / `profile_image_url` to first-class `shadow_account` columns and ensured upserts + fetches surface them.
- `tpot-analyzer/README.md`:82-128 — documented the enrichment flow with ASCII overview, highlighted preview behaviour, and referenced new CLI flags.
- Verification pending: interactive enrichment pass to confirm coverage numbers, preview sample rendering, and merged follower lists.

## 2025-10-04T17:07:57Z — Phase 1.3 Explorer Polish
- `graph-explorer/src/GraphExplorer.jsx`:34-363 — added color palette + stable metrics refs, persistent margin tab control, mutual-edge filtering, in-group sizing (mutual counts + hop distance), and custom canvas edge rendering for solid/dotted styling.
- `graph-explorer/src/App.css`:1-220 — restyled panel handle/legend colors to match new palette and support always-visible vertical toggle.
- Verification: `npm run lint`.

## 2025-10-05T13:00:00Z — Profile backfill & logging hygiene
- `scripts/setup_cookies.py`: prompt for labeled, timestamped cookie filenames instead of overwriting defaults.
- `scripts/enrich_shadow_graph.py`: auto-select cookie sessions from `secrets/`, add `--profile-only-all`, raise default delays to 5–40s, and warn on cookie fallback usage.
- `src/shadow/selenium_worker.py`: add exponential backoff + jitter, snapshot HTML on repeated timeouts, log header-count fallbacks, and slow profile-only pacing.
- `src/shadow/enricher.py`: profile-only defaults now target seeds with edges but incomplete profiles; fallback to edge counts recorded via WARN.
- `src/data/shadow_store.py`: use structured columns (website/avatar/counts) when deciding profile completeness.
- Verification pending: rerun `python3 -m scripts.enrich_shadow_graph --profile-only --quiet --delay-min 5 --delay-max 40` to backfill remaining seeds.

## 2025-10-05T05:24:23Z — Remove edge-count fallbacks for seed profiles
- `src/shadow/enricher.py`:470-507 — stop substituting follower/following totals from `edge_summary` and log when the header omits counts so we persist `NULL` instead of underestimates.
- `tests/test_seed_profile_counts.py`:1-70 — added regression coverage ensuring header totals remain intact and missing values stay `NULL` with WARN logging.
- `data/cache.db` (manual SQL): nulled legacy edge-derived follower/following counts for `shadow:*` seed profiles; restored trusted header totals (e.g., `shadow:astridwilde1.following_count=6075`).
- Verification: `pytest ../tests/test_seed_profile_counts.py -q` (under `.venv`).

## 2025-10-05T05:29:22Z — JSON-LD schema fallback for profile totals
- `src/shadow/selenium_worker.py`:100-232, 410-520 — parse `UserProfileSchema-test` JSON-LD scripts to recover followers/following counts, location, bio, avatar, and website when the visible header fails; log recoveries via INFO.
- `tests/test_selenium_extraction.py`:120-184 — unit tests for `_parse_profile_schema_payload` ensuring correct count extraction and mismatch rejection.
- Verification: `pytest tests/test_selenium_extraction.py -q` (with virtualenv).

## 2025-10-05T05:44:43Z — Preserve verbose logs in quiet mode
- `scripts/enrich_shadow_graph.py`:210-239 — `--quiet` now keeps the root logger at DEBUG with console WARN/file DEBUG so disk captures navigation details while the terminal stays quiet.
- Impact: after enrichment runs you can audit every Selenium page transition in `logs/enrichment.log` without flooding the console; `selenium`/`urllib3` chatter remains suppressed.

## 2025-10-05T11:19:23Z — Shadow package export fix
- `src/shadow/__init__.py`:1-18 — re-exported `EnrichmentPolicy` so CLI imports resolve without direct module path coupling.
- Rationale: `scripts/enrich_shadow_graph.py` relies on package-level import; missing symbol caused `ImportError` during enrichment run.

## 2025-10-05T13:57:50Z — Supabase lazy load & seed guard
- `src/data/fetcher.py`:27-226 — deferred Supabase credential loading to HTTP usage so cached-only enrichment can run without `.env` secrets; added lazy client constructor.
- `scripts/enrich_shadow_graph.py`:192-215 — normalized archive usernames defensively to ignore `NaN`/non-string values when mapping seeds.
- Verification attempt: `python3 - <<'PY' ...` failed (missing pandas in sandbox); manual run pending once dependencies installed.

## 2025-10-05T14:05:23Z — Preserve zero coverage metrics
- `src/data/shadow_store.py`:408-452 — treated coverage fields as optional explicitly so 0% coverage persists instead of collapsing to `None`.
- Verification pending: rerun metrics read/write tests once dependencies (`pandas`, `sqlalchemy`) are available.

## 2025-10-05T15:53:11Z — SQLite retry + enrichment resilience
- `src/data/shadow_store.py`:36-470 — introduced bounded retry helper for write operations, added logging, and wrapped account/edge/discovery/metrics upserts with exponential backoff to survive transient "disk I/O" / locked errors.
- `src/shadow/enricher.py`:550-700 — catch unrecoverable persistence failures per seed, emit structured summary entries, and keep subsequent seeds running.
- `tests/test_shadow_store_retry.py`:1-56 — regression coverage ensuring retry helper tolerates a transient disk I/O error and bubbles non-retryable failures.
- Verification attempt: `pytest tests/test_shadow_store_retry.py -q` (tool missing in sandbox); run pending once `pytest` is installed in the venv.

## 2025-10-06T00:30:15Z — Policy transparency & config logging
- `src/shadow/enricher.py`:210-460 — surfaced explicit policy reasons when refreshing lists (first-run vs age/delta thresholds), passed human-readable triggers into auto-confirm logs/prompts, and log when list scrapes are skipped via CLI config flags.
- Impact: enrichment logs now explain *why* refresh decisions happen, making audit trails clearer when runs proceed without manual confirmation.
- Verification pending: re-run enrichment (`python -m scripts.enrich_shadow_graph`) to observe the new logging output; pytest unavailable in sandbox.

## 2025-10-06T00:36:54Z — Reuse policy overview fetches
- `src/shadow/enricher.py`:120-620 — `_should_skip_seed` now returns the Selenium `ProfileOverview`, letting the main enrichment loop reuse the same fetch instead of reloading the page, halving redundant Selenium calls for seeds evaluated as “complete”.
- Impact: fewer profile page loads per seed, lower chance of hitting Twitter throttle while keeping policy transparency in logs.

## 2025-10-06T00:57:39Z — Archive vs shadow smoke test
- `tests/test_shadow_archive_consistency.py`:1-78 — added checks that shadow usernames match archive records and follower/following counts stay within 5% (or ±200) for overlap accounts.
- Impact: provides an automated sanity check using the 275 confirmed accounts as ground truth for Selenium scrape quality.

## 2025-10-06T02:39:31Z — Shadow/account dedupe & archive alignment
- `src/data/shadow_store.py`:170-570 — upserts now collapse `shadow:*` duplicates into canonical IDs, reuse archive follower/following counts as a floor, and expose `sync_archive_overlaps()` for retroactive repairs.
- `src/shadow/enricher.py`:146-610 — even policy-skip paths refresh seed profile metadata so counts stay current.
- Tests updated to invoke archive sync before asserting parity.

## 2025-10-06T02:57:13Z — Profile metadata validation
- `tests/test_shadow_archive_consistency.py`:1-200 — added optional checks that Selenium bio/location/website/avatar fields stay in sync with Supabase `profile` data when cached locally (test skips with guidance if the `profile` table is absent).

## 2025-10-06T03:04:04Z — Supabase cache sync CLI
- `scripts/sync_supabase_cache.py`:1-78 — added `python -m scripts.sync_supabase_cache` to pull the latest Supabase tables (accounts/profiles/followers/etc.) into `data/cache.db` with optional `--force` refresh and summary output.

## 2025-10-05T18:20:00Z — Test refactoring: behavioral testing principles
- `tests/test_shadow_enrichment_integration.py`:124-517 — refactored 3 test classes (TestSkipLogic, TestProfileOnlyMode, TestPolicyRefreshLogic) from testing private helpers to testing public `enrich()` API with observable outcome verification.
- `AGENTS.md`:105-192 — added TEST_DESIGN_PRINCIPLES section documenting anti-patterns (implementation coupling, mock verification without side effects, fixture bugs, fragile assumptions) with examples and checklist.
- `docs/test-coverage-baseline.md`:1-115 — created baseline coverage report (54% total) documenting high-priority gaps and module-level breakdown.
- Rationale: Codex identified brittleness where tests coupled to private helpers broke during refactoring; new approach tests through public APIs, verifies database side effects, uses realistic fixtures.
- Verification: `pytest tests/test_shadow_enrichment_integration.py -v -m unit` → 14/14 passed.
- Impact: Tests now survive implementation refactoring (helper renaming, code reorganization) while providing stronger guarantees (actual data persisted, not just "code called").

## 2025-10-05T19:45:00Z — Fix policy bypass for complete seeds (architectural)
- `src/shadow/enricher.py`:126-179 — refactored `_should_skip_seed()` to fetch profile overview and consult policy (age/delta triggers) BEFORE deciding to skip complete seeds; policy now controls re-scraping of stale/changed data.
- `tests/test_shadow_enrichment_integration.py`:47-92, 315-444, 551-597 — updated skip/policy tests to use complete seeds with realistic metrics, verifying policy triggers refresh for old (200d > 180d threshold) and changed data (100% delta > 50% threshold).
- Rationale: Policy was neutered—complete seeds skipped immediately without checking freshness; seeds scraped 200 days ago or with 100% follower delta never re-scraped despite policy saying they should.
- Architecture: Now `_should_skip_seed()` → `fetch_profile_overview()` → `_should_refresh_list()` (age/delta check) → skip only if policy confirms fresh.
- Tradeoff: Fetches profile overview for every complete seed (~2-5s overhead) but enables correct cache invalidation behavior.
- Verification: `pytest tests/test_shadow_enrichment_integration.py -v -m unit` → 14/14 passed.
- Impact: Policy refresh now works as designed—complete seeds with stale (age) or significantly changed (delta) data trigger re-scraping; skip reason includes "policy confirms fresh" for transparency.

## 2025-10-11T17:28:21Z — Documentation alignment
- `README.md`:213-276, 309-317 — refreshed coverage/test counts (68%, 191 tests), updated directory tree to reflect current layout, and linked to `docs/ROADMAP.md`.
- `docs/adr/002-graph-analysis-foundation.md`:2 — marked decision as accepted (accepted 2025-10-10).
- `docs/adr/003-backend-api-integration.md`:1-68 — captured Option B Flask backend decision and consequences.
- `docs/ROADMAP.md`:1-36 — established roadmap sections (Testing Coverage, Features & Analysis, Infrastructure & Tooling, Developer Experience).
- Note: No automated tests run; documentation-only update.

## 2025-10-11T17:35:54Z — README snapshot automation
- `scripts/analyze_graph.py`:1-320 — added `--summary-only` and `--update-readme` flags, coverage aggregation helper, and README marker replacement logic.
- `README.md`:12-33, 213-234 — introduced Data Snapshot section, documented refresh workflow, and referenced new CLI options.
- `docs/ROADMAP.md`:6-24 — marked snapshot automation complete with command reference.
- Pending: run `python -m scripts.analyze_graph --include-shadow --update-readme` once dependencies (`networkx`, etc.) are installed to populate the new snapshot block.

## 2025-10-11T17:42:29Z — Backend docs relocation
- Moved `BACKEND_IMPLEMENTATION.md` to `docs/BACKEND_IMPLEMENTATION.md` and updated references in README + ADR 003.

## 2025-10-11T18:06:09Z — Profile metadata logging
- `src/shadow/selenium_worker.py`:28-312 — added `_shorten_text` helper and INFO logs that record followers/following totals, location, website, and truncated bio when profile overviews succeed.
- `src/shadow/enricher.py`:31-1260 — mirrored profile snapshot/bio logging after persistence so DB writes are auditable in console/file logs.
- `src/logging_utils.py`:54-80 — allowed new log patterns (`Profile overview fetched`, `Profile snapshot`, `Profile bio`) through the console filter so the details surface in real time.

## 2025-10-13T04:56:00Z — README snapshot automation + profile counter audit tooling
- `scripts/analyze_graph.py`:27-360 — added summary-only CLI flag, README snapshot updater with coverage metrics sourced from enrichment runs, and marker-aware insertion helpers so automation remains idempotent.
- `src/logging_utils.py`:57-80 — surfaced the new profile overview/bio log lines past the console filter to align runtime output with persisted metadata.
- `src/shadow/enricher.py`:34-1270 — compressed profile logs via `_shorten_text()` and emitted persisted snapshot/bio details after each seed to tighten observability.
- `src/shadow/selenium_worker.py`:27-1140 — hardened counter extraction (canonical handle resolution, href normalization, priority scoring) and added INFO logs when profile overviews succeed.
- `scripts/verify_profile_counters.py`:1-210 — new verification script that inspects archived HTML snapshots, reports ✓/✗ for followers/following counters, and suggests next steps when data is missing.
- `docs/BACKEND_IMPLEMENTATION.md`:1-320 — captured Option B backend deliverables and performance notes for future review.
- Verification: pending — run `scripts/verify_profile_counters.py <snapshot.html>` and Selenium enrichment smoke test once fresh snapshots/cookies are available.

## 2025-10-12T10:47:26Z — Profile counter wait
- `src/shadow/selenium_worker.py`:120-945 — added `_wait_for_counter()` helper and invoked it before parsing href counters so follower/following totals have time to render, reducing false “incomplete profile” retries.

## 2025-10-12T11:01:52Z — Profile counter extraction hardening
- `src/shadow/selenium_worker.py`:806-1105 — resolved canonical handle case mismatches, layered href lookups (exact, case-insensitive, header sweep), and richer debug logs when counters still fail to resolve.
- `scripts/verify_profile_counters.py`:1-200 — added verification utility that parses saved snapshots, reports ✓/✗ for followers/following counters, and suggests follow-up actions.
- Verification: `python3 scripts/verify_profile_counters.py logs/snapshot_cardcolm_INCOMPLETE_DATA_attempt1_1760263889.html logs/snapshot_caroline30_INCOMPLETE_DATA_attempt1_1760264012.html`
- Pending: install `pytest` in the active interpreter to run `python3 -m pytest tests/test_shadow_enrichment_integration.py -k profile_overview -q` (current environment lacks the module).

## 2025-10-13T10:00:00Z — Account ID migration cache lookup fix
- **Bug**: When an account migrated from shadow ID (`shadow:username`) to real Twitter ID (e.g., `261659859`), the enricher's freshness check (`_check_list_freshness_across_runs`) would fail to find historical scrape records because it only queried by the current account_id. This caused unnecessary re-scraping of accounts that already had fresh data.
- **Root cause**: `build_seed_accounts()` in `scripts/enrich_shadow_graph.py` resolves usernames to real IDs when available (from archive/DB). Previous runs used shadow IDs, but current runs used real IDs. The freshness check query (`WHERE seed_account_id == account_id`) only matched one or the other, never both.
- **Example**: @adityaarpitha had 8 scrape runs with `seed_account_id='shadow:adityaarpitha'` (853 following on 2025-10-08, 539 followers on 2025-10-08, both within 180-day threshold). When enrichment ran with `--center adityaarpitha` using real ID `261659859`, the freshness check found no matching records and re-scraped unnecessarily.
- **Fix**: `src/shadow/enricher.py`:369-408 — `_check_list_freshness_across_runs()` now accepts optional `username` parameter and builds `account_id_variants = [account_id, f"shadow:{username.lower()}"]`, querying `WHERE seed_account_id IN (variants)`. Call sites (lines 883-884) updated to pass `seed.username`.
- **Tests**: `tests/test_shadow_enricher_utils.py`:402-485 — added `TestAccountIDMigrationCacheLookup` integration test class verifying enricher finds shadow ID records when seed has real ID, and handles None username gracefully.
- **Verification**: `pytest tests/test_shadow_enricher_utils.py::TestAccountIDMigrationCacheLookup -v` → 2/2 passed; manual DB query confirms query now returns historical scrape runs.
- **Impact**: Eliminates redundant scrapes for migrated accounts; enricher correctly skips when historical data exists under shadow ID; `--center` mode now respects cache properly.

## 2025-10-27T11:45:00Z — List snapshot caching + member count guard
- `src/data/shadow_store.py`:150-370, 520-670 — expanded list schema (name/description/owner/claimed counts/followers), added migrations, and exposed helpers to persist/reload cached list snapshots + members.
- `src/shadow/enricher.py`:64-965, 1235-1485 — list fetch now captures header metadata, reuses cached snapshots via `fetch_list_members_with_cache`, records list metrics (including claimed counts), and warns when captured members < claimed totals.
- `src/shadow/selenium_worker.py`:360-560 — parsed list overview via DOM script, scrolled the members pane with wheel + PAGE_DOWN fallbacks, and attached overview data to `UserListCapture`.
- `scripts/enrich_shadow_graph.py`:360-425 — `--force-refresh-list` flag wired into cache-aware fetch, seed prioritisation uses cached members.
- Tests: `tests/test_shadow_store_unit.py`:260-440, `tests/test_shadow_enricher_utils.py`:404-620, `tests/test_shadow_enrichment_integration.py`:40-585, `tests/conftest.py`:90-110 — exercised schema persistence, cache reuse, list overview propagation, and updated metrics fixtures.
- Tooling: `scripts/verify_small_account_totals.py`:1-170, `scripts/verify_list_snapshots.py`:1-200 — verification scripts for small-account coverage and list snapshot alignment (currently report missing tables until a list is scraped post-migration).
- Verification: `python3 -m pytest tests/test_shadow_enricher_utils.py::TestListCaching -q` (fails: No module named pytest in the active interpreter); `python3 scripts/verify_list_snapshots.py` (✗ list snapshot tables missing — expected before first list scrape on new schema).

## 2025-10-27T09:45:00Z — Small-account profile total gating
- `src/shadow/enricher.py`:520-606 — incorporated profile overview totals into list refresh heuristics so accounts with ≤13 connections skip once captured counts meet observed totals, while still flagging small-account corruption.
- `tests/test_shadow_enricher_utils.py`:220-340 — added `TestShouldRefreshListProfileTotals` unit coverage for complete, incomplete, and corrupt small-account scenarios plus legacy threshold fallback.
- `scripts/verify_small_account_totals.py`:1-150 — new verification script that scans the cache for seeds with totals ≤13 and reports coverage shortfalls with ✓/✗ status and remediation hints.
- `docs/ROADMAP.md`:17-19 — recorded follow-up to extend history-based skip logic to use profile totals.
- Verification: `python3 -m pytest tests/test_shadow_enricher_utils.py::TestShouldRefreshListProfileTotals -q` (fails: No module named pytest in current interpreter).

## 2025-11-06T02:20:08Z — macOS launcher for graph explorer
- `StartGraphExplorer.command`:1-59 — added macOS-friendly launcher that opens the Flask API (`scripts.start_api_server`) and Vite dev server in separate Terminal windows, then launches the browser to `http://localhost:5173`, with graceful fallback instructions if `osascript` automation fails.
- `README.md`:102-112 — documented how to enable and run the new `.command` helper.
- Verification: manual run pending (`chmod +x StartGraphExplorer.command && ./StartGraphExplorer.command`).

## 2025-11-06T11:41:27Z — Shadow store read retries
- `src/data/shadow_store.py`:393-915 — wrapped read operations (`fetch_accounts`, `fetch_edges`, metrics/discovery getters, account/list lookups) in `_execute_with_retry` so transient SQLite “disk i/o error” responses back off and retry instead of surfacing 500s; preserved JSON/datetime normalization after retry.
- Rationale: `/api/metrics/compute` was returning 500 during cache warm-up because `shadow_store.fetch_edges()` hit a transient disk I/O error.
- Verification: attempted `python3 -m scripts.verify_shadow_graph.py` and in-process fetch smoke test; both terminated early in this sandbox (Signal 11). UI retest pending once backend restarted with updated code.
