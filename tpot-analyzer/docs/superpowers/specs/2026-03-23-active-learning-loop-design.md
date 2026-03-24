# Active Learning Loop — Spec

**Date:** 2026-03-23
**Status:** Draft (post spec-review fixes applied)
**Budget:** $5 hard cap (Twitter API), LLM labeling cost ~$1-2 additional via OpenRouter

## Problem

Propagation produces 189K node memberships but 94.8% abstain (degree < 2). Holdout recall is 1.6% (2/122). The graph is sparse — most shadow accounts have 1-2 inbound edges and zero outbound. Blind enrichment wastes money. We need to spend API budget on the accounts that would most reduce overall uncertainty.

### Holdout Breakdown

| Category | Count |
|----------|-------|
| Total holdout rows | 389 |
| Have account_id (resolved) | 308 |
| No account_id (unresolved handles) | 81 |
| Resolved + in propagation graph | 207 |
| Are seeds (skip) | 85 |
| **Testable (in graph, not seed)** | **122** |
| Not in graph at all | 101 |

Recall denominator is 122 testable holdout accounts, not 389.

## Solution

An iterative loop: **select high-surprisal accounts → fetch their tweets via API → label tweets with an LLM ensemble → roll up to community membership → insert as seeds → re-propagate → measure improvement → stop when ROI plateaus or budget exhausted.**

## Architecture

```
┌─────────────────────────────────┐
│  1. SELECT (free)               │
│  frontier_ranking by info_value │
│  skip holdout, skip enriched    │
│  (>108 outbound edges)          │
│  skip if ≥20 enriched_tweets    │
└──────────┬──────────────────────┘
           ▼
┌─────────────────────────────────┐
│  2. FETCH (Twitter API, $0.05)  │
│  Strategic sampling via:        │
│  - /user/last_tweets (baseline) │
│  - /tweet/advanced_search       │
│    (hypothesis-driven probes)   │
│  - /user/info (bio + stats)     │
│  Store in enriched_tweets table │
└──────────┬──────────────────────┘
           ▼
┌─────────────────────────────────┐
│  3. CONTEXT ASSEMBLY (free)     │
│  Per tweet, gather:             │
│  - Account bio + graph signal   │
│  - 15 community descriptions    │
│  - Engagement context (archive) │
│  - Similar archive tweets (pre- │
│    computed TF-IDF, local)      │
│  - Other tweets from account    │
└──────────┬──────────────────────┘
           ▼
┌─────────────────────────────────┐
│  4. LABEL (LLM ensemble)        │
│  Per-tweet, same ontology as    │
│  existing labeling system:      │
│  - domain, thematic, specific,  │
│    posture tags                 │
│  - integer bits per community   │
│  - simulacrum distribution      │
│  - new-community signals        │
│  3-model ensemble for consensus │
│  Store per-model + consensus    │
│  in tweet_label_set             │
└──────────┬──────────────────────┘
           ▼
┌─────────────────────────────────┐
│  5. ROLLUP (free)               │
│  tweet bits → account_community │
│  _bits with informativeness     │
│  discount for thin evidence     │
│  (enriched accounts only)       │
└──────────┬──────────────────────┘
           ▼
┌─────────────────────────────────┐
│  6. SEED INSERTION (free)       │
│  INSERT into community_account  │
│  with source='llm_ensemble'     │
│  weight = pct/100 from rollup   │
└──────────┬──────────────────────┘
           ▼
┌─────────────────────────────────┐
│  7. RE-PROPAGATE (free compute) │
│  Harmonic label propagation     │
│  now includes new LLM seeds     │
└──────────┬──────────────────────┘
           ▼
┌─────────────────────────────────┐
│  8. MEASURE (free)              │
│  - Holdout recall (was 1.6%)    │
│  - Mean uncertainty (was 0.391) │
│  - Abstain rate (was 94.8%)     │
│  - New community signals        │
│  - Budget spent / remaining     │
└──────────┬──────────────────────┘
           ▼
┌─────────────────────────────────┐
│  9. HUMAN REVIEW GATE           │
│  - Spot-check labeled tweets    │
│  - Review new community signals │
│  - Approve/reject/correct       │
│  - Decide: continue or stop     │
└─────────────────────────────────┘
```

## Round Structure

### Round 1: Scout ($2.50 — 50 API calls)

**Select:** Top 50 accounts by `info_value` from `frontier_ranking` (non-holdout, <108 outbound edges, <20 rows in `enriched_tweets`, resolvable username).

**Fetch:** 1 call per account — `/user/last_tweets` returns 20 tweets + author bio + follower stats. Store tweets in `enriched_tweets` table, update `resolved_accounts` with bio.

**Label:** Each tweet labeled by 3-model ensemble (see Labeling section). Roll up bits per account.

**Triage:**
- HIGH confidence (top community bits >60% of total) → classified, done
- AMBIGUOUS (no community >40%) → Round 2 queue
- NO SIGNAL (all tweets low-signal/noise) → skip

### Round 2: Deepen ($2.00 — ~40 API calls)

For ambiguous accounts from Round 1. Budget: 40 calls = ~13 accounts at 3 calls each, or ~20 accounts at 2 calls each. The orchestrator allocates dynamically based on remaining budget.

**Strategic search** (1-3 calls per account):
- `/tweet/advanced_search?query=from:username "keyword"` — probe for community-specific vocabulary based on graph signal (e.g., if graph says Contemplative, search for "meditation OR jhana OR IFS")
- `/tweet/advanced_search?query=from:username filter:replies` — who they talk to
- `/user/followings` (1 page) — following overlap with classified accounts

**Re-label** with enriched context and re-roll bits.

### Round 3: Measure ($0 — compute only)

1. Roll up bits for all newly labeled accounts
2. Insert into `community_account` with `source = 'llm_ensemble'`, `weight = pct / 100`
3. Re-propagate full graph (420K edges)
4. Measure: holdout recall, mean uncertainty, abstain rate, new community signals
5. Present results + spot-check sample to human

**Remaining ~$0.50** reserved for targeted follow-ups if human review requests them.

### Budget Hard Stop

Before every API call, the orchestrator checks `SUM(estimated_cost) FROM enrichment_log`. If total ≥ $5.00, stop immediately. No exceptions.

### Stopping Conditions

Stop the loop when ANY of:
- Budget exhausted ($5)
- Holdout recall plateaus (< 1% improvement after a round)
- Mean uncertainty plateaus (< 0.01 decrease after a round)
- Human says stop

## Labeling System

### Ontology

Identical to existing `docs/LABELING_MODEL_SPEC.md`. Per-tweet output:

| Dimension | Format | DB Table |
|-----------|--------|----------|
| Domain tags | `domain:AI`, `domain:philosophy` | `tweet_tags` (category='domain') |
| Thematic tags | `theme:model-interiority` | `tweet_tags` (category='thematic') |
| Specific tags | bare string | `tweet_tags` (category=NULL) |
| Posture tags | `posture:original-insight` | `tweet_tags` (category='posture') |
| Community bits | `bits:LLM-Whisperers:+3` | `tweet_tags` (category='bits') |
| Simulacrum | `{"l1": 0.4, "l2": 0.1, "l3": 0.35, "l4": 0.15}` | `tweet_label_prob` |
| Notes | free text | `tweet_label_set.note` |
| New community | `new-community-signal:AI-Mystics` | `tweet_tags` (category='new-community') |

### Integer Bits (matching established ontology)

Bits are integers, matching the existing LABELING_MODEL_SPEC scale: +1 (weak, 2x), +2 (moderate, 4x), +3 (strong, 8x), +4 (diagnostic, 16x), -1 (weak against), -2 (moderate against).

The thin-evidence concern (20 tweets vs 1000+ archive) is handled at **rollup time** via an informativeness discount, not by making bits fractional.

### Informativeness Discount (enriched accounts only)

When rolling up bits to account-level membership for API-fetched accounts, weight by evidence depth:

```
account_bits[community] = sum(tweet_bits) × min(1.0, sqrt(N_tweets / 50))
```

- 50+ tweets (full archive): no discount (factor = 1.0)
- 20 tweets (1 API page): 0.63x discount
- 40 tweets (2 pages): 0.89x discount

This discount applies ONLY to accounts whose tweets come from `enriched_tweets`. Archive accounts whose tweets are in the `tweets` table get no discount — the existing `rollup_bits.py` handles them unchanged.

### Community Short Names (from DB, not stale spec)

The LLM prompt MUST use the actual DB short_names, pulled dynamically via `SELECT short_name FROM community`. Current set (15):

```
AI-Creativity, AI-Safety, Collective-Intelligence, Contemplative-Practitioners,
Core-TPOT, Internet-Intellectuals, LLM-Whisperers, NYC-Institution-Builders,
Qualia-Research, Queer-TPOT, Quiet-Creatives, Relational-Explorers,
Tech-Intellectuals, TfT-Coordination, highbies
```

**Note:** The LABELING_MODEL_SPEC lists 14 stale names (Builders, Feline-Poetics, Ethereum-Builders, Emergence-Self-Transformation) that do NOT exist in the DB. The active learning pipeline ignores those and uses only what the DB returns. The LABELING_MODEL_SPEC should be updated separately.

### LLM Ensemble

**Models (via OpenRouter):**
1. `x-ai/grok-4.1-fast` — primary labeler, native Twitter knowledge
2. `deepseek/deepseek-v3.2` — second perspective, more conservative
3. `google/gemini-3.1-flash-lite-preview` — third perspective

**Validated:** All three produce bits reliably in free-text JSON mode. MiniMax-m2.5 failed (no JSON output) and is excluded.

**Consensus strategy:** For each tweet, all 3 models label independently. Final bits = median of the three values per community. If 2/3 models assign bits to a community and 1 doesn't, use the lower of the two values. If only 1/3 assigns, discard (insufficient consensus).

**Known limitation:** The median/min consensus strategy systematically underestimates bits when models disagree on magnitude. This is conservative by design — acceptable for an experiment. If it causes too many accounts to stay ambiguous, the consensus can be loosened in later rounds.

**NOT using OpenRouter `json_schema` structured outputs.** Grok collapses tags to empty arrays under schema enforcement. Instead: free-text JSON in prompt → parse on our side → validate with assertions.

### Storing Per-Model Labels

Each model's output is stored as a separate `tweet_label_set` row:

| `reviewer` value | Purpose |
|-----------------|---------|
| `grok-4.1-fast` | Model 1 raw output |
| `deepseek-v3.2` | Model 2 raw output |
| `gemini-3.1-flash-lite` | Model 3 raw output |
| `llm_ensemble_consensus` | Merged consensus (used by rollup) |

The `axis` column = `'active_learning'` to distinguish from manual labeling (`axis = 'simulacrum'`).

Per-model rows preserve debugging evidence. The consensus row is what rollup reads.

### Context Assembly Per Tweet

```python
context = {
    # Account-level (shared across all tweets for same account)
    "bio": "from /user/last_tweets author field or /user/info",
    "graph_signal": "seeds who follow this account, by community",
    "following_overlap": "which classified accounts they follow (if fetched)",
    "other_tweets": "brief digest of account's other fetched tweets",

    # Tweet-level
    "tweet_text": "the tweet content",
    "engagement_stats": "likes, RTs, views",
    "mentions": "who they @mention in this tweet",
    "engagement_context": "which classified accounts liked/RT'd (from archive if available)",
    "similar_archive_tweets": "precomputed TF-IDF cosine matches from archive (cached on disk)",

    # Reference (shared across all tweets)
    "community_descriptions": "15 communities with short descriptions (from DB)",
    "community_short_names": "for bits tag format (from DB)",
}
```

**Engagement context sources:**
- **Archive accounts:** Check `likes` and `retweets` tables for classified accounts who engaged with this tweet. Free.
- **Non-archive accounts:** No engagement data in DB. Can optionally spend 1 API call on `/tweet/retweeters` for high-value tweets, but not in Round 1.

### LLM Prompt Structure

```
SYSTEM: You are a TPOT tweet labeling agent. [community descriptions, bits scale, tag format rules, short names]

USER:
  Account: @handle | Bio: ... | Followers: N
  Graph: [community]: N seeds | ...
  Other tweets: "..." (N likes); "..." (N likes)

  TWEET TO LABEL:
  Text: "..."
  Engagement: N likes, N RT, N views
  Mentions: @x, @y
  Engagement context: Liked by @a (Community1), @b (Community2)...
  Similar archive tweets: "..." (Community1, +3 bits); "..." (Community2, +2 bits)

  Assign bits and tags. Return JSON.
```

**Output format (free-text JSON, parsed + validated on our side):**
```json
{
  "bits": ["bits:LLM-Whisperers:+3", "bits:Core-TPOT:+1"],
  "themes": ["theme:model-interiority", "theme:simulator-thesis"],
  "domains": ["domain:AI", "domain:philosophy"],
  "postures": ["posture:original-insight"],
  "simulacrum": {"l1": 0.35, "l2": 0.25, "l3": 0.3, "l4": 0.1},
  "note": "Reasoning for assignments...",
  "signal_strength": "high",
  "new_community_signals": []
}
```

## Strategic Sampling via Advanced Search

Instead of only `/user/last_tweets` (biased toward recent + viral), use `/tweet/advanced_search` for hypothesis-driven probing:

| Strategy | Query template | When to use |
|----------|---------------|-------------|
| **Baseline** | `/user/last_tweets?userName=X` | Always (Round 1) |
| **Community probe** | `from:X "meditation" OR "jhana"` | Graph says Contemplative |
| **AI probe** | `from:X "model" OR "LLM" OR "Claude" OR "GPT"` | Graph says LLM Whisperers |
| **Reply behavior** | `from:X filter:replies` | Ambiguous after Round 1 |
| **Time diversity** | `from:X since:2023-01-01 until:2024-01-01` | Recent tweets are unrepresentative |
| **Interaction** | `from:X to:known_seed` | Check who they talk to |

Cost: $0.05 per search query, returns up to 20 tweets. 3 targeted searches ($0.15) can give more signal than 5 pages of timeline ($0.25).

## New Tables

### `enriched_tweets`

Tweets fetched via Twitter API for non-archive accounts.

```sql
CREATE TABLE IF NOT EXISTS enriched_tweets (
    tweet_id     TEXT PRIMARY KEY,
    account_id   TEXT NOT NULL,
    username     TEXT NOT NULL,
    text         TEXT NOT NULL,
    like_count   INTEGER DEFAULT 0,
    retweet_count INTEGER DEFAULT 0,
    reply_count  INTEGER DEFAULT 0,
    view_count   INTEGER DEFAULT 0,
    created_at   TEXT,
    lang         TEXT,
    is_reply     INTEGER DEFAULT 0,
    in_reply_to_user TEXT,
    has_media    INTEGER DEFAULT 0,
    mentions_json TEXT,         -- JSON array of mentioned usernames
    fetch_source TEXT NOT NULL, -- 'last_tweets', 'advanced_search', 'timeline'
    fetch_query  TEXT,          -- the search query if advanced_search
    fetched_at   TEXT NOT NULL
);
CREATE INDEX idx_enriched_tweets_account ON enriched_tweets(account_id);
CREATE INDEX idx_enriched_tweets_source ON enriched_tweets(fetch_source);
```

### `enrichment_log`

Tracks API spend and what was fetched per account.

```sql
CREATE TABLE IF NOT EXISTS enrichment_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   TEXT NOT NULL,
    username     TEXT NOT NULL,
    round        INTEGER NOT NULL,   -- 1, 2, 3...
    action       TEXT NOT NULL,       -- 'last_tweets', 'advanced_search', 'user_info', 'followings'
    query        TEXT,                -- search query if applicable
    api_calls    INTEGER DEFAULT 1,
    tweets_fetched INTEGER DEFAULT 0,
    estimated_cost REAL DEFAULT 0.05,
    created_at   TEXT NOT NULL
);
```

No new tables for labeling output — reuse existing `tweet_tags`, `tweet_label_set`, `tweet_label_prob`, `account_community_bits`.

## Rollup Integration (P0 fix)

The existing `rollup_bits.py` JOINs `tweet_tags` to the `tweets` table to resolve `account_id`. Enriched tweets live in `enriched_tweets`, not `tweets`. Two changes needed:

### 1. Modify `rollup_bits.py` to UNION both tweet sources

```sql
SELECT t.account_id, tt.tweet_id, tt.tag
FROM tweet_tags tt
JOIN tweets t ON t.tweet_id = tt.tweet_id
WHERE tt.category = 'bits'
UNION ALL
SELECT e.account_id, tt.tweet_id, tt.tag
FROM tweet_tags tt
JOIN enriched_tweets e ON tt.tweet_id = e.tweet_id
WHERE tt.category = 'bits'
```

### 2. Make DELETE scoped, not global

Currently `rollup_bits.py` does `DELETE FROM account_community_bits` on every run (line 297). Change to scoped delete: only delete rows for accounts being re-rolled in this run.

```sql
DELETE FROM account_community_bits WHERE account_id IN (?)
```

### 3. Apply informativeness discount for enriched accounts

After computing raw bits totals, check if the account's tweets came from `enriched_tweets`. If so, apply the `sqrt(N_tweets / 50)` discount before writing to `account_community_bits`.

## Seed Insertion (P0 fix)

After rollup, newly classified accounts must be inserted into `community_account` so propagation can use them as seeds.

```python
# For each newly classified account:
for community_id, pct in account_bits.items():
    weight = pct / 100.0  # convert percentage to 0-1 weight
    conn.execute("""
        INSERT OR REPLACE INTO community_account
        (community_id, account_id, weight, source, updated_at)
        VALUES (?, ?, ?, 'llm_ensemble', ?)
    """, (community_id, account_id, weight, now))
```

The `source = 'llm_ensemble'` distinguishes these from NMF seeds (`source = 'nmf'`).

**Propagation reads from `community_account` unchanged** — it loads all rows regardless of source. The new LLM seeds participate in the next propagation run automatically.

**Optionally** add rows to `seed_eligibility` with concentration derived from the bits distribution, so the concentration-weighted boundary conditions apply to these seeds too.

## Assertions (Fail Loud)

Every step validates and fails with descriptive errors:

### Budget Assertion (before every API call)
```python
spent = conn.execute("SELECT COALESCE(SUM(estimated_cost), 0) FROM enrichment_log").fetchone()[0]
assert spent < 5.00, f"Budget exhausted: ${spent:.2f} spent of $5.00 cap"
```

### Fetch Assertions
- API response status == "success"
- Tweet count > 0 for each account
- No duplicate tweet_ids in enriched_tweets
- Account not in holdout

### Label Assertions
- JSON parses successfully
- `bits` array is non-empty for signal_strength != "noise"
- Every bits tag matches regex: `^bits:[A-Za-z-]+:[+-]\d+$`
- Every community short_name in bits is in the valid set (loaded from DB at startup)
- Simulacrum values sum to 0.95-1.05
- `signal_strength` is one of: high, medium, low, noise
- All 3 models returned valid output (log warnings if <3, fail if 0)

### Rollup Assertions
- At least 5 tweets labeled per account before rollup
- Total bits > 0 for at least 1 community
- Informativeness discount applied for enriched accounts
- Discount NOT applied for archive accounts

### Seed Insertion Assertions
- Account not already in `community_account` with `source = 'nmf'` (don't overwrite NMF seeds)
- Weight is between 0.0 and 1.0
- At least 1 community has weight > 0.05

### Propagation Assertions
- New seeds visible in `community_account` before propagation starts
- Propagation converges (all classes)
- Metrics computed and logged

## Ontology Evolution

The labeling system can detect community births, merges, splits, deaths, and renames:

| Signal | Detection | Action |
|--------|-----------|--------|
| **Birth** | `new-community-signal` tags accumulate (3+ across 3+ accounts) | Surface to human with evidence |
| **Split** | Bimodal thematic tags within one community | Surface to human |
| **Merge** | Two communities get identical bits from same accounts | Surface to human |
| **Rename** | Accumulated evidence contradicts current name | Surface to human |

All ontology changes require human approval. The LLM proposes, the human decides.

## Dedup Guards

Two separate dedup mechanisms for two different enrichment types:

### Following enrichment (`fetch_following_for_frontier.py`)
Skip accounts with ≥108 outbound edges in `account_following`. Empirically: the distribution is bimodal (0 or 300+), so 108 cleanly separates enriched from unenriched.

### Tweet enrichment (active learning pipeline)
Skip accounts that already have ≥20 rows in `enriched_tweets`. This prevents re-fetching tweets for accounts already labeled in a previous round.

## Cross-Validation Discipline

- 389 holdout accounts in `tpot_directory_holdout` — NEVER enrich, only measure recall against
- 122 testable holdout accounts (have account_id, in graph, not seeds) — the recall denominator
- New enriched accounts get `source = 'llm_ensemble'` in `community_account`
- Holdout recall is measured AFTER re-propagation, never during

## TF-IDF Similar Tweets (Precompute)

Building TF-IDF over 5.5M tweets is expensive (~minutes, ~GB RAM). Precompute once and cache:

```python
# Run once, save to disk:
# scripts/build_tfidf_cache.py → data/tfidf_matrix.npz + data/tfidf_vocab.json
# Active learning loads the cached matrix and does cosine similarity per tweet
```

Not required for Round 1 (can skip similar tweets in first pass). Build before Round 2 if needed.

## Success Criteria

| Metric | Baseline | Target |
|--------|----------|--------|
| Holdout recall | 1.6% (2/122) | >10% |
| Abstain rate | 94.8% | <90% |
| Mean uncertainty (non-abstain) | 0.391 | <0.35 |
| Budget spent | $0 | ≤$5 |
| Accounts classified | 0 non-seed | 30+ |

## Experimental Protocol

This is an experiment. The first run validates the pipeline end-to-end:
1. Does fetching work reliably?
2. Does the LLM ensemble produce consistent, reasonable bits?
3. Does rollup produce sensible account profiles?
4. Does adding these as seeds improve propagation metrics?
5. What is the actual $/account cost and signal quality?

After Round 1, human reviews results and decides whether to continue to Round 2 or adjust the approach.

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `scripts/active_learning.py` | Create | Main orchestrator: select → fetch → label → rollup → seed insert → propagate → measure |
| `scripts/fetch_tweets_for_account.py` | Create | Twitter API fetch: last_tweets + advanced_search + user_info |
| `scripts/label_tweets_ensemble.py` | Create | 3-model ensemble labeling via OpenRouter |
| `scripts/rollup_bits.py` | Modify | UNION enriched_tweets into query, scoped DELETE, informativeness discount for enriched accounts |
| `scripts/fetch_following_for_frontier.py` | Already modified | Dedup guard (108 threshold) |
| `scripts/propagate_community_labels.py` | No change | Reads from community_account, works as-is with new llm_ensemble seeds |
| `scripts/classify_bands.py` | No change | Reads from propagation npz, works as-is |
| `scripts/export_public_site.py` | No change | Reads from npz + bands, works as-is |
| `docs/TWITTERAPI_ENDPOINTS.md` | Already updated | API endpoint reference |
| `docs/LABELING_MODEL_SPEC.md` | Needs update (separate) | Stale community short_names list |

## Dependencies

- `httpx` (already installed) — Twitter API + OpenRouter calls
- `scikit-learn` (already installed) — TF-IDF for similar archive tweets
- No new packages required

## Review Fixes Applied

Fixes from spec review (2026-03-23):

- **P0-1:** Added rollup integration section — UNION `enriched_tweets`, scoped DELETE, informativeness discount
- **P0-2:** Added explicit seed insertion step with `source = 'llm_ensemble'`, weight conversion, assertions
- **P0-3:** Changed fractional bits to integer bits (matches established ontology), discount at rollup level
- **P1-1:** Community short_names loaded from DB dynamically, stale LABELING_MODEL_SPEC list noted
- **P1-2:** Round 2 budget math made explicit (40 calls = 13-20 accounts depending on calls/account)
- **P1-3:** Informativeness discount explicitly scoped to enriched accounts only
- **P1-4:** Holdout breakdown table added (389 → 122 testable), recall denominator clarified
- **P1-5:** Per-model label storage specified (3 per-model rows + 1 consensus row per tweet)
- **P2-1:** Indexes added to enriched_tweets schema
- **P2-2:** Dedup guards separated (following vs tweets)
- **P2-3:** Budget hard stop assertion added before every API call
- **P2-4:** TF-IDF precompute noted, optional for Round 1
- **P2-6:** Consensus underestimation acknowledged as acceptable for experiment
