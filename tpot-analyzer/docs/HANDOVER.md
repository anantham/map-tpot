# Handover: 2026-03-24 (Session 10 — Chrome Audit + Edge Enrichment + Data Quality)

## Session Summary
Chrome-audited 28/29 labeled accounts (57 tweets verified, 27 corrections, 33 corrected / 23 correct / 1 flagged). Fixed 854 NULL usernames in resolved_accounts. Created None community in DB. Fetched 22,338 new outbound edges for 23 high-CI backbone accounts (batch 1). Chrome-scraped following lists for 4 accounts where API returned empty. Built quality_candidates table (256 accounts). Fetched 184 members from Aditya's curated X list. Created HOLDOUT_SOURCES.md documenting 4 ground truth sources. Another agent shipped 5 systemic pipeline fixes (consensus, normalization, None gate, URL enrichment, keyword guardrail). Round 1 active learning still running (13/50 accounts).

## Resume Instructions
1. **Check if Round 1 finished**: `tail -20 /private/tmp/claude-501/-Users-aditya-Documents-Ongoing-Local-Project-2---Map-TPOT/37432efe-8d6b-4059-818a-5189dc84739f/tasks/bo3egihz0.output`
2. **If Round 1 done**: Run `--measure` (now safe — uses scoped delete, not global wipe)
3. **Re-propagate**: `.venv/bin/python3 -m scripts.propagate_community_labels --use-archive-graph --save`
4. **Check recall**: `.venv/bin/python3 -m scripts.verify_holdout_recall` (baseline: 8.5%)
5. **Label 7 high-confidence misses**: `--accounts gptbrooke,embryosophy,touchmoonflower,sonikudzu,soundrotator,Duderichy,RosieCampbell`
6. **Label user's 37 manual picks**: accounts stored in shadow_list_member (list_id='1788441465326064008', source='manual_add')
7. **Retry edge fetch for 18 failed accounts**: @robinhanson, @vgr, @deepfates, @paulg, @patrickc, @ilyasut, etc. — API returned 0, may work later or need Chrome scrape
8. **Re-export + deploy** public site

## Key Context for Next Instance

### DB State
- 32 labeled accounts in account_community_bits (29 original + 3 from Round 1)
- 463,692 edges in account_following (was 441K, added 22K+ this session)
- 57 tweets in chrome_audit_log (10% coverage)
- 256 quality_candidates (accounts with high TPOT-following concentration, need labeling)
- 219 members in Aditya's curated X list (shadow_list_member, list_id='1788441465326064008')
- None community created: id=b878d56e-ba99-467c-9288-dbe6f77eb3b4, short_name='None'

### 5 Systemic Fixes (shipped by another agent, commit adb7e06)
1. `_enrich_low_text_tweet()` — fetches article title/description for URL-only tweets
2. AI-tool guardrail — "Claude Code" ≠ LLM-Whisperers, few-shot added
3. 1/3 consensus preserved at +1 (was: discarded). 3 emerging clusters promoted
4. Absolute-bits weight: `min(1.0, abs(bits)/30)` replaces `pct/100`
5. bits:None for adjacent ecosystems, None-dominated accounts blocked from seeding

### Critical Bug Fixed (commit bb46345)
`active_learning.py --measure` called `write_rollup()` which does GLOBAL DELETE on account_community_bits. Fixed to use scoped_delete + manual INSERT. All 29 accounts' data was rebuilt from intact tweet_tags.

### API Notes
- twitterapi.io `user/followings` endpoint fails for many accounts (returns empty)
- Cost is credit-based: ~3000 credits per followings page, 479K credits remaining
- Chrome scraping works as fallback (auto-scroll + extract handles, gets ~30-40 per account)
- LLM labeling via OpenRouter is $0 (free tier: Grok-4.1-fast + DeepSeek-v3.2 + Gemini-3.1-flash-lite)

### Chrome Audit Findings (stored in chrome_audit_findings table)
1. Account-prior bias on URL/image-only tweets
2. Keyword false matches ("Claude Code" → LLM-Whisperers)
3. RT bit dropout (consensus too conservative for RTs)
4. Normalization bias (pct overweights concentrated weak evidence)
5. None community needed for mainstream accounts

### Holdout Recall Sources (see docs/HOLDOUT_SOURCES.md)
| Source | Count | Current Recall |
|--------|-------|---------------|
| Orange directory | 209 | 20% |
| Strangest Loop | 99 | 44% |
| Aditya's curated list | 219 | ~11% |
| Ego follows | 1,457 | 8% |
| **Combined** | **1,794** | **8.5%** |

### Accounts with 0 Outbound Edges (API failed, Chrome-scraped partial)
- @NeelNanda5: 29 edges (Chrome)
- @So8res: 18 edges (Chrome)
- @jgreenhall: 40 edges (Chrome)
- @kathryndevaney: 41 edges (Chrome)
- These are partial — Chrome only renders ~30-40 per scroll

### 18 Accounts Where API Edge Fetch Failed Completely
@gptbrooke, @robinhanson, @deepfates, @vgr, @liminal_warmth, @nearcyan, @MasterTimBlais, @tracewoodgrains, @robbensinger, @JakeOrthwein, @paulg, @patrickc, @WilliamAEden, @lisatomic5, @ilyasut, @prerat, @diviacaroline, @meekaale

### Running Processes
- **Round 1 active learning**: task bo3egihz0 — 13/50 accounts processed
  - Check: `tail -20 /private/tmp/claude-501/-Users-aditya-Documents-Ongoing-Local-Project-2---Map-TPOT/37432efe-8d6b-4059-818a-5189dc84739f/tasks/bo3egihz0.output`

### Memory Files
- `memory/feedback_tpot_scope.md` — TPOT scope is broad (metacrisis/metamodern IS TPOT)
- `memory/feedback_chrome_verification.md` — Chrome verification is mandatory
- `docs/HOLDOUT_SOURCES.md` — 4 ground truth sources documented
- `config/community_glossary.json` — labeling guide with None + 3 promoted emerging clusters

---
*Handover by Claude at ~90% context*
