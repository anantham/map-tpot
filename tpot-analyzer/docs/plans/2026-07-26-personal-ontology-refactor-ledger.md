# Personal-Ontology Active Discovery — Refactor and Debt Ledger

- Date: 2026-07-26
- Status: Active companion to the thin-slice implementation plan
- Governing plan:
  `docs/plans/2026-07-26-personal-ontology-active-discovery-implementation.md`

This ledger separates implementation debt from the research sequence. A debt
item is not permission to refactor it alongside behavior changes.

## Keep

- typed directed evidence stores and `TypedGraph` layer separation;
- immutable Community Archive snapshots and graph compatibility manifests;
- Community Gold and tweet-gold stores, supersession, and per-account splits;
- context snapshots, holdout guards, deduplication, and MMR diversity;
- existing local OpenAI-compatible embedding path;
- `frontier_ranking`, `scripts/rank_frontier.py`, and
  `scripts/active_learning.py` as acquisition baselines;
- `enrichment_log`, fetchers, thread cache, and existing budget guards; and
- Community Gold curation and account-deep-dive interfaces.

## Repair

- public About/NMF core score semantics were corrected on 2026-07-28; remaining
  debt is immutable empirical provenance, typed producer views/weight ablations,
  and explicit score semantics in the shared export;
- positive-only account-gold coverage (the 167-row legacy baseline is now
  explicitly `legacy_unbound` and cannot calibrate);
- solver configuration and dangling-mass contracts;
- inference provenance, remote-egress receipts, and model-label separation;
- embedding identity and cache keys: `tweet_embedding` is keyed by `tweet_id`
  and `INSERT OR IGNORE` can silently retain an older model's vector;
- stored bio embeddings that currently lack model identity;
- action-level actual-cost accounting;
- graph-blind semantic descriptor extraction while graph stays a typed task
  view;
- sealed-test access and human anchoring (the Slice 1 storage/API gate is
  synthetic; authenticated actor identity, real roles, quotas, identities, and
  labels remain uncreated; idempotent lost-response replay shipped in A1);
- descriptive handling of every silent exception.

## Retire only after replacements pass

- `uncertainty × sqrt(degree) × (1-none)` as a scientific acquisition policy;
- automatic LLM-consensus promotion into propagation seeds;
- stale mutable endpoint cost rows and hard-coded model price estimates;
- entropy that treats genuine overlap as uncertainty;
- mutable `latest` model identities in scientific records; and
- repeated test-set score display.

## Reuse boundaries

- Extend `src/data/community_gold/` through a versioned migration for
  account-level ontology/task/evidence identity.
- Reuse `graph-explorer/src/communities/GoldLabelPanel.jsx`,
  `GoldLabelHistory.jsx`, `GoldScorecard.jsx`, and
  `AccountDeepDiveLeftColumn.jsx` for dossier review.
- Keep `src/data/golden/` for message-level style annotations.
- Keep `AccountTagStore` and `AccountTagPanel` as ego-scoped working-label
  compatibility surfaces, not gold truth.
- Keep local SQLite for the pilot; shared storage and tenancy require a
  separate ADR.

Slice 1 extended the existing Community Gold adapter rather than creating a
parallel write stack. Its candidate-pool responsibility was extracted before
role-aware work, and every new implementation/verifier module remains below
300 lines.

The narrow 2026-07-28 scientific-contract repair touched existing files above
300 LOC (`About.jsx`, `ClusterView.jsx`, its integration test, and records) without
adding responsibilities. This was an explicit exception to correct misleading
semantics; it does not retire or waive the decomposition debt below.

## Slice 1 residual debt

- The 167 imported legacy judgments are all positive and use mixed numeric,
  `shadow:*`, and `handle:*` identifiers. Persist explicit alias-resolution
  receipts before any legacy row can enter a versioned frame; never infer the
  mapping during migration.
- The modular Community Gold React components are orphaned from the live
  `Communities.jsx` / `AccountDeepDive.jsx` path. Decompose those live
  monoliths and build a blind dossier flow before wiring them; the current
  scorecard reveals model/community information and is unsuitable for sealed
  review.
- The historical global acquisition holdout guard fails open when its table is
  absent. Repair that contract before any paid acquisition slice; Slice 1 only
  seals Community Gold study reads/writes.
- Curator-token authentication now fails closed on Community Gold routes. A
  later UI slice must pass the token without publishing it or weakening the
  private-dossier boundary.
- No current artifact qualifies as `calibrated_probability`. Add a compatible
  calibration-record registry, class-support/coverage report, and untouched
  development/test evaluator before enabling that semantic.
- Recorded role-selection probabilities are nominal quota fractions until a
  pre-allocation universe commitment and independently auditable randomization
  receipt prove the seed was not selected after inspecting identities/outcomes.
- Schema v3 fails closed when an earlier terminal release lacks the new
  complete coverage manifest. Do not translate such a receipt into scientific
  evidence; create an explicit fresh generation lifecycle instead.
- Global accounts cannot currently move to or extend another role registry.
  Design registry supersession/extension as a separate immutable generation
  protocol before adding newly discovered accounts to an existing panel.
- `simplex` prediction rows need an atomic vector/finalization registry that
  proves unique ontology coverage and sum-to-one before they can support a
  compositional probability claim.
- `terminal_access_envelope` binds the stored caller assertion but a shared
  curator token does not authenticate `accessed_by`. Derive the actor from a
  principal before a live release.
- A1 resolved lost-response recovery through exact idempotent replay from one
  access row, including conflict/corruption/concurrency handling. It does not
  authenticate the caller-supplied actor; that remains the live-use debt above.
- `AccountTagStore.list_anchor_polarities(ego)` aggregates every tag key, and
  the membership endpoint/cache has no ontology/task/community target. Scope all
  three by immutable target ID and add cross-target isolation tests; until then
  only synthetic binary inference is supported.
- Evidence-coverage numerators and denominators need compatible source snapshot,
  generation, and as-of metadata. Incompatible generations must produce unknown.

## Tracked decomposition debt

| File | LOC at planning | Primary responsibility debt |
|---|---:|---|
| `graph-explorer/src/Labeling.jsx` | 1,055 | dossier, editor, interpretation, history, and metrics |
| `src/api/routes/golden.py` | 1,021 | validation, security, providers, queries, and routes |
| `public-site/src/About.jsx` | 1,010 | narrative, claims, data tables, and rendering |
| `scripts/label_tweets_ensemble.py` | 686 | prompts, providers, parsing, consensus, persistence |
| `src/shadow/acquisition.py` | 659 | signals, costs, ranking, diversity, and timing |
| `scripts/classify_tweets.py` | 657 | provider, batching, evaluation, and persistence |
| `scripts/cluster_soft.py` | 587 | feature construction, NMF, reporting, persistence |
| `scripts/embed_tweets.py` | 511 | provider, storage, embedding, clustering, CLI |
| `src/propagation/engine.py` | 469 | solver, calibration proxies, abstention, bootstrap |
| `src/propagation/typed_graph.py` | 468 | loading, layer construction, and fixed combination |
| `scripts/active_learning.py` | 415 | round orchestration and legacy policy |
| `graph-explorer/src/ClusterView.integration.test.jsx` | 885 | navigation, membership, local storage, and many unrelated integration fixtures |
| `graph-explorer/src/ClusterView.jsx` | 1,464 | navigation, state, dossier, membership, and rendering |
| `graph-explorer/src/data.js` | 739 | loading, normalization, compatibility, and data joins |
| `src/api/cluster/state.py` | 630 | state loading, cache, membership wiring, and hierarchy |

## Just-in-time order for the pilot

Only these extractions gate their owning implementation slice:

1. tweet-inference service/provider seams from `golden.py` and classification
   scripts before Slice 2;
2. action orchestration/receipts from `active_learning.py` and
   `src/shadow/acquisition.py` before Slice 4; and
3. dossier/editor responsibilities from `Labeling.jsx` before Slice 7.

Every extraction gets a focused behavioral snapshot and separate commit.
Unrelated monoliths remain visible debt and do not block the pilot.

The append-only `WORKLOG.md`, `ROADMAP.md`, and `EXPERIMENT_LOG.md` are all well
beyond 300 lines. Decompose their current views without rewriting historical records.

`docs/PROJECT_STRUCTURE.md`, listed as required reading in `AGENTS.md`, is
missing. Determine whether to recreate it or correct the pointer in a dedicated
docs-hygiene change.

## Parallelization boundaries

Subagents may independently work on:

- schema/evaluation tests;
- inference adapters and replay fixtures;
- action receipts/cost fixtures;
- offline policy baselines;
- UI decomposition; and
- documentation/reproducibility review.

They must not edit the same files concurrently. Integration, schema migrations,
test-release decisions, and paid actions stay with the primary agent.
