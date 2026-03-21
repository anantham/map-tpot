# Handover: 2026-03-20 (Session 2)

## Session Summary

Massive labeling session. Developed the full data model for tweet-level community evidence through hands-on labeling of @repligate's tweets. Discovered that NMF massively under-represents community membership (repligate = 100% Qualia Research per NMF, but tweet evidence shows 39.7% LLM Whisperers, 24.7% Qualia, 17.8% AI Safety). Built an interactive HTML labeling queue. Identified 3 potential new communities. User decided to stay within TPOT graph (not expand to external builder cluster) and wants to build the community evolution layer next.

## Commits This Session
- `0d2cf78` feat(labeling): data model v2 for tweet-level community evidence
- `515ce55` docs: handover — labeling data model v2, community evolution layer next

PUSHED: No — now 39 commits ahead of origin

## Four-Layer Architecture (Agreed With User)

```
Layer 1: Tweet Evidence Capture (EXISTS - tweet_tags, tweet_label_set, tweet_label_prob)
  - Substrate: schema.py, tags.py, golden.py
  - Conventions on top: bits:Community:+N, new-community-signal:Name (not first-class yet)
  - 252 tags, 19 notes, 19 simulacrum distributions for @repligate

Layer 2: Account-Community Truth / Evaluation (EXISTS - Codex built this)
  - ADR 014: deterministic per-account splits (70/15/15 train/dev/test)
  - account_community_gold_split, account_community_gold_label_set tables
  - IN/OUT/ABSTAIN judgments, immutable history with supersession
  - 4 evaluation methods: canonical_map, nmf_seeded, louvain_transfer, train_grf
  - Evaluator harness: AUC-PR, F1, Brier, ECE per community + macro
  - Candidate queue: entropy-weighted, disagreement-based active learning
  - Files: src/data/community_gold/ (9 modules), src/api/routes/community_gold.py

Layer 3: Tweet→Account Rollup / Inference Bridge (NOT BUILT)
  - Takes Layer 1 evidence (tags, bits per tweet)
  - Generates: candidate memberships, summaries, hypotheses
  - Feeds INTO Layer 2 as suggestions (human reviews before it becomes truth)
  - Should NOT silently become its own ground truth

Layer 4: Evidence-Driven Community Evolution (PARTIALLY BUILT)
  - EXISTS: branches/snapshots, canonical community editing (branches.py, versioning.py)
  - NOT BUILT: evidence-driven split/merge/birth from accumulated tags
  - Updates canonical map ONLY after human review or explicit policy
```

### Architectural Rules
1. Layer 3 generates hypotheses → Layer 2 remains human-reviewed truth
2. Layer 4 updates canonical map only after human review
3. Tweet evidence never silently becomes ground truth
4. Fixed deterministic splits (ADR 014) for production leaderboard
5. K-fold for offline research on tweet-to-account inference — separate metrics artifact

### Codex System Details (Layer 2)
- **Schema**: `account_community_gold_split` (per-account, SHA256 deterministic), `account_community_gold_label_set` (immutable history, IN/OUT/ABSTAIN + confidence + note + evidence_json)
- **Scoring methods**: canonical_map (membership weights), nmf_seeded, louvain_transfer (cluster majority voting), train_grf (graph random forest)
- **Candidate queue**: cold=max(canonical,nmf), warm=0.7×entropy+0.3×disagreement, round-robin across communities
- **API**: `/api/community-gold/{communities,labels,metrics,candidates,evaluate}`
- **Frontend**: `communityGoldApi.js`, `goldLabelUtils.js`
- **Tests**: 3 test files (store, routes, evaluator)

## Pending Threads

### Continue Immediately: Community Evolution Layer

**User's key question:** "What does it mean to make a community description, color, and how is it defined? By accounts? Tweets?"

The evidence layer is built (tags, bits, postures, simulacrum). What's missing is the **community evolution layer** — the mechanism that:
1. Takes accumulated tag/bits evidence
2. Proposes community description updates
3. Detects when a community should split (tag bimodality within community)
4. Detects when communities should merge (tag overlap between communities)
5. Creates new communities from `new-community-signal` tags
6. Updates community colors/names/descriptions

**Current community descriptions** are in `community` table (`description` column) — static one-paragraph bios written at NMF creation time. None incorporate tweet evidence.

**What to build:**
- A script/function that reads all bits + thematic tags for accounts in a community
- Computes whether the community's internal variance suggests a split
- Proposes updated description text based on accumulated tags
- Surfaces to human for approval (human gate)

### Continue: Finish @repligate Labeling

- 19/45 tweets labeled with full data model (domains, themes, specific, postures, bits, simulacrum, notes)
- 26 tweets remaining in HTML queue (`labeling_queue.html`)
- Top-3 community ranking is stable but minor communities and subcommunity structure would benefit from more data
- **IMPORTANT**: Must navigate to each tweet via Chrome to see images/links/context. Several early labels were wrong because images weren't checked.
- User wants to continue labeling to build more data for community evolution

### Continue: Label More TPOT Accounts

After repligate, label accounts from OTHER communities to get cross-community evidence:
- Pick accounts from Builders, highbies, Contemplative Practitioners, etc.
- These ARE in the archive (unlike the builder cluster accounts)
- Goal: 40 accounts total for k-fold cross-validation

### Deferred: External Builder Cluster

User listed 17 accounts (karpathy, Teknium, alexocheema, etc.) — none in archive, most not in TPOT graph at all. User decided to shelve this and focus on TPOT first. Saved to `docs/LABELING_NEXT_ACCOUNTS.md`.

### Deferred: On-Demand Tweet Enrichment

31% of tweets have t.co links (images, videos, quote tweets) not stored in DB. Designed JIT enrichment via twitterapi.io but not built. For now, using Chrome browser to view context manually during labeling.

### Deferred: About Page Rewrite

Story-first narrative approach. See previous handover for details.

## Key Context

### Data Model v2 (Per Tweet)
Full spec in `docs/LABELING_PIPELINE_DESIGN.md`. Summary:
1. **Domain tags** (`domain:AI`, `domain:philosophy`, etc.) — category='domain'
2. **Thematic tags** (`theme:AI-consciousness`, etc.) — category='thematic'
3. **Specific tags** (fine-grained, unlimited) — category=NULL
4. **Posture tags** (`posture:original-insight`, etc.) — category='posture'
5. **Bits** (`bits:LLM-Whisperers:+3`) — category='bits', log-likelihood ratios, PRIOR-INDEPENDENT
6. **Simulacrum distribution** — L1/L2/L3/L4 in `tweet_label_prob`
7. **New community signals** (`new-community-signal:AI Mystics`) — category='new-community'
8. **Notes** — free text in `tweet_label_set.note`

### Golden Dataset State (in archive_tweets.db)
- 252 tags in `tweet_tags` (across all categories)
- 19 notes in `tweet_label_set` (reviewer='aditya')
- 19 simulacrum distributions in `tweet_label_prob`
- All for @repligate (account_id: 1359981346119155719)

### @repligate Community Profile (from 19 tweets, 73 bits total)
```
  39.7%  LLM Whisperers (+29 bits)
  24.7%  Qualia Research (+18 bits)
  17.8%  AI Safety (+13 bits)
  11.0%  Contemplative Practitioners (+8 bits)
   5.5%  Emergence & Self-Transformation (+4 bits)
   1.4%  highbies (+1 bits)
```
vs NMF prior: 100% Qualia Research, 0% everything else

### @repligate Simulacrum Signature
L1=40%, L2=4%, L3=24%, L4=29% — truth-tracking + meta-aware, almost zero persuasion

### New Community Signals
- "AI Theorists / Ontologists" — from simulacra LessWrong post
- "Alignment via narrative/archetypes" — from archetype-attractors thread
- "AI Mystics" — from AI-as-enlightenment-vehicle tweet

### NMF Bias (Systematic)
- NMF seed accounts: avg 3.1 communities, max weight 0.740
- Propagated accounts: avg 4.3 communities, max weight 0.503
- Root cause: NMF sparsity constraint concentrates, label propagation smooths
- Fix: tweet-level tag evidence adds missing dimensions

### Approach B: Bottom-Up Communities (User's Choice)
- 14 NMF communities are just one prior
- Tags accumulate → account×tag matrix → clustering discovers communities
- Communities can split, merge, or be born
- Each reclustering is a versioned snapshot (branch system exists)

### Bits System (Prior-Independent Evidence)
- +1 bit = 2x more likely if member (weak)
- +2 bits = 4x (moderate)
- +3 bits = 8x (strong)
- +4 bits = 16x (diagnostic)
- Additive: 3 tweets with +2 each = +6 total
- Anyone can apply different priors and reuse the same evidence

### Critical Labeling Lesson
ALWAYS navigate to the tweet on X and view images/links/context before tagging. Several labels were wrong when done from text-only. The Chrome browser tools (screenshot, zoom, navigate) work for this.

## User Preferences (This Session)
- Prefers bottom-up community discovery (Approach B) over hierarchical
- Wants prior-independent evidence (bits) so different people can use different priors
- Wants k-fold cross-validation at account level, not fixed splits
- Wants tags to capture multiple levels (domain, theme, specific, posture)
- Wants dry runs before committing to DB — show thinking, get feedback
- Context is everything — always fetch full tweet context (images, replies, quote tweets)
- Interested in community evolution layer: how do community descriptions, boundaries, colors change based on evidence?
- Decided to stay within TPOT graph rather than expand to external builder cluster

## Resume Instructions
1. Read this handover + `docs/LABELING_PIPELINE_DESIGN.md`
2. **Build community evolution layer** — the mechanism that takes tag/bits evidence and proposes community description updates, splits, merges, new communities
3. Continue labeling remaining 26 @repligate tweets (use Chrome for context)
4. Then label accounts from OTHER TPOT communities for cross-community breadth
5. Goal: 40 accounts for k-fold cross-validation

---
*Handover by Claude at high context usage, 2026-03-20*
