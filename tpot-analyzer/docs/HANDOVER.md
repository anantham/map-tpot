# Handover: 2026-03-22 (Session 7 continued — 20 Accounts Labeled)

## Session Summary

Labeling marathon: went from 3 accounts to 20 accounts (446 tweets). Built membership confidence index (5-factor CI validated as stability predictor). Integrated twitterapi.io for non-archive accounts ($1.45 of $20 spent). Built engagement aggregation (408K edges). Revised propagation architecture per code review. Created operational runbook. Identified massive untapped data (17.5M likes, 4.3M replies, bookmarks, X lists) and wrote comprehensive roadmap.

## Commits This Session (9 ahead of origin — NOT PUSHED)
- `b02697d` feat(labeling): @adityaarpitha 20 tweets labeled, stabilization check
- `6945ebb` docs(handover): session 7 — enrichment pipeline
- `706953c` docs(model-spec): engagement propagation architecture design
- `c2ab032` refactor(propagation): revise architecture per code review
- `894ae08` chore: engagement aggregation built (408K edges)
- `c9f0fc9` docs: twitterapi.io endpoint map
- `602a433` feat(confidence): membership confidence index
- `78151e9` feat(labeling): 12 accounts, runbook, CI, engagement graph
- `81251fc` docs: next priorities roadmap

PUSHED: NO — `git push` needed

## All 20 Labeled Accounts

```
Account              CI     Level                Tweets  Bits  Source
@adityaarpitha      0.745   bits_stable            30    108   archive
@RomeoStevens76     0.775   bits_stable            20     67   API
@eshear             0.681   bits_stable            20     59   archive
@dschorno           0.673   bits_stable            20     28   archive
@QiaochuYuan        0.664   bits_stable            19     62   archive
@repligate          0.658   bits_stable            61    213   archive
@the_wilderless     0.645   bits_stable            20     47   archive
@imperialauditor    0.596   bits_stable            19     35   archive
@pee_zombie         0.517   bits_partial           19     81   archive
@nosilverv          0.496   bits_partial           19     25   archive
@visakanv           0.477   bits_partial           19     13   archive
@nickcammarata      0.360   bits_partial           32    148   API
@bhi5hmaraj         0.337   follow_propagated      21     76   API
@vyakart            0.302   follow_propagated      20     54   API
@Plinz              0.296   follow_propagated      16     56   API
@uh_cess            0.285   follow_propagated      20     36   API
@manohcore          0.277   follow_propagated      20     30   API
@metaforicalmuth    0.241   follow_propagated      16     12   API
@vorathep112        0.224   follow_propagated      16     11   API
@xuenay             0.223   follow_propagated      19      8   API
```

## Pending Threads

### Continue Immediately

1. **Likes into NMF feature matrix** — biggest single improvement
   - 17.5M likes not used in community detection
   - ~40 LOC in `scripts/cluster_soft.py`
   - See `docs/ROADMAP_NEXT.md` Priority 1a

2. **About page rewrite** — 3-path selector designed but not coded
   - Path A (TPOT-adjacent): discovery/deepening
   - Path B (outsider): onboarding
   - Path C (builder): pipeline walkthrough with 6 stages
   - Full content outline exists in conversation context
   - Visual prompts ready for AI image generation

3. **Push 9 commits** — `git push origin main`

### Blocked

1. **Phase 2 propagation** — need calibrated edge weights
   - Have 9 bits_stable accounts (threshold was 10)
   - Architecture revised per code review — one-hop only, stable seeds only
   - Blocked on: canonical membership table not yet built

2. **Community birth (AI Mystics / Contemplative-Alignment)** — 7 signals from 3 accounts
   - User said: keep vibes-based, don't formalize until more data
   - Blocked on: user decision on when to trigger

### Deferred

1. **Wire rich interpret to Labeling UI** — "Get AI Reading" button still uses legacy prompt
2. **Model comparison leaderboard** — tables exist, no runs stored through API
3. **Reply valence at scale** — free heuristics identified (author-liked-reply), LLM batch for rest

## Key Context

### Infrastructure Built (Persists in DB)

| Table | Rows | Purpose |
|-------|------|---------|
| `account_community_bits` | 20 accounts | Bits-derived community memberships |
| `account_engagement_agg` | 408K edges | Pairwise engagement (likes, replies, RTs, follows) |
| `tweet_enrichment_cache` | ~50 tweets | Syndication API results (images, quotes) |
| `link_content_cache` | ~5 URLs | External link content |
| `interpretation_run` | 0 | Model comparison (tables exist, no API runs stored) |
| `api_endpoint_costs` | 10 endpoints | twitterapi.io cost reference |
| `tweet_tags` | ~2000+ | All labeling tags (domain, thematic, bits, posture, specific) |
| `tweet_label_set` | ~450 | Simulacrum labels + notes |
| `tweet_label_prob` | ~1800 | L1-L4 probability distributions |

### Key Files Created/Modified

| File | What |
|------|------|
| `src/communities/confidence.py` | NEW — 5-factor CI (data_richness, labeling_depth, concentration, network_context, source_agreement) |
| `src/api/tweet_enrichment.py` | NEW — syndication, images, quotes, retweets, links, threads |
| `src/api/labeling_context.py` | NEW — gathers ALL context for AI labeling |
| `scripts/build_engagement_graph.py` | NEW — aggregates 408K engagement edges |
| `scripts/migrate_community_short_names.py` | NEW — community.short_name + bits FK migration |
| `docs/ACCOUNT_LABELING_RUNBOOK.md` | NEW — operational guide with cost tradeoffs |
| `docs/TWITTERAPI_ENDPOINTS.md` | NEW — API endpoint map with costs |
| `docs/ROADMAP_NEXT.md` | NEW — 6 priorities, 20 action items |
| `docs/LABELING_MODEL_SPEC.md` | MAJOR UPDATE — engagement signal, propagation architecture, community profiles |
| `scripts/export_public_site.py` | MODIFIED — bits overlay, CI in export |
| `src/api/routes/golden.py` | MODIFIED — rich interpret prompt, multimodal, run storage |

### Critical User Insights

1. **Sustained engagement = community membership** — using insider vocabulary skeptically is positive evidence (dschorno "gay meditation crap" = Contemplative +2)
2. **Negative bits only for nearby communities** — a contemplative tweet isn't evidence AGAINST AI-Safety
3. **CI validates as stability predictor** — high CI accounts show 0% movement with 10 more tweets; low CI accounts move 4-6%
4. **Followings endpoint is expensive but essential** — 1 page misses 94% of classified accounts (bhi5hmaraj)
5. **Likes are the biggest untapped signal** — 17.5M likes, 24× more than follow graph, no valence problem
6. **Reply valence solvable cheaply** — author-liked-reply + mutual-follow heuristics before LLM
7. **NMF diverges significantly from bits** — every labeled account shows different profile, NMF consistently wrong
8. **twitterapi.io cost model** — followings $0.03/page (expensive), tweets $0.003/page (cheap), standard account ~$0.04-0.08
9. **The prior/posterior framing** — NMF = prior, bits = posterior, engagement = structural evidence. Keep separate, combine at rollup.
10. **Community birth approaching** — 7 new-community-signals (5 AI Mystics + 2 Contemplative-Alignment) across 3 accounts

### API Budget
- twitterapi.io: $1.45 spent of $20 (7.3%), ~370 accounts remaining at standard rate
- OpenRouter: ~$5 spent on AI labeling (gemini-2.5-flash)

## Resume Instructions

1. Read `docs/ROADMAP_NEXT.md` for prioritized action items
2. Read `docs/ACCOUNT_LABELING_RUNBOOK.md` for operational procedures
3. `git push origin main` (9 commits ahead)
4. **Priority 1**: Add likes to NMF feature matrix (~40 LOC in `cluster_soft.py`)
5. **Priority 2**: Build About page 3-path selector (content outlined in conversation)
6. **Priority 3**: Build community lifecycle operators (birth first — 7 signals ready)
7. Before closing any session: sync community descriptions, check new-community-signals, update ROADMAP

---
*Handover by Claude Opus 4.6 at high context usage, 2026-03-22*
