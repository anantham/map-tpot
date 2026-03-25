# Handover: 2026-03-25 (Session 11 — Seed Fix + Profiles + Bio Embeddings + Labeling)

## Session Summary
Fixed seed-neighbor counting (raw weights, not class-balanced). Fetched profiles for 8,532 core members ($1.54) — bio, location, follower counts. Embedded 15,182 bios (all-MiniLM-L6-v2, 384-dim). Labeled 5 accounts (ilex_ulmus, eenthymeme, dissproportion + AaronBergman18 enriched, bayeslord empty). Rewrote About page Path C in essay voice. Updated Vancouver outreach doc with 23 new leads. Deep brainstorm on noise filtering — reciprocity is the cleanest signal but requires API calls. 355 seeds now.

## Resume Instructions
1. **Deploy** — export is ready (17,634 accounts), waiting on KV storage fix (other agent handling)
2. **After deploy** — re-export once more (propagation with 355 seeds running at session end)
3. **Reciprocity spot-check** — `check_follow` endpoint for top 500 accounts, ~5K API calls
4. **NMF v2 alignment + promotion** — formal factor alignment score, human review of 3 shifted communities
5. **Round 1 remaining** — @bayeslord had no tweets, 24+ accounts still in the Round 1 queue
6. **Label remaining** — @AlexKrusz (holdout, skip), @bayeslord (empty)

## Key Context

### Data State
- **799,521 follow edges**, 297,402 nodes
- **355 seeds** (317 NMF + 38 LLM ensemble) across 16 communities
- **50 accounts** with bits rollup (tweet-level evidence)
- **9,364 profiles** in `user_profile_cache` (8,913 with bio, 6,693 with location)
- **331 user_about** profiles with verified locations
- **15,182 bio embeddings** in `bio_embeddings` table (384-dim, all-MiniLM-L6-v2)
- **17,634 accounts** in latest export (338 exemplar, 4,831 specialist, 1,974 bridge, 1,097 frontier, 9,394 faint)

### Noise Analysis (Session 11 Key Finding)
No graph-internal signal cleanly separates "famous tech accounts" from "TPOT members." Tried:
- Concentration (seed_neighbors / inbound): fooled by low-degree nodes
- Spread (entropy of seed-neighbor vector): TPOT communities overlap too much, everything is high-spread
- Score × neighbors composite: Elon (0.35) overlaps with TPOT P25 (0.27)

**Reciprocity is the answer:** `mutual_seeds / inbound_seeds`. Famous < 0.06, TPOT > 0.17. Clean 3x gap. But requires knowing who accounts follow (only 14% of placed accounts have outbound data). `check_follow` API endpoint can spot-check ~10 seeds per account.

**Decision:** Accept famous accounts as "adjacent/faint" — TPOT IS tech-adjacent. Use celebrity concentration filter (from commit f9727e4) for accounts with > 100K followers. Frontend UX fix (hide faint from community pages by default) is better than data-level filtering.

### Bio Embeddings (Experiment Results)
- **Partial separation:** TfT-Coordination, LLM-Whisperers, AI-Safety most distinct by bio content
- **Near-identical:** Core-TPOT ↔ Internet-Intellectuals (0.86 cosine) — bios sound the same
- **Intra-community coherence:** 0.38-0.53 (moderate clustering)
- **Verdict:** Useful as secondary signal for cold-start accounts. Not a replacement for graph structure.

### New DB Tables
- `user_profile_cache`: followers, following, bio, location, raw_json (from batch_info_by_ids)
- `user_about_cache`: account_based_in, affiliate_label, username_changes (from user_about)
- `bio_embeddings`: 384-dim sentence-transformer vectors per account

### Commits This Session (6)
- `ab859bd` fix(propagation): raw weights for seed-neighbor counting
- `bec6b64` docs(about): Path C rewrite in essay voice
- `8eedd9c` docs: HANDOVER + API endpoint docs updated
- `d6bb27d` docs: Schema Guesser anti-pattern + README rewrite
- `f735430` docs(vancouver): 23 new leads + 7 stale locations corrected

### Running / Pending
- **Propagation with 355 seeds** — running at session end (~15 min)
- **KV storage fix** — other agent migrating to Vercel Blob or purging gallery
- **@bayeslord** — no tweets available from API, may need Chrome or archive

---
*Handover by Claude Opus 4.6 (session 11, ~45% context)*
