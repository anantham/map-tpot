# Handover: 2026-03-19

## Session Summary

Took the project from "research tool" to "deployed public site." Started with a tech debt surface scan (5 dimensions, 26 issues), triaged to 6 worth fixing, implemented security hardening (error sanitization, loopback fix, rate limiting, headers). Then pivoted to the real goal: public hosting. Interviewed the user to capture the distribution vision (power users + casual users, static site, growth flywheel). Designed, specced, and built the "Find My Ingroup" static site — export pipeline + Vite/React frontend. Deployed to Vercel at https://amiingroup.vercel.app with 9,263 searchable accounts.

Session ended with a new feature direction: **JIT collectible card generation** using OpenRouter image generation, replacing the current bar-chart cards with AI-generated collectible-style artwork per account.

## Commits This Session
- `596924c` fix(security): harden API for production deployment
- `34177bd` docs(public-site): add design spec and implementation plan
- `a3a8267` feat(public-site): add export config for public site
- `3f9793f` feat(public-site): add export script for Find My Ingroup data pipeline
- `eb7f3ec` feat(public-site): scaffold Vite + React app
- `1608039` feat(public-site): add SearchBar, CommunityCard, ContributePrompt, CardDownload components
- `6479fc5` chore: gitignore public-site generated data and build artifacts
- `5757eb3` docs(audit): full doc audit remediation
- `47333d1` fix(export): relax abstain gate for public site reach
- `f4d05c2` chore: add vercel-generated gitignore for public-site

PUSHED: No — 10 commits ahead of origin/main

## Pending Threads

### Continue Immediately
1. **JIT Collectible Card Generation**
   - Status: Vision agreed, not designed or implemented
   - What: Replace bar-chart community cards with AI-generated collectible artwork
   - Key decisions already made:
     - Use OpenRouter (Gemini Flash image preview) for generation
     - Vercel serverless function (`/api/generate-card`) proxies calls with curator's API key
     - $5/day budget cap, first-come-first-served
     - Settings icon for BYOK (bring your own key) stored in localStorage
     - Unified prompt template: same collectible card aesthetic for all accounts
     - Prompt uses account data: bio, tweets, communities, mutuals for personalization
   - Architecture needed: Vercel serverless function (new — site was fully static before)
   - Next step: Design the prompt template + serverless function, then implement
   - Files to create: `public-site/api/generate-card.js` (Vercel serverless), prompt template
   - Cost model: ~$0.02/image at Gemini Flash rates, $5/day = ~250 cards/day
   - Consider: card caching (don't regenerate same handle within 24h)

### Blocked
None

### Deferred
1. **Spec/export schema mismatch** — The spec doc (`2026-03-19-find-my-ingroup-design.md`) diverges from actual implementation on JSON schema details (meta.counts nesting, search.json entry shapes). The frontend and export are internally consistent. Update the spec to match reality, or leave as-is since the JIT cards feature will change the frontend significantly anyway.

2. **Abstain gate tuning** — Currently at 0.08 threshold with abstain_mask ignored. Only 253 propagated handles had the mask=False; ignoring it expanded to 8,965. If label propagation is re-run with better seeds (after more golden labeling), revisit these thresholds.

3. **Tech debt items deferred from scan** — graphTransform.js tests, Discovery/Labeling component tests, ADRs for cluster expansion. See the tech debt scan output earlier in this session.

## Key Context

### Architecture (as of now)
- **Export script**: `scripts/export_public_site.py` reads SQLite + NPZ + Parquet, produces `data.json` (169KB, 14 communities + 298 classified) and `search.json` (5.3MB, 9,263 handles)
- **Frontend**: `tpot-analyzer/public-site/` — Vite + React, single page app
- **Deployed**: https://amiingroup.vercel.app (alias set manually via `vercel alias set`)
- **Community data**: 14 NMF communities with names/colors, 298 direct members, 8,965 propagated from follow graph

### The visual design intent for JIT cards
- User wants "collectible card" aesthetic — not progress bars
- Each card should be unique, generated from the account's actual data
- Grayscale cards for propagated accounts should STILL incentivize data contribution
- The prompt should use: bio, sample tweets, community names + weights, mutual connections
- Same prompt template for all cards (unified aesthetic, like a trading card series)
- Generated images should be downloadable as PNG (replaces current canvas-to-PNG)

### Security hardening already done
- `MAX_CONTENT_LENGTH` (16MB), security headers (HSTS, X-Frame-Options, etc.)
- Error sanitization: 18 sites, no `str(exc)` leaked to clients
- `/golden/interpret`: token-based auth replacing broken loopback check
- Flask-Limiter: 200/min default, 10/hr interpret, 30/min clusters
- Dockerfile: non-root `appuser`
- `cluster_routes.py`: `@_require_loaded` decorator, `_parse_lens()`, `_require_ego()` helpers

### The user's vision (captured in VISION.md)
- Two user types: power users (clone repo, run locally) and casual users (visit static site)
- Publishing workflow: local analysis → static JSON export → deploy to Vercel
- Growth flywheel: grayscale cards → "contribute your data to see yourself in color"
- Open source: framework + data bundled (v1), separable later if demand

## Learnings Captured
- [x] Updated VISION.md with distribution model sections
- [x] Created docs/reference/ENVIRONMENT_VARIABLES.md
- [x] Created design spec: docs/superpowers/specs/2026-03-19-find-my-ingroup-design.md
- [x] Created implementation plan: docs/superpowers/plans/2026-03-19-find-my-ingroup.md

## Running Processes
None — all background tasks completed

## Resume Instructions
1. Read this handover doc
2. Read VISION.md "Distribution" section for the user's product vision
3. Design the JIT collectible card feature:
   - Vercel serverless function at `/api/generate-card`
   - OpenRouter integration (Gemini Flash image preview)
   - $5/day budget tracking (could use KV store or simple file-based counter)
   - Prompt template that creates unified collectible aesthetic
   - Settings icon for BYOK
   - Card caching strategy (24h by handle?)
4. Consider pushing the 10 commits to origin first

---
*Handover by Claude at high context usage*
