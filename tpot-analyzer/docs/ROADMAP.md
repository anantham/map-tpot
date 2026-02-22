# Roadmap

Living backlog of follow-on work items. Update this document as new ideas,
coverage gaps, or UX improvements surface.

## Testing Coverage

- Expand Selenium worker coverage to browser lifecycle + scrolling workflows once
  reliable integration harness is available.
- [x] Automate README graph snapshot insertion via `python -m scripts.analyze_graph --update-readme`
  (implemented 2025-10-11; maintains marker block in README).
- Add Playwright smoke tests for graph-explorer front end (load graph, adjust
  weights, inspect node detail panel).
- Refactor shadow enricher orchestration tests to assert persisted outcomes
  (recording store or sqlite-backed fixtures) instead of mock call counts.
- Replace production-data dependent tests (e.g., shadow coverage + archive
  consistency) with deterministic fixture datasets.
- Add a dedicated opt-in shared-DB regression lane (`TPOT_RUN_REAL_DB_TESTS=1`)
  so `data/cache.db` dependent tests remain monitored without destabilizing
  default local/CI suites.
- [x] Add discovery endpoint regression matrix + smoke verifier
  (`tests/test_discovery_endpoint_matrix.py`, `scripts/verify_discovery_endpoint.py`)
  (implemented 2026-02-09).
- Add partial-observability censoring benchmark suite (MCAR + degree-biased
  masking) with VI/ARI/AUC-PR/Brier/ECE thresholds and confidence intervals.
- [x] Ensure expansion-strategy environments pin `python-louvain` (module
  `community`) via `requirements.txt` and ship dependency-contract verifier
  (`scripts/verify_louvain_dependency_contract.py`) (implemented 2026-02-21).

## Features & Analysis

- Phase 1.4 completion: finalize policy-driven refresh loop and document human
  confirmation UX.
- Phase 2 planning: temporal analysis of follower deltas and community evolution
  (requires historical scrape storage upgrades).
- Investigate advanced metrics (heat diffusion, GNN embeddings) once baseline
  enrichment stabilizes.
- Surface cached list snapshot freshness in CLI summaries and reuse them when
  prioritising seeds (now that persistence exists).
- Implement anchor-conditioned TPOT membership scoring that combines graph
  proximity, latent-space similarity, semantic tags/text, and missingness-aware
  confidence.
- [x] Ship Phase 1 GRF membership endpoint (`GET /api/clusters/accounts/<id>/membership`)
  using ego-scoped account-tag anchors with cacheable graph solve
  (`src/graph/membership_grf.py`, `tests/test_cluster_membership_endpoint.py`,
  implemented 2026-02-17).
- Add active-learning queueing (uncertainty sampling) so users can label
  highest-entropy accounts first and improve TPOT boundary quality over time.
- Add embedding jobs for extension-captured tweet text and feed-exposure
  recency weighting so TPOT membership scores can use content semantics with
  ranking-bias normalization.
- Add uncertainty decomposition for TPOT membership (`epistemic` vs
  `coverage-driven`) and surface it in API/UI evidence cards.
- Calibrate GRF probability outputs against held-out anchors (Platt/isotonic)
  and persist calibration metadata in membership responses.
- [x] Add membership endpoint integration into graph-explorer account panel so
  users can inspect probability/CI while navigating clusters
  (`graph-explorer/src/AccountMembershipPanel.jsx`,
  `graph-explorer/src/ClusterView.integration.test.jsx`,
  implemented 2026-02-18).
- Add MNAR stress diagnostics comparing metric degradation under MCAR vs
  degree/community-biased masking to validate MAR approximation safety.

## Infrastructure & Tooling

- Introduce caching layer for Flask metrics endpoint to reduce recomputation
  during rapid slider adjustments.
- Monitor SQLite growth and evaluate move to PostgreSQL if enrichment scale
  exceeds current performance envelope.
- Bundle verification scripts (`scripts/verify_*.py`) into a consolidated CLI
  entry point for Phase 2.
- Add housekeeping task to expire or refresh list snapshots that exceed
  `list_refresh_days` so cache stays accurate.
- [x] Add frontend/backend API contract verifier (`scripts/verify_api_contracts.py`)
  and wire it into CI workflow checks (implemented 2026-02-09).
- Instrument Selenium/enricher phases with timing metrics so slow steps are
  visible in summaries and `ScrapeRunMetrics`.
- Add GPU-aware execution path: at startup detect CUDA-capable hardware
  (e.g., via `nvidia-smi` or PyTorch), route heavy graph metrics to cuGraph /
  RAPIDS when available, and fall back to CPU when no dGPU is present.
- Standardize third-party relationship audit wiring (`twitterapi.io`): document
  canonical env var names, pagination/identifier parameters, and JSON shape
  adapters so subset-verification scripts remain stable across provider changes.
- Migrate account tagging from local SQLite (`account_tags.db`) to shared
  workspace-backed storage with actor/source provenance and conflict policy.
- Ship Chrome extension labeling integration against canonical backend tag
  endpoints with auth/workspace scoping and audit logs.
- [x] Add a firehose relay worker that tails `indra_net/feed_events.ndjson`
  and forwards to TemporalCoordination/Indra ingestion endpoints with retry,
  checkpointing, and backpressure metrics
  (`scripts/relay_firehose_to_indra.py`,
  `scripts/verify_firehose_relay.py`, implemented 2026-02-10).
- Add storage-growth and privacy-boundary verification for extension firehose
  mode (e.g., allowlist coverage %, bytes/day, tag-scope purge impact).

## Developer Experience

- [x] Document end-to-end enrichment + explorer refresh workflow in `docs/PLAYBOOK.md`
  (implemented 2026-02-09).
- [x] Add `make` targets to standardize test and verification entrypoints
  (`Makefile`, implemented 2026-02-21).
- Decompose `tpot-analyzer/graph-explorer/src/GraphExplorer.jsx` into smaller components/hooks (<300 LOC each) to keep debugging manageable.
- Decompose `tpot-analyzer/graph-explorer/src/ClusterCanvas.jsx` into smaller components/hooks (<300 LOC each) to keep debugging manageable.
- Decompose `tpot-analyzer/graph-explorer/src/ClusterView.jsx` and `tpot-analyzer/graph-explorer/src/data.js` into focused modules/hooks (<300 LOC each); current files exceed 1100 LOC and 700 LOC.
- Decompose `tpot-analyzer/src/api/cluster_routes.py` into focused route/service modules (<300 LOC each); current file is >1000 LOC and now contains both hierarchy and membership endpoints.
- Add ADR documenting testability refactor decisions (fixtures, helper extraction, verification scripts).
