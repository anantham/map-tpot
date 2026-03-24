# Session 10 Ideas Inventory

> Everything done, designed, deferred, or blocked across sessions 10a-10c.
> Last updated: 2026-03-24. This is a living document — update as items ship.

---

## DONE (shipped this session)

### Edge Enrichment (+358K edges, graph 441K → 800K)

| # | Item | Result | Notes |
|---|------|--------|-------|
| 1 | Batch 1: 23 high-CI backbone accounts | 22,338 edges | @ESYudkowsky, @AmandaAskell, @karpathy, @Aella_Girl, etc. |
| 2 | API bug fix: `followings` not `data` | Recovered 15,396 edges | twitterapi.io returns `{"followings":[...]}` — we read wrong key all session |
| 3 | Tier 1 fetch (51 accounts) | 6,393 + 18,686 edges | Hit 402, recharged, resumed |
| 4 | Tier 2 fetch (200 new accounts) | 88,563 + 118,253 edges | Two batches of 100 untouched accounts |
| 5 | Round 1 account edges (12 accounts) | 15,255 edges | All 26 Round 1 accounts now have outbound |
| 6 | Seed follower lists (40 seeds < 2K followers) | 21,712 edges | Near-complete: 673/674 for @SahilLalani0, etc. |
| 7 | Tier 1+2 follower lists (22 accounts) | 22,704 edges | Quiet gems with < 3K followers |
| 8 | Chrome-scraped following (15 accounts) | ~250 edges | @gwern (22), @vgr (18), etc. — API fallback |
| 9 | Resumable edge fetcher | `scripts/fetch_edges_resumable.py` | Cursor persistence in `edge_fetch_state` table |
| 10 | Priority scoring system | 573 accounts scored | `priority = inbound×0.3 + sources×10 + labeled×20 + seed×15 + user_pick×25` |

### Chrome Audit (28 accounts, 57 tweets)

| # | Item | Result | Notes |
|---|------|--------|-------|
| 11 | Profile checks (9 enriched + 12 archive) | All 29 labeled accounts | Bio + sidebar + community verification |
| 12 | Tweet-level verification | 57 tweets in `chrome_audit_log` | 23 correct, 33 corrected, 1 flagged |
| 13 | Teknium zero-bit fix | 14 RTs got LLM-Whisperers bits | Ensemble consensus too conservative for RTs |
| 14 | Keyword false match corrections | 5 tweets fixed | "Claude Code" ≠ LLM-Whisperers, etc. |
| 15 | Account-prior bias corrections | 8 tweets fixed | URL-only tweets labeled from account profile, not content |

### Independent Propagation (zero-sum → multi-label)

| # | Item | Result | Notes |
|---|------|--------|-------|
| 16 | `--mode independent` in propagation | 17,634 searchable accounts | Each community scored independently, no sum-to-1 |
| 17 | Seed-neighbor counting | Stored in NPZ | Noise filter: @googlecalendar (0 neighbors) filtered out |
| 18 | Raw scores (no per-column normalization) | Approach C+E implemented | Fixes noise inflation from per-column scaling |
| 19 | Threshold calibration (ROC on held-out) | t=0.02 chosen | 80% precision on held-out, validated by spot-check |
| 20 | Export pipeline adaptation | UUID fix + CI formula | `_extract_bits_accounts` resolves short_name → UUID |

### NMF v2 Validation

| # | Item | Result | Notes |
|---|------|--------|-------|
| 21 | NMF v2 (k=16, 800K edges, likes) | 11/16 strong match with v1 | Ontology is real structure, not sparse-data artifact |
| 22 | Saved to DB branch | `nmf-k16-follow+rt+like-lw0.4-20260324-6f6f95` | Not promoted to primary yet |

### Data Quality

| # | Item | Result | Notes |
|---|------|--------|-------|
| 23 | 854 NULL usernames fixed | `resolved_accounts` populated from `profiles` | Silent data corruption from earlier sessions |
| 24 | 16 duplicate bits tags cleaned | Kept latest per (tweet, community) | From multiple labeling runs with different prompts |
| 25 | 3 accounts missing rollup rebuilt | bryan_johnson, jgreenhall, ohabryka | Labeled after last rollup |
| 26 | Global DELETE bug fixed | `active_learning.py --measure` uses scoped delete | `write_rollup()` was nuking all accounts |
| 27 | None community created | id=b878d56e, short_name='None' | Gate blocks None-dominated accounts from seeding |
| 28 | Protected accounts table | 5 protected + 3 deleted/renamed | Prevents wasting API calls on unfetchable accounts |

### Active Learning Round 1

| # | Item | Result | Notes |
|---|------|--------|-------|
| 29 | Round 1 (26/50 accounts) | 1,640 bits tags | Budget exhausted at $2.55 |
| 30 | `--measure` rollup + seed insertion | 14 new accounts, 70 seeds | Scoped delete (no global wipe) |
| 31 | Notable: @jkcarlsmith AI-Safety 82% | Correct | |
| 32 | Notable: @glenweyl None 33% | Correctly ambiguous | Borderline mainstream policy |
| 33 | 3 errors total | 1 Grok 503, 1 Gemini parse fail, budget stop | Pipeline self-healed on model errors |

### Public Site + About Page

| # | Item | Result | Notes |
|---|------|--------|-------|
| 34 | Deployed 17,634 accounts | amiingroup.vercel.app | 338 exemplar, 4831 specialist, 1974 bridge |
| 35 | Dejargoned Path C | "3-model ensemble" → "three AI models", etc. | Still needs full voice rewrite |
| 36 | Added source links | Orange TPOT, Strangest Loop, Aditya's watchlist, follows | All linked |
| 37 | Honest recall table | Per-source: 65% multi-source, 30% ego follows | Split in-graph vs total |
| 38 | "What We Don't Know" section | 6 honest uncertainties | Archive bias, temporal freeze, ontology subjectivity |
| 39 | "This is Aditya's map" | Fork invitation with repo link | Replaced "Ontology is one curator's lens" |

### Documentation

| # | Item | File | Notes |
|---|------|------|-------|
| 40 | Holdout sources doc | `docs/HOLDOUT_SOURCES.md` | 4 sources, multi-source confidence, recall queries |
| 41 | Propagation analysis | `docs/PROPAGATION_ANALYSIS.md` | Independent mode results, threshold sensitivity, ROC |
| 42 | NMF v2 validation | `docs/NMF_V2_VALIDATION.md` | Factor alignment, 11/16 match |
| 43 | Tech debt scan | `docs/TECH_DEBT_SCAN_2026-03-24.md` | 14 items across 5 dimensions |
| 44 | Independent mode spec | `docs/superpowers/specs/2026-03-24-independent-community-propagation-design.md` | Design rationale |
| 45 | Schema Guesser anti-pattern | CLAUDE.md (local) | Never assume API response field names |

---

## DESIGNED BUT NOT BUILT

| # | Item | Effort | Why not done |
|---|------|--------|-------------|
| 46 | **5-factor confidence index** | ~100 LOC | `src/communities/confidence.py` exists for exemplars only. Needs extension to all accounts using propagation score + degree + seed proximity + source count + bootstrap stability. |
| 47 | **Seed-neighbor fix (proper)** | ~20 LOC | Use `community_account.weight` directly instead of processed boundary. Current `> 0` threshold is a hack. |
| 48 | **Content vectors in propagation** | ~50 LOC | 4,071 accounts have TF-IDF profiles in `account_content_profile`. Could weight edges by content similarity. |
| 49 | **About page voice rewrite** | ~2hr writing | Path C needs Scott Alexander style. See `memory/feedback_about_page_voice.md`. |
| 50 | **NMF v2 factor alignment score** | ~30 LOC | Cosine similarity of H matrices (session 8 method). Would give formal % overlap. |
| 51 | **Propagation metrics table** | ~40 LOC | Track specialists/bridges/frontier per run for historical comparison. |

---

## API BUDGET STATUS

| Item | Credits | Edges | Notes |
|------|---------|-------|-------|
| Batch 1 (23 backbone accounts) | ~360K | 22,338 | `user/followings` — correct key |
| Bug wasted (wrong key `data`) | ~180K | 0 | Double-paid on retry |
| Retry with fixed key | ~180K | 15,396 | Recovered all data |
| Tier 1 (51 accounts) | ~270K | 24,479 | Hit 402, recharged, resumed |
| Tier 2 (200 accounts) | ~900K | 206,816 | Two batches |
| Round 1 account edges | ~90K | 15,255 | 12 accounts |
| Seed follower lists | ~225K | 21,712 | 40 seeds < 2K followers |
| Tier 1+2 follower lists | ~126K | 22,704 | 22 accounts |
| Round 1 API (tweets + labeling) | $2.55 | — | Twitter API, not credits |
| **Total credits spent** | **~2.3M** | **~328K edges** | Started at 479K credits, recharged multiple times |

---

## BLOCKED

| # | Item | Blocker | Action |
|---|------|---------|--------|
| 52 | **5 protected accounts** | Private following lists | @tracewoodgrains, @lioninawhat, @teleosistem, @grantadever, @HamishDoodles — can only use inbound edges |
| 53 | **3 deleted accounts** | Accounts don't exist | @sashachapin, @chairsign, @prerationalist — removed from queues |
| 54 | **12 Tier 2 handles unresolved** | Not in `resolved_accounts` or `profiles`, API returned "not found" for some | Need case-insensitive search or handle may have changed |
| 55 | **204 incomplete edge fetches** | Capped at 5 pages without saved cursor (pre-resumable fetcher) | Re-fetch from page 1, or accept partial coverage |

---

## DEFERRED

| # | Item | Why deferred | When to revisit |
|---|------|-------------|-----------------|
| 56 | **Full About page voice rewrite** | Too large for tail-end of session. Needs dedicated writing focus. | Next session, first priority if user-facing |
| 57 | **NMF v2 promotion to primary** | Need formal factor alignment + human review of 3 shifted communities | After alignment score computed |
| 58 | **Community lifecycle (birth/merge/split)** | Open-Source-AI, AI-Mystics, d-acc-Builders promoted in prompt but no DB rows | After NMF v2 review |
| 59 | **Bootstrap CV re-run** | Need 800K graph propagation to stabilize first | After seed-neighbor fix |
| 60 | **Wire TF-IDF into pipeline** | Architectural decision: weight edges vs context for LLM vs hybrid CI | After confidence index designed |
| 61 | **Re-run NMF at k=14 and k=18** | k sensitivity on v2 graph would validate k=16 choice | Low priority — v2 already confirms v1 |
| 62 | **Fetch followers for 3,175 confident non-seeds** | Need re-propagation with fixed seed-neighbor counting first | After fix #47 |
| 63 | **Round 1 remaining 24 accounts** | Budget exhausted at $2.55 | Next `--round 1 --top 24 --budget 2.50` run |
| 64 | **Tier 3 edge fetch (111 accounts)** | Low priority, small impact | After Tier 1+2 value validated |

---

## KEY NUMBERS

| Metric | Session start | Session end | Change |
|--------|-------------|-------------|--------|
| Graph edges | 441,226 | 815,363 | **+85%** |
| Graph nodes | 201,723 | 297,402 | **+47%** |
| Searchable accounts | 13,360 | 17,634 | **+32%** |
| Bridges detected | 1,362 | 1,974 | **+45%** |
| Seeds (NMF + LLM) | 338 | 352 | +14 |
| Labeled accounts | 32 | 46 | +14 (Round 1) |
| Chrome-audited tweets | 0 | 57 | New capability |
| NMF validated | v1 only | v2 confirms v1 | 11/16 strong match |
| Protected accounts tracked | 0 | 8 | New table |
| Holdout sources | 2 | 4 | +curated list, +ego follows |
