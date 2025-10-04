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

## 2025-10-05T04:20:00Z — Preview ergonomics & coverage metrics
- `src/shadow/selenium_worker.py`:30-210 — introduced `CapturedUser`/`UserListCapture`/`ProfileOverview` dataclasses, captured claimed totals from profile tabs, scraped optional bios, and added dedicated fetch for `followers_you_follow`.
- `src/shadow/enricher.py`:26-430 — reworked enrichment to consume structured captures, merge multi-list memberships, compute coverage ratios, present richer confirmation previews (top N, seed metadata), and persist profile overview details alongside summary stats.
- `scripts/enrich_shadow_graph.py`:20-170 — added `--preview-count` and `--no-followers-you-follow` flags, plumbed preview/sample sizing, and defaulted reciprocal follower scraping on.
- `tpot-analyzer/README.md`:82-128 — documented the enrichment flow with ASCII overview, highlighted preview behaviour, and referenced new CLI flags.
- Verification pending: interactive enrichment pass to confirm coverage numbers, preview sample rendering, and merged follower lists.

## 2025-10-04T17:07:57Z — Phase 1.3 Explorer Polish
- `graph-explorer/src/GraphExplorer.jsx`:34-363 — added color palette + stable metrics refs, persistent margin tab control, mutual-edge filtering, in-group sizing (mutual counts + hop distance), and custom canvas edge rendering for solid/dotted styling.
- `graph-explorer/src/App.css`:1-220 — restyled panel handle/legend colors to match new palette and support always-visible vertical toggle.
- Verification: `npm run lint`.
