# ADR 009: Labeling Dashboard and LLM Evaluation Harness

- Status: Proposed
- Date: 2026-02-25
- Deciders: Human collaborator + computational peer
- Group: Data pipeline, UI/UX, active learning
- Related ADRs: 008-tweet-classification-account-fingerprinting

---

## Issue

The golden dataset backend (`src/data/golden/`) is fully built — schema, label store,
Brier scoring, uncertainty queue, API routes. But two things are missing before the
classification pipeline can run:

1. **A labeling UI** — humans need to read tweets (with thread context) and assign L1/L2/L3
   probability distributions. Doing this in the YAML by hand does not scale.
2. **An LLM classification script** — to fill `model_prediction_set` and trigger Brier
   score evaluation so the active learning loop can close.

Without these, the golden set stays at 6 examples and the uncertainty queue never populates.

---

## Context

### What's already built

| Component | Location | Status |
|---|---|---|
| Archive tweets DB (tweets + likes + thread cache) | `data/archive_tweets.db` | ✓ operational |
| Golden schema + label store | `src/data/golden/` | ✓ complete |
| Train/dev/test split (70/15/15 by tweet_id hash) | `src/data/golden/base.py` | ✓ complete |
| Brier score evaluation | `src/data/golden/evals.py` | ✓ complete |
| Uncertainty queue (entropy + disagreement scoring) | `src/data/golden/schema.py` | ✓ complete |
| `/api/golden/*` routes | `src/api/routes/golden.py` | ✓ complete |
| Taxonomy YAML with 6 labeled examples | `data/golden/taxonomy.yaml` | ✓ partial |
| Simulacrum theory doc | `docs/specs/simulacrum_taxonomy.md` | ✓ complete |

### What's missing

1. **Labeling dashboard** — a UI panel in the graph-explorer for reviewing tweets and
   submitting L1/L2/L3 distributions.
2. **`scripts/classify_tweets.py`** — calls OpenRouter with few-shot prompt from
   `taxonomy.yaml`, ingests results via `/api/golden/predictions/run`, computes Brier score.

### The active learning loop (design goal)

```
taxonomy.yaml (few-shot examples)
    ↓
LLM classifies candidate tweets → model_prediction_set
    ↓
Brier score (eval/run) → did the LLM get the labeled tweets right?
    ↓
Uncertainty queue → GET /api/golden/queue → high-entropy tweets surfaced
    ↓
Human reviews in labeling dashboard → POST /api/golden/labels
    ↓
Golden set grows → taxonomy.yaml updated → prompt improves
    ↓
(repeat)
```

---

## Decision

### 1. Labeling Dashboard: new panel in graph-explorer

A new React component `LabelingPanel.jsx` added to the graph-explorer. Accessible from
the sidebar when a tweet is selected, or as a standalone route `/labeling`.

**Core interaction:**

```
Tweet display:
  - Full tweet text (with thread context if reply)
  - Author handle, date
  - [CLASSIFY THIS] marker on the target tweet in a thread

Labeling form:
  - Four probability sliders: L1 | L2 | L3 | L4
  - Auto-normalize so they sum to 1.0 (slider adjustment rebalances)
  - Notes field (free text — captures reasoning, important for negative examples)
  - Submit button → POST /api/golden/labels

Navigation:
  - "Next unlabeled" button (walks through candidates from GET /api/golden/candidates)
  - "Next uncertain" button (walks through uncertainty queue, highest entropy first)
  - Progress counter (labeled / total in split)
```

**Data source:** `GET /api/golden/candidates?status=unlabeled&split=train&limit=1`
returns the next tweet to label. Thread context is fetched from `thread_context_cache`
table in archive_tweets.db (already cached on first access).

### 2. LLM Classification Script

`scripts/classify_tweets.py` — standalone CLI, no dashboard dependency.

```
Usage:
  python3 scripts/classify_tweets.py \
    --model kimi-k2.5 \
    --prompt-version v1 \
    --split dev \
    --limit 50 \
    [--budget 2.00]

Flow:
  1. Load few-shot examples from data/golden/taxonomy.yaml
  2. Fetch candidate tweets from GET /api/golden/candidates?status=unlabeled
  3. For each tweet (batched 10/call):
     - Build prompt: taxonomy examples + thread context + target tweet
     - Call OpenRouter → parse JSON response → validate distribution sums to 1.0
  4. Ingest via POST /api/golden/predictions/run
  5. Run POST /api/golden/eval/run → print Brier score
  6. Print: which tweets are now in uncertainty queue (entropy > threshold)
```

**Cost controls:**
- `--budget 2.00` hard-stops when estimated spend exceeds $2
- `--limit N` caps number of tweets per run
- `--split dev` targets only dev split for eval runs; `train` for few-shot improvement

### 3. Lucidity Axis Extension to Taxonomy

Extend the taxonomy YAML and the golden label schema to capture the L3-naive vs
L3-lucid distinction identified as the "post-irony gap" (the defining register of TPOT):

```yaml
lucidity:
  description: >
    How aware is the author that they are playing a language game?
    0.0 = no self-awareness (pure egregore channeling)
    1.0 = fully meta-aware, winking at the audience about their own performance
  range: [0.0, 1.0]
  key_test: >
    If you told the author "you're performing a tribal signal right now,"
    would they say "I know, that's the point" (high lucidity) or
    "no I'm not" (low lucidity)?
  TPOT_signature: >
    High L3 + High Lucidity is the most diagnostic TPOT fingerprint.
    The speaker is aware they're channeling the egregore, signals it,
    and that meta-awareness is itself the authentic signal.
```

**Implementation note:** lucidity is a separate axis from simulacrum level. It's not a
fifth level — it's a modifier that applies primarily to L3. Add as a separate float field
in the labeling form and the `tweet_label_set` schema.

---

## Positions Considered

**A. Build dashboard first, script later**
- Pro: better labeling UX from the start
- Con: delays validation of the core assumption; dashboard is wasted if taxonomy fails

**B. Build script first, dashboard later (chosen)**
- Pro: validates core assumption ($0.63 pilot) before investing in UI
- Con: labeling UX is clunky (API calls by hand) until dashboard ships
- Mitigation: the YAML labeling workflow already works for the initial 50 examples

**C. Use an off-the-shelf annotation tool (Argilla, Label Studio)**
- Pro: mature UX, team labeling features
- Con: external dependency, hosting complexity, doesn't integrate with the golden DB schema
  that's already built

**D. Label everything in the YAML by hand**
- Viable for 6–20 examples; does not scale to 200+ or active learning

---

## Assumptions

1. The existing `/api/golden/*` routes are correctly integrated into the Flask server
   (check `src/api/server.py` registration).
2. OpenRouter supports kimi-k2.5 (moonshotai/kimi-k2) and returns structured JSON output.
3. The archive_tweets.db `tweets` table has sufficient content for the 32 accounts
   currently fetched; pilot can proceed before all 316 are done.
4. The lucidity axis is worth adding before validation — this is a risk. If L1/L2/L3 alone
   doesn't cluster, lucidity won't save it. The pilot should test L1/L2/L3 only first.

---

## Consequences

- **Classification script gates everything downstream.** Once it runs, Phase 5 (fingerprints)
  and Phase 6 (community viz) can proceed.
- **The labeling dashboard is the primary human interface** for growing the golden set
  beyond what can be done in conversation. Build it before the classification pilot
  reaches 200+ tweets.
- **Lucidity extension may need its own ADR** if it requires schema changes to the golden
  label tables (currently only L1/L2/L3/L4 stored in `tweet_label_prob`).
- **Next ADRs to write:** 010 (content-aware fingerprinting), 011 (community visualization).
