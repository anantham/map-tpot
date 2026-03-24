# Handover: 2026-03-23 (Sessions 8b+9 — UX Polish, Active Learning Pipeline, 23K Accounts)

## Session Summary

**Session 8b**: Redesigned About page (3-path selector), wrote 106 tests, built
auto-export pipeline, fullscreen card gallery with version history, Gemini Pro community
banners (15), Grok-written descriptions (15), migrated community colors to iconography,
resolved 25K+ usernames (18K free + 7.7K API), added faint tier (8K→23K searchable),
CI-driven card opacity, fixed tier mapping bug, standardized back button, deployed ~15 times.

**Session 9**: Built full active learning pipeline (select → fetch → context → 3-model
ensemble → consensus → rollup → seed insertion). 8 files, 85 tests. Enriched 6 accounts
($0.55 of $5). Added diverse sampling + community glossary + RT dedup. Expanded glossary
from 26-account audit.

## Commits (selected, both sessions)

### Session 8b
- `d4bbb39` feat: fullscreen lightbox + auto-export pipeline
- `57acba9` feat: card version history (KV array, carousel)
- `0a30935` feat: Grok descriptions + iconography colors
- `1ed61d6` feat: Gemini Pro community banner images
- `c005391` feat: batch resolve follow IDs to usernames
- `ace1ce8` feat: faint tier — unknown-band accounts searchable
- `c9f6f33` fix: support new band tiers in search (THE BIG BUG)
- `6e427f8` feat: CI score as number + opacity
- `7d064c7` feat: CI-aware messaging (identified/detected/glimpsed)
- `99f9165` fix: regenerate button busts server cache
- `dae16ba` fix: back button + gallery merges local cards
- `e8a8ccf` fix: fullscreen persists grayscale/opacity
- `1ee1cbe` fix: fixed back button — top-left every page

### Session 9
- `596924c` fix(security): harden API for production deployment
- `2161f83` test(frontend): add tests for storage, communitiesApi, labelingApi, fetchClient
- `68c2339` chore: remove dead ClusterView.utils.js
- `5bb870d` test(frontend): add tests for clusterGeometry, tweetText, graphTransform
- `5cd38f7` fix(tests): align test assertions with standardized API contracts
- `8fb77cf` feat(active-learning): diverse sampling + community glossary + RT handling
- `104a5bf` docs(glossary): expand community glossary from full 26-account audit

PUSHED: Yes, all to origin/main. Site deployed at amiingroup.vercel.app.

## Pending Threads

### Continue Immediately (Next Session Priority)

1. **Gallery toggle: all-cards vs per-account carousel**
   - User wants: click card in gallery → go to `/?handle=X` fullscreen (shareable URL)
   - Toggle button: "all cards" mode (current cross-card carousel) vs "individual" mode (per-account versions)
   - In individual mode, clicking any card navigates to that handle's page
   - Files: `CardGallery.jsx`, `useRouting.js`, `CommunityCard.jsx`

2. **Browser back button doesn't work**
   - Site uses pushState but doesn't handle popstate consistently
   - User expects browser back to work like any normal site
   - Files: `useRouting.js` — needs popstate listener

3. **About page images** — 4 prompts drafted, not generated yet
   - Hero, Path A (illegibility), Path B (portal), Path C (propagation)
   - Use Gemini Pro 21:9, same pipeline as community banners

4. **438K signed reply count** — About.jsx claims 438K, DB has 17,362
   - Need to verify and fix

### Active Learning Pipeline (Session 9 — built, needs scaling)

1. **Full Round 1** — `--round 1 --top 50 --ego adityaarpitha --budget 2.50`
2. **Check earthlypath/YeshodharaB results** — were running when session 9 ended
3. **@mykola labeling** — in holdout (match_type='seed'), need to relax guard or label from archive separately
4. **Round 2** — deepen ambiguous accounts with advanced_search
5. **Per-model label storage** — orchestrator stores only consensus, not per-model rows
6. **TF-IDF precompute** — needed for Round 2 context

### Blocked

1. **Git-connected Vercel deploys** — data.json (19MB) gitignored
   - Currently using: `vercel build --prod && vercel deploy --prebuilt --prod && vercel alias`
   - Root directory on Vercel dashboard must stay EMPTY for CLI deploys

### Deferred

1. Community lifecycle operators (birth/merge/split)
2. Canonical membership table
3. personalization.js parsing
4. Remaining 163K unresolved follows ($250 to resolve all)
5. Re-export + deploy after active learning rounds

## Key Context

- **Deploy flow**: `cd public-site && npx vercel build --prod && npx vercel deploy --prebuilt --prod --yes && npx vercel alias <url> amiingroup.vercel.app`
- **Vercel project**: `find-my-ingroup`, root directory EMPTY on dashboard
- **THE BIG BUG**: Export uses tiers exemplar/specialist/bridge/frontier/faint, but App.jsx only recognized classified/propagated → everything showed "not found". Fixed in `c9f6f33`.
- **CI formula**: `top_weight × (1 - none_weight) × (1 - entropy)` — computed in export for all 23K accounts
- **CI → display**: opacity 0.3–1.0, messaging: ≥15% "Identified", 5-15% "Detected", <5% "Glimpsed"
- **Regenerate (↻)**: now sends `force: true` to server, busting Redis 24h cache
- **Gallery merge**: local cards + server cards, local wins (prevents new cards disappearing)
- **Back button**: position fixed, top 12px left 12px, z-100, backdrop blur, 44px min target
- **Community banners**: 15 Gemini Pro images in `public-site/public/images/communities/`
- **Flash drafts**: preserved in `flash-drafts/` subfolder (not committed)
- **twitterapi.io**: needs User-Agent header, 1.3M credits remaining, key works
- **23,578 accounts**: 317 exemplar + 4,850 specialist + 2,113 bridge + 1,187 frontier + 15,111 faint
- **Active learning models**: Grok-4.1-fast + DeepSeek-v3.2 + Gemini-3.1-flash-lite via OpenRouter
- **Active learning --ego flag**: proximity boost from follow graph (hop1=3x, hop2=1.5x)
- **Holdout recall**: unchanged at 1.7% after 4 seeds (graph sparsity is bottleneck, not seed quality)
- **Community glossary**: `config/community_glossary.json` — 26-account audit, rich exemplar descriptions

## Resume Instructions

1. Read `docs/SESSION8_IDEAS_INVENTORY.md` for full roadmap
2. Read memory file `project_session9_handover.md` for active learning state
3. **First**: Build gallery toggle (all-cards vs per-account)
4. **Second**: Fix browser back button (popstate in useRouting.js)
5. **Third**: Generate About page images
6. **Fourth**: Run active learning Round 1 (`--round 1 --top 50 --ego adityaarpitha --budget 2.50`)
7. Deploy: `cd public-site && npx vercel build --prod && npx vercel deploy --prebuilt --prod --yes && npx vercel alias <url> amiingroup.vercel.app`

---
*Handover by Claude Opus 4.6 at post-compaction context, 2026-03-23*
