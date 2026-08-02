# Roadmap

Living backlog of follow-on work items. Update this document as new ideas,
coverage gaps, or UX improvements surface.

*Last updated: 2026-08-02*

---

## What's Shipped (Sessions 7-9, 2026-03-21 to 2026-03-23)

These items were built but not tracked in the original Phase 4-8 roadmap below. They leapfrogged parts of the original plan.

### Community System
- [x] 15 named communities (k=16 NMF with likes), all with descriptions + iconography
- [x] 75 community aliases in `community_alias` table
- [x] Community short_names for labeling: `SELECT short_name FROM community`

### Label Propagation + Bands
- [x] Harmonic label propagation on 189K-node archive follow graph (`propagate_community_labels.py`)
- [x] Preserve the historical classic-mode four-band classifier as an
  explicitly uncalibrated display heuristic (`classify_bands.py`).
- [x] Quarantine independent-Lift bands and fail closed in classification,
  public export, frontier ranking, automatic active-learning selection, and
  frontier-ranked following/band-resolution acquisition after EXP-024
  falsified their entropy, precedence, and artifact-coherence contracts
  (2026-07-30). Topic searches now hand off an explicit inspectable handles
  file instead of assigning an artificial rank.
- [ ] Define and validate independent specialist/bridge semantics on frozen
  development judgments and an untouched holdout; do not regenerate
  `account_band` unless they beat Lift-plus-seed-neighbor baselines.
- [ ] Replace the historical frontier information-value formula before it can
  steer acquisition; the active independent artifact has zero uncertainty and
  synthetic `none` Lift is not `p_none`.
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

The implementation remains useful as a baseline, but its scientific
acquisition policy, automatic LLM-seed promotion, and stale estimated cost
model are partially superseded by ADR 022. Do not run the historical “next
round” checklist as an approved spend plan.

### Signal Framework
- [x] Mention graph: 8.5M edges from Supabase user_mentions
- [x] Quote graph: from Supabase quote_tweets (keyset pagination + resume)
- [x] Signed replies: 17,362 pairs (R1-R2 heuristics)
- [x] Co-followed similarity: 16,701 pairs
- [x] Content topics: 25 topics via TF-IDF + NMF on 17.5M liked tweets

### Public Site
- [x] maptpot.vercel.app — deployed, 8,429 searchable accounts
- [x] Historical export: four-band metadata, community descriptions,
  iconography. Independent band export is now blocked; the already hosted
  labels remain quarantined legacy metadata, not current findings.
- [ ] Publish a replacement export only after every band row is bound to an
  exact propagation digest, mode, taxonomy, method version, and evaluation
  receipt.
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

- Freeze generalized dossier-verifier work after EXP-033. Do not add another
  verifier module or speculative tamper class before a concrete consumer or
  observed failure requires it. Run the registered $0 ontology-boundary test
  and $0 ranking bake-off first.
- Mark `tests/test_connection.py` as `requires_supabase` or replace its live
  network calls with an explicit integration fixture. The nominal CI selector
  (`not requires_supabase`) still collected all three tests; under restricted
  network they were the only failures while 1,648 local tests passed and two
  were skipped on 2026-07-31.
- Split the inherited 855-line `tests/test_pipeline_e2e.py` scenario chain
  into phase-scoped fixtures/tests before expanding it again. Slice 4 changed
  one public export assertion only; broad decomposition was intentionally
  deferred so the safety fix did not become a test-harness refactor.
- Replace `public-site/src/App.test.jsx`'s copied card-opacity/message helper
  formulas with rendered public-component behavior tests; the copied formulas
  can pass while production semantics change.
- [x] Implement the Slice 1 account-level integrity substrate in the
  [personal-ontology plan](plans/2026-07-26-personal-ontology-active-discovery-implementation.md):
  versioned ontology/task identity, frozen eligible universe and global roles,
  nominal quota probabilities, SQL-level purpose isolation, append-only
  judgments, separate prediction semantics, curator auth, and a complete
  generation-level one-use terminal release manifest (synthetic-only
  substrate implemented 2026-07-26; adversarial hardening and final local
  verification performed 2026-07-28).
- **Next implementation slice / high-priority research gate:** scope working anchors, membership cache keys,
  and membership responses by `ego + ontology/task/community target` (or an
  equivalent immutable target ID). `AccountTagStore.list_anchor_polarities(ego)`
  currently aggregates polarity across every tag key and the membership endpoint
  has no target parameter, collapsing different subculture judgments into one
  binary GRF. Synthetic binary endpoint tests remain useful, but real overlapping
  multi-subculture inference is blocked until a cross-target-isolation test proves
  that changing one target cannot affect another target's anchors or cached result.
- Authenticate the terminal-release actor from a principal rather than accepting
  `accessed_by` as a caller assertion under a shared curator token. The current
  envelope detects post-write tampering but does not establish who created it.
- [x] Add A1 idempotent terminal replay for lost-response recovery. The first
  release verifies before commit; an identical retry replays the exact payload
  and original access metadata from one row; conflicts return HTTP 409 without
  rows; corruption fails closed; and concurrent calls converge (delivery tests
  12/12, broader Community Gold/Slice 1 102/102, human verifier 6/6;
  implemented 2026-07-28). This does not authenticate caller-asserted
  `accessed_by`; principal-derived identity remains the separate gate above.
- Bind evidence-coverage numerators and denominators to the same source snapshot,
  generation, and as-of time; otherwise return unknown/incompatible.
- Create the first real evaluation frame only after reviewing stable account
  identity receipts, source/degree/time strata, quotas, explicit
  negative/abstain budget, minimum 20/20 labelable class support, and an
  independently auditable pre-allocation seed/randomization receipt. Slice 1
  creates no real ontology, roles, labels, or design-based/calibration claim.
- Bind that receipt to the role-registry ID, ordered eligible-universe hash,
  normalized roles, strata, integer quotas, randomization seed/algorithm,
  allocator code identity, timestamp, and an externally auditable pre-outcome
  commitment.
- Add an immutable generation-extension/supersession protocol before an account
  can join a later global-role registry; caller-selected registry IDs must
  never reassign an existing account.
- Bind frozen frames directly to ontology/task definition hashes so portable
  replay does not depend on mutable lookup context.
- Add an atomic prediction-vector finalization record before treating stored
  `simplex` scalars as a complete sum-to-one composition.
- Do not confuse complete terminal-head coverage with adequate class support;
  gate real evaluation separately on labelable positive/negative support and
  report abstention.
- Add time-matched, wrong-time, and placebo-context ablations so news/trend
  features cannot leak later knowledge into historical interpretations.
- Calibrate predicted versus realized action value under mask/reveal before any
  adaptive paid batch. Refit/cross-fit the full policy inside offline
  uncertainty estimation; use the exact 20% randomized live arm for cost,
  yield, and bias auditing rather than unsupported whole-policy counterfactuals.

- [x] Add frozen-control verifiers for propagation solver contracts, soft-target
  agreement, hard-label confidence calibration, taxonomy/edge-loss assumptions,
  and structural
  discoverability bias. Standardize exit codes as 0=measurement complete,
  1=input/method failure, and 2=strict scientific falsification; expose one
  combined Make target (implemented 2026-07-26).
- Add end-to-end propagation censoring tests that rerun the solver under MCAR,
  capture-center, degree-biased, and community-biased edge masking. The shipped
  2026-07-26 edge-loss check holds memberships fixed and only recomputes
  degree/relevance/core/halo.
- Add a high-precision full-class reference replay for the legacy Laplacian-CG
  artifact. Gate on residual, membership delta, top-label flips, selection
  Jaccard, and holdout-recall change rather than the solver's boolean alone.
- [x] Replace the clean-clone CI dependency on ignored
  `data/graph_snapshot.spectral.npz` with the committed medium fixture at
  granularities 25 and 40; make the cluster verifier use a sparse synthetic
  adjacency plus temporary label DB and fail with explicit diagnostics
  (implemented 2026-07-25).
- Add a Node dependency-security upgrade lane. The 2026-07-25 lockfile install
  reported 23 graph-explorer vulnerabilities (2 critical) and 4 high-severity
  public-site vulnerabilities; remediate through reviewed dependency upgrades,
  not an unbounded `npm audit fix --force`. The graph-explorer count was
  reproduced by a clean `npm ci` on 2026-08-02 (2 low, 8 moderate, 11 high, 2
  critical); first separate direct from transitive and production-reachable
  findings.
- Add a CI assertion that local developer toolchain pins (`.python-version`,
  `.nvmrc`) stay aligned with workflow Python/Node versions.
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
- [ ] Restore the graph-explorer repository-wide lint gate. A 2026-07-28 full
  run found `15` errors and `2` warnings across pre-existing empty catches,
  Fast Refresh export boundaries, unused imports/locals, and hook dependencies
  in `ClusterTour`, `ClusterView`, `Labeling`, `TweetCard`, and several tests.
  This supersedes the earlier “fully warning-free” completion note; keep the
  cleanup separate from the personal-ontology integrity slice.
- Replace ClusterView utility reimplementation tests with exported helpers or
  behavioral flows (remove reimplementation markers in
  `tpot-analyzer/graph-explorer/src/ClusterView.test.jsx`).
- Replace internal-state assertions in
  `tpot-analyzer/tests/test_parse_compact_count.py` with behavior-level tests
  that exercise the public Selenium worker parsing path.
- Expand the Phase 1 community-correctness audit from the 36-item pilot to
  full 15-community coverage once the first human-review import cycle lands.
- Add a richer local-context path for Phase 1 hard negatives (API fetch or
  cached external post samples) so famous-adjacent reviews are not bio-only.
- Split the append-only `WORKLOG.md`, `ROADMAP.md`, and `EXPERIMENT_LOG.md`
  into indexed yearly or phase files. All three are already far beyond the
  300-line agent-context threshold; preserve their history through indexed
  archives rather than rewriting it.

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
  — 394 ok, 19 no archive (accounts without uploaded archive). The systematic
  fetch produced 5,553,228 tweets and 17,501,243 likes as of 2026-02-26; later
  targeted additions brought the frozen 2026-07-25 local baseline to 5,553,430
  tweets without constituting a full refresh.
- [ ] Run data quality verification (`scripts/verify_archive_vs_cache.py`)
- [x] Add versioned, bounded, no-clobber acquisition and evidence-grade
  verification for the mutable Community Archive enriched-tweet Parquet export
  (`scripts/refresh_community_archive_snapshot.py`, ADR 019, implemented
  2026-07-26). The frozen baseline remains unchanged.
- [ ] Extend snapshot-aware refresh to per-account raw archives. The current
  one-shot fetch log suppresses already-successful accounts before `--force`
  can act, while `INSERT OR IGNORE` preserves a historical union rather than
  upstream deletions/updates. Record stable account identity, upstream
  validators/hash, fetch cutoff, row deltas, and presence/tombstone policy.
- [ ] Inventory raw archive freshness with bounded HEAD requests before any
  multi-gigabyte transfer; do not infer topology freshness from the tweet-only
  Parquet export.
- [ ] Investigate and define downstream handling for the current bulk export's
  108 source-`created_at`/Snowflake disagreements larger than one second,
  including five impossible pre-Twitter timestamps. Use Snowflake-derived
  cutoffs for eligible tweet IDs and preserve both values for auditability.
- [ ] Unify runtime data configuration around an approved `TPOT_DATA_DIR` (or
  equivalent manifest) so archive DB, cache DB, snapshot, and propagation
  input/output paths cannot silently point at different vintages.
- [ ] Add a versioned artifact manifest binding source Git SHA, database hashes,
  row/date cutoffs, graph snapshot generation, propagation generation, seeds,
  and model parameters; warn first, then reject incompatible topology and
  semantic-propagation combinations. The graph/adjacency/propagation/community
  schema/calibration compatibility slice is shipped under ADR 020; source
  database cutoffs, effective propagation parameters, seed provenance, and
  producer Git identity remain.
- [ ] Add a no-clobber, versioned propagation producer with explicit input and
  output directories. The current `propagate_community_labels --save` path
  overwrites flat active/train artifacts and must not be used to regenerate the
  certified control. Persist graph generation, mode/score semantics, solver
  tolerances, effective iterations, convergence, random seeds, code hashes, and
  Git state.
- [ ] Publish calibration and TPOT outputs as immutable generation directories
  with validated manifests and one atomically replaced current-generation
  pointer. API readers must resolve the pointer once, load into local state,
  validate the full generation, and swap state only after success. Retain the
  flat frozen bundle as a warned, read-only fallback.
- [ ] Make the compatibility verifier generation-aware (`--calibration-path`
  and `--output-prefix` or a manifest path). The shipped command deliberately
  verifies the frozen flat control; newly written unpublished candidates need
  an equivalent full-chain verifier before they can be promoted.
- [ ] Unify adjacency construction semantics. The pinned full cache is
  `directed_edge_rows`, while the API rebuild path adds mutual reverse edges;
  deleting/rebuilding the cache currently changes its scientific meaning.
  Store construction in the manifest and make producers explicit.
- [x] Repair `build_tpot_spectral.py` so propagation arrays are selected and
  aligned by node ID before elementwise scoring. The active 298,347-node
  propagation overlaps the full 95,057-node spectral graph at only 358 IDs;
  the 95,057-node training propagation is exactly order-compatible and
  reproduces the frozen 8,984-node TPOT selection. Bind the chosen propagation,
  node-order digest, topology digest, community schema, and calibrated threshold
  in one compatibility record, including persisted size/SHA-256 identities for
  all 15 frozen scientific files
  (`scripts/verify_artifact_compatibility.py`, ADR 020, implemented
  2026-07-26).
- [ ] Rerun the compatible propagation in a new versioned generation with
  convergence diagnostics before interpreting soft membership. The frozen
  control has 0/15 converged classes at the 800-iteration cap and an older
  14-community taxonomy with zero UUID overlap against the active
  16-community independent-Lift schema.

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

The product surface: users define tags extensionally by adding, excluding, and
removing exemplar accounts while reading evidence, then explore overlapping
communities over the shared embedding. Free-form evidence notes are optional;
the curation surface must not ask for an abstract boundary definition.

### What Already Exists
- [x] `AccountTagStore` — per-ego, per-account current tags plus timestamped,
  source-marked set/remove events (`src/data/account_tags.py` and focused helpers)
- [x] `AccountTagPanel.jsx` — tag CRUD in graph explorer
- [x] `AccountMembershipPanel.jsx` — uncalibrated GRF affinity, heuristic graph
  uncertainty, and separate evidence coverage; retained only as an all-tag
  legacy control, not a target-specific position
- [x] Curator-private tag CRUD/API history routes
  (`src/api/routes/account_tags.py`), including curator-authenticated derived
  tag-summary and legacy GRF-affinity reads
- [x] GRF membership scoring from anchor tags (`src/graph/membership_grf.py`),
  currently unscoped across tag keys

### What's Missing
- [x] **Extensional curation surface (2026-08-01)** — browse an account beside its posts and
  provenance, apply/remove several independent tags, show the current human
  tag state and append-only action history, and clearly label the extension as
  mutable working data rather than gold. Queue order remains manual and model
  position explicitly unavailable until target-scoped predictions exist. The
  curator identity is session-local and need not already be a graph node.
  Failed tag reads remain unknown, disable mutation, and provide Retry rather
  than appearing as an empty extension.
- [x] **Working-tag identity gate (2026-08-01)** — Research Notes permits a
  durable tag write only after the dossier resolves a stable archive account
  ID. A failed dossier retains an X investigation link and retry, but never
  creates a `handle:*` tag that can disappear after reload. Any future
  handle-only write path requires durable, reviewed alias reconciliation first.
- [ ] **Queue-wide classification overview** — batch-load known tag state for
  every queued/followed account so a fresh session can distinguish classified,
  unclassified, and unresolved rows without visiting each one. Until then,
  unvisited rows must say `tags not loaded`, never imply `review` or no tags.
- [ ] **Canonical ego migration** — Research Notes lowercases newly typed X
  handles, but the API/store still treat historical ego keys as exact strings.
  Inventory and migrate case variants before enforcing server-wide
  canonicalization, so existing extensions do not silently disappear.
- [ ] **Remote/multi-client write hardening (deferred)** — before exposing
  working-tag mutation beyond the local curator, add idempotency keys and SQL
  immutability checks. Do not build that substrate while the only consumer is
  the current local UI and the human corpus is still below 30.
- [ ] **Frozen-extension checkpoint** — once at least 30 real human judgments
  support evaluation, preserve the current positive/explicit-negative sets as
  a named ontology version (`tag-v1`, then `tag-v2`) without stopping continued
  working edits. Report membership additions/removals between versions as
  ontology drift.
- [ ] **Community score API** — given a user-defined tag (e.g., "woo"), return
  independent affinity scores for all 334 accounts. Keep them as affinities
  until each task passes held-out calibration; they are not a probability
  distribution over accounts. Bind anchors, cache, response, snapshot, and
  model generation to that one target before exposing a model position or
  disagreement-first review queue.
- [ ] **Venn/overlap visualization** — accounts with high scores on multiple communities
  rendered as overlapping zones. Start with a 2D scatterplot colored by dominant community
  while encoding affinity, heuristic uncertainty, and known/unknown evidence
  coverage separately. Venn comes later when communities are stable.
- [ ] **Toggle between users' label sets** — same underlying embedding, different community
  boundaries per ego. UI control to switch the active ego.
- [ ] Soft affinity scores in graph explorer node color (dominant community);
  do not use one opacity channel to conflate affinity, uncertainty, and
  coverage.

---

## Phase 7: Generalization — Latent Member Discovery (ADR 012)

Uses the fingerprinted 334 as seeds to find latent community members in the broader
follow graph.

### Dependency
Requires Phase 5 fingerprints plus frozen Phase 6 tag extensions and
target-scoped scores; it does not require a necessary-and-sufficient prose
definition.

### Broader Graph Scoring
- [ ] For accounts in follow graph but outside 334: fetch recent tweets via
  `twitterapi.io /Get User Last Tweets` (budget-controlled, ~$0.15/1000 calls)
- [ ] Score fetched tweets with same classification pipeline
- [ ] Compute content fingerprint on the observed subset; report content volume,
  freshness, and coverage separately rather than calling fewer tweets lower
  confidence
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

- [x] Quarantine legacy community scores at every primary presentation boundary:
  internal list/editor, public card/evidence/community page, downloaded card,
  generated-card prompt, homepage/gallery/fullscreen art, tweet share, and
  OpenGraph metadata now use decimal legacy scores, bounded within-card relative
  geometry, or rank-only names with an adjacent “not membership probabilities”
  caveat
  (`scripts/verify_legacy_community_truthfulness.py`, implemented 2026-07-30).
- [x] Add a pure source-side follow-selectivity ranking primitive with
  duplicate-resistant support, conservative effective-degree diagnostics, and
  explicit uncalibrated score semantics
  (`src/graph/source_selectivity.py`,
  `scripts/verify_source_selectivity.py`, implemented 2026-07-30).
- [x] Run a zero-spend named-seed coverage triage against the latest
  deep-verified Community Archive tweet snapshot and explicit local follow
  views. The four Dharma seeds yielded 3,305 source-selective candidates, but
  the follow batch remains acquisition-unattributed and the SQLite inputs are
  mutable query-time views
  (`data/evals/dharma_seed_coverage_report_20260730.json`,
  `scripts/verify_seed_coverage_triage.py`, implemented 2026-07-30).
- Add a blind candidate-review surface over the frozen named-seed ranking.
  Show source support and raw evidence, never legacy community names or a
  membership percentage; record relevance only after canonical task and
  snapshot-addressed judgment contracts exist.
- Compare source-selective ranking against raw distinct-seed support only after
  30 real scoped judgments permit a frozen development/holdout split. Report
  Recall@K, precision@K, reciprocal rank, degree/community strata, and
  sensitivity to `1 / degree` versus log-inverse, capped, learned, and
  time-decayed weighting.
- Freeze new `src/data/community_gold/` modules and schema expansion until at
  least 30 real, human, task-scoped judgments exist. Product work may reuse the
  existing working-tag store and event history, but it must not create another
  persistence substrate, promote mutable tags directly to gold, or feed them
  through the legacy unbound route.
- Implement ADR 021's independently overlapping, user-scoped affiliation,
  observable-competence, and publicly expressed participation-interest heads.
  Keep style descriptors and evidence coverage separate; call outputs
  affinities until task-specific calibration passes.
- [x] Add a separate blind Research Notes thin slice that parses messy account
  notes, shows allowlisted raw profile/authored-post evidence with capture
  times, and keeps `IN` / `OUT` / `ABSTAIN` drafts session-only while clearly
  identifying the source as mutable and not snapshot-bound
  (`graph-explorer/src/ResearchNotesInbox.jsx`,
  `src/api/routes/research_notes.py`,
  `scripts/verify_research_notes_inbox.py`; synthetic-only, implemented
  2026-07-30). The API explicitly rejects `frameId`; no real write path exists.
  The 2026-07-31 block-import amendment preserves exact source spans and the
  full rationale, and recovered 57 intended subjects from the dated real takes
  snapshot without promoting employer citations into subjects (EXP-025).
- [x] Add two clearly provisional Dharma boundary probes before gold activation:
  retrieval relevance (“should this person be surfaced?”) and social
  affiliation (“is this person part of the Dharma social group?”). Keep drafts
  keyed by account and question so navigation cannot erase them
  (`ResearchNotesInbox.jsx`, implemented session-only 2026-07-31). Do not
  misencode retrieval relevance as `participation_interest`, and do not
  persist either probe as gold until its task contract is approved. This is a
  historical formative surface: the 2026-08-01 extensional-tagging amendment
  supersedes abstract boundary questions as the active product workflow.
- [x] Run a zero-cost, same-family model-provisional extraction over the 12
  dated takes blocks before asking for 24 clicks (EXP-034). Exact agreement was
  18/24, with 6 `REVIEW` and 6 consensus `ABSTAIN` slots; this rejects the
  hypothesis that the notes alone resolve most accounts. Keep the private
  artifact non-training and non-scoring.
- [x] Retire the proposed follow-up that asked Aditya to resolve three abstract
  ontology rules from EXP-034. User review on 2026-08-01 established that these
  family-resemblance categories are recognized from examples rather than
  necessary-and-sufficient definitions. Preserve EXP-034 as a negative result;
  do not propagate its model-derived answers into working tags or gold.
- Replace the provisional probes with an evidence-first multi-tag workspace:
  show the account's posts and provenance, current `IN` / `NOT IN` assignments,
  first-class removal, and action history. Do not show legacy NMF placement as
  a model position. Until target-scoped predictions exist, explicitly report
  model position and disagreement ranking as unavailable.
- Park the registered boundary-enriched 12-account, two-pass formative pretrial
  as historical methodology. If a later frozen-extension study reuses its
  evidence plan, measure disagreement, abstention, answer time,
  external-investigation rate, and repeat consistency. Keep the private panel
  identities outside git and
  publish only its manifest digest and aggregate descriptive results. The
  pre-answer 4/6/2 panel is now frozen privately with zero historical-holdout
  overlap, and its revised non-executing profile-plus-20-post plan reserves USD
  0.03846 below a local USD 0.05 planning ceiling, including two conservatively
  priced balance checks and an exact 26-call no-retry ceiling (EXP-027/028).
  The provider does not expose a server-side dollar cap. A receipt-producing
  no-retry executor, real artifact
  preflight, private raw-evidence contract, and immutable dossier transform are
  now implemented and adversarially verified (EXP-030/031). The first exact
  live attempt stopped fail-closed after four HTTP-200 calls with zero measured
  debit because the new parser guessed top-level `tweets` even though the
  actual response and existing repository documentation use `data.tweets`
  (EXP-032). Behavior-first nested-envelope coverage and the complete post-key
  private-safe console boundary are now implemented (EXP-033). A generalized
  bundle-verifier prototype was deliberately parked after its audit scope became
  disproportionate to a four-call, zero-debit abort. Collect real working tags
  and run the compatible $0 ranking bake-off after freezing an evaluation
  extension; do this before reconsidering paid evidence.
  Any resumed human study must use a frozen extension rather than demand an
  intensional definition. A completed exact acquisition and snapshot-bound UI
  route remain possible later only if those results show evidence coverage is
  the binding constraint.
- Add gold/evaluation Research Notes save/resume only after the server derives
  the target label/question from the immutable task, serves snapshot-addressed dossier
  evidence, verifies the full context receipt on write, accepts an idempotency
  key, and exposes role-independent cumulative progress. Never use
  `purpose=training` count deltas as curator progress because they reveal
  withheld evaluation roles. This does not block reversible working-tag writes
  through the ego-scoped tag surface, provided add/update/remove events remain
  inspectable and the UI never labels them as gold.
- Measure Research Notes review time, abstention, correction frequency,
  external-investigation frequency, and progress-to-30. Use those observations
  to decide whether the next dossier view should add replies, likes, quote
  context, network neighbors, or contemporaneous context.
- Rebuild the formative two-pass ledger only after the UI is bound to the live
  dossier snapshot. It must persist the pass-two transition, expose only the
  active pass, bind every event to the run manifest, use real SHA-256 with a
  cross-runtime fixture, seal the completed run, and test concurrent writes.
- [x] Persist every paid attempt before HTTP and every credential-free JSON
  response before continuing. Invalid/non-object/credential-echo responses
  retain a private body-free observation with raw-byte hash when available;
  never add an automatic retry to compensate (EXP-031).
- Implement ADR 022's typed observe/interpret/judge action policy, beginning
  with the existing frontier heuristic as a baseline and the USD 0
  retrospective mask/reveal tranche.
- Add the frozen \(C_{\mathrm{new}}\) prospective expansion cohort: retain all
  novel IDs, probability-audit relevance/yield per dollar, report support and
  source/coverage diversity, and abstain outside registered model support.

- Phase 1.4 completion: finalize policy-driven refresh loop and document human
  confirmation UX.
- Phase 2 planning: temporal analysis of follower deltas and community evolution
  (requires historical scrape storage upgrades).
- Investigate advanced metrics (heat diffusion, GNN embeddings) once baseline
  enrichment stabilizes.
- Surface cached list snapshot freshness in CLI summaries and reuse them when
  prioritising seeds (now that persistence exists).
- Implement anchor-conditioned TPOT membership scoring that combines graph
  proximity, latent-space similarity, and semantic tags/text, with separately
  typed affinity, heuristic uncertainty, and evidence-coverage fields.
- [x] Ship Phase 1 GRF membership endpoint (`GET /api/clusters/accounts/<id>/membership`)
  using ego-scoped account-tag anchors with cacheable graph solve
  (`src/graph/membership_grf.py`, `tests/test_cluster_membership_endpoint.py`,
  implemented 2026-02-17).
- Add active-learning queueing (uncertainty sampling) so users can label
  highest-entropy accounts first and improve TPOT boundary quality over time.
- Replace the quarantined automatic active-learning selector with a
  receipt-bound, archive-first policy that ranks from raw evidence and
  intersects candidates with locally archived `tweets` before any paid fetch
  is considered. Do not reuse unversioned `frontier_ranking` rows.
- Add embedding jobs for extension-captured tweet text and feed-exposure
  recency weighting so TPOT membership scores can use content semantics with
  ranking-bias normalization.
- Replace the current entropy/degree heuristic with a validated uncertainty
  decomposition (`epistemic` versus coverage-driven) and surface both
  components separately in API/UI evidence cards.
- Calibrate GRF affinity outputs against held-out positives and negatives
  (Platt/isotonic) before adding any probability field; persist compatible
  calibration metadata in membership responses.
- Replace the current positive-recall/graph-compactness threshold utility with
  an evaluation containing held-out negatives and probability-quality metrics
  (at minimum precision-recall, Brier score, and calibration curves). The
  historical score is not classification F1.
- Design a Lift-aware TPOT relevance model for `independent` propagation or
  retain an explicitly versioned classic probability model. Do not feed
  independent Lift rows into the current `1 - p_none` probability equation.
- Bind any future `account_band` and `frontier_ranking` artifact to the exact
  NPZ digest, propagation mode, community taxonomy, thresholds, method
  version, and source snapshot. Current consumers reject all unbound band rows,
  including rows paired with a valid but unrelated classic artifact; restore
  them only after version-skewed joins can be rejected at read time.
- Replace `rank_frontier.py`'s hardcoded 15-community slice with
  artifact-derived dimensionality when the ranker is redesigned; add a
  regression whose top signal is in the final active community column.
- Decide whether compositional Lift entropy adds stable retrieval value over
  max Lift, affinity margin, and seed-neighbor counts. Treat zero-evidence
  rows as undefined/abstained and delete entropy from banding if the holdout
  shows no gain.
- Add an explicit score-mode contract to
  `src/communities/cluster_colors.py`. Its ADR-013 rendering formula still
  treats synthetic `none` Lift as `p_none` and independent zero uncertainty
  as confidence; reject independent artifacts until a Lift-aware rendering
  contract has behavioral tests.
- Fix and behaviorally verify directed-PPR solver contracts before producing a
  replacement bundle: plumb `PropagationConfig.max_iter`/`tolerance`, conserve
  dangling-node mass, remove or implement unused parameters, and version the
  changed score semantics. The 2026-07-26 strict verifier currently rejects
  iteration plumbing and mass conservation.
- [x] Correct the public About page's NMF and graph-score semantics: normalized
  NMF rows are compositional shares, GRF output is uncalibrated affinity,
  heuristic uncertainty and coverage remain separate, and active acquisition
  is planned rather than autonomous. The 2026-07-28 audit also separated raw
  from working-graph counts, producer-specific edge views, heuristic edge
  weights, like ambiguity, provider/compute cost, and unregistered legacy
  measurements. The 2026-07-30 amendment also marks independent specialist,
  bridge, frontier, and faint labels as stale quarantined metadata after
  EXP-024 falsified their entropy and artifact-binding contracts.
- Register and ablate producer-specific typed-edge views. NMF currently uses
  follow + retweet + optional like blocks, while propagation has a different
  eight-type weighting table. Test edge direction, time decay, polarity/context,
  and weight sensitivity; a like may mean attention, bookmarking, irony, or
  disagreement rather than endorsement.
- Add explicit per-score semantics to the public export and card contract.
  Exemplar NMF/bits shares, classic simplex rows, and independent PPR Lift
  values currently share one `weight` field; the UI must format factor share,
  probability, Lift, and future affinity differently before those producers
  can be mixed without ambiguity. The 2026-07-30 truthfulness patch removes the
  generic percentage/probability affordance, but producer-specific export
  metadata remains unimplemented.
- Benchmark soft group membership with time-split and topology-split holdouts:
  compare harmonic/GRF, directed PPR, degree-corrected block-model or mixed
  membership baselines, and graph+semantic late fusion. Report uncertainty,
  missing-not-at-random sensitivity, and performance by degree/community.
- Benchmark network discoverability as a retrieval problem on future or hidden
  edges: seed-to-account recall@k, precision@k, mean reciprocal rank, coverage
  across low-degree accounts, and stability across topology snapshots. Keep
  current frozen topology as the control arm rather than a freshness claim.
- Add an explicit offline/local-only snapshot mode for
  `scripts.refresh_graph_snapshot` (or a quickstart flag pattern) so first-run
  onboarding does not unexpectedly attempt Supabase refresh when local cache is
  stale.
- [x] Add membership endpoint integration into graph-explorer account panel;
  the UI path was wired 2026-02-18 and its semantics were corrected and
  reverified 2026-07-28. It displays uncalibrated affinity, heuristic graph
  uncertainty, and evidence coverage separately, with no probability/CI claim
  (`graph-explorer/src/AccountMembershipPanel.jsx`,
  `graph-explorer/src/ClusterView.integration.test.jsx`).
- Add MNAR stress diagnostics comparing metric degradation under MCAR vs
  degree/community-biased masking to validate MAR approximation safety.

## Infrastructure & Tooling

- [x] Add immutable Community Archive snapshot comparison with deep hash
  verification, corpus/linkage deltas, samples, no-clobber JSON, strict
  falsifiers, and a Make target (implemented 2026-07-26).
- Track a small committed pointer/lock record for the approved Community
  Archive snapshot ID and SHA-256 while keeping the ~902 MB Parquet bodies
  ignored. Snapshot presence alone must not silently activate downstream data.
- Canonicalize one explicit data root (or a versioned data-root manifest) and
  fail on ambiguous sibling copies. EXP-023 found independent 12 GB archive
  databases whose selection changed the named-seed candidate universe from
  894 to 3,305.
- Make follow experiments snapshot-addressed: export the exact queried edge
  subset with a content digest, or copy/checkpoint the SQLite database and WAL.
  A path/inode/mtime receipt from a mutable WAL database preserves history but
  cannot reproduce the exact ranking after the source advances.
- Add row-level `source_provider`, `source_channel`, `fetch_run_id`, and
  `fetched_at` receipts to every future follow ingestion. Migrate or explicitly
  mark current `account_following` / `account_followers` rows as unattributed;
  do not infer Community Archive or twitterapi.io provenance from timing.
- Audit and version `shadow_edge` orientation semantics across historical
  writers. Current producer code and stored metadata treat `direction` as
  capture context, while `docs/reference/DATABASE_SCHEMA.md` contains
  contradictory source/target prose.
- Extend named-seed triage with source-separated typed-edge coverage
  (replies, mentions, quotes, retweets, and likes) only after event timestamps
  are distinguished from aggregate-build timestamps.
- Introduce caching layer for Flask metrics endpoint to reduce recomputation
  during rapid slider adjustments.
- Monitor SQLite growth and evaluate move to PostgreSQL if enrichment scale
  exceeds current performance envelope.
- Bundle verification scripts (`scripts/verify_*.py`) into a consolidated CLI
  entry point for Phase 2.
- Decompose `scripts/verify_search_teleport_tagging.py` (468 LOC after its
  2026-08-01 auth/provenance safety patch) by separating read-only graph checks
  from isolated tag-state verification; do not grow the live verifier further.
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
- Persist per-model active-learning outputs alongside `llm_ensemble`
  consensus rows so `scripts.verify_active_learning` can measure real
  3-model coverage instead of reporting a false `0/N` gap.
- Keep pilot judgments in versioned local SQLite. Revisit shared
  workspace-backed storage, tenancy, and conflict policy only through a
  separate approved ADR; ADR 006's proposed Postgres migration is not approved.
- Add immutable alias-resolution receipts for mixed numeric, `shadow:*`, and
  `handle:*` Community Gold identities before any legacy label is admitted to
  a versioned study.
- Freeze, retire, or explicitly audit curator-authenticated writes to the
  `legacy_unbound` compatibility surface before creating a real versioned
  study.
- Capture an immutable source manifest (path-independent snapshot ID, size,
  timestamps, deep hash, and query receipt) before reusing EXP-017's
  point-in-time Community Gold counts.
- Make bound Research Notes dossiers snapshot-addressed, or recompute and
  verify their full dossier-context hash server-side during judgment writes.
  The 2026-07-30 thin slice queries mutable local rows, labels them as such,
  rejects frame binding, and has no write path. Do not enable real saves while
  old snapshot metadata could describe post-cutoff backfills or edits.
- Add an artifact registry that proves evidence/context/model/method/calibration
  artifacts exist and are mutually compatible; format-valid hashes alone are
  not provenance.
- Add a registered calibration-record artifact with ontology/task/evidence
  compatibility, class support, labelability/abstain coverage, and untouched
  development/test identity before enabling `calibrated_probability`.
- Add a backend-neutral inference seam with immutable model/prompt/schema/cache
  identity, explicit unavailable provider fields, usage receipts, and a record
  of whether and which public evidence left the machine.
- Extend `enrichment_log` and current budget guards with actual credits,
  modality/direction, propensity, usable yield, egress, and provenance.
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

- Treat the 300-LOC threshold as a diagnostic and human-review trigger, not an
  automatic instruction to split unchanged scope across more modules. A useful
  decomposition must name the responsibility or dependency edge it removes.
- [x] Make each isolated worktree able to resolve the pinned graph-explorer test
  runtime without borrowing a sibling checkout's `node_modules`. A clean
  `npm ci` from `graph-explorer/package-lock.json` restored the runtime and the
  extensional slice's expanded impacted suite passed 121/121 on 2026-08-02.
- Fail fast when `ARCHIVE_DB_PATH` is absent, zero bytes, or lacks the expected
  archive schema. Print the resolved path and remediation instead of letting a
  worktree silently create or accept an empty SQLite database; live extensional
  QA exposed this failure mode on 2026-08-02.
- Make `scripts/verify_personal_ontology_docs.py` bootstrap the project root
  when invoked directly, matching its documented script-style usage. The
  2026-07-30 source-selectivity checkpoint found that module invocation passes
  21/21 while direct invocation raises `ModuleNotFoundError: scripts`.
- `scripts/verify_research_notes_inbox.py` is now exactly 300 LOC. Do not append
  another responsibility; if its next change is substantive, extract backend
  and frontend execution behind one human-readable orchestrator rather than
  splitting only to satisfy the metric.
- Pin a supported Node version for frontend CI/developer parity and retire the
  conditional graph-explorer test `Storage` shim once Vitest/jsdom no longer
  conflicts with Node 26 experimental web storage.
- Split `public-site/src/CommunityCard.test.jsx` (325 LOC after the 2026-07-30
  semantics assertion update) into score-semantics and presentation-behavior
  files without duplicating fixtures.
- [x] Add clean-checkout toolchain pins, a non-deploying
  `make verify-baseline`, and a read-only assumption-baseline verifier that
  reports Git state, lock hashes, data-copy independence, hashes, SQLite
  integrity/counts, and artifact freshness (implemented 2026-07-25).
- [x] Document end-to-end enrichment + explorer refresh workflow in `docs/PLAYBOOK.md`
  (implemented 2026-02-09).
- [x] Add `make` targets to standardize test and verification entrypoints
  (`Makefile`, implemented 2026-02-21).
- Decompose `docs/WORKLOG.md` and `docs/ROADMAP.md` into archived session
  slices or sub-docs; both are now >300 LOC and violate the repo's own
  working-set guidance for agents.
- Split `docs/modules/data.md` (361 LOC after the 2026-08-01 account-tag contract
  update) by moving durable annotation/tag stores into a focused module guide;
  preserve the existing index link and do not split merely by line count.
- Decompose `docs/EXPERIMENT_LOG.md` into an index plus dated experiment
  slices; it is also now >300 LOC and should not remain a growing monolith.
- Recreate `docs/PROJECT_STRUCTURE.md` or correct the required-reading pointer
  in `AGENTS.md` after identifying the intended canonical structure source.
- Track the additional monoliths and reuse boundaries in the
  [personal-ontology refactor ledger](plans/2026-07-26-personal-ontology-refactor-ledger.md).
- Wire the currently orphaned Community Gold React modules only after
  decomposing the live `Communities.jsx` and `AccountDeepDive.jsx` path and
  adding a blind dossier mode that cannot reveal model/group recommendations
  before judgment. Before mounting them, add `withCuratorAuth` to
  `graph-explorer/src/communityGoldApi.js`; every corresponding backend route
  is curator-protected while the current orphaned client sends no token. This
  auth repair was discovered during the 2026-07-30 preview slice and kept out
  of that commit because the preview has no Community Gold consumer.
- Decompose `tpot-analyzer/graph-explorer/src/GraphExplorer.jsx` into smaller components/hooks (<300 LOC each) to keep debugging manageable.
- Decompose `tpot-analyzer/graph-explorer/src/ClusterCanvas.jsx` into smaller components/hooks (<300 LOC each) to keep debugging manageable.
- Decompose `tpot-analyzer/graph-explorer/src/ClusterView.jsx` (1,464 LOC in the
  2026-07-28 audit) and `tpot-analyzer/graph-explorer/src/data.js` (739 LOC) into
  focused modules/hooks below 300 LOC.
- Continue the cluster-route decomposition under `tpot-analyzer/src/api/cluster/`.
  The historical `src/api/cluster_routes.py` path no longer exists, but
  `src/api/cluster/state.py` remains 630 LOC and mixes state loading, caching,
  membership wiring, and hierarchy concerns.
- Finish decomposing `tpot-analyzer/public-site/api/generate-card.js` (353 LOC
  after extracting the rank-only legacy prompt) into request validation,
  OpenRouter client, and cache/budget helpers so timeout and observability
  changes stop accumulating in one serverless file.
- Finish decomposing `tpot-analyzer/public-site/src/GenerateCard.jsx` (345 LOC
  after extracting the rank-only legacy prompt) into cache persistence,
  generation transport, and React hook orchestration. Keep the browser/server
  prompt contracts behaviorally aligned while their ESM/CommonJS packaging
  remains separate.
- Decompose `tpot-analyzer/scripts/_export_helpers/_community_extractors.py`
  (556 LOC after the 2026-07-30 fail-closed guard) into artifact compatibility,
  username resolution, membership extraction, and band-account assembly.
  Keep the compatibility guard at the orchestration boundary during the split.
- Decompose `tpot-analyzer/scripts/active_learning.py` (over 420 LOC after the
  2026-07-30 spend guard) into CLI/account-policy orchestration and round
  execution. Keep automatic-selection rejection at the public selection API
  and spend boundary until a receipt-bound policy replaces it.
- Decompose `tpot-analyzer/scripts/fetch_tweets_for_account.py` (631 LOC after
  the 2026-07-30 source-aware staleness fix) into provider transport, archive
  loading, persistence, and freshness policy. Preserve the contract that
  topic-search context does not count as a completed account enrichment.
- Split `tpot-analyzer/tests/test_export_public_site.py` (over 1,100 LOC) by
  export contract (communities, propagated handles, bands, and orchestration)
  without weakening its fail-closed artifact fixtures.
- Decompose `tpot-analyzer/public-site/src/About.jsx` (1,080 LOC after the
  2026-07-30 copy-only truthfulness amendment) by methodology section. Preserve
  the behavioral copy contract that independent display bands are quarantined
  legacy metadata.
- Decompose `tpot-analyzer/src/shadow/enricher.py` (2449 LOC) into orchestration, retry/backoff, state management, and API dispatch modules (<300 LOC each); current file mixes all four concerns.
- Decompose `tpot-analyzer/src/shadow/selenium_worker.py` (2173 LOC) into browser control, HTML parsing, and network handling modules (<300 LOC each); tightly coupled to enricher — decompose both together.
- Decompose `tpot-analyzer/src/data/shadow_store.py` (1252 LOC) into focused store modules by table domain (<300 LOC each); currently mixes multi-table CRUD with business logic.
- Decompose `tpot-analyzer/src/graph/hierarchy/expansion_strategy.py` (1013 LOC) into scoring, strategy selection, and memoization modules (<300 LOC each).
- Add ADR documenting testability refactor decisions (fixtures, helper extraction, verification scripts).
- Add a one-command public-site deploy flow that respects Vercel `rootDirectory=tpot-analyzer/public-site` without CLI path recursion; current Blob-backed data fix is ready locally, but deployment still requires Git integration or project-setting surgery.

## Infrastructure / Observability

- [x] Add credential-free, read-only, self-hashed acquisition planning for
  full followings pages and fixed formative dossiers. Pin a dated official
  price card, selection-manifest digest, worst-case integer-credit reserve,
  hard USD cap, and `authorizes_execution=false`; verify the real private plan
  without printing identities (`src/evaluation/acquisition_plan_contract.py`,
  `src/evaluation/dossier_acquisition_plan.py`, and
  `scripts/verify_acquisition_plan_contract.py`, implemented 2026-07-31).
- **API credit telemetry**: extend the acquisition receipt ledger and expose
  quoted worst-case versus actual provider usage before and after each action.
  The 2026-02-25 endpoint estimates formerly listed here are historical, not a
  current rate card. Price cards must be versioned and refreshed before spend.
- Make the historical acquisition holdout guard fail closed when its schema is
  absent, and verify that behavior before any TwitterAPI.io or other paid
  enrichment action.
- Replace both existing following fetchers before paid use. The planning half
  is complete; the execution half must verify the exact plan hash, reserve
  worst-case integer credits before every request;
  reject handle/ID conflicts and holdout matches; store per-request response
  hashes, cursors, balance receipts, dated snapshot edges, completeness, and
  exact insertion counts. The 2026-07-31 audit found stale pricing/parameters,
  pre-dry-run paid identity calls, account-level budget overruns, missing
  receipts, and timeless union writes in the current paths. Start with a
  maximum `$0.25` non-holdout microtrial rather than the available `$5` cap.
