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
  - queue score = `0.7 × entropy + 0.3 × disagreement`,
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
- Queue score formula is `0.7 × entropy + 0.3 × disagreement` (constants `QUEUE_ENTROPY_WEIGHT`/`QUEUE_DISAGREEMENT_WEIGHT` in `src/data/golden/constants.py`). Entropy is weighted higher because self-uncertainty is a stronger signal for labeling value than cross-model disagreement; 70/30 was chosen empirically as a sensible prior pending calibration data.
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

### Brier score formula and threshold

The implementation (`evals.py:63`) uses a **per-label normalized variant**:

```
BS_norm = mean_i( mean_k (pred_k − label_k)² )  =  BS_standard / K
```

This differs from the standard Brier score (`mean_i( sum_k (pred_k − label_k)² )`).

**Why this choice:** K-invariance — if the system later extends to axes with a different
number of classes (topic, functional), normalized scores remain comparable across axes.
The standard formula scores a 4-class problem differently than a 6-class one in absolute
terms.

**Tradeoff:** The 0.18 threshold was set intuitively and is not calibrated to this
formula. Under the normalized variant with K=4, a uniform random predictor scores
~0.1875 on one-hot labels — so ≤ 0.18 is barely above random chance for one-hot labels.
For soft labels (which this system uses), the random baseline is lower, so 0.18 may
represent genuinely decent performance in practice, but this is unverified.

**Follow-up constraint:** Before treating the 0.18 threshold as a meaningful acceptance
criterion, compute the marginal-distribution baseline on the actual labeled set:

```python
# Compute once enough labels exist (≥ 100 labeled tweets)
# baseline_score = BS_norm of always predicting the marginal label distribution
# meaningful_threshold = baseline_score - 0.05  (5 points better than naive)
```

Until then, the threshold is a placeholder. Treat Brier scores from `run_evaluation()`
as relative indicators (is the model improving across runs?) rather than absolute pass/fail.

### Follow-up

- Add UI curation dashboard bindings to `/api/golden/*`.
- Add optional dual-reviewer adjudication mode.
- Extend schema to functional/topic axes after simulacrum loop stabilizes.
- **Recalibrate the ≤ 0.18 threshold** once ≥ 100 labeled tweets exist (see Brier score note above).
