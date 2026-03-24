# Roadmap

Living backlog of follow-on work items. Update this document as new ideas,
coverage gaps, or UX improvements surface.

*Last updated: 2026-03-23*

---

## What's Shipped (Sessions 7-9, 2026-03-21 to 2026-03-23)

These items were built but not tracked in the original Phase 4-8 roadmap below. They leapfrogged parts of the original plan.

### Community System
- [x] 15 named communities (k=16 NMF with likes), all with descriptions + iconography
- [x] 75 community aliases in `community_alias` table
- [x] Community short_names for labeling: `SELECT short_name FROM community`

### Label Propagation + Bands
- [x] Harmonic label propagation on 189K-node archive follow graph (`propagate_community_labels.py`)
- [x] Four-band classification: exemplar / specialist / bridge / frontier / unknown (`classify_bands.py`)
- [x] Frontier ranking by information value for enrichment prioritization (`rank_frontier.py`)
- [x] Seed eligibility with concentration-based weighting

### Labeling System
- [x] Per-tweet labeling ontology: domain, thematic, posture, bits, simulacrum, new-community signals
- [x] Labeling model spec: `docs/LABELING_MODEL_SPEC.md` — 15 community profiles, exemplar tweets
- [x] 20 accounts labeled with bits (213+ total bits across 51 tweets for @repligate alone)
- [x] Bits rollup: `rollup_bits.py` with simulacrum weighting option

### Active Learning Pipeline (2026-03-23)
- [x] Active learning spec + plan: `docs/superpowers/specs/2026-03-23-active-learning-loop-design.md`
- [x] Tweet fetcher via twitterapi.io with budget tracking + dedup guard
- [x] 3-model LLM ensemble labeler (Grok + DeepSeek + Gemini) via OpenRouter
- [x] Context assembly: graph signal, engagement context, community descriptions
- [x] Rollup modification: UNION enriched_tweets, scoped DELETE, informativeness discount
- [x] Seed insertion with concentration discount (0.5 for LLM seeds vs 1.0 for NMF)
- [x] Orchestrator with CLI, budget hard stop, holdout guard, model agreement logging
- [x] Verification script: `scripts/verify_active_learning.py`
- [x] 85 tests across 7 test files, all passing
- [x] First experiment: 5 accounts enriched + labeled ($0.25 spent), @Teknium correctly classified

### Signal Framework
- [x] Mention graph: 8.5M edges from Supabase user_mentions
- [x] Quote graph: from Supabase quote_tweets (keyset pagination + resume)
- [x] Signed replies: 17,362 pairs (R1-R2 heuristics)
- [x] Co-followed similarity: 16,701 pairs
- [x] Content topics: 25 topics via TF-IDF + NMF on 17.5M liked tweets

### Public Site
- [x] amiingroup.vercel.app — deployed, 8,429 searchable accounts
- [x] Export: four-band system, community descriptions, iconography
- [x] Community detail pages with spotlights + all-members sidebar
- [x] Card generation with community iconography
- [x] Gallery, share-to-X, card regeneration

### Holdout / Cross-Validation
- [x] 389 holdout accounts in `tpot_directory_holdout`
- [x] 122 testable (in graph, not seed) — baseline recall: 1.6% (2/122)
- [x] Holdout recall verification script: `scripts/verify_holdout_recall.py`

### What's Next
- [ ] Full active learning Round 1 (50 accounts, `--ego adityaarpitha`, $2.50)
- [ ] Round 2: deepen ambiguous accounts via advanced_search
- [ ] Label @mykola from archive (109K tweets, NMF says Essayists but graph says Quiet Creatives + Jhana)
- [x] Label @earthlypath, @YeshodharaB via API fetch (in progress session 9)
- [ ] Investigate Regen absorption (68x ratio — bridge into non-TPOT metacrisis ecosystem)
- [ ] Re-export + deploy updated public site
- [ ] TF-IDF precompute for similar archive tweet context in labeling
- [ ] Send CA team message (bookmarks, lists, feed JSONL)

### Chrome/Playwright Enrichment (future — higher quality, slower)
- [ ] **Playwright-based tweet investigation**: for each enriched account, visit top tweets in browser, screenshot images, read thread context, capture replies + quote tweets. Produces richer labeling context than API text alone.
- [ ] **MCP Chrome labeling**: Claude orchestrates Chrome to visit tweets, sees images directly, describes visual content in labeling notes. Semi-automated, highest quality.
- [ ] **Following list + Chrome combo**: API fetch following list ($0.05 for ~500 edges) + Chrome for tweet investigation (free). Best signal-per-dollar: graph edges via API, content via browser.
- [ ] Integrate with existing `src/shadow/selenium_worker.py` and `src/archive/thread_fetcher.py` patterns.

### Historical Phases (partially superseded)
*Phases 4-8 below were planned in February 2026. The actual implementation diverged significantly — sessions 7-9 built propagation, bands, public site, and active learning directly. See "What's Shipped" above for current state.*

---

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
- [x] Resolve remaining `react-hooks/exhaustive-deps` warnings in
  `graph-explorer/src/ClusterCanvas.jsx` and `graph-explorer/src/ClusterView.jsx`
  so `npm run lint` is fully warning-free and hook dependency semantics are explicit
  (implemented 2026-02-25).
- Replace ClusterView utility reimplementation tests with exported helpers or
  behavioral flows (remove reimplementation markers in
  `tpot-analyzer/graph-explorer/src/ClusterView.test.jsx`).
- Replace internal-state assertions in
  `tpot-analyzer/tests/test_parse_compact_count.py` with behavior-level tests
  that exercise the public Selenium worker parsing path.

---

## Phase 4: Golden Dataset + LLM Classification Pipeline (ADR 008, ADR 009)

The foundational layer. Goal: reliable per-tweet L1/L2/L3 scoring that the account
fingerprinting and clustering pipeline can consume. Human judgment governs quality at
every step via an active learning loop.

### Dependency order
```
Archive fetch (running)
    ↓
Golden dataset labeling (human + LLM in parallel)
    ↓
LLM eval harness (Brier score validates the taxonomy)
    ↓
Full classification pipeline (all accounts)
    ↓
→ Phase 5 (fingerprinting) unblocks
```

### Data Access
- [x] Community Archive fetcher with streaming, atomic cache, retry (`src/archive/fetcher.py`,
  implemented 2026-02-25)
- [x] Archive SQLite store — tweets, likes, fetch_log, thread_context_cache
  (`src/archive/store.py`, implemented 2026-02-25)
- [x] Thread context fetcher with local cache — pays for each thread once
  (`src/archive/thread_fetcher.py`, implemented 2026-02-25)
- [x] **Complete community archive fetch for all 334 accounts** (`scripts/fetch_archive_data.py`)
  — 394 ok, 19 no archive (accounts without uploaded archive). 5,553,228 tweets and
  17,501,243 likes in DB. Archive fetch complete as of 2026-02-26.
- [ ] Run data quality verification (`scripts/verify_archive_vs_cache.py`)

### Golden Dataset Curation
- [x] Simulacrum taxonomy theory doc (`docs/specs/simulacrum_taxonomy.md`)
- [x] Machine-readable taxonomy YAML with 6 golden examples (`data/golden/taxonomy.yaml`)
- [x] Golden dataset backend — schema, label store, train/dev/test split, Brier eval, uncertainty
  queue (`src/data/golden/`, `src/api/routes/golden.py`, `scripts/verify_mvp_a.py`,
  implemented 2026-02-25)
- [x] **Labeling dashboard UI** — tweet display with thread context, L1/L2/L3 probability sliders,
  notes field, submit → `POST /api/golden/labels` (ADR 009). Implemented as `Labeling.jsx` with
  `labelingApi.js`; integer-thousandths normalization for backend-compatible precision (2026-02-25)
- [ ] Grow golden set to 50+ labeled examples (currently 6), prioritizing near-miss
  negatives at L1/L2 and L2/L3 boundaries
- [ ] Extend taxonomy.yaml with lucidity axis (0.0–1.0) per ADR 009

### LLM Evaluation Harness
- [x] **`scripts/classify_tweets.py`** — few-shot prompt from `taxonomy.yaml`, calls OpenRouter,
  ingests via `POST /api/golden/predictions/run`, prints Brier score per axis. Client-side SHA256
  split filtering for performance (4s vs 107s JOIN). 15 tests passing (2026-02-27)
- [ ] Validate core assumption: simulacrum distributions separate TPOT from non-TPOT accounts
  in 2D space (pilot: 10 accounts × 100 tweets ≈ $0.63, takes 1 hour)
- [ ] Multi-model benchmark (kimi-k2.5, claude-sonnet-4.5, gpt-4o) on dev split
- [ ] Uncertainty queue drives arbitration: `GET /api/golden/queue` surfaces high-entropy tweets
  → human labels → golden set grows

### Full Classification Pipeline
- [ ] `scripts/classify_tweets.py` batch mode with `--budget`, `--tweets-per-account`,
  `--accounts` controls
- [ ] Classify all 334 accounts posted tweets (pilot: 500/account ≈ $105 at kimi-k2.5 rates)
- [ ] Classify liked tweets (separate run — passive aesthetic signal, same taxonomy)

---

## Phase 5: Content-Aware Account Fingerprinting (ADR 010)

Aggregates per-tweet scores into per-account vectors and recomputes clustering on richer
features. Unblocks: content-aware community boundaries, latent member discovery.

### Dependency
Requires Phase 4 classification pipeline complete for pilot accounts.

### Account Fingerprints
- [ ] `scripts/build_fingerprints.py` — aggregate per-tweet distributions per account:
  ```
  account_fingerprint = [
    posted_l1, posted_l2, posted_l3, posted_l4,        # simulacrum dist over posted tweets
    posted_lucidity_mean,                                 # avg lucidity over posted tweets
    liked_l1, liked_l2, liked_l3, liked_l4,             # same over liked tweets
    liked_lucidity_mean,
    graph_mutual_ratio, graph_degree_norm,               # existing graph features
  ]
  ```
- [ ] Store fingerprints in `account_fingerprints` table (archive_tweets.db)
- [ ] Build new node feature format compatible with existing spectral pipeline

### Clustering Recompute
- [ ] Recompute spectral micro-clustering on content-aware fingerprints
- [ ] Compare cluster quality: graph-only vs content-aware (VI, ARI on held-out labels)
- [ ] Update hierarchy builder to use content fingerprints as node features

### Validation Gate
Before proceeding to Phase 6: content-aware clusters must score higher than graph-only
clusters on held-out account labels (ADR 010). Gate: ARI improvement > 0.05.

---

## Phase 6: Community Visualization + Per-User Labeling (ADR 006, ADR 011)

The product surface: users label exemplar accounts → see overlapping communities → explore
their personal taxonomy over the shared embedding.

### What Already Exists
- [x] `AccountTagStore` — per-ego, per-account tagging with polarity + confidence
  (`src/data/account_tags.py`)
- [x] `AccountTagPanel.jsx` — tag CRUD in graph explorer
- [x] `AccountMembershipPanel.jsx` — GRF membership probability with uncertainty
- [x] Tag CRUD API routes (`src/api/routes/accounts.py`)
- [x] GRF membership scoring from anchor tags (`src/graph/membership_grf.py`)

### What's Missing
- [ ] **Community score API** — given a user-defined tag (e.g., "woo"), return probability
  distribution over all 334 accounts. Currently GRF scores binary TPOT/not-TPOT; extend
  to multi-label soft scoring.
- [ ] **Venn/overlap visualization** — accounts with high scores on multiple communities
  rendered as overlapping zones. Start with a 2D scatterplot colored by dominant community
  with opacity = confidence. Venn comes later when communities are stable.
- [ ] **Toggle between users' label sets** — same underlying embedding, different community
  boundaries per ego. UI control to switch the active ego.
- [ ] Soft membership scores in graph explorer node color (dominant community) + opacity
  (certainty) — replaces current graph-cluster coloring.

---

## Phase 7: Generalization — Latent Member Discovery (ADR 012)

Uses the fingerprinted 334 as seeds to find latent community members in the broader
follow graph.

### Dependency
Requires Phase 5 fingerprints + Phase 6 community definitions.

### Broader Graph Scoring
- [ ] For accounts in follow graph but outside 334: fetch recent tweets via
  `twitterapi.io /Get User Last Tweets` (budget-controlled, ~$0.15/1000 calls)
- [ ] Score fetched tweets with same classification pipeline
- [ ] Compute content fingerprint (subset — fewer tweets, lower confidence)
- [ ] Cosine similarity to community centroids → latent member score
- [ ] Rank output: "These 50 accounts in your follow graph score high on your 'woo' community"

### Ideological NER (Optional Extension)
- [ ] Custom entity extraction pass: egregores named, ideological lineages cited,
  authorities invoked, metaphorical vehicles used
- [ ] Store as per-tweet entity table; aggregate to per-account entity frequency vectors
- [ ] Use as additional feature alongside simulacrum distributions

---

## Phase 8: Meme Dynamics (Research Phase, ADR 013)

Track how ideas propagate between accounts and clusters over time. Requires stable
communities from Phase 6 and temporal data.

### What This Enables
- Trace when a concept/frame appears for the first time in the corpus
- Track which accounts adopt it next, in what order
- Identify "scissor statements" — tweets that bifurcate communities into opposing camps
- Map egregore genealogy: which clusters spawned which ideas

### Prerequisites
- Stable community definitions (Phase 6 complete)
- Timestamps in archive data (already present in tweets table)
- Concept-level similarity across tweets (embedding or entity-based)

### Rough Approach
- [ ] Identify candidate "seed frames" by clustering tweet embeddings within a time window
- [ ] Track adoption: who uses similar frames within 7/30 days of first use?
- [ ] Scissor detection: high-variance engagement (many QTs) + bifurcating reply sentiment
  → requires twitterapi.io reply data for targeted tweets
- [ ] Visualize as timeline overlay on community map

### Memetic Shockwave Propagation (Future)
Measure how fast information travels through TPOT sub-communities and who
sits closest to the epicenter of different event types.

- [ ] **Event detection from tweet bursts** — cluster tweet embeddings in
  short time windows (6h buckets); a sudden burst of semantically similar
  content across multiple accounts = a shockwave event
- [ ] **Per-account propagation delay** — for each detected event, measure
  time between first tweet/like and each account's first engagement;
  averaged across events → stable "epicenter proximity score" per account
- [ ] **Community-level propagation profile** — aggregate per-account delays
  by NMF community to see which sub-communities are upstream vs downstream
  for different event types
- [ ] **Translation fidelity measurement** — compare embeddings of early vs
  late tweets for the same event; embedding drift across the wavefront =
  frame shift as information crosses bubble boundaries
- [ ] **Likes as leading indicator** — likes are timestamped and closer to
  "moment of encounter" than tweets; use like-then-tweet delay as a measure
  of processing time per account

Data available: 5.5M tweets + 17.5M likes with timestamps across 334
accounts. Sufficient for intra-TPOT propagation analysis. Cannot measure
propagation out of TPOT to mainstream (no data on journalists/policymakers).

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
- Add an explicit offline/local-only snapshot mode for
  `scripts.refresh_graph_snapshot` (or a quickstart flag pattern) so first-run
  onboarding does not unexpectedly attempt Supabase refresh when local cache is
  stale.
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
- Decompose `tpot-analyzer/src/shadow/enricher.py` (2449 LOC) into orchestration, retry/backoff, state management, and API dispatch modules (<300 LOC each); current file mixes all four concerns.
- Decompose `tpot-analyzer/src/shadow/selenium_worker.py` (2173 LOC) into browser control, HTML parsing, and network handling modules (<300 LOC each); tightly coupled to enricher — decompose both together.
- Decompose `tpot-analyzer/src/data/shadow_store.py` (1252 LOC) into focused store modules by table domain (<300 LOC each); currently mixes multi-table CRUD with business logic.
- Decompose `tpot-analyzer/src/graph/hierarchy/expansion_strategy.py` (1013 LOC) into scoring, strategy selection, and memoization modules (<300 LOC each).
- Add ADR documenting testability refactor decisions (fixtures, helper extraction, verification scripts).

## Infrastructure / Observability

- **API credit telemetry**: Add a lightweight ledger for twitterapi.io credit usage.
  Store in a DB table `api_calls(endpoint, credits_used, timestamp, note)` and expose
  via `/api/usage`. Surface in a settings panel in the UI so credit burn is always
  visible before running enrichment jobs. Current costs for reference:
  - `/twitter/tweets` (batch): 15 credits per returned tweet
  - `/twitter/user/info`: 18 credits per profile
  - `/twitter/tweet/replies/v2`: 75 credits per call
  - `/twitter/tweet/advanced_search`: 75 credits per call
  - Budget as of 2026-02-25: ~1,988,340 credits ($19.88)
