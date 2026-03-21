# ADR 014: Account-Community Gold Labels and Held-Out Evaluation Contract

- Status: Proposed
- Date: 2026-03-20
- Deciders: Human collaborator + computational peer
- Group: Data pipeline, community curation, evaluation
- Related ADRs: 006-shared-tagging-and-tpot-membership, 009-golden-curation-schema-and-active-learning-loop,
  011-content-aware-fingerprinting-and-community-visualization, 012-community-seeded-cluster-navigation

## Issue

We need a principled way to answer:

1. does community math beat simpler baselines,
2. can we prove that without label leakage, and
3. where do human account-community judgments live without polluting the canonical map.

Today, `community_account` is the working community map and the future training source.
It is not an evaluation store. The older holdout plan in `docs/archive/HOLDOUT_VALIDATION_PLAN.md`
is directionally useful, but it relies on tags plus external JSON files and does not enforce
split isolation by construction.

## Context

- Communities already exist as a canonical human-edited map in `archive_tweets.db`:
  `community`, `community_account`, branches, snapshots.
- Tweet labeling already has a cleaner pattern:
  deterministic split assignment, immutable label history, and a verifier-first workflow
  (`src/data/golden/`, ADR 009).
- ADR 011 and ADR 012 both assume held-out account labels will eventually gate
  content-aware clustering and community-aware propagation, but the repo does not yet
  have a canonical substrate for those labels.

The main danger is not physical storage location. The danger is semantic reuse:
if the same label surface both seeds the graph math and grades it, evaluation stops
being trustworthy.

## Decision

Adopt a dedicated **account-community gold label subsystem** inside `archive_tweets.db`,
with explicit train/dev/test separation and immutable human judgment history.

### Storage model

Add two tables:

1. `account_community_gold_split`
   - one row per `account_id`
   - deterministic `train/dev/test` split
   - assigned once and reused for every community judgment on that account

2. `account_community_gold_label_set`
   - immutable human judgments over `(account_id, community_id, reviewer)`
   - labels are `in | out | abstain`
   - supersession keeps history without destructive overwrite

### Split rule

The split is assigned **per account**, not per `(account, community)` pair.

Rationale:
- If the same account is train for community A but test for community B, the graph can
  still learn from that account’s local structure and indirectly leak information.
- Per-account splitting is stricter and easier to explain: a held-out account is held
  out everywhere.

Phase-1 split assignment uses deterministic hashing of `account_id`:
- `train`: 70%
- `dev`: 15%
- `test`: 15%

No manual override is part of phase 1. If we later need stratified overrides for tiny
communities, that should be an explicit follow-on decision, not an ad hoc escape hatch.

### Label semantics

- `in`: the reviewer believes the account belongs in the community
- `out`: explicit negative boundary label
- `abstain`: ambiguous / insufficient confidence / should not be forced

`abstain` is a first-class label, not equivalent to “missing data.”

### API surface

Add a dedicated route family under `/api/community-gold/*`:

- `GET /api/community-gold/communities`
- `GET /api/community-gold/labels`
- `POST /api/community-gold/labels`
- `DELETE /api/community-gold/labels`
- `GET /api/community-gold/metrics`

Phase 1 deliberately stops at CRUD + leakage/coverage metrics. It does **not** yet ship
the full baseline-vs-method evaluator. The substrate comes first; scoring plugs into it
next.

## Rationale

- Reusing ADR 009’s deterministic-split + immutable-history pattern gives us a proven
  shape instead of inventing a new workflow.
- Keeping the gold labels in the same SQLite database as communities preserves foreign-key
  integrity to `community(id)` and keeps local workflows simple.
- Separate tables prevent canonical map edits from silently becoming evaluation truth.
- Split isolation per account is stricter than the archived holdout plan and better matches
  the leakage risk of graph-based methods.

## Assumptions

1. Phase 1 should optimize for evaluation integrity, not labeling throughput.
2. Deterministic account hashing is acceptable as the initial split policy.
3. Curators will need explicit negatives and abstentions, not just positive membership.
4. The future evaluator will compare soft/overlapping community methods, so the label
   substrate must support more than hard positives.

## Constraints

- `community_account` remains the canonical working map and may continue to seed graph math.
- `account_community_gold_*` tables are evaluation inputs and must never be auto-consumed
  as training labels without an explicit split filter.
- Phase 1 does not attempt to design the full UI yet.
- Phase 1 does not add manual split editing or active-learning candidate generation.

## Consequences

### Positive

- We can maintain a real held-out account-community gold set without abusing tags or
  community branches.
- Leakage checks become mechanical: one account, one split.
- Future evaluator work has a stable contract for baselines, graph methods, and calibration.
- `abstain` is preserved as evaluation signal instead of being erased as “unlabeled.”

### Tradeoffs

- Deterministic hashing may under-sample tiny communities in dev/test.
- The phase-1 backend is useful but not yet the full product loop; the UI and evaluator
  still need to be built.
- Sharing `archive_tweets.db` keeps local ergonomics simple, but logical separation must
  be respected in every downstream query.

## Follow-up

1. Add evaluator endpoints + `scripts/verify_account_community_evaluator.py` for:
   - Louvain baseline
   - NMF baseline
   - GRF / propagation
   - community-aware spectral blend
2. Add UI for account-community gold labeling with:
   - `IN / OUT / ABSTAIN`
   - confidence
   - notes
   - split badges
3. Decide whether small-community split stratification needs an explicit override path.
4. Mark `docs/archive/HOLDOUT_VALIDATION_PLAN.md` as superseded by this ADR once the
   UI/evaluator phases land.
