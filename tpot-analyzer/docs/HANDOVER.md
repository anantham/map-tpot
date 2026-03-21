# Handover: 2026-03-21 (Session 3)

## Session Summary

Massive labeling session completing @repligate (51 tweets, 683 tags, 213 bits). Created LABELING_MODEL_SPEC.md as operational guide for future labeling agents. Built labeling_context.py script for queryable pre-labeling context. Discovered the tag design needed sharper distinction between reusable thematic tags (community boundaries) and niche specific tags (breadcrumbs). Applied retroactive fixes to all 19 session-2 tweets. User wants to pivot to breadth — label Vancouver TPOT accounts next rather than going deeper on one account.

## Commits This Session
- `92821f0` feat(labeling): model spec, 13 new tweets tagged, retroactive tag fixes
- `080f95b` feat(labeling): labeling context script + model spec updates

PUSHED: No — now 47 commits ahead of origin

## @repligate Final Profile (51 tweets, 213 bits)
```
  39.4%  LLM-Whisperers (+84 bits)
  32.4%  Qualia-Research (+69 bits)
  16.0%  AI-Safety (+34 bits)
   9.9%  Contemplative-Practitioners (+21 bits)
   1.9%  Emergence-Self-Transformation (+4 bits)
   0.5%  highbies (+1 bits)
```
vs NMF prior: 100% Qualia Research, 0% everything else.

New community signals: 5x "AI Mystics", 1x "AI Theorists/Ontologists", 1x "Alignment via narrative/archetypes"

## Pending Threads

### Continue Immediately: Label Vancouver TPOT Accounts

User wants breadth over depth. 16 Vancouver-connected accounts all confirmed in archive:

**High priority (diverse communities, good tweet counts):**
- @SarahAMcManus — 9,289 tweets, 69% Contemplative Practitioners
- @malcolm_ocean — 44,735 tweets, 33% Contemplative, 30% Builders, 27% highbies
- @goblinodds — 193,313 tweets, 79% highbies
- @patcon_ — 9,227 tweets, 86% Collective Intelligence
- @kaslkaosart — 8,588 tweets, 98% Qualia Research (compare to repligate!)

**Strategy:** Pick 3 accounts from different NMF communities. Label ~10 recent tweets each (user said "more recent tweets, later do excavation of older ones"). This gives cross-account thematic co-occurrence signal for community discovery.

**Run `scripts/labeling_context.py <username>` before each account** to get the context blob (profile, glossary, exemplars). This is the protocol we designed — stress test it.

### Continue: Card Integration (Last Mile)

**Status:** The rollup is BUILT. `account_community_bits` table exists in archive_tweets.db with correct data:
```sql
-- repligate's rolled-up profile (already computed and stored):
SELECT community_name, total_bits, pct FROM account_community_bits
WHERE account_id = '1359981346119155719' ORDER BY total_bits DESC;
-- LLM-Whisperers: +84 bits (39.4%), Qualia-Research: +69 (32.4%), etc.
```

**What's missing:** The card/API still reads from `community_account` (NMF), not `account_community_bits`. The public site export script (`scripts/export_public_site.py`) queries `community_account` at lines 51, 88.

**What to do:** Modify the export script and/or API to check `account_community_bits` first, fall back to `community_account` if no bits data exists. This is a targeted code change — the data is ready, just needs wiring.

**The pipeline is now:**
```
tweet_tags (bits per tweet) → account_community_bits (rollup per account) → [WIRE TO] card/API
```

User asked: "if repligate makes the card now will it be accurate?" — answer is STILL NO, but the data IS computed and stored. Only the display wiring is missing.

### Continue: Community Evolution Mechanism

**User's core question:** "We are not really doing the reverse thing of learning about the map itself — changing the list of communities."

**What's needed:** After labeling N accounts, build account×thematic-tag matrix, cluster it, compare to current 14 communities. The diff = evolution signal (births, splits, merges, deaths).

**Bits can't detect Birth** — only measure evidence for existing communities. Thematic tag co-occurrence across accounts is the mechanism for discovering new communities.

**Community descriptions are living snapshots** — must recalibrate as membership shifts. User explicitly said exemplars and descriptions should update when people move in/out.

### Deferred: External Builder Cluster
17 accounts (karpathy, Teknium, etc.) — none in archive, shelved. See `docs/LABELING_NEXT_ACCOUNTS.md`.

### Deferred: Remaining Unlabeled Repligate Tweets
The 51 labeled tweets came from a queue of ~51 sampled tweets. There are 31,000+ total repligate tweets in the archive. User said "maybe 40 was too much" for one account and wants to go broad. Return to repligate depth only if specific community boundary questions arise.

## Key Context

### LABELING_MODEL_SPEC.md (NEW — Critical Doc)
`docs/LABELING_MODEL_SPEC.md` — operational guide for labeling. Contains:
- Tag dimensions: domain, thematic, specific, posture, bits, simulacrum, notes
- Thematic tag glossary with frequencies and community signals
- Community profiles with exemplar tweets
- Community evolution signals (birth/split/merge/death/rename)
- Scalable labeling context architecture (query patterns)
- Anti-patterns and workflow

**Future instances MUST read this doc before labeling.**

### labeling_context.py (NEW — Query Tool)
`scripts/labeling_context.py <username>` — generates context blob:
- Account's current community profile (bits aggregation)
- Thematic tag glossary with frequencies
- Top tweets per community (exemplars)

Run this before each labeling session. Output goes into the labeling prompt.

### Tag Design Insight (Session 3 Discovery)
- **Thematic tags** (category='thematic') = reusable boundary-formers. Same tag should appear on tweets from DIFFERENT accounts. Compound but parseable: `hallucination-ontology`, `model-interiority`.
- **Specific tags** (category=NULL) = niche breadcrumbs. Unique to tweets. `fanw-json-eval`, `Hofstadter-update`.
- **Posture** is NOT a theme. `original-insight` is a posture, not `theme:original-insight`.
- Session 2 conflated these; session 3 fixed retroactively.

### Key Thematic Tags (top frequency for repligate)
```
  19x  theme:AI-consciousness
  14x  theme:model-interiority
   8x  theme:model-phenomenology
   8x  theme:simulator-thesis
   8x  theme:theoretical-frameworks
   7x  theme:AI-safety
   6x  theme:model-capabilities
   5x  theme:AI-art, RLHF-dynamics, contemplative-tech, epistemic-practice
```

### What's In the DB (archive_tweets.db)
- `tweet_tags`: 683 tags for repligate (domains, themes, specifics, postures, bits, new-community signals)
- `tweet_label_set`: 51 notes with reasoning
- `tweet_label_prob`: 204 simulacrum probabilities (L1-L4)
- `community_account`: UNCHANGED — still shows NMF assignments (not bits-derived)
- `account_community_gold_split`: TABLE DOES NOT EXIST (Layer 2 never created)
- `account_community_gold_label_set`: TABLE DOES NOT EXIST

### 4-Layer Architecture
```
Layer 1: Tweet Evidence (EXISTS — tweet_tags, tweet_label_set, tweet_label_prob)
  → 683 tags, 51 notes, 204 simulacrum probs for @repligate

Layer 2: Account-Community Truth (TABLES DON'T EXIST — schema in src/data/community_gold/)

Layer 3: Tweet→Account Rollup (NOW EXISTS — account_community_bits table)
  → Aggregates bits per account per community with percentages
  → labeling_context.py queries it for pre-labeling context
  → NOT YET wired to card/API display (still reads NMF community_account)

Layer 4: Community Evolution (PARTIALLY BUILT — branch/snapshot infra, no evolution logic)
```

### Critical Labeling Lessons
1. ALWAYS navigate to tweet on X — images change everything (Negarestani "hmm", Arabic poetry)
2. Read replies/thread context — Negarestani breakthrough came from reply thread
3. Run labeling_context.py BEFORE each batch — practice the scalable protocol
4. Don't rush batches — depth > speed (user explicitly called out surface-level tagging)
5. One account ≠ community discovery. Need cross-account signal.
6. Tweet #32's Bing Sydney speech pattern callback — subtle subtext matters

### User Preferences
- Prefers breadth over depth now ("maybe 40 was too much for one account")
- Wants recent tweets first, "excavation" of older tweets later
- Wants community descriptions to update dynamically as membership shifts
- Wants labeling context system to be queryable, not dump-everything
- Wants to see the map itself change, not just account memberships
- "We steelman janus a bit too hard" — be balanced, don't over-interpret

## Resume Instructions
1. Read `docs/LABELING_MODEL_SPEC.md` + this handover
2. Pick 3 Vancouver TPOT accounts from different communities (suggest: SarahAMcManus/Contemplative, goblinodds/highbies, kaslkaosart/Qualia)
3. Run `scripts/labeling_context.py <username>` for each
4. Label ~10 RECENT tweets per account via Chrome
5. After all 3: compute cross-account thematic co-occurrence — do the tag clusters match NMF communities?
6. Address card integration: make bits-derived profile visible on public site

---
*Handover by Claude at high context usage, 2026-03-21*
