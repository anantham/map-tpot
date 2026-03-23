# Roadmap: Next Priorities (2026-03-22)

## Status Snapshot

- **20 accounts labeled**, 446 tweets, 5 bits_stable + 3 bits_partial + 12 follow_propagated
- **Phase 2 threshold crossed** (10+ accounts) — engagement propagation now viable
- **Engagement aggregation built** — 408K edges in `account_engagement_agg`
- **Confidence index live** — 5-factor CI validated as stability predictor
- **twitterapi.io tested** — endpoints documented, $1.45 of $20 spent
- **Enrichment pipeline complete** — syndication images, quotes, retweets, links, threads
- **Architecture revised** per code review — canonical table, phased propagation, safety valves

## Priority 1: Unused Data Integration

### 1a. Likes into NMF feature matrix
**Effort:** ~40 LOC in `scripts/cluster_soft.py`
**Signal:** 17.5M likes (24× more than follow graph)
**Cost:** Zero — data already in `likes` table
**Impact:** Biggest single improvement to community detection quality

Steps:
- Build like-target matrix from `likes` table (liker → tweet_author)
- TF-IDF normalize separately
- Concatenate with follows and retweets: `hstack([follows, retweets*0.6, likes*0.4])`
- Re-run NMF with k=14
- Compare new communities against bits-validated accounts

### 1b. Author-liked-reply valence
**Effort:** ~30 LOC query
**Signal:** Signs a large subset of 4.3M replies as "positive"
**Cost:** Zero — join `likes` with `tweets` where liker = parent author
**Impact:** Unlocks replies as a usable signal (currently blocked by unsigned problem)

Steps:
- Query: replies where the parent tweet's author also liked the reply
- Mark these as `positive_reply` in engagement aggregation
- Mutual-follow + reply = second positive signal (also free)
- Remaining unsigned replies → batch through cheap LLM later

### 1c. Parse bookmarks from archive JSON
**Effort:** ~50 LOC extraction script
**Signal:** Very high — deliberate save-for-later is stronger than a like
**Cost:** Zero — data already in archive JSON, never parsed
**Impact:** New signal type for community detection

Steps:
- Find bookmark data in archive JSON structure
- Extract bookmark → tweet_id → tweet_author mappings
- Build bookmark-target matrix (similar to like-target)
- Add as feature to NMF or use for validation

### 1d. Simulacrum-weighted bits
**Effort:** ~10 LOC weight lookup
**Signal:** Makes existing 446 labeled tweets work harder
**Cost:** Zero
**Impact:** L3 (tribe-signaling) tweets weighted 2× for community detection; L4 (meta) weighted 0.5×

Steps:
- In bits rollup computation, multiply by simulacrum weight: `L3×2.0, L1×1.5, L2×1.0, L4×0.5`
- Recompute `account_community_bits` for all 20 accounts
- Compare profiles before/after weighting

## Priority 2: Community Lifecycle

### 2a. Birth operator
**Effort:** ~100 LOC
**Signal:** 7 new-community-signals accumulated (5 "AI Mystics" + 2 "Contemplative-Alignment")
**Trigger:** 3+ accounts showing co-occurring theme pattern not captured by existing communities

Steps:
- `birth_community(name, description, exemplar_accounts)` function
- Creates new community in `community` table with UUID + short_name
- Seeds `community_account` for exemplar accounts
- Logs event in audit trail
- Re-runs propagation with new seed

### 2b. Merge operator
**Effort:** ~80 LOC
**Trigger:** Two communities share >70% thematic overlap across members

Steps:
- `merge_communities(id_a, id_b, new_name)` function
- Reassigns all memberships from both to new community
- Preserves old IDs in audit log
- Re-snapshots branch

### 2c. Split operator
**Effort:** ~100 LOC
**Trigger:** Bimodal theme distribution within one community

Steps:
- `split_community(id, split_criteria)` function
- Creates two child communities
- Assigns members based on which side of the split they fall on
- Preserves parent ID in audit

### 2d. Lifecycle audit log
**Effort:** ~40 LOC schema + inserts

```sql
CREATE TABLE community_lifecycle_event (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL, -- birth, merge, split, death, rename
    community_ids TEXT NOT NULL, -- JSON array of involved community IDs
    description TEXT,
    evidence TEXT, -- JSON: what signals triggered this
    created_at TEXT NOT NULL
);
```

## Priority 3: External Data Fetching

### 3a. Fetch X Lists for known accounts
**Effort:** API integration + list parsing
**Signal:** Very high — lists ARE manual community curation ("AI Safety people", "Dharma Twitter")
**Cost:** ~$0.15/1K calls via twitterapi.io
**Impact:** Free human-created ontology that validates/challenges NMF communities

Steps:
- Use `GET /twitter/list/members` endpoint
- Fetch lists owned by and subscribed to by labeled accounts
- Cross-reference list membership with community assignments
- Use as validation: does "Meditation Twitter" list match Contemplative-Practitioners?

### 3b. Fetch followers for small accounts
**Effort:** Already built, just run for more accounts
**Cost:** $0.015/page, worthwhile for accounts with <5K followers
**Impact:** Structural credibility signal — who endorses them

### 3c. Fetch tweet replies for high-engagement tweets
**Effort:** Already built (`tweet/replies` endpoint)
**Cost:** $0.002/call
**Impact:** Engagement context for labeling, replaces Chrome for most cases

## Priority 4: About Page Rewrite

### 4a. Three-path selector (A/B/C)
- "I know what tpot is, sorta" → discovery/deepening
- "What is going on?!" → onboarding/sampling
- "I want to be inspired by your math" → pipeline walkthrough

### 4b. Path C: 6-stage pipeline visual walkthrough
1. What We Can See — observation, shadow graph, invisible accounts
2. What Signals We Use — signal stack with live/experimental/planned badges
3. How The First Map Is Made — NMF + curation (the 4 design decisions)
4. How The Map Gets Corrected — tweet labeling, bits, ontology refinement
5. How Confidence Spreads — propagation, uncertainty, restraint
6. How We Check Ourselves — recall, gates, failure modes

Visual style: dark tarot/sacred geometry backgrounds for atmosphere, real SVG/HTML/CSS charts for data, community colors fixed across all diagrams.

### 4c. AI-generated visuals (prompts ready)
- Stage 1: cosmic network with bright core → dim shadow → darkness
- Stage 3: matrix decomposition with colored factors
- Stage 4: prism refracting single beam into multiple community colors
- Stage 5: ripples spreading from bright seed nodes

## Priority 5: Canonical Membership Table

### 5a. Build `account_community_canonical`
Single source of truth replacing the current 3-table split:

```sql
CREATE TABLE account_community_canonical (
    account_id TEXT NOT NULL,
    community_id TEXT NOT NULL,
    nmf_weight REAL,
    bits_weight REAL,
    engagement_weight REAL,
    final_weight REAL NOT NULL,
    evidence_level TEXT NOT NULL,
    confidence REAL NOT NULL,
    snapshot_id TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (account_id, community_id)
);
```

### 5b. Migrate consumers
- Export script reads from canonical table
- Labeling context reads from canonical table
- Propagation writes to canonical table
- Deprecate direct reads from `community_account` and `account_community_bits`

## Priority 6: Phase 2 Propagation

### 6a. One-hop from stable seeds
- Only propagate FROM accounts with CI > 0.55 (bits_stable)
- Currently 9 accounts qualify
- One hop only — no transitive chains
- Include none/unknown — don't force thin evidence into communities

### 6b. Calibrate edge weights
- Compare engagement-derived profiles against bits-validated profiles
- Derive weights empirically instead of hand-tuning (follow=1.0, RT=0.7, etc.)
- Need 20+ stable accounts to calibrate (have 9, close)

## Budget

| Resource | Spent | Remaining | Rate |
|----------|-------|-----------|------|
| twitterapi.io | $1.45 | $18.55 | ~370 more accounts at standard |
| OpenRouter (labeling) | ~$5 | — | ~$0.01/tweet |
| Human review time | ~8 hours | — | — |

## Open Questions

1. Should we collapse the two-tier architecture into a single unified prior?
2. When do we trigger the first community birth (AI Mystics / Contemplative-Alignment)?
3. How to handle accounts that genuinely don't fit any community — explicit "none" or forced assignment?
4. Should NMF prior strength depend on observation depth (archive vs shadow)?
5. Is k=14 still right after likes are added to the feature matrix?

---
*Created 2026-03-22 after labeling 20 accounts*
