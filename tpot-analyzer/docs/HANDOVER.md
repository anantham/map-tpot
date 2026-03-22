# Handover: 2026-03-22 (Session 5)

## Session Summary

Community detail pages + card infrastructure session. Built clickable community pages for Find My Ingroup (prototypical member spotlights with tweets, all-members sidebar, sibling nav, browser back/forward). Added card caching (localStorage + Vercel KV gallery), Share-to-X with OG card previews, card regeneration button, enriched card prompt with community descriptions. Portfolio fixes: hover behavior, Dāna link, Map TPOT URL.

## Commits This Session (TPOT — 15 commits, NOT pushed to origin)

14+ commits ahead of origin/main. Push when ready: `git push`

Key commits:
- Community detail pages (export enrichment, CommunityPage component, useRouting hook, CSS)
- Card caching + server gallery (localStorage + Vercel KV + `/api/gallery` endpoints)
- Share-to-X with OG meta tags (`/api/og`, `/api/card-image`)
- Card regeneration button (↻)
- Enriched card prompt (community descriptions, anti-text constraints)
- Portfolio link in footer

## Pending Threads

### Continue Immediately

1. **Portfolio journey/camera bug** — Camera doesn't follow pill during A→B travel, pill movement is discontinuous. Inspect `CesiumJourneyExperience.tsx` and `CesiumViewerClient.tsx` for data continuity and camera follow logic. Uncommitted changes exist in these files.

2. **Push TPOT commits** — 14+ ahead of origin/main.

3. **Card gallery incognito test** — Server gallery has 2 cards. Never verified server-side fetch works in clean browser.

### Blocked

1. **Card history/carousel** — Needs Vercel Blob for storage (~1MB/card × many). KV free tier too small.

### Deferred

1. **Vancouver TPOT labeling** — 10+ accounts identified, parked for UI work
2. **Bits-derived profile on cards** — 213 bits for @repligate in DB, not displayed on public site
3. **15th community "Interesting"** — appeared in export, may need filtering

## Architecture Notes

### Community Pages
- `export_public_site.py`: slug assignment, featured_members (top 5), all_members, tweet selection with type detection
- `slug_registry.json`: persists slugs across renames
- `useRouting.js`: 3-way state (community > handle > homepage), pushState + popstate
- `CommunityPage.jsx`: two-column (spotlights left, members right), full-width layout
- `.app-wide` class overrides 640px max-width

### Card Gallery
- `/api/generate-card.js`: writes to `gallery` KV hash (permanent) + `card:{handle}` (24h TTL)
- `/api/gallery.js`: GET all cards
- `/api/gallery-submit.js`: POST for BYOK cards
- `/api/card-image.js`: decodes base64 → serves PNG (for OG tags)
- `/api/og.js`: twitter:card meta tags + redirect

### Portfolio
- Project card hover: 1s delay, 0.9s expand, spring layout (160/28), no reorder
- Dāna links to innerwilds.blog
- Map TPOT links to amiingroup.vercel.app

## Resume Instructions
1. Push TPOT commits
2. Debug portfolio Cesium camera/pill
3. Test gallery in incognito
4. Or: Vancouver accounts labeling

---

# Handover: 2026-03-21 (Session 4)

## Session Summary

Card integration session: wired bits-derived profiles to public site export, labeled @dschorno (10 tweets, first non-AI community signal), built rich AI interpret pipeline with full DB context, added interpretation run storage for model comparison. Major model spec updates: community profiles for Quiet Creatives/highbies, engagement signal protocol, community description sync cadence.

## Commits This Session
- `10d391c` feat(labeling): card integration, rich interpret pipeline, dschorno labels

PUSHED: No — now 6 commits ahead of origin

## Key Accomplishments

### 1. Card Integration (Bits → Display)
- `community.short_name` column added to all 14 communities
- `account_community_bits` migrated from `community_name` (string) → `community_id` (FK)
- Export overlay: `extract_classified_accounts()` checks bits (posterior) first, falls back to NMF (prior)
- Repligate card now shows correct 4-community profile (was 100% Qualia → now 39% LLM-Whisperers, 32% Qualia, 16% AI-Safety, 10% Contemplative)
- 8 community descriptions updated in DB from labeling evidence

### 2. @dschorno Labeled (10 tweets, 85 tags, 28 bits)
```
  46.4%  highbies (+13 bits)
  35.7%  Quiet-Creatives (+10 bits)
  10.7%  Emergence-Self-Transformation (+3 bits)
   7.1%  Contemplative-Practitioners (+2 bits)
```
vs NMF: 55% Quiet Creatives, 44% highbies (ordering flipped, picked up 2 new communities)

### 3. Rich AI Interpret Pipeline
- `src/api/labeling_context.py` — context gatherer (account profile, engagement, similar labeled tweets, community profiles, thematic glossary)
- `_build_rich_interpret_prompt()` in golden.py — sends full DB context to LLM
- `/interpret` endpoint supports `mode: "rich"` with `tweet_id` param
- `interpretation_run` + `interpretation_prompt` tables store prompt + model_id + response for comparison
- JSON parser handles `+N` syntax from LLM output
- Prompt includes tweet timestamp + account bio/display_name

### 4. AI vs Human Comparison (Kimi K2)
Tested all 10 dschorno tweets. Key findings:
- **Themes**: Strong agreement on absurdist-humor, self-transformation, creative-expression
- **Bits inflation**: AI consistently assigns +3 where humans gave +2
- **Political tweet fail**: AI hallucinates AI themes because it confuses "context" (word) with AI context windows — needs image context
- **Meditation tweet disagreement**: AI gives Contemplative-Practitioners:-1 (skepticism = against), humans gave +2 (knowing vocabulary = adjacent). **Correct interpretation: sustained engagement even as skeptic = positive bit. One-off dismissal = negative bit.**

## Pending Threads

### Continue Immediately: Label @daniellefong + @SarahAMcManus
Two more Vancouver accounts for cross-community signal:
- @daniellefong — Builders 59%, LLM Whisperers 15%, 99K tweets, latest Nov 2024
- @SarahAMcManus — Contemplative Practitioners 69%, 9K tweets, latest Sep 2024

Use the review HTML generator pattern (dschorno_review.html) — pick top engagement tweets, generate full-label review page.

### Continue: Enrich AI Pipeline
Gaps identified but not yet built:
1. **Images**: No media URLs in tweets table. Need t.co resolution or Chrome screenshot → multimodal model
2. **Quote tweet context**: Need to resolve quoted tweets and include original text
3. **Retweet context**: When tweet IS a retweet, fetch the original
4. **Model comparison leaderboard**: Tables exist (`interpretation_run`), need scoring function (bits direction agreement, theme F1, distribution KL-divergence) + run multiple models

### Continue: Review @dschorno Labels
User has `dschorno_review.html` open. May give corrections on:
- Missing themes (user noted jhana should be a theme, absurdist-humor was missing)
- Negative bits usage (only for nearby communities, not distant ones)
- Engagement context (check who replied to each tweet)

### Deferred: Community Evolution
Need 3+ labeled accounts before cross-account thematic clustering makes sense. After daniellefong + SarahAMcManus, will have 4 accounts across 8+ communities.

### Deferred: Deploy
- Export re-run needed after next labeling round
- `vercel --prod` from public-site/ to deploy
- Re-alias to amiingroup.vercel.app

## Key Context

### New Tables Created This Session
- `community.short_name` — stable labeling handle per community (e.g., "LLM-Whisperers")
- `interpretation_run` — stores tweet_id, model_id, prompt_hash, response_json, created_at
- `interpretation_prompt` — stores prompt_hash → full prompt text (deduplicated)

### Model Spec Updates (LABELING_MODEL_SPEC.md)
- **Community profiles**: Quiet Creatives, highbies (expanded), Emergence (expanded) — with exemplar tweets from dschorno
- **Thematic tags added**: `theme:absurdist-humor`, `theme:contemplative-practice`, `theme:creative-expression`
- **All 14 community short_names** listed in bits section
- **Engagement Signal section**: credibility hierarchy (follow > RT > like > reply), two-way flow, account discovery from reply threads
- **Negative bits principle**: only for nearby communities ("would this tweet surprise a member?")
- **Community Description Sync**: mandatory cadence — after each account, before handover, before deploy

### User Insights (Session 4 Discoveries)
- NMF = prior, bits = posterior. The card should show posterior when available, fall back to prior.
- Community names are mutable (short_name is the stable handle, UUID is the FK, display name can evolve)
- Sustained skeptical engagement = positive community bit (knowing the vocabulary = being adjacent). One-off dismissal = negative bit.
- Engagement in reply threads is community evidence + account discovery vector
- "Posting into the void" (chips tweet) is low but nonzero signal — trust in audience IS community membership
- The AI interpret pipeline should store prompts + model IDs for leaderboard comparison
- Images/links/quote tweets are critical missing context for AI interpretation

### Files Changed
- `src/communities/store.py` — short_name column, account_community_bits table schema
- `scripts/migrate_community_short_names.py` — NEW migration script
- `scripts/export_public_site.py` — bits overlay in extract_classified_accounts
- `scripts/labeling_context.py` — reads from rollup table
- `src/api/labeling_context.py` — NEW context gatherer
- `src/api/routes/golden.py` — rich interpret prompt, run storage
- `docs/LABELING_MODEL_SPEC.md` — community profiles, engagement signal, sync cadence
- `tests/test_export_public_site.py` — 3 new bits overlay tests
- `dschorno_review.html` — review page with full label cards

## Resume Instructions
1. Read `docs/LABELING_MODEL_SPEC.md` + this handover
2. Check if user gave corrections on dschorno labels (review dschorno_review.html)
3. Pick @daniellefong (Builders) — run `scripts/labeling_context.py daniellefong`
4. Pull top engagement tweets, generate review HTML, label ~10
5. After labeling: update model spec community profiles, sync to DB descriptions, compute rollup
6. After 3+ accounts: attempt cross-account thematic clustering

---
*Handover by Claude at high context usage, 2026-03-21*
