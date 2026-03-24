# Handover: 2026-03-24 (Session 9 — Active Learning Pipeline End-to-End)

## Session Summary
Built complete active learning pipeline (8 files, 85+ tests), labeled 29 accounts total (20 manual + 9 API), Chrome-audited 6 accounts finding 5 failure modes, created comprehensive community glossary from Grok TPOT-native feedback, rewrote LLM prompt with 13 few-shot examples + accumulating prior, added principled seed concentration, extracted rich tweet context from existing API data, fetched 21K+ outbound edges. Round 1 (50 accounts) was started with old prompt and killed — 2 of 50 accounts saved. All code committed and pushed.

## Resume Instructions
1. **Re-run Round 1 with NEW prompt**: `.venv/bin/python3 -m scripts.active_learning --round 1 --top 50 --ego adityaarpitha --budget 2.50` — now uses glossary, few-shots, context extraction, accumulating prior
2. **Chrome-audit blind accounts** — visit each account's tweets in Chrome, compare LLM bits vs actual content, store corrected observations to resolved_accounts.bio and tweet_label_set.note
3. **Run measure**: `.venv/bin/python3 -m scripts.active_learning --measure`
4. **Re-propagate**: `.venv/bin/python3 -m scripts.propagate_community_labels --use-archive-graph --save`
5. **Check recall**: `.venv/bin/python3 -m scripts.verify_holdout_recall`
6. **Fetch following lists for Round 1's new accounts** (same pattern as today's 21K edge fetch)
7. **Label @So8res**: `--accounts So8res`
8. **Re-export + deploy**

## Key Context for Next Instance

### The Pipeline
```
scripts/active_learning.py --round 1 --top 50 --ego adityaarpitha --budget 2.50
```
Three selection modes: `--ego` (proximity boost from follow graph), `--accounts handle1,handle2` (direct), default (info_value ranking).

### Critical Design Decisions
- **Regen/metacrisis IS TPOT** — Game B, metamodern, polycrisis all tracked. NOT adjacent.
- **Principled concentration** — `sqrt(total_bits/50) × (1 - normalized_entropy)`. Weak evidence propagates weakly.
- **Context extraction is FREE** — twitterapi.io already returns quoted_tweet, media URLs, expanded links. Just parse them.
- **Chrome verification is mandatory** — automated pipeline gets ~70% right. Chrome investigation catches keyword false matches, missing bio context, invisible images.
- **Accumulating prior** — each tweet sees the running bits profile and focuses on surprising evidence.

### Known Failures to Watch
1. Keyword → community false matches ("Claude Code" → LLM-Whisperers, "institutions" → NYC)
2. Core-TPOT over-assignment as default bucket
3. Retweet content attributed to retweeter
4. Bio invisible for accounts not in profiles table

### DB State
- 29 labeled accounts, 21K+ new outbound edges
- Total graph: ~441K edges
- $0.95 of $5.00 Twitter API budget spent
- config/community_glossary.json: 15 communities + 13 emerging + 46 themes + 13 few-shots

### Accounts to Label Next
- @So8res (id=245375936) — user requested
- @mykola — 109K archive tweets, in holdout (match_type='seed')
- Remaining 48 from Round 1 (were killed, need re-run with new prompt)

### Memory Files
- `memory/project_session9_handover.md` — detailed session state
- `config/community_glossary.json` — labeling guide (load into prompts)
- `docs/superpowers/specs/2026-03-23-active-learning-loop-design.md` — spec
- `docs/superpowers/plans/2026-03-23-active-learning-loop.md` — plan
