# ADR 009: Golden Curation Schema and MVP A Active-Learning Loop

- Status: Proposed
- Date: 2026-02-25
- Deciders: Human collaborator + computational peer
- Group: Data pipeline, labeling, evaluation
- Related ADRs: 008-tweet-classification-account-fingerprinting, 007-observation-aware-clustering-membership

## Issue

Phase 4 requires a durable, queryable curation backbone for tweet-level labels and model predictions. The current codebase has account-level tagging and signal feedback, but no normalized tweet-label store that can support:

1. fixed train/dev/test splits,
2. uncertainty queue ranking,
3. Brier-score evaluation against active human labels,
4. reproducible single-reviewer curation.

Without this, active learning remains ad hoc and cannot be validated as a dependable workflow.

## Context

- We are starting with simulacrum classification only (`l1/l2/l3/l4`) for MVP A.
- Reply context is cached in `thread_context_cache`; curation should remain DB-first for context lookup.
- Human selected these constraints:
  - single reviewer,
  - fixed split now,
  - queue score = entropy + model disagreement,
  - acceptance target: simulacrum Brier <= 0.18.

## Decision

Adopt **Option B (normalized probability sets)** on `archive_tweets.db`:

- `curation_split`
- `tweet_label_set` + `tweet_label_prob`
- `model_prediction_set` + `model_prediction_prob`
- `uncertainty_queue`
- `evaluation_run`

Implement API surface under `/api/golden/*`:

- `GET /api/golden/candidates`
- `POST /api/golden/labels`
- `GET /api/golden/queue`
- `POST /api/golden/predictions/run`
- `POST /api/golden/eval/run`
- `GET /api/golden/metrics`

## Rationale

- Normalized rows enable strict validation, SQL-level analytics, and easy evaluation queries.
- Versioned `*_set` records retain curation history while preserving one active label per reviewer/tweet/axis.
- Queue score combines model uncertainty and cross-model disagreement, matching active-learning intent.
- Fixed split assignment is deterministic and stable across reruns.

## Assumptions

1. Simulacrum-only MVP A is enough to validate curation/eval loop quality.
2. Single reviewer is acceptable for initial calibration.
3. Deterministic split assignment is sufficient before introducing stratified sampling.
4. Existing archive DB remains canonical storage for tweet text and thread context.

## Constraints

- This ADR does not yet define multi-reviewer arbitration policies.
- This ADR does not include dashboard UI implementation.
- This ADR does not run external LLM inference itself; prediction ingest endpoint accepts scored distributions.

## Consequences

### Positive

- Human labels, model predictions, and evaluation metrics become persistent and inspectable.
- We can compute and enforce Brier thresholds per run/split.
- Queue ordering is reproducible and reviewable.

### Tradeoffs

- Additional schema complexity vs JSON blob simplicity.
- Endpoint behavior depends on `tweets` availability in `archive_tweets.db`.

### Follow-up

- Add UI curation dashboard bindings to `/api/golden/*`.
- Add optional dual-reviewer adjudication mode.
- Extend schema to functional/topic axes after simulacrum loop stabilizes.
