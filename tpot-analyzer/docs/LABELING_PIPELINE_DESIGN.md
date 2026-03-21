# Labeling Pipeline Design — Data Model v2 (2026-03-20)

## Core Insight

Each tweet is a sample from an account's epistemic generator at a point in time.
Tweet-level evidence accumulates into account-level community membership profiles.
Communities emerge bottom-up from tag co-occurrence patterns (Approach B).

## Data Model Per Tweet

### 1. Tags (4 levels)

**Domain** (very broad, ~8 options, category='domain'):
- `domain:AI`, `domain:philosophy`, `domain:social`, `domain:technical`
- `domain:politics`, `domain:personal`, `domain:art`, `domain:science`

**Theme** (mid-level, ~20-30, category='thematic'):
- These form communities via co-occurrence clustering
- Examples: `theme:AI-consciousness`, `theme:model-capabilities`, `theme:evals`,
  `theme:AI-safety`, `theme:RLHF-dynamics`, `theme:AI-art`, `theme:forecasting`,
  `theme:theoretical-frameworks`, `theme:community-meta`, `theme:contemplative-tech`,
  `theme:self-transformation`, `theme:model-phenomenology`, `theme:social-commentary`,
  `theme:in-group-culture`, `theme:pedagogy`

**Specific** (unlimited, fine-grained, category=NULL):
- Searchable evidence, unique to tweets
- Examples: `waluigi-effect-cited`, `self-referential-loop`, `RLHF-personality-convergence`

**Posture** (HOW they engage, category='posture'):
- `posture:original-insight`, `posture:signal-boost`, `posture:provocation`
- `posture:pedagogy`, `posture:defense`, `posture:playful-exploration`
- `posture:critique`, `posture:personal-testimony`

### 2. Community Evidence — Bits (category='bits')

**Prior-independent evidence.** Stored as `bits:CommunityName:+N` or `bits:CommunityName:-N`.

```
bits = log2( P(tweet | member) / P(tweet | ~member) )
```

| Bits | Meaning |
|------|---------|
| 0 | Irrelevant — equally likely either way |
| +1 | Weak evidence FOR (2x more likely if member) |
| +2 | Moderate (4x more likely) |
| +3 | Strong (8x more likely) |
| +4 | Very strong / diagnostic (16x more likely) |
| -1 | Weak evidence AGAINST |
| -2 | Moderate AGAINST |

**Why bits, not "strong/medium/weak":**
- Prior-independent: different labelers with different priors can reuse the same evidence
- Additive: 3 tweets with +2 bits each = +6 bits total (probabilities multiply, log-probs add)
- Information-theoretic: directly measures surprise/information gain

### 3. Simulacrum Distribution

L1/L2/L3/L4 probabilities per tweet, stored in `tweet_label_prob`.
- L1 = truth-tracking (genuine belief/observation)
- L2 = persuasion (selling, convincing)
- L3 = tribe-signaling (community membership, in-group)
- L4 = meta/game (self-aware, intentionally channeling)

Account-level simulacrum signature = average across all labeled tweets (weighted by signal).

### 4. New Community Signal (category='new-community')

When a tweet doesn't map to any existing community: `new-community-signal:Name`.
These accumulate and trigger community creation when enough evidence.

### 5. Notes

Free text in `tweet_label_set.note`. Captures:
- Reasoning for tags
- Context not visible in tags (what the image showed, thread structure)
- Why this tweet is/isn't informative

## Storage

All tags stored in `tweet_tags` table:
```sql
tweet_tags (tweet_id, tag, category, added_by, created_at)
```

Categories: `domain`, `thematic`, `posture`, `bits`, `new-community`, NULL (specific)

Simulacrum: `tweet_label_set` + `tweet_label_prob` tables.

## Community Discovery Pipeline

```
Tweets → Human/AI labels (tags, bits, simulacrum, notes)
    ↓
Tags accumulate per account
    ↓
Account × Theme matrix (from thematic tags)
    ↓
Clustering (NMF, spectral, etc.) discovers communities
    ↓
Bits validate: do the clusters match the bits evidence?
    ↓
New community signals trigger splits/births
    ↓
Community map snapshot (versioned via branch system)
```

## Evaluation: K-Fold Cross-Validation

- Label ~40 accounts deeply
- K-fold at ACCOUNT level (not tweet level)
- 5-fold: each run holds out 8 accounts, trains on 32
- Every account tested exactly once
- No fixed split — split is a parameter of evaluation run

## Progress

### @repligate (19/45 tweets labeled)
```
Cumulative bits:
  +29 bits  LLM Whisperers (NMF prior: 0%)
  +18 bits  Qualia Research (NMF prior: 100%)
  +13 bits  AI Safety (NMF prior: 0%)
   +8 bits  Contemplative Practitioners (NMF prior: 0%)
   +4 bits  Emergence & Self-Transformation (NMF prior: 0%)
   +1 bits  highbies (NMF prior: 0%)

Account-level simulacrum signature:
  L1: 40%  L2: 4%  L3: 24%  L4: 29%
  → Primarily truth-tracking + meta-aware, almost zero persuasion
```

New community signals discovered:
- "AI Theorists / Ontologists"
- "Alignment via narrative/archetypes"
- "AI Mystics"

### Next accounts (not in archive, need tweet fetch):
See `docs/LABELING_NEXT_ACCOUNTS.md` — 17 accounts in the
"Local Inference / Open Source AI / Hardware Tinkerers" cluster.

## Data Enrichment: On-Demand + Cache

Many tweets have images, quote tweets, links that are critical for interpretation.
Strategy: JIT enrichment when labeling, cached in SQLite.
Extend `thread_context_cache` pattern.

## NMF Bias (Discovered)

NMF gives concentrated memberships (avg max weight 0.740).
Label propagation gives spread-out memberships (avg max weight 0.503).
Root cause: NMF sparsity constraint. Tweet evidence fixes this.

---
*Updated 2026-03-20 after labeling session with @repligate*
