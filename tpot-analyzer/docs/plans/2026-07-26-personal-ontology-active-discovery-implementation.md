# Personal-Ontology Active Discovery — Thin-Slice Implementation Plan

- Date: 2026-07-26
- Status: Ready for implementation after documentation verification
- Governing decisions: ADR 021 and ADR 022
- Research protocol: `docs/experiments/2026-07-26-budgeted-personal-ontology-local-first-pilot.md`
- Evaluation methods:
  `docs/experiments/2026-07-26-personal-ontology-evaluation-methods.md`

## Outcome

Build an evidence-backed discovery loop that:

- preserves typed public evidence and provenance;
- learns Aditya-specific, independently overlapping group affinities;
- keeps affiliation, competence, participation interest, style, and coverage
  separate;
- uses local models where the benchmark demonstrates acceptable quality;
- decides whether to buy evidence, run inference, ask a human, or abstain;
- proves improvement on sealed labels; and
- stays maintainable through small, reversible commits.

No slice may make a remote call or incur external spend unless its entry
criteria explicitly permit it.

## Operating rules

1. Follow `AGENTS.md`: one behavior per commit, applicable TDD, human verifier,
   experiment log, docs index, descriptive failures, and files below 300 lines.
2. ML/inference uses fixed fixtures, instrumentation, and golden snapshots.
3. Keep compatibility shims until callers and tests migrate.
4. Preserve frozen controls and outputs; publish new generations.
5. Stop on schema guessing, silent failure, leakage, or ambiguous provenance.
6. Before first modifying a file above 300 lines, extract the touched
   responsibility in a separate behavior-preserving mini-slice and commit.

## Slice 0 — Documentation and preregistration

Status: this branch. Deliver the vision, ADRs, pilot/methods, plan/debt ledger,
index/roadmap/worklog, and verifier. Exit only when both docs verifiers pass,
new docs stay below 300 lines, `git diff --check` is clean, and no application,
data, label, model, API, or external state changed.

## Slice 1 — Evaluation integrity and ontology identity

Goal: make the target and holdout impossible to confuse before modeling.

Likely surfaces are `src/data/community_gold/`, its versioned migration,
`src/api/routes/community_gold.py`, existing Community Gold deep-dive panels, and
account-community evaluator tests.

Changes:

- add user/ontology/version identity to community judgments and predictions;
- freeze \(U_0\), training/challenge exclusions, \(U_{\mathrm{eval}}\),
  mask/reveal \(U_{\mathrm{rich}}\), novel-candidate/OOD rules, inclusion
  probabilities, and one mutually exclusive global account-role allocation;
- persist evidence/context hashes and observation timestamps;
- preserve supersession;
- prohibit test reads from training/selection paths;
- add explicit negative/abstain coverage reports;
- label existing frozen outputs by score semantics (`simplex`, `lift`,
  `affinity`, `calibrated_probability`).

Predicted verification:

- cross-group split leakage remains zero;
- training APIs cannot request test labels;
- old records migrate/read without fabricated ontology meaning;
- evaluator refuses positive-only calibration.

Fallback: keep legacy tables read-only behind the one canonical Community Gold
adapter. A migration-shadow table is temporary only, has no independent write
API, and must have explicit parity and retirement criteria.

## Slice 2 — Backend-neutral inference receipts

Goal: reuse existing inference code while removing provider lock-in and missing
provenance.

Create focused `src/inference/` modules for types, clients, OpenAI-compatible
and Ollama adapters, registry, cache, and receipts.

Keep compatibility shims in the existing classify/ensemble/audit scripts and
`src/api/routes/golden.py`.

Before changing those monoliths, extract the tweet-inference service and shared
provider seam in behavior-preserving commits.

Contract:

- validated schema in, typed result or descriptive failure out;
- record resolved model/provider/runtime, prompt/schema/input/context/output
  hashes, usage, timings, and egress fields;
- record digest, quantization, decoding settings, and seed when exposed, with
  explicit unavailable/not-disclosed values otherwise;
- cache key includes every semantic input;
- migrate `tweet_embedding` beyond its tweet-ID-only resume key and add
  model/input/preprocessing/dimensionality identity to tweet and bio embeddings;
- model predictions never masquerade as human labels.

Predicted verification:

- replay provider makes tests network-free;
- Ollama and OpenRouter adapters produce the same internal receipt shape;
- changing model/prompt/context invalidates cache;
- legacy embeddings cannot silently satisfy a new representation identity;
- raw outputs and usage are never discarded.

Fallback:

- route one existing script through the seam first; retain direct callers until
  parity is demonstrated.

## Slice 3 — Local-model benchmark, no production routing

Goal: establish what is accurate and fast enough on this 64 GB machine.

Split message/context packets by account into extraction-development and
untouched routing-evaluation; keep disjoint account routing-development and
untouched routing-evaluation panels. Compare the embedding baseline,
`qwen3-embedding`, and fast/strong local extractors against human gold. Use a
hosted treatment only if authoritative cached receipts already exist.

Exit:

- shortlist, but do not production-route, a local treatment only if the
  zero-spend absolute human-gold thresholds pass;
- pin immutable model digests and context limits;
- require downstream account-panel value/no-harm before routing structured
  features;
- publish negative results if no local treatment beats simpler embeddings.

No download or new hosted call belongs inside this slice. The authorized USD 10
microtrial begins with an at-most-USD 2 hosted reference substage and completes
the one-sided non-inferiority gate before any local production routing.

## Slice 4 — Versioned action costs and receipts

Goal: replace stale estimated rate-card rows with actual action accounting.

Extend existing `enrichment_log`, budget guards, frontier ranking, and
`scripts/active_learning.py`; add only focused `src/acquisition/` action, cost,
receipt, and adapter contracts.

First extract the action orchestrator from the 415-line script and the touched
selection/receipt seam from the acquisition monolith in behavior-preserving
commits.

Record one row per atomic request/page or bounded pagination bundle with quoted
worst-case and actual usage, response/duplicate/usable counts, schema
fingerprint, snapshot, policy version, propensity, latency, and failure.

Predicted verification:

- full-page, partial-page, empty, duplicate, and schema-drift fixtures price
  correctly;
- worst-case preflight prevents reserve breach;
- the documented `followings` response key is exercised by a fixture;
- estimated and actual usage are visibly distinct.

No paid call is required for this slice.

## Slice 5 — Offline mask/reveal simulator

Goal: make acquisition-policy beliefs pay rent before buying data.

Split richly observed accounts into policy-development and untouched
policy-evaluation partitions before masking. Hide one modality at a time:

- profile;
- 20 versus 60 authored tweets;
- outgoing versus incoming edges;
- reply/quote/thread context; and
- contemporaneous event context.

Historical context is reconstructed as of the evidence timestamp. A separate
wrong-time/placebo reveal measures temporal leakage.

Compare random, degree-first, current frontier, entropy-only, topology VOI, and
full multiplex VOI at equal simulated cost.

Exit:

- verify the frozen practical effect is statistically resolvable;
- stop and create a new preregistration/run ID if it is underpowered;
- reject policies that do not beat simple baselines;
- check low-degree, capture-center, source, community, and time strata;
- produce predicted-versus-realized value calibration;
- resample development/evaluation separately in each paired bootstrap, fitting
  only development and scoring only evaluation accounts.

Open the one-use policy-evaluation partition only after the policy is frozen.
It may promote the unchanged policy to live collection; any tuning requires a
fresh partition. The final sealed \(U_{\mathrm{eval}}\) task-head test remains
separate.

## Slice 6 — Remaining decomposition debt, parallel and nonblocking

Run required just-in-time extractions before first touch. Other ledger targets
get independent mini-plans/commits and do not block the pilot.

## Slice 7 — Blind dossier and visible learning flywheel

Goal: make valuable human review feasible and motivating.

Reuse the Community Gold deep-dive, label/history/scorecard panels, and
account-level `in | out | abstain` store. Extend them through the Slice 1
migration; do not create a third labeling stack. `AccountTagStore` remains a
working-label compatibility surface, not gold truth.

Extract only the touched dossier/editor responsibilities from
`graph-explorer/src/Labeling.jsx` before adding behavior.

The dossier contains:

- temporally stratified authored posts;
- parent, quote, and reply context;
- typed graph evidence by direction/modality;
- content/style descriptors and supporting spans;
- contemporaneous context with as-of provenance;
- evidence coverage, missingness, and source links.

Interaction contract:

- hide model/group recommendation until initial judgment;
- support investigation notes, save/resume, `in | out | abstain`, confidence,
  and superseding corrections;
- show prior/posterior and development-set changes after judgment;
- show “no measured improvement” honestly;
- reveal a test generation once, only in the terminal report.

Tests cover observable API/UI behavior, not component internals.

## Slice 8 — USD 10 randomized microtrial

Entry criteria:

- slices 1–5 and 7 green, with every touched-monolith mini-slice green;
- seed/boundary panel and human-time ceiling frozen;
- current archive dedup check complete;
- pricing/schema probe recorded;
- worst-case reserve enforcement verified;
- one explicit USD 10 tranche authorization, with no per-action confirmation;
- user credentials available without logging them.

Run a matched small sample across evidence modalities. Inspect actual response
keys before parsing. Report cost, yield, duplicates, failures, latency, and
incremental development value.

First run the capped hosted-reference substage if Slice 3 lacked authoritative
cached receipts. A failed local non-inferiority result leaves routing unchanged;
it does not fabricate a pass or block unrelated endpoint schema/yield probes.

Retain every deduplicated novel account, probability-audit relevance and yield,
and abstain on outside-support or below-coverage task-head predictions.

Stop if schema drifts, duplicate/empty yield breaches its threshold, or the
microtrial cannot estimate action costs safely.

## Slice 9 — Adaptive paid batches

After one explicit USD 70 tranche authorization, release at most four small
batches without routine human gates. Preserve the exact 20% randomized audit
arm and selection propensities. Recompute the queue and stopping rules after
every batch; pause only on a registered stop or unresolved scope decision.

The USD 20 reserve remains unspent and is never available to the selector,
random audit, test enrichment, or an invalid run. The sealed test opens once
after every continuation decision is final.

Keep implementation debt and parallelization boundaries in the companion
`docs/plans/2026-07-26-personal-ontology-refactor-ledger.md`, not in this
execution sequence.
