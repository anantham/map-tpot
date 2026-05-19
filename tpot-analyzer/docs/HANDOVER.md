# Handover: 2026-05-19 (Cluster UX Redesign + Fly Investigation)

## Session Summary

Continuation of the 2026-05-18 session. After pushing the 8 security/test commits, the user pivoted to redesigning the graph-explorer cluster UX for discoverability. Shipped 4 commits (ClusterView redesign, lens/legend chrome consolidation, shareable URLs + smart hint, drawer scrollbar fix). Visual QA was done in Chrome with a synthetic snapshot built on the fly because the user's local `cache.db` was empty (12 KB). Session ended with an investigation that produced the single most important finding: **the Fly.io API has never been deployed.** The 2026-05-18 "URGENT operator action" reminders about Fly secrets were misleading — there is no Fly app to set secrets on.

## Commits This Session (4 — 3 already pushed, 1 unpushed)

```
2b903cc fix(graph-explorer): drawer +24px translate so scrollbar doesn't reveal it   ← UNPUSHED
916a998 feat(graph-explorer): shareable cluster URLs + smart empty-state hint
9cb731e feat(graph-explorer): fold lens bar + community legend into chrome
5025d38 feat(graph-explorer): redesign ClusterView for discoverability + density
```

`2b903cc` is 1 ahead of `origin/main`. Not pushed per the "no push without explicit ask" standing rule. Earlier in the session the user said "push" once for the 8-commit batch from the prior handover — that authorization does NOT extend to this commit.

## Data State

Unchanged. Real `cache.db` is still empty in the user's local clone (12 KB). The synthetic snapshot files in `tpot-analyzer/data/` (graph_snapshot.* — 2,000 nodes, ~16k random edges, copied spectral fixtures) were generated for visual QA and are gitignored — safe to leave or delete.

## Test State

Not re-run end-to-end this session. Vitest suites for the 4 new files (`Drawer`, `granularity`, `ColorLegendChip`, `ClusterTour`) plus updates to ClusterView tests were green at commit time. Python suite unchanged from prior handover (1,138 green).

## Pending Threads

### Continue Immediately

1. **Push `2b903cc`** when the user says so. First push of the new CI workflow against a Vite-only change — should be uneventful, but it's the first signal.

2. **Decide what to do about Fly.** Two paths (user has not chosen):
   - **(a) Actually deploy.** Requires `flyctl` installed + Fly auth + first-time `flyctl launch`. Then the auth-rollout memory below becomes operational again.
   - **(b) Accept Flask-as-local-only.** Then `tpot-analyzer/fly.toml`, the Fly references in `graph-explorer/.env.example`, and the "URGENT operator action" framing should be deleted. The Vercel public-site is the only deployed surface.

### Blocked

Nothing.

### Deferred (Acknowledged but Parked)

1. **Drawer `+24px` defensive buffer.** Initially attributed to a real scrollbar bug; later analysis suggested it was likely a Chrome hidden-tab animation throttling artifact (`document.hidden: true` paused the CSS transform at `currentTime=0`, leaving the drawer mid-slide). The +24 was kept as defensive — harmless overscan in real use. If revisiting transition bugs, suspect tab-visibility throttling first.

2. **All prior session's deferred items still parked** (see prior handover, lines 57–67: SSRF hardening, token rotation runbook, `MAX_CONTENT_LENGTH`, splitting `enricher.py` / `selenium_worker.py`, Bridge Detection UI). None of them came up this session.

## Key Context (non-obvious things the next instance needs)

### The Fly app does not exist (definitive)

Evidence collected at end of session:
- `nslookup tpot-analyzer-api.fly.dev` — NXDOMAIN from both Reliance ISP and Cloudflare 1.1.1.1.
- `curl -sI https://api.fly.io/v1/apps/tpot-analyzer-api` — HTTP 404.
- `tpot-analyzer/fly.toml` was added in commit `7f914e4` on 2025-12-17 and has not been modified since.
- No deploy runbooks/scripts exist beyond fly.toml's header comment "Deploy with: fly launch (first time) or fly deploy (updates)".
- The only `fly.dev` reference outside `fly.toml` is in `graph-explorer/.env.example`, commented out as aspirational.

**Implications:**
- The 5 security vulnerabilities the 2026-05-16 audit found were never exposed on the public internet.
- The curator-auth gate (commit `e29f04f`) protects a local Flask backend only.
- The production stack today is: `maptpot.vercel.app` (Vercel + serverless functions + Vercel Blob) and the public-site frontend. `graph-explorer` is local-only by design (curator token would be bundled into Vite client). Flask is local-development only.

### The cluster UX redesign goals (so you don't undo them)

- **A+C direction** chosen by user: collapse 3-row toolbar to 2 rows, inline the lens pills, fold the community legend into a floating chip (`ColorLegendChip.jsx`). Replaced explicit Visible/Budget sliders with a single **Granularity** slider that maps via piecewise-linear `granularityToConfig(percent)` so the legacy `budget=25` lands at the slider midpoint.
- Drawer overlays the canvas (`position: absolute`) so opening it doesn't reshrink the simulation. Canvas reads `containerRef.clientWidth`; if the drawer were a flex sibling, every open/close would re-layout.
- `?selected=` deep-linking + `hasEverSelected` localStorage smart-hint were intentional — the empty-state hint is one of the two places that mention "Click any blob"; the tour is the other. Test regex `/Click any blob → details panel/` distinguishes them.
- `ClusterTour.jsx` has a localStorage guard so it only auto-fires once; the `?` trigger in `ClusterTourTrigger` re-opens it.

### Synthetic snapshot is gitignored

`tpot-analyzer/data/graph_snapshot.*` files are real on disk but gitignored. If a future session needs them again and they're missing, regenerate via the scratch script that copies spectral fixtures and synthesizes nodes.parquet + edges.parquet. Don't commit them.

### Goodhart guardrails from this session

User caught me twice this session and they're now memories:
1. **Parametrize-list inflation** (prior session, commit `d5e1c0a` cleaned it up) — `[[feedback-pushback-on-test-goodharting]]`.
2. **Treating blockers as terminal** — when the dev environment was missing data, I initially stopped and asked the user to provide it. User pushed: "why cant you get it running why is it blocked on me", "can't you reset credentials make new". The right move was to synthesize what I needed. Logged in `[[feedback-verify-before-done]]` implicitly; consider a dedicated memory if it recurs.

## Running Processes (still alive on user's machine)

| Purpose | PID | Started | Notes |
|---|---:|---|---|
| Flask API server | 48884 | 07:46 | `python -m scripts.start_api_server` — was needed for visual QA, can be killed |
| Vite dev (graph-explorer) | 43368 | 07:47 | `vite` in `graph-explorer/` — same, can be killed |

Two `npm run dev` parents (28156, 30376) and one Playwright MCP node (47228, 22716) also running but not part of this work. **Recommendation:** if the user isn't actively using the Vite preview, kill 43368 + 48884 to free RAM. Otherwise harmless.

## Learnings Captured

### Updated memories (cross-session)
- ✏️ `project_auth_rollout_pending.md` — corrected to reflect Fly was never deployed
- ➕ `project_fly_never_deployed.md` (new) — captures the investigation finding so it doesn't have to be redone

### Skill update opportunities (not applied)
- **surface-tech-debt skill** — could grow a "Deployment Reality Check" pass: cross-reference `fly.toml` / `vercel.json` / `Dockerfile` / `k8s/*` against actual DNS + provider API to detect "scaffolding without deployment." Would have caught this in the original audit.

## Resume Instructions

In order of priority:

1. **Acknowledge the Fly finding** to the user if they ask anything about deployment / Fly / production / the curator API. The instinct to say "set the secrets" is stale.

2. **If user says "push":** `git push` will send `2b903cc` and trigger CI on a graph-explorer-only change. Should be a trivial CI run.

3. **If user wants to deploy Fly:** they need to run `flyctl launch` from `tpot-analyzer/` (interactive, requires Fly account + auth). Don't try to do it without explicit permission — it's a "create account/transact" boundary.

4. **If user wants to delete the Fly scaffolding:** small cleanup PR — remove `fly.toml`, the commented `fly.dev` line in `graph-explorer/.env.example`, and the "Fly secrets" framing in `project_auth_rollout_pending.md`. Update `ENVIRONMENT_VARIABLES.md` to reflect Vercel-only production.

5. **Don't reopen the cluster UX redesign** unless the user introduces a new requirement. The four commits represent a coherent direction the user explicitly approved; further iteration risks bikeshedding.

---
*Handover by Claude Opus 4.7 at end of post-compaction handover request. Sourced from raw transcript at `~/.claude/projects/.../1eb59b1c-e554-49d5-8279-16c37393821e.jsonl` (lines 2235–2916).*
