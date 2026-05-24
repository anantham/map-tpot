# Handover: 2026-05-24 (SSRF guard + IndrasNet log cleanup + rotation investigation paused)

## Session Summary

This session began as a continuation of the 2026-05-19 handover. The user pivoted through three distinct workstreams:

1. **Map TPOT — SSRF guard for tweet-enrichment URL fetches.** Closed the `POST /interpret` (mode=rich) → t.co resolution SSRF path with a per-hop URL validator that also blocks Tailscale/CGNAT space. Shipped commit `27c8173` with 20 passing unit tests. The local Flask is the only user, so blast radius is local-only today — but this hardens the boundary before any future Fly deploy.
2. **TemporalCoordination — `server.log` cleanup.** Compressed the 1.85 GB stale `server.log` to `.local/logs/server.log.gz` (28.7 MB, 64× ratio), verified by full-decompression byte-count match, removed the original. No code change.
3. **TemporalCoordination — `web_server.log` rotation investigation, PAUSED.** Started hypothesis-driven hunt for the child-process spawn site causing potential `RotatingFileHandler` conflicts on Windows. Empirical state captured but spawn site not yet located when user pivoted with "ok what else can we work on" then asked for this handover.

## Commits This Session

**Map TPOT (1 new, 3 unpushed cumulatively):**

```
27c8173 feat(api): add SSRF guard for tweet-enrichment URL fetches    ← NEW this session, UNPUSHED
2807db6 docs(handover): 2026-05-19 — cluster UX redesign + Fly never-deployed finding   ← UNPUSHED (carried from 2026-05-19)
2b903cc fix(graph-explorer): drawer +24px translate so scrollbar doesn't reveal it      ← UNPUSHED (carried from 2026-05-19)
```

All 3 unpushed per the "no push without explicit ask" standing rule. The 2026-05-19 handover noted the same about `2b903cc`; that hasn't changed.

**TemporalCoordination:** Zero commits. The 3 modified files in its working tree (`smart_runner_v4.py`, `change_renderer.py`, `trial_owner_review_local.py`) and the untracked `docs/HANDOVER_2026-05-24_share-pipeline-review-doc-redesign.md` are the user's separate share-pipeline / privacy review work, **not from this session**. Don't touch them.

## Disk Artifacts This Session

| Path | Size | Notes |
|---|---:|---|
| `tpot-analyzer/src/api/url_guard.py` | ~150 LOC | NEW — SSRF guard module (committed) |
| `tpot-analyzer/tests/test_url_guard.py` | 119 LOC | NEW — 20 tests, all green (committed) |
| `tpot-analyzer/src/api/tweet_enrichment.py` | edits | 3 urlopen sites replaced + tweet_id digit-guard (committed) |
| `tpot-analyzer/docs/WORKLOG.md` | +SSRF section at top | committed |
| `TemporalCoordination/.local/logs/server.log.gz` | 28.7 MB | gitignored — gzip of the 1.85 GB log |
| `TemporalCoordination/server.log` | **deleted** | original 1.85 GB file removed after gzip verified |

## Test State

- Map TPOT: SSRF unit suite — 20 passed locally on anaconda. Wider suite not re-run this session.
- TemporalCoordination: nothing run; investigation was pre-test.

## Pending Threads

### A. Active — Continue Immediately

1. **Push the 3 Map TPOT commits** (`2b903cc`, `2807db6`, `27c8173`) — waiting on user "push" word. First push of the SSRF guard against the new CI workflow.

2. **IndrasNet `web_server.log` rotation investigation (PAUSED mid-hypothesis).**
   - Repo: `C:\Users\adity\Documents\Ongoing Local\TemporalCoordination`
   - Full state captured in cross-session memory `project_indrasnet_log_rotation_investigation.md` so a future TemporalCoordination session can pick it up without re-doing the empirical scan.
   - **What's known:** 3 unnamed `multiprocessing.spawn` children under web_server PID 63036; `agents.py:42-76` is *not* the spawner (it already has the env-var mitigation). Rotation is currently working (7 clean ~9.5 MB backups dated 2026-05-13 → 2026-05-22) — fix becomes preventative, not curative.
   - **Next step:** Grep for the third spawn site (not `agents.py`, not `ProcessPoolExecutor`, not `multiprocessing.Pool`). Then apply belt-and-braces fix per the memory.
   - **Tasks #35-39** still in the active task list track this. Should they be cleared? See section "Stale Task List" below.

### B. Blocked

Nothing actively waiting on an external trigger. The IndrasNet investigation is paused by user pivot, not blocked.

### C. Deferred This Session (parked deliberately)

1. **Full IndrasNet URL/SSRF audit.** Originally proposed when user said "we should also audit that project also where I process a lot of insecure urls" — the user pivoted to `server.log` cleanup before this started. Revisit trigger: a quiet moment, or before any IndrasNet network exposure changes.

2. **IndrasNet `web_server.launcher.log` 95 MB rotation bug.** Separate from the RotatingFileHandler issue above. `start_all.py:273` does manual rotation that's supposed to fire at 5 MB per `docs/indrasnet/LOGGING.md` but the file is 95 MB. Flagged but untouched.

3. **"What else can we work on" menu was never presented** — the user asked for handover before I produced the menu. The candidate list at pivot time was: continue rotation investigation / launcher.log rotation bug / IndrasNet SSRF audit / push the 3 Map TPOT commits / pick up older deferred tech-debt items (token rotation, MAX_CONTENT_LENGTH, splitting enricher.py & selenium_worker.py, Bridge Detection UI) / run full `surface-tech-debt` sweep on IndrasNet. Surface this menu first on resume.

### D. Carried Over From Prior Handovers (still open)

From `2807db6` (2026-05-19 handover):

1. **Decide what to do about Fly.** Two paths, user hasn't chosen:
   - (a) Actually deploy: requires user-run `flyctl launch` (account/transact boundary — don't auto-run).
   - (b) Delete Fly scaffolding: remove `tpot-analyzer/fly.toml`, commented `fly.dev` line in `graph-explorer/.env.example`, "Fly secrets" framing in `project_auth_rollout_pending.md`, and update `ENVIRONMENT_VARIABLES.md` for Vercel-only.
   - Memory: [[project_fly_never_deployed]] for the evidence, [[project_auth_rollout_pending]] (STALE) for the framing that would need rewriting if (a).

2. **Drawer `+24px` defensive buffer** kept after analysis suggested the original bug was likely Chrome tab-visibility throttling, not a real scrollbar issue. Harmless in real use; revisit only if transition bugs recur.

From `ce8a3d0` (2026-05-18 handover, transitively still open):

3. **Token rotation runbook** — never written. Curator token rotation procedure undocumented.
4. **`MAX_CONTENT_LENGTH` cap on the Flask API** — never added. Bodies can be unboundedly large.
5. **Split `enricher.py` / `selenium_worker.py`** — both grown past comfortable monolith thresholds.
6. **Bridge Detection UI** — backend exists, no UI surface.

(None of 3–6 came up this session. Listing for completeness so they don't fall off the map.)

### E. Bugs / Gaps Flagged But Not Addressed

| Item | Repo | Severity | Notes |
|---|---|---|---|
| `web_server.launcher.log` 95 MB | IndrasNet | medium | Launcher-stdout rotation, separate from RotatingFileHandler |
| Tweet-enrichment cache may not invalidate on SSRF block | Map TPOT | low | Not investigated; speculative |

## Background Tasks Launched This Session

| ID | Purpose | Output | Status |
|---|---|---|---|
| `b9cbw672c` | gzip the 1.85 GB server.log | `DONE src=1847.5MB gz=28.7MB ratio=64.4x` | consumed |
| `b5m6ttxk4` | `Get-CimInstance Win32_Process` for web_server PID 63036 children | 3 unnamed `--multiprocessing-fork` PIDs | consumed (logged in memory) |
| `b8jqnul5w` | grep `web_server.launcher.log` for recent `WinError 32` / rotation errors | empty (no recent errors) | consumed |
| `b6y2i3lw9` | speculative grep over transcript for "deferred"/"parked" keywords | output not consumed | abandon — Explore agent superseded |

No long-running processes left alive. The Vite/Flask PIDs from the 2026-05-19 handover (43368, 48884) may or may not still be alive — not checked this session.

## Memory Writes This Session

- ➕ `project_powershell_exit255_false_failure.md` — cross-session warning that PowerShell background tasks reporting `failed exit 255` are often `2>&1` artifacts; read the output file before believing the failure.
- ➕ `project_indrasnet_log_rotation_investigation.md` — paused investigation state so a future TemporalCoordination session can pick up without re-discovery.
- Both indexed in `MEMORY.md`.

## Stale Task List

Tasks `#35-#39` currently in the task list track the IndrasNet rotation fix. They're real and the work is paused (not abandoned), but they're scoped to a different repo. **Recommendation on resume:** ask user whether to (a) keep them as-is, (b) clear them since the cross-session memory now captures the same state, or (c) defer until user actively pivots back to TemporalCoordination.

## Key Context (non-obvious things the next instance needs)

- **SSRF guard scope:** the guard validates scheme + host IP at submission AND at every redirect hop. Tailscale 100.64.0.0/10 is explicitly blocked because `ipaddress.is_private` doesn't cover CGNAT on older Python. DNS rebinding TOCTOU is documented as accepted residual — close with IP-pinned connections only if/when a public deploy happens.
- **The Python 3.9 type-union gotcha bit again:** `X | Y` syntax in runtime contexts is a Python 3.10+ feature; this codebase runs 3.9 on anaconda. Use `from typing import Union` for any runtime-evaluated type union.
- **TemporalCoordination AGENTS.md PRIME_DIRECTIVE #6** = "Don't be trigger happy." That repo expects propose-then-approve. Do not auto-apply patches there. (Map TPOT's AGENTS.md has the same TDD-default-on convention but is more permissive on small fixes — see [[project_tdd_convention]].)
- **The 1.85 GB `server.log` cleanup was done per `docs/indrasnet/LOGGING.md`'s explicit policy** ("rotate or move them into a local-only folder", "Desired Local Layout: `.local/logs/`"). Verified before delete: full-decompression byte count matched 1,937,258,602 bytes.
- **Don't conflate the two log issues in IndrasNet:** `web_server.log` (Python `RotatingFileHandler`) and `web_server.launcher.log` (launcher stdout, manual rotation in `start_all.py:273`) are separate code paths with separate bugs.

## Resume Instructions

In order of likely priority:

1. **If user says anything implying push:** `git -C "C:/Users/adity/Documents/Ongoing Local/Project 2 - Map TPOT" push` sends the 3 commits. First push of the SSRF change against CI.

2. **If user picks "what else can we work on":** present the menu from section C.3 above.

3. **If user revisits IndrasNet:** read `project_indrasnet_log_rotation_investigation.md` first — don't re-run the empirical CIM scan, it's already captured.

4. **If user asks about deployment / Fly / production:** the answer is still "Fly was never deployed, Vercel is prod." See `project_fly_never_deployed.md`.

5. **Don't reopen** the 2026-05-19 cluster UX redesign unless a new requirement comes up.

---
*Handover by Claude Opus 4.7 at end of explicit `/handover` request after compaction. Sourced from raw transcript at `~/.claude/projects/.../1eb59b1c-e554-49d5-8279-16c37393821e.jsonl` (5,718 lines, 16.9 MB) plus prior handovers `HANDOVER.md` (2026-05-19) and inline session memory.*
