# Experiment Log

> Hypotheses tested, results observed, lessons learned. This is institutional memory — what we tried, what worked, what didn't, and why. Each entry records the question, the method, the data, and the verdict so future sessions don't re-run failed experiments or miss validated insights.

*Last updated: 2026-07-30 (off-platform evidence channel; selectivity weighting)*

---

## EXP-019: Can off-platform bio links and source-selectivity recover a named subculture?

**Date:** 2026-07-30

**Question:** Three channels (follows, engagement, tweet text) miss accounts whose
substance lives elsewhere. Does resolving profile bio links add evidence the follow
graph structurally cannot contain — and does weighting a follow by the *source's*
selectivity recover a subculture the operator named by hand?

**Hypothesis:** (H1) `profiles.website` is write-only and its t.co stubs hide real
personal sites. (H2) A follow emitted by a selective account carries more
information than one from a promiscuous account, so selectivity-weighted
co-following should recover operator-named seeds. (H3) Seeds named from lived
experience are largely absent from a Feb–Mar 2026 snapshot.

**Method:** Resolved all 2,114 URLs mined from `profiles.website` and bio text
through the existing SSRF-guarded `safe_urlopen`; classified each page with pure
heuristics; captioned undecided pages with a two-model local ollama ensemble.
Separately fetched following lists for 40 operator-named handles via twitterapi.io
and scored candidates with `src/propagation/selectivity.py`.

**Result:**
- 1,894 of 2,114 URLs resolved (89.6%); 532 person-shaped pages; 674 Substack and
  521 GitHub outbound links. **~310 of the GitHub links are boilerplate footers
  (`docs.github.com`) — a known over-count, not yet excluded.**
- **H3 confirmed:** 5 of the operator's first 8 named accounts were absent from
  every table; follow snapshot is 2026-03-24 against July judgements.
- **H2 partially confirmed.** A cluster built from 4 dharma seeds contained
  `O1A2S3D` *before* the operator named it — an unprompted recovery. Against 19
  later-written labels the ranking placed positives at median rank 71 of 2,786
  (top 2.5%), 12 inside the top 100.
- **H2 limit found:** the method recovers the *neighbourhood*, not the *boundary*.
  `Meaningness`, labelled "NOT tpot", ranked #43 — above most positives — because
  co-following measures adjacency, not membership.
- Source selectivity alone surfaced only celebrities; a target-side popularity
  discount was required, and that discount needed a floor or it inverted into a
  bounty on unmeasured accounts. Neither term works alone.
- With 7–8 seeds the celebrity floor dominates; at 23 seeds it clears. **Seed
  count, not the weighting formula, was the binding constraint.**
- Cost: 40 accounts, ~61k edges, **$0.35**. The repo's cost model
  (`CREDITS_PER_FOLLOWER = 15`) over-estimates actual spend by ~14x.

**Lesson:** Selectivity × rarity is necessary but not sufficient. It ranks the
neighbourhood well and cannot express membership, so human labels remain the only
encoding of the boundary. Negative examples are worth more than positives here:
the two explicit OUTs did more to expose the metric's limits than 25 INs.

**Next step:** Exclude the operator from their own candidate lists; drop
`docs.github.com` from signal links; add interface-cluster seeds, which are far
sparser than the dharma seeds.

---

## EXP-020: Do the local vision models actually disagree, and does it matter?

**Date:** 2026-07-30

**Question:** Text classification abstains on 386 of 1,894 fetched pages. Can a
local vision model resolve them, and should its self-reported confidence be trusted?

**Hypothesis:** A vision model can classify a page image where HTML heuristics
abstain; model-reported confidence is a usable gate.

**Method:** Probed `/api/show` for capabilities, then baked off `qwen2.5vl:7b`,
`gemma4:latest` and `qwen3.6:latest` on identical images. Ran the surviving two as
an independent-vote ensemble over 437 undecided pages.

**Result:**
- **A prior claim of ours was wrong:** `gemma4` and `qwen3.6` already had vision.
  It was inferred from the `families` metadata field, which does not report it;
  `/api/show` → `capabilities` is authoritative. A 6 GB pull was unnecessary.
- `qwen3.6` returns empty replies under `format:json` (thinking model) — unusable.
- The two working models agreed 8/8 on the decision that matters, so accuracy did
  not separate them. **Calibration did:** `gemma4` reported `confidence: 1.0`
  three times in eight, and once alongside an *empty caption*.
- Ensemble over 437 pages: 213 unanimous (51%), 99 single-voter, **88 split**,
  16 no-signal. 121 pages show a person.

**Lesson:** A model's self-reported confidence is not evidence — confident
emptiness is a real failure mode. Independent agreement is, which is why trust
gates on voter count, mirroring the existing 2-of-3 rule in
`scripts/label_tweets_ensemble.py`. Splits are stored and surfaced for human
adjudication rather than averaged away.

**Next step:** Route the 88 splits into the review queue; nothing currently reads
`bio_link_image_verdict`.

---

## EXP-018: Does the Slice 1 store enforce its holdout and identity claims?

**Date:** 2026-07-26; amended 2026-07-28

**Question:** Can a local versioned Community Gold adapter preserve legacy
meaning, keep global account roles stable, prevent terminal-label leakage,
separate predictions from human judgments, and make a terminal release
one-use and reproducible?

**Hypothesis:** An additive nullable migration plus immutable ontology/task,
global-role, evidence, head, prediction, and release records should preserve
legacy rows without invented scope. Purpose-gated SQL should exclude terminal
labels from training, and adversarial direct writes should fail or be detected
by stored digests.

**Method:** Built behavior-first SQLite tests and a synthetic, network-blocked
verifier. Falsifiers included reopening after corrections, stale/malformed
migrations and triggers, same- and cross-registry account reassignment,
ontology projection append, role alias collision, head deletion/rewind, empty
or partial terminal release, sibling-task writes after release, forged terminal
JSON/hashes, direct probability insertion, missing method output, terminal
reads through training SQL, live GRF probability/interval wording, table/index
name impersonation, post-write terminal actor/time tampering, a missing coverage
denominator, zero/missing public graph signals, and malformed graph-settings
JSON. The final hardening queue
also tests a post-cutoff terminal head, incomplete full-judgment/lineage
attestation, future-schema no-mutation, weakened partial-index predicates and
UNIQUE/CHECK clauses, a silent schema marker, fractional counts, and nullable
`TEXT PRIMARY KEY` columns. Three independent computational peers reviewed
migration, access, evaluator, construct validity, and public claims.

**Result:** **The seven hostile schema/release classes were reproduced and
repaired on synthetic data, and A1 idempotent terminal replay is green.
Real-use randomization, authenticated actor identity, and label-support gates
remain open.**

- Verifier: 6/6 checks passed with 12 global roles and nominal terminal
  probability at least `0.166667`. This is a quota probability conditional on
  uniform seed randomization, not proof that the caller-supplied seed was
  committed before outcome knowledge.
- Synthetic allocation: 4 model-development, 1 policy-development, 2 terminal,
  and 3 frame-only accounts, plus fixed training/challenge identities.
- Training returned only its development-role label at the raw SQL-query
  boundary. The terminal release required all four account/group heads for one
  reviewer, reported `in/out/abstain` and labelability coverage, and stored
  frame, role, receipt, and release digests.
- A second release and writes to any sibling frame sharing the global role
  generation failed. Prediction records remained separate from five human
  scoped-history rows.
- `calibrated_probability` remained unavailable through both the store API and
  direct SQL. Legacy diagnostics now report missing-score coverage and suppress
  Brier/ECE; the live GRF surface reports affinity, heuristic uncertainty, and
  coverage separately.
- Missing expected-following data previously fabricated `1.0` coverage; it now
  returns `value=null`, `status=unknown`. A zero public graph signal remains
  zero, while a missing signal is displayed as unavailable rather than as
  weakest evidence.
- Full structural migration validation at the earlier checkpoint rejected
  table/index impostors. The terminal access-envelope digest rejected
  post-write mutation of the caller-asserted actor or access time; it did not
  authenticate who supplied that actor.
- Final falsification produced nine expected-failing tests covering ten concrete
  hostile shapes (the weakened-CHECK test was parameterized). The shapes were a
  post-cutoff terminal head, incomplete full-judgment/lineage attestation,
  future-schema mutation, weakened partial index, weakened UNIQUE, two weakened
  CHECK forms, silent schema marker, fractional count, and nullable text primary
  key. After repair, the focused Community Gold suite passed 101/101.
- Red-to-green surfaces: trigger regression 3/3; schema/migration guard 8/8;
  adversarial head/prediction/migration/terminal/provenance 12/12; role/frame
  20/20; membership endpoint 5/5; graph-explorer membership panel 4/4;
  public EvidenceSummary 2/2; combined backend GRF/evaluator 17/17.
- Prior integrated checkpoint, now superseded by final hardening: focused
  backend 114/114; credential-free Python 1,425 passed and five skipped; public
  site 189/189; graph explorer 730/730; synthetic verifier 6/6.
- Final core handoff also passed the Slice 1 verifier 6/6 and its verifier unit
  test 1/1; `git diff --check` was clean. The largest scoped implementation file
  was 264 LOC and the largest regression file 260 LOC.
- **A1 idempotent terminal replay — GREEN:** the RED phase deliberately
  produced 11/11 expected failures across two focused files, covering
  lost-response recovery; exact payload/`accessedAt` replay; actor, reviewer,
  receipt, and frame conflicts; corruption; sealing; concurrent requests; no
  post-commit reload; and HTTP 409 with no leaked rows. Final delivery tests pass
  12/12, the broader Community Gold/Slice 1 surface passes 102/102, and the human
  verifier passes 6/6. The first release fully verifies before commit and its
  rollback test passes; an identical retry returns exact judgments/access
  metadata, preserves `accessedAt`, uses one row, and marks `replayed=true`;
  mismatches map to HTTP 409 with no rows; corruption fails closed; concurrent
  calls converge; and the route no longer reloads post-commit. Maximum route
  size is 270 LOC and the new delivery module is 262 LOC. `accessedBy` remains
  caller-asserted.
- The verifier test's socket hooks observed no network attempt; no real database,
  label, model, provider, or external state was changed.
- A separate architecture falsifier remains open: `list_anchor_polarities(ego)`
  aggregates polarity across all tag keys and the membership endpoint/cache has
  no ontology/task/community target. Synthetic binary endpoint results are
  valid smoke checks, but they do not test overlapping multi-subculture
  inference or cross-target isolation.
- A no-filesystem malformed-settings stub made the GRF verifier print the
  settings path and exact `JSONDecodeError` as a failed parse check; malformed
  JSON no longer silently becomes an empty settings dictionary.
- Independent final verification passed credential-free Python
  `1,449 passed, 5 skipped`, public site `190/190`, graph explorer `741/741`,
  Slice 1 `6/6`, documentation contracts `21/21`, documentation hygiene `9/9`,
  GRF affinity smoke checks `10/10`, and both production frontend builds.
  The graph explorer's repository-wide lint command separately exposed
  `15` errors and `2` warnings in existing unrelated frontend debt, so this
  experiment does not claim a clean full lint gate.

**Lesson:** Passing happy-path tests was insufficient. Restart-time index
recreation, mutable ontology/head/release state, caller-selected registry
escape, frame-local rather than generation-level sealing, late filtering, and
unverified payloads all survived the first implementation. A validated
transactional migration, one registry per stable account, complete release
coverage, and read-time recomputation are necessary to make “sealed”
operational rather than rhetorical.

**Next step:** Add a pre-allocation universe commitment plus independently
auditable seed/randomization receipt, then review real identity receipts,
strata, quotas, and negative/abstain labeling capacity before creating any
non-synthetic frame. Keep probability language disabled until a compatible
calibration record and untouched class support exist. Before live release,
derive actor provenance from an authenticated principal; A1 now supplies safe
idempotent lost-response replay. Before real membership inference, scope
anchors, cache, and responses by immutable target ID and pass
cross-target-isolation tests. Bind coverage numerator/denominator to compatible
generation/as-of data.

---

## EXP-019: Why did graph-explorer lose localStorage under the full suite?

**Date:** 2026-07-28

**Question:** Were 43 graph-explorer failures evidence of application
regressions, test contamination, or a runtime/toolchain mismatch?

**Hypothesis:** Node 26's experimental global web-storage accessor was
shadowing jsdom's `window.localStorage`. If true, disabling experimental web
storage should make the four affected files pass without application changes.

**Method:** Ran the ordinary full Vitest command, inspected the runtime/config,
then reran `storage`, `discoveryCache`, `ClusterTour`, and `ClusterView`
integration tests with `NODE_OPTIONS=--no-experimental-webstorage`. Added a
conditional, standards-shaped in-memory `Storage` in test setup only when
jsdom storage is unusable, then reran both the focused set and ordinary full
command.

**Result:** **Confirmed.** The initial ordinary run had 687 passes and 43
localStorage-only failures. Disabling Node's experimental web storage produced
107/107 focused passes. The conditional setup repair produced 107/107 without
the flag and 730/730 on the ordinary full suite. No application storage code
was changed.

**Lesson:** A new runtime global can shadow a browser emulator even though the
test environment is configured as jsdom. Patching product storage behavior
would have hidden the root cause; the correct seam was conditional test
environment setup.

**Next step:** Pin a supported Node version for CI/developer parity or remove
the shim after Vitest/jsdom no longer expose the Node 26 conflict. The runtime
still emits an experimental-webstorage warning before setup executes.

---

## EXP-017: Can the imported Community Gold rows calibrate a versioned task?

**Date:** 2026-07-26

**Question:** What is actually present in the existing Community Gold tables,
and can migration safely attach a personal ontology or calibration meaning?

**Hypothesis:** Existing rows should migrate without loss, but their identity,
class balance, evidence provenance, and correction history must determine
whether they can enter a versioned task.

**Method:** Queried the local archive database read-only through SQLite's
immutable-URI connection mode. That mode prevented writes through the
connection; it did not prove that the source artifact itself was immutable.
Counted label/split/reviewer/judgment/history rows, inspected evidence keys and
creation times, classified account-ID forms, and checked available
alias-to-numeric mappings. No path-independent snapshot ID, size, mtime,
SHA-256, or query receipt was recorded.

**Result:** **The observed source shape was migration-compatible; calibration
eligibility was decisively rejected.**

- 167 label rows and 167 split rows, all active: 113 train, 25 development,
  and 29 test.
- All 167 judgments are `in`; there are zero `out`, zero `abstain`, and zero
  supersessions. The only reviewer is `curator:adityaarpitha`.
- Evidence contains only `handle` and `source`; creation spans less than one
  second on 2026-03-21.
- IDs comprise 81 `shadow:*`, 54 `handle:*`, and 32 numeric values. At least 61
  shadow and 4 handle identifiers have candidate numeric profile mappings, but
  no immutable resolution receipt binds them.

**Lesson:** These rows are imported positive membership evidence, not a
binary calibration or untouched evaluation set. Automatically assigning user,
ontology, task, stable account, evidence generation, or negative meaning would
fabricate semantics.

**Next step:** Preserve every row as `legacy_unbound`. Build explicit
identity-resolution receipts and collect blinded `out`/`abstain` judgments in
a frozen frame before estimating calibration or prevalence-sensitive metrics.
Capture a deep-hashed source/query manifest before reusing these point-in-time
counts; they are not evidence that the Community Archive corpus was latest.

---

## EXP-016: Do frozen soft memberships and graph discoverability satisfy their stated contracts?

**Date:** 2026-07-26

**Question:** Once the frozen graph-to-output chain is identity-compatible, do
its solver behavior, probability interpretation, threshold behavior, taxonomy
stability, and discoverability structure support the claims made about them?

**Hypotheses:** The historical uncertainty post-processing fingerprint should
reproduce; configured PPR controls and probability mass should behave as
declared; soft-target predictions should beat empirical-prior and uniform
baselines; top-class confidence should have ECE ≤ .05; propagation-heldout
calibration positives should usually be core rather than halo;
information-equivalent taxonomy splits should preserve selection; bounded edge
loss should preserve selection; and capture, direction, and degree mechanisms
should be measurable explicitly.

**Method:** Added three frozen-manifest-first evaluators with deterministic
fixtures, explicit falsifiers, stable ties, no-clobber outputs, and a shared
`0/1/2` exit contract. Measured a bounded solver cycle and dangling-node
control, the 55-account propagation-heldout calibration set, an equal split of
every taxonomy factor, ten fixed-seed edge-deletion repetitions at 1%/5%/10%,
directed versus undirected versus reciprocal components/reachability, the exact
18-handle seed panel, capture-center incidence, and degree-stratified selection.
Full methods and limitations are recorded in
`docs/experiments/2026-07-26-membership-discoverability-audit.md`.

**Predicted outcomes:** A valid solver must respect `max_iter=1` and conserve
mass within `1e-9`. Soft-target predictions must beat empirical-prior and
uniform Brier and soft-label log loss; hard dominant-class confidence must have
ECE ≤ .05. At least half of recalled calibration accounts must cross τ. Equal
factor splitting must keep core Jaccard ≥ .95 and core-count change ≤ 5%.
Selection Jaccard must remain at least .95/.90/.85 under the three edge-loss
levels.

**Result:** **The historical uncertainty fingerprint and bounded selection
stability survived; solver validity, soft-target agreement, hard-label
confidence calibration, calibration-set core interpretation, and taxonomy
invariance were falsified. Capture, direction, and degree mechanisms were
confirmed as material.**

- Legacy uncertainty reconstruction maximum error: `3.6783e-08`, with zero
  cells above `1e-6`.
- Requested `max_iter=1`, but all three probe classes reported 90 iterations.
- Dangling graph converged with mass `.21375`; reciprocal control retained `1`.
- Static documentation correspondence rejected the About page's independent
  overlapping-percent interpretation: the NMF producer explicitly
  row-normalizes `W` to sum to one.
- Holdout: top-1 `11/55`, top-3 `27/55`; model/prior/uniform Brier
  `.586815/.505926/.517078`, log loss
  `3.737831/2.620363/2.708050`, ECE `.094255`. The empirical prior is
  optimistically estimated from the evaluation holdout, but uniform also wins.
- Core/halo: `0/53/2` propagation-heldout calibration accounts were
  core/halo-only/missed. Because these accounts selected τ, this is
  retrospective behavior rather than threshold generalization.
- Equal split-all: core `175→71`, core Jaccard `.405714`; selection
  `8,984→5,179`, Jaccard `.576469`.
- Minimum selection Jaccards under 1%/5%/10% stored-edge deletion:
  `.990984/.961264/.922418`. Memberships were fixed, so this is not an
  end-to-end propagation result.
- Capture centers are 1.731% of nodes but touch 100% of shadow edges; 80.336%
  of nodes have degree one.
- Seed reachability is 39.944% forward, 66.780% reverse, 99.991% when
  undirected, and 6.425% on reciprocal-only edges.
- Published selection reconstructs exactly as 175 core + 8,809 one-hop halo;
  degree-one versus degree≥51 selection differs by 80.176 percentage points.

**Lesson:** Reproducible soft values can still have an unsupported probability
interpretation. The current output is a useful weak ranking/control artifact,
but its soft-target agreement and hard-label confidence calibration both fail
these diagnostics. The threshold result needs a second untouched validation
set. Near-total weak connectivity is also not network discoverability when
capture design, edge direction, reciprocity, and degree change the reachable
universe.

**Next step:** Keep the frozen bundle immutable. Fix the PPR contracts, choose
compositional versus independently overlapping membership semantics, collect
taxonomy-compatible positives and verified negatives, and evaluate
future-time/multi-center retrieval before generating a replacement.

---

## EXP-015: Did the Community Archive corpus advance, and did archive linkage keep pace?

**Date:** 2026-07-26

**Question:** Is the July 25 immutable snapshot stale relative to the mutable
bulk object one day later, and can the delta be measured without treating
missing linkage as known provenance?

**Hypothesis:** A changed source identity should add rows/accounts and advance
the newest-tweet cutoff. If archive linkage keeps pace, new linked rows should
cover the row delta and missing-upload-ID rows should not grow.

**Method:** Probed and downloaded the changed object into a new no-clobber
snapshot directory, then independently verified the full file hash and Parquet
metrics. Added a comparator that verifies both immutable snapshots before
reporting numeric deltas, samples, falsifiers, and optional exclusive-create
JSON.

**Result:** **Corpus advance confirmed; archive-linkage pace falsified.**

- Candidate `20260726T045149Z-37a97fa3e057`, SHA-256
  `99e93da98bb9fbdbddaa46a9e7f00da7ae501144294c123155e4d56447a8e9bd`.
- Rows `8,318,250→8,321,675` (`+3,425`); accounts
  `34,684→34,698` (`+14`); newest tweet advanced `87,038` seconds.
- Archive-linked rows changed by `0`; missing upload-ID rows grew by `3,425`;
  linked fraction declined by `.000333`.

**Lesson:** “Latest bulk export” and “latest fully archive-linked evidence” are
different claims. The new snapshot is the latest corpus observation made in
this experiment, but it does not refresh follower topology and its added rows
must not be silently asserted to have archive-upload provenance.

**Next step:** Bind this candidate snapshot by ID and hash to any downstream
tweet-corpus experiment. Keep graph/topology freshness and raw per-user archive
inventory as separate experiments.

---

## EXP-014: Do the graph, propagation, calibration, and frozen TPOT output belong together?

**Date:** 2026-07-26

**Question:** Can the existing graph artifacts safely support controlled
experiments on network discoverability and soft group membership, or are
positional arrays from different node universes being combined?

**Hypotheses:**

1. The bare 95,057 × 95,057 adjacency cache still represents the ordered
   `graph_snapshot.nodes.parquet` and `graph_snapshot.edges.parquet`.
2. The newer 298,347-node `community_propagation.npz` is a usable superset that
   can be reindexed to the full graph.
3. The 95,057-node training propagation is the artifact that generated the
   current calibrated 8,984-node TPOT output.

**Method:**

1. Reconstructed a directed binary CSR matrix from every graph edge under the
   Parquet node order and compared its shape, sparse structure, and values
   exactly with the cache.
2. Compared unique account IDs and order for both propagation candidates
   against the graph, and inspected every array dimension before permitting
   alignment.
3. Recomputed degrees, relevance, calibrated core + one-hop halo selection, and
   ordered selected-node identity at the saved threshold.
4. Compared the recomputed relevance vector with the producer's saved float32
   vector, then verified the selected mapping, exact induced node/edge Parquets,
   full and TPOT spectral row order, and TPOT runtime adjacency semantics.
5. Inspected membership score mode, community schema, solver convergence, and
   held-out-label leakage. Corrected the historical “F1” description: the
   threshold objective is the harmonic mean of positive holdout recall and
   graph compactness, not precision/recall F1 because no negatives were used.
6. Added behavioral tests for stale same-shape caches, duplicate IDs, partial
   overlap, caller-priority plus safe superset reindexing of every known
   node-indexed array, classic versus independent score semantics, malformed
   calibration provenance, exact relevance binding, output reservation, and
   spectral node/shape mismatches.

**Predicted outcomes:**

- If hypothesis 1 is true, all 319,771 edge rows reconstruct with zero ignored
  edges and zero differing sparse cells.
- If hypothesis 2 is true, all 95,057 graph IDs occur uniquely in the active
  propagation and can be reordered without truncation.
- If hypothesis 3 is true, training propagation has exact graph order and
  reproduces core=175, halo=8,809, total=8,984 and the frozen ordered node list.

**Result:** **H1 and H3 confirmed; H2 decisively rejected.**

- A committed compatibility record pins all 15 frozen scientific files:
  27,272,597 total bytes, with exact size and SHA-256 for graph Parquets,
  adjacency caches, selected propagation, calibration/holdout/relevance,
  mapping, both spectral pairs, and TPOT Parquets. Bundle ID:
  `frozen-tpot-control-20260726`.
- The adjacency cache exactly reconstructs: 95,057 nodes, 319,771 edge rows,
  319,771 nonzeros, and zero ignored edges.
- Ordered graph digest:
  `c5ba0e5e9ef297fe5e1ddc3790301df4d9a4f659a5332c340262a4b07384ee86`.
- Adjacency structure digest:
  `df84d5d1a3c596bb1eefa95b7d99ebdba0f7e71332be830e4fb835a93dd18d0f`.
- Adjacency value digest:
  `b9246583162bc508dc3c6e564e0a21e2ffbeefc2a498e4399510c713c78b61f3`.
- The active propagation matches only 358 graph IDs and omits 94,699. It is a
  larger, largely different node universe, not a safe superset. It declares
  `independent` Lift semantics, has 16 communities plus `none`, and cannot be
  passed into the probability-based TPOT relevance scorer even if its node
  domain were rebuilt to match.
- `community_propagation_train.npz` contains exactly the same 95,057 IDs in the
  same order. At `tau=0.05644444444444444`, it exactly reproduces the saved
  175 core + 8,809 halo = 8,984 total selection.
- The train artifact is legacy 14-community-plus-`none`; it has no saved mode,
  but its finite nonnegative rows sum to one within `2.38e-7`, so it satisfies
  the legacy classic probability contract and matches the certified file hash
  `610d59cfdae3e6f3bb1520b6a86e53c9df850ad3beeb01949bb1a768c4dbaab2`.
  New mode-less artifacts are rejected. Its community UUIDs have zero overlap
  with the active 16-community schema.
- All 15 train-artifact convergence flags are false and every recorded solver
  iteration count is 800. The downstream relevance scorer therefore applies
  its non-convergence factor of `0.3` to every dominant class. Compatibility is
  proven; solver validity is not.
- Recomputed relevance is exactly equal after the producer's float32 cast;
  saved-vector SHA-256:
  `e08d5a87fdf096f7c7751de2cedbc2a01871831e2afc72a6b7022da496b576dd`.
- The recomputed ordered selection matches the frozen mapping at compatibility
  digest
  `5b6a8bc27ccedcab9c6d10b676a5158543e9e044397f8a259d1615263a8beed2`.
- The TPOT node/edge Parquets are the exact induced subset (8,984 nodes,
  186,442 edge rows), both spectral artifacts have exact node-row binding
  (95,057 × 20 full; 8,984 × 30 TPOT), and the TPOT runtime adjacency exactly
  reconstructs with `directed_plus_mutual_reverse` semantics at structure
  digest
  `95ef9a4623d0a54b2f6e105faea7d9f05563f169e1d749d674e46983bb195e65`.
- The existing calibration predates provenance manifests, so it is explicitly
  labeled `legacy-runtime-validation-required`; its graph count and all saved
  selection counts are nevertheless reproduced at runtime.
- The recorded holdout declares 55 accounts and 243 training labels. All 55
  resolve, `labeled_mask.sum()` is 243, and none of the holdout accounts is
  labeled in the train propagation.
- The full frozen cache uses raw `directed_edge_rows`, while the API's current
  cache rebuild path adds reverse entries for mutual edges. Deleting the cache
  would therefore change construction semantics instead of reproducing this
  pinned digest.

**Lesson:** Filename recency and matrix dimensions are not compatibility
evidence. The prior builder preferred the active filename and would combine it
positionally with a different graph, producing a broadcast failure today and
potentially silent scientific corruption if dimensions happened to agree.
Account-ID coverage, explicit ordering, score semantics, topology
reconstruction, community schema, calibration identity, scorer identity, and
output reproduction must be one gate. Reproducibility alone does not establish
convergence, taxonomy currency, calibration validity, or topology freshness.

**Assumptions and confidence:**

- String account IDs are stable join keys across these artifacts: `0.99` for
  the frozen bundle.
- Exact reconstruction proves this cache belongs to these node/edge tables:
  `0.99`.
- The exact training-artifact reproduction identifies the frozen TPOT
  derivation: `0.99`.
- The frozen artifact is suitable as a deterministic control: `0.98`.
- The frozen soft memberships are scientifically calibrated current group
  probabilities: `0.20`, because the solver did not converge, the taxonomy is
  legacy, and the threshold sweep used no negatives.
- This proves current social-network freshness: `0.10`; the topology remains a
  frozen control and is not refreshed by the tweet-only Community Archive
  export.

**Fallback:** If any future artifact lacks full ID coverage, changes node
ordering, fails cache reconstruction, contradicts calibration provenance, or
changes the saved selection unexpectedly, fail closed and retain the certified
frozen bundle. Rebuild from a single source snapshot rather than truncating,
broadcasting, or choosing the newest-looking file.

**Next step:** Use this frozen, compatibility-checked bundle as the control arm.
First test solver convergence and taxonomy sensitivity in a new no-clobber
generation. Then design refreshed-topology, out-of-sample discoverability, and
proper probability-calibration experiments as new versioned bundles. Do not
overwrite, rebuild through the current cache path, or silently reinterpret this
control. Atomic generation publication remains required before deployment.

---

## EXP-013: Can the mutable Community Archive export be captured reproducibly?

**Date:** 2026-07-26

**Question:** Is the frozen local corpus stale relative to Community Archive,
and can the current mutable bulk export be identified and acquired without
overwriting the baseline or accepting a mid-transfer source change?

**Hypothesis:** The release-label date is not a sufficient freshness marker.
A HEAD probe should expose a newer object identity, and a versioned,
validator-bound, byte-capped, hash-verified workflow can capture it additively.

**Method:**

1. Read Community Archive's current `llms.txt`, API guide, release metadata,
   storage behavior, and upstream relationship-ingest schema.
2. Issued a HEAD-only probe against the canonical enriched-tweet Parquet object
   and bounded one-row REST freshness probes. No bulk body was downloaded.
3. Compared those dates with the certified local baseline's Snowflake-derived
   tweet cutoff.
4. Wrote behavioral tests first for metadata identity, strict validators,
   streaming caps, no-clobber publication, Parquet ID/schema checks, structural
   manifest invariants, immutable reuse, and probe-only CLI behavior.
5. Implemented ADR 019's snapshot acquisition and verifier modules, keeping
   every new code and test file below 300 lines.
6. Committed the acquisition code at `48f8daa`, downloaded the full object with
   a clean Git state, and ran the schema/coverage inspection.
7. When the strict timestamp-type assumption failed, inspected the actual
   schema and timestamp values, wrote canonical-string and Snowflake-quality
   regressions, then rescanned all 8.3 million rows.

**Result:** **CONFIRMED, with explicit upstream timestamp-quality warnings.**

- The canonical object is newer than both the frozen corpus and its GitHub
  release title. On 2026-07-26 its metadata was:
  - snapshot ID: `20260725T045122Z-4123f74b1a43`
  - `Last-Modified`: `2026-07-25T04:51:22+00:00`
  - size: `901,456,905` bytes
  - ETag: `"b07a2925eca027be751c5814fe3ddffe-54"`
- The release page said “updated 2026-07-13,” while the mutable object was
  modified on 2026-07-25. Release-title freshness is therefore rejected.
- The newest one-row REST tweet probe was tweet `2081177390386950643` at
  `2026-07-26T00:38:50+00:00`; the frozen archive's newest tweet is
  2026-03-22, about 124 days older.
- A bounded exact `all_account` count returned 502,629. An exact enriched-tweet
  count hit the database statement timeout, confirming that exact bulk counts
  should come from Parquet metadata rather than an expensive API count.
- The canonical object passed the 2,000,000,000-byte safety ceiling. Probe-only
  mode issued HEAD and changed no files.
- Attempt 1/3 transferred all 901,456,905 bytes with matching HEAD/GET
  validators and clean producer Git state, then correctly refused to write a
  manifest because live `created_at` is `string`, not Arrow timestamp. The
  incomplete candidate did not replace or activate anything.
- Actual schema inspection showed canonical UTC strings such as
  `2019-06-20 06:22:41+00`. The refined parser accepts that exact validated
  representation while retaining timezone-aware Arrow timestamp support.
- Full candidate scan:
  - 8,318,250 rows and 34,684 distinct account IDs
  - 6,728,898 archive-upload-linked rows and 1,589,352 rows with no upload ID
  - source `created_at` range: 1998-10-28 to 2026-07-25
  - Snowflake-derived eligible range: 2010-11-04 to 2026-07-25
  - 8,261,478 of 8,261,586 eligible IDs agree within one second
  - 108 disagree by more than one second; five source timestamps predate
    Twitter and are demonstrably wrong for their tweet IDs
- Focused regression surface: `23 passed`.
- Attempt 2/3, after commit `7b405bb`, reacquired and manifested the same
  still-current remote identity successfully:
  - local SHA-256:
    `f40645e181976558f2e107528e9eebf90d82038881fdb886d759e973c3fd3667`
  - acquisition code: `7b405bb5b56a83d2764ffb9598ae6279efd14a6f`,
    `git_dirty=false`
  - independent deep verification recomputed the same hash and rescanned all
    Parquet metrics with zero failed checks

**Lesson:** Community Archive provides mutable views, not immutable releases.
Freshness must use live validators and ingestion metadata; evidence must use a
locally recorded SHA-256. The tweet-only export does not establish social-graph
freshness, and a null `archive_upload_id` should be reported as missing linkage,
not asserted to be streamed without a stronger upstream invariant. Source
`created_at` also cannot be treated as infallible: retain it, expose anomaly
counts/samples, and use Snowflake-derived cutoffs for eligible tweet IDs.

**Assumptions and confidence:**

- HTTP validators change when the mutable object changes: `0.98`.
- Strict HEAD/GET validator equality plus byte count and SHA-256 detects an
  unsafe acquisition: `0.99`.
- The Parquet export preserves snowflake IDs as strings: confirmed, `0.99`.
- `created_at` is a timezone-aware Arrow timestamp: rejected. The observed
  contract is a canonical `YYYY-MM-DD HH:MM:SS+00` string; confidence `0.99`
  for this snapshot, while the verifier remains explicit about future drift.

**Fallback:** If the full download changes validators, violates the cap, or
fails schema/manifest checks, leave the frozen baseline active and keep the
candidate directory unmanifested. Re-probe rather than weakening validation.

**Data stored:** Gitignored immutable snapshot at
`data/community_archive/snapshots/20260725T045122Z-4123f74b1a43/`.
The manifest and Parquet file together are the evidence boundary; neither is a
replacement for the frozen control databases or social-topology artifacts.

**Next step:** Bind graph, adjacency, spectral, propagation, calibration, and
selection artifacts to explicit node-order/topology/source identities before
running refreshed network-discoverability or soft-membership comparisons.

---

## EXP-012: Can current main become a reproducible assumption-testing baseline?

**Date:** 2026-07-25

**Question:** Can we recover from the backup-synchronized conflicted checkout
without losing local work, reproduce the code gates, and attach the existing
research data without allowing experiments to mutate the source baseline?

**Hypothesis:** Current `origin/main` contains the intended source, while most
apparent local changes are upstream copies, CRLF/mode drift, and sync-conflict
artifacts. An isolated checkout on the CI toolchain plus an independent
copy-on-write data copy should produce a green code gate and a certifiable,
read-only handoff boundary.

**Method:**

1. Cloned current `origin/main` at `7cfb45fc6cf84115fdd9968064a962751983a55b`
   beside the old checkout and created `codex/community-archive-readiness`.
2. Compared 749 relevant paths after CRLF normalization and separately
   classified tracked content, file-mode changes, symlink flattening,
   non-conflict untracked files, and `sync-conflict` artifacts.
3. Tried the pinned Python dependencies on 3.12, then on CI's Python 3.11.
4. Ran the CI verifier surface before attaching production data, including the
   expected ignored-artifact cluster failure.
5. Created independent APFS copy-on-write files for the two core databases and
   active graph/propagation artifacts. Compared device/inode identity, sizes,
   SHA-256 hashes, schema/count probes, and SQLite `quick_check`.
6. Ran the credential-free Python suite and both frontend suites. The
   graph-explorer suite was deliberately repeated under Node 22 after Node 26's
   experimental unusable `localStorage` global caused a correlated failure.

**Result:** **CONFIRMED, with explicit freshness and runtime warnings.**

- Genuine local-only source/docs/tests: **0**. Of 749 relevant paths, 746 match
  current main after EOL normalization, one historical `AGENTS.md` was
  superseded upstream, and two old-only compatibility/server files were
  intentionally deleted upstream. The old checkout remains untouched.
- Python 3.12 was rejected by evidence: `pandas==2.1.0` fell back to a failing
  source build. Python 3.11.15 installed all 55 requirements and passed the
  backend suite.
- Clean-clone CI had a real contract defect: its granularity-25 cluster step
  required gitignored `data/graph_snapshot.spectral.npz`. Both granularity
  checks now use the committed deterministic medium fixture.
- The working `archive_tweets.db` and `cache.db` have distinct inodes from the
  source, equal byte sizes, matching SHA-256 hashes, zero-byte source WALs, and
  quiescent working WALs, with `quick_check: ok`. Eight required
  artifacts—including graph metadata sidecars—were bound into the certificate.
  Core hashes include:
  - `archive_tweets.db`: `c99b23fc83e1d01e64962124385674324a163ab6ccfee2a36d59cb995b894cd4`
  - `cache.db`: `4e04289dd6d86f7166f8cdfadb03443e6925f6b90b710393fc93a648baf8a552`
  - `graph_snapshot.meta.json`: `2f1692e62a92df497dba49abce1a7e55c3442d526336b7e50c1d4c1cfe321150`
  - `graph_snapshot.spectral.npz`: `05306f30c329bc7461c770228db77b39ac34144b0919e62070567e55e3796b8e`
  - `graph_snapshot.spectral_meta.json`: `854677cbf47d9c98758e0d9247add2c3c09c6bc15e8d7b5e8190d883f9e7018e`
  - `community_propagation.npz`: `1d12f3371205260d7808d1b01c6ecd66cb3cdb7013420cb9a591993d2082a830`
- Baseline volume: 5,553,430 tweets, 17,501,243 likes, 413 fetch-log usernames
  representing 334 distinct account IDs, and 95,057-node spectral metadata.
  Newest archived tweet is 2026-03-22; spectral topology is from 2026-02-26 and
  propagation is from 2026-04-10. This is a valid frozen baseline but not
  current network truth.
- Verification:
  - `make verify-baseline` under Node 22.23.1: pass; under Node 26: expected
    failure on the now-strict runtime contract
  - deep data certificate: `56 passed, 0 failed`
  - Python: `1210 passed, 5 skipped`
  - readiness verifier regressions: `3 passed`
  - public-site: `184 passed`
  - graph-explorer under Node 22.23.1: `729 passed`
  - graph-explorer under host Node 26: `43 failed`, all coupled to the
    experimental unavailable `localStorage`; this falsified the assumption that
    any newer Node runtime is an equivalent local test environment.

**Lesson:** Code recovery and data recovery are separate problems. Normalized
content comparison is necessary before trusting a dirty synchronized checkout;
CI must depend only on tracked fixtures; exact runtime majors matter; and
SQLite source data must be copied independently and certified before
experimentation. Freshness must be derived from Twitter Snowflake IDs—the
archive's textual `created_at` values cannot be ordered with SQL `MAX`.

**Data stored:** Clean checkout at
`Project 2 - Map TPOT - clean-main`; source data remains in the original
checkout; working data is gitignored under the clean checkout's `data/`.
Certification is reproducible with
`scripts/verify_assumption_baseline.py --require-data --source-data-dir PATH --hash-data --deep`.

**Next step:** Treat this as the frozen control dataset. Before drawing claims
about current network discoverability or soft membership, approve and implement
the snapshot-aware Community Archive refresh/manifest design, then rerun the
same evaluations on both frozen and refreshed snapshots.

---

## EXP-006: Does topic-seed ingestion actually hand off into active learning?

**Date:** 2026-04-15
**Question:** The new `fetch_topic_seeds.py` flow claims to (1) ingest advanced-search topic tweets, (2) stage authors in `frontier_ranking`, and (3) let `scripts.active_learning --round 1` fetch those authors next. Do the current helper contracts actually support that?

**Hypothesis:** The original implementation is broken at two contract boundaries: it logs API calls with the wrong function signature and stores raw `advanced_search` payloads without parsing them into the `enriched_tweets` schema. Even if corrected, the current round-1 selector will still suppress those authors because it excludes any account already present in `enriched_tweets`.

**Method:** Performed static review of `scripts/fetch_topic_seeds.py`, `scripts/fetch_tweets_for_account.py`, and `scripts/active_learning.py`. Added focused regression tests that simulate raw `advanced_search` rows, then verified selection behavior for accounts with only `topic_seed` rows versus mixed `topic_seed` + normal fetch rows.

**Result:** **CONFIRMED.** The initial implementation would fail on `log_api_call(...)` and fed `store_tweets(...)` the wrong data shape. After repair:
- raw search hits are parsed through `parse_tweet(...)`,
- search spend is logged through the real enrichment-log contract,
- staged authors land in `frontier_ranking`,
- accounts with only `topic_seed` rows remain eligible for round 1,
- accounts with any non-`topic_seed` enrichment remain suppressed.

**Lesson:** Topic-seed search hits are contextual preload data, not proof that an account has already gone through the account-level fetch/label loop. Dedup has to respect fetch provenance, not just table presence.

**Next step:** Run `scripts/verify_topic_seed_ingestion.py` against the real `archive_tweets.db` after the next topic-search batch to confirm staged-author counts and round-1 eligibility on production data.

---

## EXP-001: Can higher-k NMF split ideological sub-communities?

**Date:** 2026-03-25
**Question:** EA & Forecasting contains mech-interp people, governance people, agent-foundations people, forecasters, and e/acc sympathizers. Can NMF at k=20 or k=24 separate them?

**Hypothesis:** If sub-communities have distinct follow patterns, higher k should produce factors that align with ideological facets.

**Method:** Ran NMF on the 800K-edge follow+like matrix (4,214 accounts × 268K targets) at k=16, k=20, and k=24. Compared factor compositions.

**Result:** **FAILED.** Higher k fragments existing communities into social sub-clusters (who follows whom within the group), NOT ideological facets. The same accounts appear across multiple factors. At k=24, EA doesn't split into mech-interp vs governance — it splits into "@bayeslord's cluster" vs "@torulane's cluster" vs "@strangestloop's cluster."

**Why:** Everyone in alignment follows @ESYudkowsky, @KatjaGrace, @tobyordoxford. The follow graph is identical across ideological facets. Mech-interp people and governance people attend the same conferences, follow the same accounts. They differ in what they WRITE about, not who they FOLLOW.

**Lesson:** Follow-graph NMF finds social clusters. Content analysis finds ideological facets. Don't conflate the two. See CLAUDE.md anti-pattern #9 (Signal Conflation).

**Next step:** Two-level labeling — LLMs tag sub-community facets (theme:mech-interp, theme:ai-governance) from tweet content. Cluster tags to discover sub-community boundaries.

---

## EXP-002: Do bio embeddings separate communities?

**Date:** 2026-03-25
**Question:** If we embed 15K account bios with sentence-transformers, do the embeddings cluster by community?

**Method:** Embedded 15,182 bios with `all-MiniLM-L6-v2` (384-dim). Computed community centroids from 343 seeds. Measured inter-community cosine similarity and intra-community coherence.

**Result:** **PARTIAL.** Some communities clearly separate by bio content:
- TfT-Coordination (0.51-0.69 similarity to others) — very distinct bios
- LLM-Whisperers (0.60-0.76) — technical bios stand apart
- AI-Safety (0.62-0.80) — quantitative/alignment language
- Highbies (0.51-0.78) — distinct voice

But others are nearly identical:
- Core-TPOT ↔ Internet-Intellectuals: 0.86 cosine — same vocabulary
- Contemplative ↔ Quiet-Creatives: 0.84 — overlapping language
- Core-TPOT ↔ Queer-TPOT: 0.83 — shared TPOT voice

Intra-community coherence: 0.38-0.53 (moderate). Tightest: Collective-Intelligence (0.53), TfT-Coordination (0.50). Loosest: Highbies (0.38), Qualia-Research (0.39).

**Lesson:** Bio embeddings are useful as a SECONDARY signal — especially for cold-start accounts without follow data. Not a replacement for graph structure. Best for: confirming community membership, distinguishing TfT/LLM-Whisperers from everyone else, bio-based search.

**Data stored:** `bio_embeddings` table (account_id, 384-dim BLOB, bio_source, created_at).

---

## EXP-003: What signal separates "famous-adjacent" from "TPOT member"?

**Date:** 2026-03-25
**Question:** @elonmusk scores 0.012 with 30 seed neighbors. @eigenrobot scores 0.058 with 92 seed neighbors. The graph can't tell them apart. What can?

**Tested signals:**

| Signal | Method | Result | Verdict |
|--------|--------|--------|---------|
| **Concentration** (seed_nbrs / inbound) | Computed for all placed accounts | @googlecalendar = 0.50, @eigenrobot = 0.66 | **FAILED** — low-degree noise inflates concentration |
| **Spread** (entropy of seed-neighbor vector) | Measured community entropy | @repligate = 0.952, @elonmusk = 0.927 | **FAILED** — TPOT communities overlap too much, everything is high-spread |
| **Score × neighbors composite** | Swept thresholds | @sama (0.56) = TPOT median | **FAILED** — popular tech people have many real TPOT connections |
| **Broadcast ratio** (following/followers) | From profile cache | @elonmusk = 0.000005, @eigenrobot ≈ 0.15 | **WORKS** but need follower counts (fetched for 9.3K accounts) |
| **Reciprocity** (mutuals / inbound from seeds) | Computed for accounts with outbound data | Famous < 0.06, TPOT > 0.17 | **CLEAN SEPARATION** — 3x gap, no overlap in samples |

**Key finding:** Reciprocity is the cleanest separator. Community membership is bidirectional — you're TPOT not because TPOT follows you, but because you follow TPOT back. Famous accounts are one-way: TPOT follows them, they don't follow TPOT.

**Limitation:** Only 14% of placed accounts have outbound edge data. The `check_follow` API endpoint can spot-check reciprocity for the rest (~10 per-pair checks per account).

**Decision:** Accept famous accounts as "adjacent/faint" rather than filter them out. TPOT IS tech-adjacent. Use celebrity concentration filter (follower-count based) for accounts with > 100K followers. Frontend UX fix (hide faint from community pages by default) is better than data-level filtering.

---

## EXP-004: Does NMF v2 (800K edges, k=16, with likes) validate v1 ontology?

**Date:** 2026-03-24 (Session 10c)
**Question:** Does doubling the graph and adding like signals destroy or confirm the 16-community structure?

**Method:** Re-ran NMF (k=16, follow+RT+like, like_weight=0.4) on 800K-edge graph (was 441K in v1). Formal factor alignment via feature overlap (greedy matching, threshold 0.1).

**Result:** **CONFIRMED.** 10/14 v1 factors survived with >= 17.5% overlap. 6 new births at k=16 that map cleanly to communities we already named by hand. 4 disappearances (Crypto/Web3 dissolved, Tools-for-Thought absorbed).

**Key shifts:**
- Core TPOT narrowed to @visakanv-adjacent nucleus
- Sensemaking split into essayist-flavored + builder-flavored
- Internet Essayists + Tech Philosophers merged at one level, split at another
- Crypto/Web3 dissolved — not a real TPOT community

**Lesson:** The 16-community ontology is real structure, not a sparse-data artifact. More data sharpens boundaries rather than blurring them. The community that disappeared (Crypto) was the weakest signal.

**Data:** v2 run saved as `nmf-k16-follow+rt+like-lw0.4-20260324-6f6f95` in `community_run` table. Not yet promoted to primary (v1 still active).

---

## EXP-005: Does tweet labeling agree with NMF graph placement?

**Date:** 2026-03-26
**Question:** If we label tweets for accounts already classified by NMF (graph-based), do the tweet-derived community assignments agree?

**Hypothesis:** If both signals capture the same underlying community structure, they should agree most of the time. Disagreements reveal accounts where social affiliation (follows) diverges from intellectual identity (content).

**Method:** Selected 15 NMF-only seeds (1 per community, weight > 0.3, no prior tweet labels). Ran through the enriched labeling pipeline (3-model LLM ensemble with bio, engagement partners, mention communities, RT source, sub-community facets, content profile). Compared NMF dominant community vs tweet-derived dominant community. 12 of 15 produced enough tags for comparison (3 had no tweets available).

**Result:** **42% exact match, 58% top-3 match.**

| Account | NMF (follows) | Tweets (content) | Verdict |
|---------|--------------|-------------------|---------|
| @NunoSempere | AI-Safety | AI-Safety | MATCH |
| @technoshaman | Collective-Intelligence | Collective-Intelligence | MATCH |
| @realpilleater | Core-TPOT | Core-TPOT | MATCH |
| @v01dpr1mr0s3 | LLM-Whisperers | LLM-Whisperers | MATCH |
| @Lithros | Highbies | Highbies | MATCH |
| @AnniePosting | Queer-TPOT | Highbies | partial (Queer-TPOT in top-3) |
| @taijitu_sees | Quiet-Creatives | Contemplative-Practitioners | partial |
| @rndmcnlly | AI-Creativity | Tech-Intellectuals | DIFFER |
| @sharanvkaur | Internet-Intellectuals | Highbies | DIFFER |
| @archived_videos | Qualia-Research | Highbies | DIFFER |
| @LChoshen | TfT-Coordination | Tech-Intellectuals | DIFFER |
| @petersuber | Tech-Intellectuals | TfT-Coordination | DIFFER |

**Pattern in disagreements:** All 5 "DIFFER" accounts follow one community but write content that fits another. @rndmcnlly follows AI art accounts but tweets about philosophy. @sharanvkaur follows essayists but posts highbie content. @LChoshen and @petersuber are mirror images — each assigned to the other's community by the opposite signal. These are genuine bridges where social scene ≠ intellectual identity.

**The 5 exact matches** are accounts where social and intellectual identity align perfectly — @NunoSempere IS EA through and through, @v01dpr1mr0s3 IS pure LLM Whisperers.

**Lesson:** Neither NMF (follows) nor tweet labeling (content) is "right" alone. They capture different dimensions:
- **Follows** = who you listen to, your social scene, where you hang out
- **Tweets** = what you think about, your intellectual identity, what you amplify

The combination is the truth. An account that follows Qualia researchers but tweets Highbie content is genuinely straddling both worlds. The disagreement IS the signal, not an error to resolve.

**Implication for seed criteria:** Accounts where NMF and tweets agree are the highest-confidence seeds (both signals converge). Accounts where they disagree should be flagged as bridges, not forced into one community. This suggests a confidence metric: `source_agreement = 1 if NMF_top == tweet_top else 0.5 if NMF_top in tweet_top3 else 0`.

**Data:** Cross-validation results for 12 accounts stored in tweet_tags + account_community_bits. NMF assignments in community_membership table (run `nmf-k16-follow+rt+like-lw0.4-20260324-6f6f95`).

---

## EXP-006: Can the local DB support a Phase 1 community-correctness audit without new fetches?

**Date:** 2026-03-26
**Question:** Can we build the first external-audit + human-review benchmark from the current local `archive_tweets.db`, or do we need another fetch pass first?

**Hypothesis:** Core and boundary TPOT accounts should mostly have enough local context already, but famous-adjacent hard negatives will often only exist as `profiles` rows without local tweet text.

**Method:** Queried `profiles`, `tweets`, `enriched_tweets`, `community_account`, and `account_community_gold_*` while assembling the Phase 1 pilot slate. Checked core candidates, boundary candidates, and famous-adjacent hard negatives for local text availability and current community assignments.

**Result:** **PARTIAL.** The local DB is sufficient to ship the pilot substrate now:
- core and boundary items generally have strong local tweet coverage
- current ontology / target-community IDs are all available locally
- `account_community_gold_*` tables already exist and can accept Phase 1 imports

But most hard negatives only have bios and profiles locally:
- `karpathy`, `pmarca`, `lexfridman`, `naval`, `hubermanlab`, `dwarkesh_sp`, and similar accounts are present in `profiles`
- most have `0` local `tweets` and `0` `enriched_tweets`

**Lesson:** The benchmark can start now, but the runner must degrade gracefully for hard negatives. Grok can still be used as an external auditor on bio-only rows, but those rows should be explicitly flagged as `missing_local_posts` so reviewers know the evidence basis is thinner.

**Data stored:** `data/evals/phase1_membership_audit_accounts.json`, `data/evals/phase1_membership_audit_review_sheet.csv`

**Next step:** Run the pilot with the current mixed-context slate, then decide whether Phase 1.1 needs a focused fetch pass for hard negatives before scaling the benchmark.

---

## EXP-007: Can archive-only active learning label what archive accounts talk about without spending Twitter API credits?

**Date:** 2026-03-26
**Question:** Can the active-learning pipeline use local archive tweets plus LLM labeling to infer content identity, while avoiding any new twitterapi.io spend for archive-backed accounts?

**Hypothesis:** Yes, if archive loading adapts to the real `tweets` schema and archive-only mode gates every paid context path, then locally archived tweets can drive LLM labeling with zero new Twitter API spend.

**Method:** Started with the archive-safe handle pool (`/tmp/tpot_archive_active_learning_handles.txt`) and ran `python -m scripts.active_learning --round 1 --archive-only`. First run failed on a schema mismatch (`like_count` assumed, real DB has `favorite_count`). Patched `load_archive_tweets()` to inspect `PRAGMA table_info(tweets)` and normalize real/archive-test schemas. A second smoke run exposed a second leak: reply tweets still called `thread_context` through twitterapi.io. Patched `src/archive/thread_fetcher.get_thread_context(... allow_api=False)` and threaded `allow_paid_api=not archive_only` through `scripts.active_learning.py`. Verified with smoke runs, then ran the only true archive-backed frontier tranche: `uh_cess`, `vyakart`, `vorathep112` with `--archive-only --archive-limit 5`.

**Result:** **Confirmed, with two hidden-paid-path fixes required.**
- `spent` stayed flat at `5.05`
- `reply_fetch_rows` stayed `0`
- `thread_context_cache` stayed flat at `310` after the final fixed runs
- `archive_enriched_rows` grew from `0` to `30`
- `archive_enriched_accounts` grew from `0` to `6`
- `label_sets_active_learning` grew from `1510` to `1527`
- `tweet_tags` LLM bits grew from `4005` to `4045`
- Frontier tranche outcome:
  - `uh_cess` → ambiguous (`LLM-Whisperers`, `highbies`, `Collective-Intelligence`)
  - `vyakart` → ambiguous (`Tech-Intellectuals`, `Collective-Intelligence`, `Core-TPOT`)
  - `vorathep112` → ambiguous (`highbies`, `Quiet-Creatives`, `Relational-Explorers`)

**Lesson:** "Archive-only" was not a single switch; it required closing three separate paid paths: timeline/search fetches, reply-community fetches, and thread-context fetches. Once those were all gated, the pipeline started using tweet content as intended. Also, only 3 not-yet-enriched archive accounts are currently in `frontier_ranking`, so a much larger archive sweep would be a bulk labeling job, not active learning.

**Data stored:** Results persisted in `data/archive_tweets.db` tables `enriched_tweets`, `tweet_label_set`, and `tweet_tags`. Smoke/probe account outcomes include `0xosprey`, `33asr`, `5matthewdub`; active-learning frontier tranche includes `uh_cess`, `vyakart`, `vorathep112`.

**Next step:** Decide whether to (a) keep using uncertainty-ranked archive tranches only, or (b) build a separate bulk archive-labeling queue for the remaining archive-backed accounts that are outside `frontier_ranking`. Also persist per-model label rows so `verify_active_learning` can report real agreement coverage.

---

## EXP-008: Multi-scale tweet clustering vs NMF communities

**Date:** 2026-03-29
**Question:** Does clustering tweet content at multiple scales discover structure that follow-graph NMF misses? Are NMF communities content-coherent, or purely social?

**Hypothesis:** NMF communities are defined by follow patterns (social tribes). Tweet content should capture a different dimension (intellectual interests). If so, AMI between the two should be low, and some NMF communities should scatter across many content clusters.

**Method:**
1. Exported 50K random authored tweets as CSV from archive
2. Embedded with `text-embedding-embeddinggemma-300m` (dim=768) on RTX 3080 via LM Studio
3. 23,808 tweets successfully embedded (model crashed twice at ~12K, used `--resume`)
4. K-means clustering at k=2,4,8,16,32,64 on L2-normalized embeddings
5. Rolled up tweet cluster memberships to 309 accounts
6. Cross-referenced against NMF primary community assignments
7. Computed cross-scale nesting purity and AMI/ARI

**Result:** **CONFIRMED — NMF and tweet content are nearly independent signals.**

Cross-scale nesting purity (tweet clusters):
- k=2→4: 0.928 (strong hierarchical structure)
- k=4→8: 0.841 (real sub-clusters)
- k=8→16: 0.666 (moderate)
- k=16→32: 0.518 (dissolving)
- k=32→64: 0.521 (noise)

NMF→tweet purity (does NMF community map to a tweet cluster?):
- At k=2: avg 0.61 — some signal. Quiet-Creatives 0.96, TfT 0.86.
- At k=8: avg 0.42 — most NMF communities scatter across content clusters.
- At k=16: avg 0.29 — near random. Core-TPOT, highbies, Internet-Intellectuals have no content coherence.

Adjusted Mutual Information (NMF vs tweet clusters):
- Peak AMI at k=16: **0.080** (0=independent, 1=identical)
- Peak ARI at k=16: **0.040**
- Both barely above random — these are genuinely orthogonal dimensions.

Communities with HIGH content coherence (social tribe ≈ intellectual tribe):
- Quiet-Creatives (0.96 at k=2), Queer-TPOT (0.45 at k=16), AI-Safety (0.47 at k=32)

Communities with LOW content coherence (social tribe ≠ intellectual tribe):
- Core-TPOT, highbies, Internet-Intellectuals — scatter everywhere. Defined by social position, not content.

Reverse analysis: tweet clusters are also NMF-diverse. At k=16, cluster_1 (n=43) mixes AI-Creativity, AI-Safety, and Qualia-Research — they write about similar things but are socially distinct.

**Lesson:** Follow graph and tweet content measure orthogonal dimensions of community structure. An account in AI-Safety (by follows) who tweets about contemplative practice is a bridge that only a multi-view system can detect. NMF alone would call them AI-Safety. Content alone would call them Contemplative. The truth is both. This validates the multi-view ensemble prior architecture from ADR 016.

**Data stored:** `data/embed_experiment.db` — tables: tweet_embedding (23,808 rows), tweet_cluster (6 scales), account_cluster_histogram (309 accounts × 6 scales), cluster_run (6 entries). Also tweets table with account_id for rollup joins.

**Next step:** Build multi-view account descriptor combining graph view (NMF/propagation), semantic view (tweet cluster histograms), taste view (like cluster histograms), and interaction view (quote/reply patterns). Fit ensemble prior on gold labels. This becomes the replacement for NMF-as-sole-prior.

---

## EXP-009: View agreement as confidence signal for holdout detection

**Date:** 2026-03-30
**Question:** Does graph-semantic agreement predict TPOT membership better than graph confidence alone? Should we boost confidence when views agree and penalize when they disagree?

**Hypothesis:** Accounts where graph-view and semantic-view agree on community assignment are more reliably classifiable. Agreement = higher confidence, disagreement = lower confidence or bridge account.

**Method:**
1. Used 238 seed accounts with both views (graph NMF weights + k=8 tweet cluster histograms) as training set
2. Trained separate KNN classifiers (k=5, cosine) on graph-only and semantic-only views
3. For 71 holdout TPOT members with both views, computed: graph community prediction, semantic community prediction, and whether they agree
4. Measured detection rate under different confidence strategies
5. Tested combined scoring: graph_conf * agreement_factor

**Result:** **HYPOTHESIS REJECTED — view disagreement is the signal, not agreement.**

82% of holdout TPOT members have views that DISAGREE (graph community ≠ semantic community). Only 18% agree.

Detection rates:
- Graph KNN conf > 0.3: 100% (all 71 detected)
- Propagation score > 0.05: 62% (44/71)
- Views AGREE + graph conf > 0.3: only 18% (13/71)
- Views DISAGREE: 82% (58/71)

The combined scoring (boosting agreement, penalizing disagreement) HURTS — it pushes real TPOT members down the ranking because they're bridges.

Bridge examples from holdout (all confirmed TPOT):
- @visakanv: graph=Internet-Intellectuals, semantic=Contemplative
- @repligate: graph=LLM-Whisperers, semantic=Core-TPOT
- @RomeoStevens76: graph=Contemplative, semantic=AI-Creativity
- @patio11: graph=Tech-Intellectuals, semantic=Collective-Intelligence
- @adityaarpitha: graph=AI-Safety, semantic=Quiet-Creatives

**Lesson:** TPOT is definitionally a cross-cutting meta-community. Its members follow one social tribe but intellectually range across several. View disagreement is a *feature* of TPOT membership, not noise. A "pure" account (follows and tweets about the same thing) is less likely to be TPOT — they'd be in a single-topic community instead.

This reframes the multi-view architecture:
- **Graph view's job**: detect proximity to TPOT seeds (works at 100% recall)
- **Semantic view's job**: characterize *what kind* of TPOT member (intellectual profile), NOT whether they're TPOT
- **View disagreement's job**: identify bridge accounts and multi-community members (the most interesting TPOT members)
- **Confidence**: should NOT penalize disagreement. Instead: graph confidence for TPOT membership, view disagreement for richness/bridge detection.

**Data stored:** Analysis run in-memory on `data/archive_tweets.db` + `data/embed_experiment.db`. No new tables created.

**Next step:** Revise ADR 017 to reflect that views serve different purposes (detection vs characterization vs bridge detection), not a single ensemble vote. The semantic view enriches the account description rather than replacing the graph-based community assignment.

## EXP-010: Can Blob-backed site data bypass gitignored public exports without fighting Vercel deploy limits?

**Date:** 2026-04-09
**Question:** Can we serve fresh `data.json` / `search.json` to the public site by uploading them to Vercel Blob and proxying them through site-owned API routes, instead of relying on gitignored files being present in each deployment?

**Hypothesis:** Uploading the two generated JSON files to fixed public Blob pathnames (`public-site/data.json`, `public-site/search.json`) will solve the stale-data problem cleanly. The only remaining risk is whether Vercel deployment of the new proxy routes is blocked by the project's `rootDirectory` behavior.

**Method:**
1. Inspected the frontend fetch path and confirmed it hardcoded `/data.json` and `/search.json`.
2. Added local code for:
   - shared frontend endpoint constants,
   - `GET /api/data` and `GET /api/search` Blob proxy routes,
   - a `node scripts/upload-public-site-data.mjs` uploader,
   - a human-readable verification script `scripts/verify_public_site_blob.py`.
3. Ran targeted frontend tests, the public-site build, and the Python export test suite.
4. Uploaded local `public/data.json` and `public/search.json` to Vercel Blob with stable pathnames and overwrite enabled.
5. Probed the direct Blob URLs and the public `amiingroup.vercel.app/api/data` and `/api/search` routes.
6. Tried three deployment paths for the new code: direct deploy from `public-site`, deploy from repo root, and local prebuild + prebuilt deploy.

**Result:** **PARTIALLY CONFIRMED.**

What worked:
- Blob upload succeeded.
- Direct Blob URLs serve the current export:
  - `data.json` = `25,637,670` bytes
  - `search.json` = `16,492,299` bytes
- Local code is sound:
  - frontend targeted tests: `43 passed`
  - `npm run build`: passed
  - `pytest tests/test_export_public_site.py -q`: `40 passed`

What failed:
- Public routes are still `404` because the new code is not yet deployed.
- Vercel CLI deploy attempts continue to recurse the configured project root:
  - from `tpot-analyzer/public-site`: path becomes `.../tpot-analyzer/public-site/tpot-analyzer/public-site`
  - from repo root: CLI ignores the existing link and tries to infer a new project from the workspace folder name
  - `vercel build --prod` only worked after locally nulling the ignored `.vercel/project.json.settings.rootDirectory`, but `vercel deploy --prebuilt --prod` still failed against the remote root-directory setting

**Lesson:** Blob is a valid fix for runtime data delivery; the remaining blocker is Vercel deployment mechanics, not the Blob approach or the app code. The project has a deploy-path mismatch between Git-integrated `rootDirectory=tpot-analyzer/public-site` and the Vercel CLI's local deploy resolution.

**Data stored:**
- Blob URLs:
  - `https://afob6mgxltjpsd5j.public.blob.vercel-storage.com/public-site/data.json`
  - `https://afob6mgxltjpsd5j.public.blob.vercel-storage.com/public-site/search.json`
- Verification output:
  - local `tpot-analyzer/scripts/verify_public_site_blob.py`
  - public URL probes against `https://amiingroup.vercel.app`

**Next step:** Ship the new code through the Git-integrated deployment path or reconfigure project-level deploy settings so the proxy routes can go live; once that deploy lands, `/api/data` and `/api/search` should immediately serve the already-uploaded Blob data.

---

## EXP-011: Parameterizing Directed Personalized PageRank for Subfield Resolution

**Date:** 2026-04-15
**Question:** If we parameterize the teleport probability (`alpha`) in Directed Personalized PageRank (instead of a globally hardcoded 0.15), can we force the math engine to isolate hyper-specific intellectual subfields inside dense macro-communities?
**Hypothesis:** Higher teleport probabilities force random walks to be shorter and more highly localized to the immediate seed neighborhoods, reducing the "washing out" smoothing effect across large macro hubs, solving our Subfield mapping boundary problem.
**Method:** 
1. Expose `alpha` parameter in `src/propagation/types.py` through to `compute_ppr`.
2. Ran `scripts.propagate_community_labels` at `alpha=0.15` (baseline wide), `alpha=0.45` (tight), and `alpha=0.85` (hyper-local).
3. Compared shadow-node assignments, "Seeds Absorbed Ratio", unassigned abstain count, and maximum Lift scaling.
**Result:** **HYPOTHESIS CONFIRMED.** Higher alpha creates extreme subfield localization:
- At `alpha=0.15`: 91.4% abstained. Max Lift for "LLM Whisperers" was 68.8x. Walk wandered deeply into generic graph.
- At `alpha=0.45`: 85.7% abstained. Max Lift for "LLM Whisperers" scaled to 388.5x. Tight clustered assignments.
- At `alpha=0.85`: 83.1% abstained. Max Lift for "LLM Whisperers" exploded to 5361.6x. Solved in 6 iterations instead of 55. We isolated purely the mathematically closest connections.
**Lesson:** The teleport probability `alpha` behaves directly like focal length for our clustering lens. By setting `alpha=0.15` for the global graph (identifying macro hubs) and then rerunning at `alpha=0.45` or higher solely inside the filtered subsets (e.g. `AI-Safety` only), we trivially slice granular subfields apart without Goodhart-ing or over-smoothing.
**Data stored:** Output logged to `docs/diagnostics/alpha_0.15.txt`, `_0.45.txt`, and `_0.85.txt`.
**Next step:** Integrate hierarchical propagation into the ingestion pipeline, ensuring AI-Safety / mechanistic interpretability seeds acquired via the topic search API are given high `alpha` localized propagation spaces.

---

## Template for future experiments

```markdown
## EXP-NNN: [Question in one line]

**Date:** YYYY-MM-DD
**Question:** [What are we trying to learn?]
**Hypothesis:** [What we predicted and why]
**Method:** [What we did — specific scripts, data, parameters]
**Result:** [What happened — with numbers]
**Lesson:** [What this means for future work]
**Data stored:** [Where the results live in the DB/filesystem]
**Next step:** [What this enables or blocks]
```
