# Handover: 2026-03-20

## Session Summary

Massive session. Took the project from security hardening through full public site deployment with AI-generated collectible cards, then pivoted to improving the labeling pipeline for the content-aware community detection phase.

## Commits This Session (main branch, not pushed)
- `596924c` fix(security): harden API for production deployment
- `34177bd` docs(public-site): design spec and implementation plan
- `a3a8267` feat(public-site): add export config
- `3f9793f` feat(public-site): add export script (28 tests)
- `eb7f3ec` feat(public-site): scaffold Vite + React app
- `1608039` feat(public-site): SearchBar, CommunityCard, ContributePrompt, CardDownload
- `47333d1` fix(export): relax abstain gate (551 → 9,263 accounts)
- `f4d05c2` chore: vercel gitignore
- Multiple JIT card commits: serverless function, prompt builder, BYOK settings, tarot styling
- `544b676` fix: switch to ioredis for Redis Cloud
- `b937ca1` fix: correct Gemini model ID
- `f4522af` fix: typewriter generating banner
- `1419dca` feat: shareable URLs and copy-link button
- `8e29793` fix: grayscale AI cards for propagated accounts
- `ee2eafe` feat: about page with methodology + infographics
- `6e676e0` feat: homepage redesign with hero + community showcase
- `865170b` feat: per-user rate limit (10 free generations)
- Golden tags system: backend + frontend + LLM suggestions
- Likes index fix (85s → 0.001s)
- Tweet date links to x.com

PUSHED: No — many commits ahead of origin

## What's Deployed
- **https://amiingroup.vercel.app** — public site with AI collectible cards
- Vercel env vars: OPENROUTER_API_KEY, CARD_DAILY_BUDGET=5.00, KV_REDIS_URL
- Redis Cloud for caching + budget tracking (may need REST credentials verified)

## Pending Threads

### Continue Immediately: Account-First Labeling Workflow

**The big insight from this session:** Simulacrum levels should be assigned at the ACCOUNT level indexed by time, not per-tweet. Each tweet is a sample from the account's epistemic generator at that timestamp. With enough samples across time, you reconstruct the trajectory.

**What to build:**
1. **Account picker in labeling UI** — let user choose which account to label (start with @eshear, @repligate, @Plinz, @nickcammarata)
2. **Batch mode** — show 10-20 tweets from one account sorted by date
3. **Account-level summary** — after labeling N tweets, show the aggregate L1/L2/L3/L4 distribution for that account over time
4. **Temporal trajectory view** — plot how the account's epistemic stance shifts over months/years

**No schema change needed** — tweet labels already have account_id + created_at. Aggregation is downstream.

**Accounts not in archive:** @Plinz and @nickcammarata are NOT in the archive (only @eshear and @repligate found). May need to fetch their data.

### Continue: About Page Rewrite

**The current about page is too technical.** User wants a story-first approach:
1. Start with PEOPLE (Aditya, Arun, Devi) not nodes
2. Motivate each algorithm step (WHY, not just HOW)
3. Explain what data we have and what contributing unlocks
4. Frame communities as attractors/gravitational fields, not boxes
5. Regenerate infographics with `google/gemini-3-pro-image-preview` (better text rendering)
6. Add representative accounts per community

**Narrative arc designed but not yet written:**
People → The question → The data → The gap → Follow graph (motivated) → Natural groups (motivated) → Naming communities (motivated) → Reaching everyone (motivated) → Your card → Contribute

### Continue: Content-Aware Community Detection

**Key insight:** Topic tags (object-level: "alignment", "jhanas", "LLM psychology") may be more useful for community discovery than simulacrum levels. The current 14 communities are topic-based (from follow/retweet NMF), so topic classification on tweets would directly validate and refine them.

**Two competing axes identified:**
1. Community discovery: what groups exist? (unsupervised)
2. Community assignment: who belongs where? (classification)

These interact — tweet content may reveal NEW communities the graph didn't find.

**Approach:** Topic tags from human labeling bootstrap automatic classification. LLM suggests tags, human curates. The tag vocabulary grows organically and becomes the feature set for content-aware NMF.

### Deferred
1. **Gallery view** — show all previously generated cards in a browsable gallery. Redis already caches them.
2. **Video generation** (Veo 3.1) — v2 stretch goal
3. **Profile pic as input** — v2 user upload
4. **OpenGraph previews** — server-rendered social cards for link sharing

## Key Context

### Architecture (as of now)
- **Public site:** `tpot-analyzer/public-site/` — Vite + React, deployed to Vercel
- **Serverless function:** `public-site/api/generate-card.js` — OpenRouter Gemini image gen, ioredis caching
- **Export:** `scripts/export_public_site.py` — 33 tests, produces data.json + search.json
- **Budget:** $5/day global (Redis) + 10/user (localStorage), configurable
- **Labeling:** Topic tags added to golden schema, LLM suggests tags on interpret

### User Preferences (captured in memory)
- Prefers JIT generation over precomputation
- Wants justification for every fix before implementing
- Sees communities as attractors/gravitational fields, not static boxes
- Wants the about page to tell a story starting with people, not math

### Things That Need Fixing
- Vercel deployment protection was disabled — may want to re-enable for preview deployments only
- Redis REST credentials may not be fully configured (KV_REDIS_URL is set but REST API URL/token unclear)
- @Plinz and @nickcammarata not in archive — need data fetch
- About page infographics have spelling errors (Gemini Flash text rendering) — regenerate with Pro

## Resume Instructions
1. Read this handover
2. Push commits to origin (many ahead)
3. Build account-first labeling workflow (the immediate next feature)
4. Start with: account picker → batch tweet display → temporal sorting
5. Then: rewrite about page with story arc

---
*Handover by Claude at high context usage, 2026-03-20*
