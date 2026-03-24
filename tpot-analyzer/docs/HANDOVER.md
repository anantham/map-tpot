# Handover: 2026-03-24 (Session 10 — UX, Tests, Pipeline Fixes, Independent Propagation, Tech Debt)

## Session Summary

Massive session across 5 domains: (1) Public site UX — SPA routing, gallery toggle, browser back button fix. (2) Testing — 138 new frontend tests from zero + 8 independent mode propagation tests. (3) About page — corrected 6 factual errors, full essay rewrite applying Peterson's writing guide (-173 lines), updated recall tables with real holdout data. (4) Pipeline — 5 Chrome audit fixes (URL enrichment, keyword guardrail, softened consensus, absolute-bits weights, None community), @So8res labeled (68 AI-Safety bits), rollup global DELETE bug fixed, UUID/short_name seed insertion bug fixed. (5) Architecture — discovered independent mode propagation was already implemented but unused, ran it (41K active accounts, 6K bridges vs 0 in classic mode), analyzed export pipeline adaptation needs, ran bootstrap CV, full tech debt scan (14 action items), fixed 2 security issues.

## Commits This Session (selected)

- `8cadd73` feat(ux): SPA routing + gallery toggle + browser back button
- `cabeaea` test(public-site): add Vitest infrastructure + 67 tests
- `8f0b828` test(public-site): add 63 more tests — App tier mapping, SearchBar, CardGallery
- `a59d405` fix(about): correct 6 inaccurate claims on About page
- `63e828f` refactor(about): rewrite Path C from spec-doc to essay voice
- `0471dff` refactor(about): tighten Paths A & B — sentence-level editing
- `f54d9db` refactor(about): tighten shared sections
- `adb7e06` fix(pipeline): 5 Chrome audit fixes — enrichment, consensus, weights, None
- `bb46345` fix(rollup): prevent global DELETE in active_learning --measure
- `f804467` fix(seeds): resolve short_name to UUID before inserting into community_account
- `4fa8734` feat(propagation): add --mode independent for multi-label support
- `da9d569` docs: tech debt surface scan across 5 dimensions
- `ee1bb4a` fix(security): SQL injection + debug mode on 0.0.0.0
- `27b0d1a` test(propagation): add 8 tests for independent mode

PUSHED: Yes, all to origin/main. Site deployed at amiingroup.vercel.app.

## Pending Threads

### Continue Immediately

1. **Round 1 active learning — still running**
   - PID 68730, started ~1:08 AM
   - 9 accounts triaged so far: @kathryndevaney, @NeelNanda5, @karan4d, @river_kenna, @ThatsMauvelous, @petrichor_lull, @jkcarlsmith, @DougTataryn, @wendell_britt
   - Budget: $2.50 Twitter API. LLM calls free (OpenRouter free tier)
   - Check: `tail -20 /private/tmp/claude-501/-Users-aditya-Documents-Ongoing-Local-Project-2---Map-TPOT/37432efe-8d6b-4059-818a-5189dc84739f/tasks/bo3egihz0.output`
   - On complete: run rollup + insert_seeds + re-propagate + re-export + deploy

2. **Adapt export pipeline for independent mode**
   - Analysis complete. 4 problems:
     - `_load_npz_memberships` min_weight=0.05 filters out raw scores (needs ~0.005)
     - CI formula `tw*(1-nw)*(1-ent)` uses zero-sum assumptions
     - Band assignment thresholds calibrated for classic mode only
     - `seed_neighbor_counts` not saved in NPZ
   - Files: `scripts/export_public_site.py:233-269`, `scripts/export_public_site.py:419-422`

3. **Re-propagate with independent mode for production**
   - Currently deployed with classic mode
   - Independent mode tested: 41K active (vs 10K classic), 6K bridges detected
   - Need: export pipeline adaptation first (#2 above)

### Blocked

1. **Bootstrap CV contradicted About page** — 0% held-out seed recall vs claimed 83.8%. User updated About page with honest numbers. Need to investigate methodology.

### Deferred

1. **Tech debt** — see `docs/TECH_DEBT_SCAN_2026-03-24.md` (14 items)
2. **About page images** — 4 Gemini Pro visuals
3. **Fetch outbound edges** for 4 labeled accounts ($0.60)
4. **Label 7 high-confidence misses** from holdout sources
5. **Propagation metrics table** — track CI histogram per run

## Key Context

- **Independent mode propagation**: Fully implemented at `propagate_community_labels.py:579-617`. `--mode independent` flag. Produces non-zero-sum scores + seed_neighbor_counts. Export pipeline does NOT yet support it.
- **5-factor confidence**: `src/communities/confidence.py` — used for exemplars only. Inline `tw*(1-nw)*(1-ent)` used for everyone else. Dual-CI is tech debt.
- **Community ID formats**: UUIDs in `community_account`, short_names in `account_community_bits`. `insert_seeds.py` bridges them with `short_to_uuid` lookup.
- **write_rollup global DELETE**: FIXED — `active_learning.py --measure` now uses scoped delete.
- **Holdout sources**: 4 sources in `docs/HOLDOUT_SOURCES.md` — Orange (283), Strangest Loop (106), curated list (219), ego follows (1,457). Total 1,794.
- **Deploy**: `cd public-site && npx vite build && npx vercel build --prod && npx vercel deploy --prebuilt --prod --yes && npx vercel alias <url> amiingroup.vercel.app`
- **23,655 accounts** live. 32 labeled with bits. Round 1 adding more.
- **User updated About page independently** — changed ~190K to ~200K, added independent propagation description, rewrote recall table with real holdout data, updated "One Map" section.

## Running Processes

- **Round 1** — PID 68730 — `--round 1 --top 50 --ego adityaarpitha --budget 2.50`
  - On complete: rollup + seeds + propagate + export + deploy

## Resume Instructions

1. Check if Round 1 finished: `ps aux | grep active_learning | grep -v grep`
2. If finished: rollup + insert seeds for new accounts, re-propagate, re-export, deploy
3. Read `docs/TECH_DEBT_SCAN_2026-03-24.md` for debt inventory
4. **Priority decision**: Adapt export for independent mode OR label more accounts
5. If adapting export: `_load_npz_memberships` threshold + band recalibration
6. If labeling: `--accounts gptbrooke,embryosophy,touchmoonflower,sonikudzu,soundrotator,Duderichy,RosieCampbell`

---
*Handover by Claude Opus 4.6 at ~65% context, 2026-03-24*
