# Handover: 2026-05-25 — Monolith-split sweep + final push

> File: `docs/HANDOVER_2026-05-25_monolith-splits.md`

## Session Summary

Cleared every file from `docs/TECH_DEBT_SCAN_2026-03-24.md`'s "Size Hotspots" list using a repeated mixin/helper-package pattern. 10 commits, all pushed to `origin/main` at `d8af722`. Zero in-flight work; cleanest end-of-session state in recent memory.

This session continued directly from `HANDOVER_2026-05-24_share-pipeline-review-doc-redesign.md` and the 2026-05-19 handover. It started post-compaction with a `/handover` rebuild, shipped the SSRF guard already committed before compaction, then ran a 5-file monolith-split sweep at the user's direction.

## Commits This Session (10 total, all pushed)

```
d8af722 docs(worklog): monolith-split sweep — 5 splits + reusable mixin pattern
7a6b393 refactor(shadow): split HybridShadowEnricher into coordinator + 5 mixins
89d074a refactor(scripts): split active_learning.py into orchestrator + 4 helpers
7967243 refactor(scripts): split export_public_site.py into orchestrator + 3 helpers
a548088 refactor(shadow): split SeleniumWorker into coordinator + 4 behavior mixins
68b5c56 refactor(shadow): extract 9 pure parsers from SeleniumWorker (-252 LOC)
ed5764b docs(handover): 2026-05-24 — SSRF guard, IndrasNet log cleanup, rotation paused
27c8173 feat(api): add SSRF guard for tweet-enrichment URL fetches
2807db6 docs(handover): 2026-05-19 — cluster UX redesign + Fly never-deployed finding
2b903cc fix(graph-explorer): drawer +24px translate so scrollbar doesn't reveal it
```

## Monolith Scorecard

| File | Before | After | Reduction |
|---|---:|---:|---:|
| `src/shadow/selenium_worker.py` | 2,449 | **102** | -96% (parsers commit + mixin split) |
| `src/shadow/enricher.py` | 2,449 | **953** | -61% (mixin split; `enrich()` 750 LOC stays) |
| `scripts/export_public_site.py` | 1,285 | **388** | -70% |
| `scripts/active_learning.py` | 1,066 | **415** | -61% |

Tests across all refactors: **319 unique tests** (219 shadow+selenium, 48 export, 52 active_learning), zero failures, zero behavior change. The back-compat re-export pattern means every existing `from src.shadow.X import Y` / `from scripts.X import Y` still works.

## Pending Threads

### Continue Immediately

Nothing. Clean state.

### Blocked

Nothing.

### Deferred (parked this session)

1. **`enrich()` decomposition.** `src/shadow/enricher.py:enrich` is still 750 LOC and the dominant contributor to that file's 953 LOC. Decomposing it means extracting the three intertwined blocks (skip-gates / ever-scraped logic ~150 LOC, status-marker block ~70 LOC, refresh+persist+metrics block ~600 LOC) into helper methods on the coordinator. Higher risk than the file split because it touches the orchestrator's local-variable flows. The user explicitly chose "file split only" for this session.

2. **`pure_followers` dead-code finding.** `src/shadow/_enricher_internals/_record_builders_mixin.py` in `_make_discovery_records` computes `pure_followers = followers_usernames - followers_you_follow_usernames` and never uses it. The loop iterates ALL `followers`. Looks like dropped filter intent. Not investigated — pre-existing, not introduced by the refactor. Worth a `git blame` next time someone touches that area.

3. **Test-import migration.** All 5 splits use back-compat re-exports (staticmethod wrappers, module re-exports). A cleanup pass would migrate the ~150 test import sites to the new internal paths and remove the wrappers. LOC-neutral, zero risk, deferred indefinitely.

4. **Method-level decomposition residuals.** `_freshness_mixin.py` (423 LOC) and `_list_capture_mixin.py` (884 LOC) are the next-largest post-split files. The latter is driven by `_collect_user_list` being ~370 LOC alone. Same shape as the `enrich()` problem — method-level decomposition, separate concern.

### Carried over from prior handovers (still open)

From `HANDOVER.md` (2026-05-19 / 2026-05-24):

5. **Fly decision** — deploy or delete `tpot-analyzer/fly.toml`. Production is Vercel-only; the Fly scaffolding has never been deployed. Memory: `project_fly_never_deployed.md`.

6. **Token rotation runbook** — never written.

7. **`MAX_CONTENT_LENGTH` cap on the Flask API** — never added.

8. **Bridge Detection UI** — backend exists, no UI surface.

9. **Drawer `+24px` defensive buffer** — kept after analysis suggested original bug was likely Chrome tab-visibility throttling; revisit only if transition bugs recur.

10. **IndrasNet `web_server.log` rotation investigation** — PAUSED mid-hypothesis. Empirical state in cross-session memory `project_indrasnet_log_rotation_investigation.md`. Different repo (`C:\Users\adity\Documents\Ongoing Local\TemporalCoordination`). Do NOT touch that repo from a Map TPOT session — user has separate share-pipeline / privacy review work in its working tree.

11. **Full IndrasNet URL/SSRF audit** — proposed before user pivoted away. Revisit when convenient.

12. **IndrasNet `web_server.launcher.log` 95MB rotation bug** — separate from the RotatingFileHandler issue. `start_all.py:273` manual rotation supposedly fires at 5MB but doesn't.

## Key Context

### The monolith split pattern is now codified

See `project_monolith_split_pattern.md` (new memory entry). The pattern works in two variants:
- **Mixin split** for god-classes (`SeleniumWorker`, `HybridShadowEnricher`): coordinator + N mixin files under `<file>_internals/`. State on coordinator, behavior on mixins. Cross-mixin calls via `self.method(...)`.
- **Helper-package split** for scripts (`export_public_site`, `active_learning`): orchestrator + N helper files under `_<script>_helpers/`. Helpers are module-level functions, re-exported from the orchestrator for back-compat.

Both variants share: staticmethod-wrapper trick for parsers, `from __future__ import annotations` to avoid circular type-hint imports, explicit `LOGGER = logging.getLogger("src.X")` to keep log channel names stable.

### One gotcha that bit once: relative-import depth

From `src/shadow/_enricher_internals/_X.py`, the right path to `src/data/shadow_store.py` is `from ...data.shadow_store import Y` (three dots up to `src`), **not** `..data` (which would hit nonexistent `src.shadow.data`). Caught at first import attempt. If you write a new mixin file under `_<area>_internals/`, count dots carefully.

### Test patching when methods move into mixins

Tests that did `patch('src.shadow.selenium_worker.WebDriverWait')` had to be updated to `patch('src.shadow.selenium_internals._profile_mixin.WebDriverWait')` after the split — because `from X import Y` creates a local binding that re-exports can't shadow. Two such fixes were needed in `a548088`. The AST-based regression test in `test_selenium_worker_silent_failures.py` also had to be widened to glob `selenium_internals/*.py` instead of just the coordinator.

### The Vercel-only / Fly-not-deployed truth

Still true. If user asks about deployment / Fly / production, the answer is still "Fly was never deployed, Vercel is prod." See `project_fly_never_deployed.md`.

### Don't touch the TemporalCoordination repo

That repo has the user's own separate sharing-pipeline / privacy-review work in its working tree (modified `smart_runner_v4.py`, `change_renderer.py`, `trial_owner_review_local.py` + untracked `HANDOVER_2026-05-24_share-pipeline-review-doc-redesign.md`). The IndrasNet investigation memory exists for cross-session pickup, but a Map TPOT session should not edit that repo.

## Learnings Captured

- [x] Added to memory: `project_monolith_split_pattern.md` — the mixin/helper-package pattern, both variants, with gotchas
- [x] Updated `MEMORY.md` index
- [x] Updated `WORKLOG.md` with the sweep entry (commit `d8af722`)
- [ ] No skill update needed — the existing `handover` skill worked exactly right for this session

## Running Processes

None. Selenium / Flask / Vite from the 2026-05-19 handover were not checked this session and may or may not still be alive (PIDs `48884` Flask, `43368` Vite, two `npm run dev` parents `28156`/`30376`). If user complains about laggy machine, those are the candidates to kill.

## Resume Instructions

1. **If user has no specific request:** the codebase is in a notably clean state — recent refactors all tested + pushed. Good moment to ask "what's next" rather than reaching for the deferred-items list.

2. **If user asks about deployment / Fly:** answer is still "Vercel-only, Fly was never deployed" — see `project_fly_never_deployed.md`.

3. **If user picks any of the deferred items above:** all of #5-#9 are well-scoped enough to start cold. `enrich()` decomposition (#1) benefits from reading `_enricher_internals/_freshness_mixin.py` + the `enrich()` method side-by-side first to internalize state flows.

4. **If user revisits IndrasNet:** read `project_indrasnet_log_rotation_investigation.md` FIRST. Don't re-run the empirical CIM scan, it's already captured.

5. **If user proposes another monolith split:** apply `project_monolith_split_pattern.md` — don't reinvent.

---
*Handover by Claude Opus 4.7 after explicit `/handover` request. Session ended with 10 commits pushed, clean working tree, nothing in-flight. Context usage ~85%.*
