# Handover: 2026-03-30 (Mega-Session — Tech Debt, Validation, Bulk Labeling, CI Rewire)

## Session Summary

Multi-day session across 7 domains: (1) Tech debt — 10/14 items closed: silent exceptions, str(exc), error_response migration, shared paths, split propagation + cluster_routes monoliths, ADR numbering, schema docs. (2) Pipeline — TF-IDF content profiles, thread context, archive-first fetching, LLM backoff. (3) Noise filtering — batch profile fetch (1,428 accounts), CI scaling by true concentration. (4) Validation — veil-of-ignorance CV (AUC 0.999 on seed_neighbors), skeleton keys (17 accounts find 81%), leave-one-community-out (all survive). (5) Bulk labeling — 85 archive accounts profiled at $0 (25 high, 43 ambiguous, 17 no signal). (6) Frontend — CI-driven rendering, evidence summary, removed raw CI %. (7) Infra — Vercel Blob, independent mode bands, API cost corrections.

## Data State
- **2,715,658 edges**, 298,347 nodes, 359 seeds, 16 communities
- **16,650 accounts** in latest export (359 exemplar, 3,279 specialist, 918 bridge, 12,094 frontier)
- CI formula: `min(1.0, top_neighbors / 20)` with concentration scaling

## Key Findings
- **seed_neighbors AUC 0.999** — the correct CI signal (raw propagation = 0.225, worse than random)
- **17 skeleton-key accounts** find 81% of holdout TPOT
- **All communities survive full deletion** — structure is real
- **API costs were 50-67% overestimated** — actual $0.03/page not $0.05

## Commits (28, all pushed)
`125352a` `808608a` `73acbea` `2ae470d` `ff2d865` `b18d7fa` `f9727e4` `3524fb9` `58abc96` `2c31c5e` `0d25e89` `2ff70ab` `0830b6e` `46b2c8e` `0c12102` `4645ddd` `f52046e` `fa4df82` `36a42d5` `0f2961f` `8eabe25` `30d11d4` `8a20fdb` `0778730`

## Resume Instructions
1. **Deploy** — export ready, Vercel config fixed in web UI
2. Other instance has uncommitted Phase 1 audit + multi-scale changes
3. Frontend: "show all" toggle for community pages
4. When budget: `--mode zero-outbound --budget 17` (188 accounts, ~$17)

## Architecture Changes
- `src/propagation/` package (types, engine, diagnostics, io)
- `src/api/cluster/` package (state, views, sidebar, membership, actions)
- `src/config.py` shared constants, `src/data/adjacency.py` shared loader
- `classify_bands.py` independent mode thresholds
- `label_tweets_ensemble.py` exponential backoff
- `fetch_following_for_frontier.py` zero-outbound mode
- Vercel Blob for card images

---
*Handover by Claude Opus 4.6*
