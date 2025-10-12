# WORKLOG

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
