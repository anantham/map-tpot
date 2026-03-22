# Handover: 2026-03-22 (Session 7 — Enrichment Pipeline + 3 Accounts Labeled)

## Session Summary

Massive infrastructure + labeling session. Built the full tweet enrichment pipeline (syndication API for images/quotes/retweets, external link content, thread context). Wired bits-derived profiles to public site export. Labeled 3 accounts (repligate 51, dschorno 10, adityaarpitha 20). Created rich AI interpret endpoint with full DB context + multimodal images. Discovered 17.5M likes + 4.3M replies are NOT being used for community membership — this is the next major priority.

## Commits This Session
- `10d391c` feat(labeling): card integration, rich interpret pipeline, dschorno labels
- `cd5e7b0` docs(model-spec): sustained engagement = community membership
- `524d707` feat(enrichment): syndication API for images/quotes, multimodal interpret
- `6e4e048` feat(enrichment): thread context, external link content, t.co resolution
- `9641ae2` feat(enrichment): retweet source resolution via syndication
- `b02697d` feat(labeling): @adityaarpitha 20 tweets labeled, stabilization check

PUSHED: 1 commit ahead of origin

## Labeled Accounts

```
Account          Tweets  Bits Profile (posterior)                    NMF (prior)
@repligate         51   39% LLM-Whisperers, 32% Qualia, 16% Safety  100% Qualia
@dschorno          10   46% highbies, 36% Quiet-Creatives            55% QC, 44% highbies
@adityaarpitha     20   23% Safety, 23% Contemplative, 22% Emergence 52% Safety, 18% LLM-Whisp
```

All 3 accounts show significant divergence from NMF priors. The bits system is working — posteriors are richer and more accurate.

## Pending Threads

### Continue Immediately: Engagement-Based Community Propagation

**THE BIG NEXT THING.** Raw engagement data exists but is unused:
- 17.5M likes (who liked whose tweets, with liker identity)
- 4.3M reply relationships
- 774K retweets
- 1.6M follower edges

Each engagement carries SPECIFIC community signal. @adityaarpitha liked @repligate 226 times — that's Qualia-Research credibility flowing. @romeostevens76 got 102 likes — Contemplative-Practitioners signal.

**Architecture needed:**
```
Account A (community weights) engages with Account B
  → B gets community-weighted signal from A
  → Signal = A's community weights × engagement_type_weight
  → follow=1.0, RT=0.7, reply=0.5, like=0.3
  → Propagation: PageRank-style iterative until convergence
```

**Key design decisions:**
- Bits (content-based) are prior-independent — never need re-propagation
- Engagement (structural) depends on engager's membership — needs re-propagation when memberships update
- Keep these separate — combine at rollup level
- Use existing `propagate_community_labels.py` as template

**adityaarpitha engagement data (already computed):**
```
Top likes: 226x @repligate, 102x @romeostevens76, 54x @algekalipso, 45x @visakanv
Top reply targets: 17x @repligate, 9x @algekalipso, 8x @Tymtweet
Top repliers: 6x @hrosspet, 5x @lu_sichu, 4x @repligate
```

### Continue: Label @daniellefong + @SarahAMcManus

- @daniellefong — Builders 59%, 99K tweets. Top tweets already pulled.
- @SarahAMcManus — Contemplative 69%. Potential 3rd signal for community birth.

### Continue: Community Birth Decision

7 new-community signals:
- 5x "AI Mystics" (repligate)
- 2x "Contemplative-Alignment" (adityaarpitha)
- Likely same emerging community. Need 1 more account to trigger birth.
- User: keep vibes-based for now, formalize after 10+ accounts.

### Continue: Model Comparison

Tables exist (`interpretation_run`, `interpretation_prompt`) but no runs stored through API yet. Need scoring function + multi-model comparison.

### Deferred: Wire Rich Interpret to Labeling UI

"Get AI Reading" button still uses legacy prompt. Needs `mode: "rich"` + frontend changes to display all dimensions.

## Key Context

### New Infrastructure (This Session)

| Component | File | What it does |
|-----------|------|-------------|
| Tweet enrichment | `src/api/tweet_enrichment.py` | Syndication API: images, quotes, retweets, link content. All cached. |
| Labeling context | `src/api/labeling_context.py` | Gathers ALL context: profile, engagement, similar tweets, top tweets, thread, enrichment |
| Rich interpret | `golden.py:_build_rich_interpret_prompt()` | Multimodal prompt with full DB context |
| Run storage | `interpretation_run` table | Stores prompt + model + response for comparison |
| Export overlay | `export_public_site.py` | Bits override NMF for classified accounts |
| Community short_names | `community.short_name` column | Stable labeling handles (UUID is FK, name is mutable) |

### Model Spec Updates

- Sustained engagement = community membership (not just agreement)
- Negative bits only for nearby communities
- Engagement Signal protocol (follow > RT > like > reply)
- Community Description Sync (mandatory cadence)
- New profiles: Quiet Creatives, highbies, Emergence (with exemplars)
- New themes: rationalist-fiction, field-building, wholeness-integration, absurdist-humor, contemplative-practice, creative-expression

### Critical User Insights

1. Engagement data is the biggest untapped signal — must build propagation
2. Follow graph > tweet content for structural community signal
3. Community birth is vibes-based until 10+ accounts labeled
4. Bits are prior-independent — NMF prior gets drowned out with evidence
5. AI (Kimi/Gemini) systematically: gives wrong negative bits, never proposes births, over-attributes L2
6. Pick tweets by engagement not recency
7. Review HTML must show ALL dimensions with no truncation
8. The circularity concern: engagement propagation needs convergence guarantee (PageRank-style)

## Resume Instructions

1. Read `docs/LABELING_MODEL_SPEC.md` + this handover
2. **Priority 1**: Build engagement-based community propagation (aggregate typed edges → weighted community signal → iterate until convergence)
3. **Priority 2**: Label @SarahAMcManus — check for Contemplative-Alignment birth
4. **Priority 3**: Wire rich interpret to Labeling UI
5. Before closing: sync community descriptions, compute rollups, re-export

---
*Handover by Claude at high context usage, 2026-03-22*
