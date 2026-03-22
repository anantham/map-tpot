# Handover: 2026-03-22 (Session 6 — Doc Audit + About Page + Vancouver Outreach)

## Session Summary

Massive documentation + validation session. Full codebase doc audit (found and fixed 10 issues),
wrote end-to-end DATA_PIPELINE.md with 5 Obsidian canvas diagrams, redesigned the About page
from scratch (spec → plan → subagent implementation → review → recall table), ingested 167
gold labels from curator's "Interesting people" list, ran first pipeline recall check
(18.6% NMF / 67.7% propagation / 33.5% export), then pivoted to finding Vancouver TPOT
people for an IRL meetup. All pushed.

## Commits This Session (key ones)

- `5757eb3` docs(audit): full doc audit remediation — fixes, module doc, test backfill
- `9512b7c` docs: data pipeline reference, canvas diagrams, about page spec + plan
- `d3a0580` → `c627a4d` feat(public-site): About page rewrite (5 commits)
- `8726fdc` feat(public-site): add recall validation table to About page
- `bf43f22` feat(labeling): schema additions (short_name, account_community_bits)
- `6d6ecc6` feat(gold): account-community gold label system (ADR-014)
- `b6298c2` feat(ui): community detail pages + gold label editor
- `88a3dae` docs: vancouver outreach — office hours intel, DM tracking

PUSHED: Yes, all to origin/main

## Pending Threads

### Continue Immediately

1. **Vancouver outreach — wait for DM replies**
   - DMs sent to: @aphercotropist, @dschorno, @daniellefong (daniellefong uncertain if sent)
   - Key action: **Go to The Lido on March 25 at 7pm** (office hours, aphercotropist confirmed "next week should be packed")
   - Tracking doc: `docs/vancouver-outreach-2026-03.md`

2. **Golden dataset recall improvements**
   - Current recall: 67.7% propagation, 33.5% export, 32.3% completely missed
   - 54 accounts on the "Interesting" list are invisible to the pipeline
   - Next: investigate why — are they not in the shadow graph at all?

### Blocked

1. **ADR-010 scope decision** — amend existing vs create new ADR for 5 extra golden endpoints
   - Waiting on: human decision
2. **camelCase migration** — communities.py, branches.py, preview.py snake_case responses
   - Waiting on: scoping session (blast radius includes frontend consumers)
3. **Labeling pipeline open questions** — bits semantics, layer 3 rollup, evaluation regime
   - Answers proposed in this session, waiting on human confirmation
   - See conversation for detailed answers to 9 open questions

### Deferred

1. **WORKLOG backfill** — public-site + JIT cards work (~15 commits) still not in WORKLOG
2. **community_gold module doc** — backend built, no docs/modules/ entry yet
3. **Security patterns → ENGINEERING_GUARDRAILS.md** — commit 596924c not captured
4. **VISION.md update** — outdated "What's Built" section

## Key Context

- **167 gold labels ingested** as "Interesting" community in account_community_gold_label_set
  - Community ID: `29014beb-9981-452a-97ae-6484d98cafa7`
  - Reviewer: `curator:adityaarpitha`
  - Source: `list:1788441465326064008` (X list "Interesting people")
  - Splits: 113 train / 25 dev / 29 test
  - 54 accounts stored as `handle:username` (not resolved to account_id)

- **Canvas skill updated** — now uses dynamic project folders in Exocortex vault
  - MapTPOT folder created at `Research/Projects/MapTPOT/`
  - 5 canvas files with nested embedding for zoom-in math detail

- **About page** is live at localhost:5175/about with:
  - Personal origin story, two evidence layers, validation recall table
  - Progressive disclosure (details/summary) for NMF and propagation math
  - Dynamic counts from data.json (no hardcoded numbers)
  - Tweet evidence honestly placed in "Coming Next" section

- **@aphercotropist** is the Vancouver TPOT hub
  - Runs weekly office hours at The Lido (Tuesdays 7pm)
  - Next one: March 25 — "should be packed"
  - Interacts with: @OneEyedAlpaca, @exgenesis, @SarahAMcManus, @nosilverv

- **Feedback memory saved**: `feedback_audit_accuracy.md` — never trust subagent claims
  about endpoints, test counts, or dates without reading the actual files

## Learnings Captured

- [x] feedback_audit_accuracy.md — subagent verification rules
- [x] MEMORY.md updated with current state (tech debt, next steps)
- [x] Canvas skill updated (dynamic project folders)
- [ ] Meta-update to CLAUDE.md — proposed 3 additions, user said "skip, overkill" — correct call

## Running Processes

None.

## Resume Instructions

1. Check if @aphercotropist replied to the DM — if yes, confirm March 25 office hours
2. Check `docs/vancouver-outreach-2026-03.md` for full outreach state
3. If continuing dev work: ADR-010 decision and camelCase migration are the top outstanding items
4. If continuing labeling: see `docs/LABELING_PIPELINE_DESIGN.md` for the bits system + 9 open questions with proposed answers from this session

---
*Handover by Claude Opus 4.6 at high context usage, 2026-03-22*
