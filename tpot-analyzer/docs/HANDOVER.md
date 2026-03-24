# Handover: 2026-03-23 (Session 8b final — UX Polish, CI, Faint Tier, 23K Accounts)

## Session Summary

Massive session: redesigned About page (3-path selector), wrote 106 tests, built
auto-export pipeline, fullscreen card gallery with version history, Gemini Pro community
banners (15), Grok-written descriptions (15), migrated community colors to iconography,
resolved 25K+ usernames (18K free + 7.7K API), added faint tier (8K→23K searchable),
CI-driven card opacity, fixed tier mapping bug, standardized back button, deployed ~15 times.

## Commits This Session (selected)

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

### Blocked

1. **Git-connected Vercel deploys** — data.json (19MB) gitignored
   - Currently using: `vercel build --prod && vercel deploy --prebuilt --prod && vercel alias`
   - Root directory on Vercel dashboard must stay EMPTY for CLI deploys

### Deferred

1. Community lifecycle operators (birth/merge/split)
2. Canonical membership table
3. Active learning loop (plan written, partial implementation)
4. personalization.js parsing
5. Remaining 163K unresolved follows ($250 to resolve all)

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

## Resume Instructions

1. Read `docs/SESSION8_IDEAS_INVENTORY.md` for full roadmap
2. **First**: Build gallery toggle (all-cards vs per-account)
3. **Second**: Fix browser back button (popstate in useRouting.js)
4. **Third**: Generate About page images
5. Deploy: `cd public-site && npx vercel build --prod && npx vercel deploy --prebuilt --prod --yes && npx vercel alias <url> amiingroup.vercel.app`

---
*Handover by Claude Opus 4.6 at very high context usage, 2026-03-23*
