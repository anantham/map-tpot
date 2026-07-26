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

- membership semantics and probability wording;
- positive-only account-gold coverage;
- solver configuration and dangling-mass contracts;
- inference provenance, remote-egress receipts, and model-label separation;
- embedding identity and cache keys: `tweet_embedding` is keyed by `tweet_id`
  and `INSERT OR IGNORE` can silently retain an older model's vector;
- stored bio embeddings that currently lack model identity;
- action-level actual-cost accounting;
- graph-blind semantic descriptor extraction while graph stays a typed task
  view;
- sealed-test access and human anchoring; and
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

## Just-in-time order for the pilot

Only these extractions gate their owning implementation slice:

1. tweet-inference service/provider seams from `golden.py` and classification
   scripts before Slice 2;
2. action orchestration/receipts from `active_learning.py` and
   `src/shadow/acquisition.py` before Slice 4; and
3. dossier/editor responsibilities from `Labeling.jsx` before Slice 7.

Every extraction gets a focused behavioral snapshot and separate commit.
Unrelated monoliths remain visible debt and do not block the pilot.

The append-only `WORKLOG.md`, `ROADMAP.md`, and `EXPERIMENT_LOG.md` also exceed
300 lines. Decompose their current views without rewriting historical records.

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
