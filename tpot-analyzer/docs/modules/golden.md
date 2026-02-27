# Golden Dataset — Curation & Active Learning

<!--
Last verified: 2026-02-27
Code hash: a9a572c
Verified by: agent
-->

## Purpose

Provides a human-in-the-loop labeling pipeline for the simulacrum taxonomy. Tweets get deterministic train/dev/test splits, humans label distributions (L1–L4), models predict distributions, Brier scoring evaluates model quality, and an uncertainty queue surfaces high-entropy predictions for human review. The goal: grow a golden dataset that grounds LLM classification in human judgment.

## Design Rationale

### Why this approach?

We need labeled data with known quality to evaluate LLM tweet classifiers. The system must support:
- **Reproducible splits** — same tweet always lands in the same split, across machines and time
- **Soft labels** — tweets aren't just "L3"; they're distributions like `{l1: 0.05, l2: 0.10, l3: 0.80, l4: 0.05}`
- **Active learning** — surface tweets where models are most uncertain, so human labeling time goes where it matters most
- **Multi-model comparison** — disagrement between models is a signal, not noise

### Key decisions

| Decision | Chosen | Alternatives considered | Why |
|----------|--------|------------------------|-----|
| Split assignment | SHA256 hash of tweet_id mod 100 | Random assignment, SQL RANDOM() | Deterministic, reproducible, no state needed |
| Label format | Normalized probability distribution | Single-class label, top-k | Captures ambiguity (most tweets mix levels) |
| Storage | Normalized tables (label_set + label_prob) | JSON blob per label | SQL-level analytics, version control |
| Queue scoring | 0.7 × entropy + 0.3 × disagreement | Entropy only, committee voting | Balances self-uncertainty with peer-disagreement |
| Store pattern | Mixin composition (Base + Predictions + Evals) | Single monolith, separate stores | Each mixin stays under 200 LOC; composed via `GoldenStore` |

### ADR references

- [ADR-009: Golden Curation Schema and Active-Learning Loop](../adr/009-golden-curation-schema-and-active-learning-loop.md)
- [ADR-010: Labeling Dashboard and LLM Evaluation Harness](../adr/010-labeling-dashboard-and-llm-eval-harness.md)

## Public API

### `GoldenStore(db_path: Path)`

Composed class: `BaseGoldenStore + PredictionMixin + EvaluationMixin`. All methods below are on this class.

### `ensure_fixed_splits(axis, assigned_by, force_reassign=False) → dict`

**Purpose:** Assign all tweets to train/dev/test splits deterministically.
**Returns:** `{train: int, dev: int, test: int, total: int}`
**Side effects:** Inserts into `curation_split` table. Caches result in `_split_counts_cache`.
**Performance:** Fast-path — if splits exist (LIMIT 1 check), returns cached counts. Full bootstrap batches 10K inserts.

### `list_candidates(axis, split, status, reviewer, limit) → list`

**Purpose:** Fetch tweets for the labeling UI.
**Returns:** List of candidate dicts with `tweetId`, `text`, `createdAt`, `authorUsername`, `threadContext`, `labelStatus`, `existingLabel`.
**Invariants:** `status="unlabeled"` uses NOT EXISTS subquery (fast for 5.5M tweets). Thread context loaded from `thread_context_cache` if available.

### `upsert_label(tweet_id, axis, reviewer, distribution, note, context_snapshot_json) → int`

**Purpose:** Save or update a human label.
**Returns:** `label_set_id` (integer).
**Side effects:** Validates distribution sums to 1.0 (±0.001). Marks previous label inactive (`is_active=0`). Links via `supersedes_label_set_id`. Updates uncertainty queue status to `"resolved"` if queued.

### `insert_predictions(axis, model_name, model_version, prompt_version, run_id, reviewer, predictions) → dict`

**Purpose:** Batch-insert model predictions and update uncertainty queue.
**Returns:** `{inserted, meanEntropy, meanDisagreement, queueCounts}`.
**Side effects:** For each prediction: validates distribution, computes entropy + disagreement, calculates `queue_score = 0.7*entropy + 0.3*disagreement`. Upserts uncertainty queue (status: `"resolved"` if already labeled, else `"pending"`).

### `list_queue(axis, status, split, limit) → list`

**Purpose:** Fetch uncertainty queue items for review.
**Returns:** Ordered by `queue_score DESC`, enriched with thread context.

### `run_evaluation(axis, model_name, model_version, prompt_version, split, threshold, reviewer, run_id) → dict`

**Purpose:** Compute Brier score for model predictions vs gold labels on a split.
**Returns:** `{runId, brierScore, threshold, passed, sampleSize, splitCounts}`.
**Side effects:** Inserts `evaluation_run` record. Brier score formula: `mean(sum((pred[k] - label[k])^2) / K)` where K=4 (per-label normalized variant).

### `metrics(axis, reviewer) → dict`

**Purpose:** Dashboard summary statistics.
**Returns:** `{totalTweets, splitCounts, labeledCount, predictedCount, queueCounts, latestEvaluation}`.

## Internal Architecture

```
GoldenStore (store.py, 12 LOC)
  ├── BaseGoldenStore (base.py, 323 LOC)
  │     ├── DB connection management (WAL mode, FK enabled)
  │     ├── Schema bootstrap (_init_db)
  │     ├── Split assignment (ensure_fixed_splits)
  │     ├── Candidate queries (list_candidates, _list_unlabeled_fast)
  │     ├── Label upsert with versioning
  │     └── Thread context loading (_load_context → thread_context_cache)
  ├── PredictionMixin (predictions.py, 199 LOC)
  │     ├── Prediction ingestion with entropy/disagreement scoring
  │     ├── Cross-model disagreement computation
  │     └── Uncertainty queue management
  └── EvaluationMixin (evals.py, 145 LOC)
        ├── Brier score evaluation
        └── Metrics aggregation
```

**Math helpers** live in `schema.py` (155 LOC): `split_for_tweet()`, `normalized_entropy()`, `total_variation_distance()`, `validate_distribution()`.

**Constants** in `constants.py` (8 LOC): axis name, label names, split names, queue status enum, scoring weights.

## Dependencies

| Depends on | Why | Import path |
|------------|-----|-------------|
| `archive_tweets.db` (tweets table) | Source of tweet text, metadata | Same DB connection |
| `thread_context_cache` table | Thread context for reply tweets | Populated by `src/archive/thread_fetcher.py` |
| `data/golden/taxonomy.yaml` | Few-shot examples for LLM interpret | Read by `src/api/routes/golden.py` |

## API Routes

7 endpoints registered at `/api/golden/*` via `src/api/routes/golden.py` (421 LOC):

| Method | Path | Handler |
|--------|------|---------|
| GET | `/candidates` | Fetch tweets for labeling |
| POST | `/labels` | Submit human label |
| GET | `/queue` | Uncertainty queue |
| POST | `/predictions/run` | Ingest model predictions |
| POST | `/eval/run` | Run Brier evaluation |
| GET | `/metrics` | Dashboard stats |
| POST | `/interpret` | LLM classify (loopback-only) |

**Security:** `/interpret` is loopback-only by default (`GOLDEN_INTERPRET_ALLOW_REMOTE=1` to override). Model allowlist enforced (`GOLDEN_INTERPRET_ALLOWED_MODELS`).

## ASSERTIONs

- **ASSERTION: Split assignment is deterministic** → [`docs/proofs/split-determinism.md`](../proofs/split-determinism.md) — **valid**

_Candidates for future proofs:_

- **ASSERTION: Brier score formula matches documented specification** — verify against ADR-009
- **ASSERTION: API keys never leave localhost** — OPENROUTER_API_KEY only sent to openrouter.ai

## Known Limitations

- **Single axis only** — `"simulacrum"` is the only supported axis; `_assert_axis()` enforces this
- **Lucidity field is a ghost** — referenced in ADR-010 and interpret endpoint response but not stored in DB schema
- **No multi-reviewer aggregation** — each reviewer's label is independent; no consensus mechanism
- **Thread context may be empty** — if `thread_context_cache` wasn't populated for a tweet, context silently degrades to `[]`
- **Interpret endpoint is synchronous** — blocks on OpenRouter API call; no timeout beyond requests default

## Tech Debt

- **Duplicated `split_for_tweet()`** — exists in both `schema.py` and `scripts/classify_tweets.py` (should import from schema)
- **Brier score formula is non-standard** — uses `sum/K` (per-label normalized) instead of standard `sum`. ADR-009 should document this choice explicitly.
- **No unit tests for schema.py math** — `normalized_entropy`, `total_variation_distance` lack dedicated unit tests (only tested indirectly via integration tests)
- **f-string SQL in some queries** — table/column names interpolated via f-string (safe for controlled inputs, but inconsistent with parameterized style)
- **`_load_context()` silent degradation** — if thread_context_cache table doesn't exist, logs warning and returns empty; could silently reduce label quality

## Implementation Notes (bottom-up)

- **Client-side hash filtering** (2026-02-27): `scripts/classify_tweets.py` duplicates `split_for_tweet()` to filter tweets client-side rather than SQL JOIN with `curation_split` (107s → 4s). Trade-off: slight over-fetch (~7x for 15% splits). Root cause: can't do `ORDER BY RANDOM()` on 5.5M-row JOIN.

- **Mixin composition over inheritance** (2026-02-25): Store split into `base.py` + `predictions.py` + `evals.py` to keep each under 200 LOC. `GoldenStore` is a 12-line composition class. Trade-off: harder to find methods (need to check 3 files), but each file has clear single responsibility.

- **NOT EXISTS over LEFT JOIN** (2026-02-25): `_list_unlabeled_fast()` uses `NOT EXISTS` subquery instead of `LEFT JOIN ... WHERE label IS NULL`. Reason: NOT EXISTS short-circuits per row, much faster on 5.5M tweets when labeled count is small.
