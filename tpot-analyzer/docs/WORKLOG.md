# Public worklog

This publication ledger is intentionally not the private operational diary.
Personal observations, account-level evaluations, contact records and local paths
remain outside this branch. See [methods](guides/DISCOVERY_METHODS.md).

## 2026-10-20 — Documentation entrypoints and folder navigation

Outcome: a reader can start at the repository root and reach methods, setup,
architecture and history without navigating a legacy pipeline README first.

- Root `README.md`: prominent docs hub, purpose-based reading links and actual layout.
- `tpot-analyzer/README.md`: shortened from 274 to 77 lines, focused on current Review.
- Previous README preserved in `docs/archive/legacy-community-map.md` with a
  supersession notice and repaired relative links. No historical explanation removed.
- `docs/README.md`: GitHub directory landing page pointing to the single maintained hub.
- `docs/index.md`: folder responsibilities, current/legacy reading paths and a
  repair for the broken `PROJECT_STRUCTURE.md` destination.
- `scripts/verify_docs_hygiene.py`: checks README-to-hub routes and local links
  in five entrypoints; `tests/test_docs_navigation.py`: isolated regression cases.
- Roadmap and experiment summary record the bounded slice and diagnostic finding.

The former docs check passed despite missing navigation coverage. New regressions
failed first; after the changes, three tests and all 11 docs checks pass, including
74 local links. Existing public-base source CI passed all three jobs. Application,
data and runtime checks are reused for unchanged code; no service is restarted.
Independent Google Gemini review found no blockers. An optional concern about
`./` normalization was contradicted by Python 3.11 behavior and the passing
relative-link fixture, so no workaround was added. Heading-anchor validation is
outside this bounded local-file check. Exact outgoing/remote checks close this slice.

The documentation-writing guidance kept one canonical hub and preserved the repo's
Markdown format rather than creating a parallel documentation destination.

## 2026-10-20 — Clean methodology/source publication

Intent: make the reusable work learnable without publishing the research subjects.

- Port the accepted final application/configuration/synthetic-test tree onto the
  existing public main, without merging unpublished local commit ancestry.
- Replace four operational ledgers with curated public summaries.
- Curate `guides/DISCOVERY_METHODS.md`, `guides/DATA_BOUNDARY.md`,
  `guides/DISCOVERY_REVIEW.md`, `DATA_INVENTORY.md`, architecture and product notes.
- Omit private pilot/activation diaries. Preserve generic source, identity and
  contact semantics rather than stripping important limitations with the diaries.
- Neutralize owner-specific examples in the ported UI and test fixtures.
- Remove legacy dataset/archive paths from the publication tree, not from the
  original private workspace or existing public history.

Acceptance is tracked in [ROADMAP.md](ROADMAP.md). Tests and independent review
are distinct from publication. A pushed branch is not a merge to main, a
deployment or publication of private Review.

Verification checkpoint:

- Combined synthetic Review acceptance: 13/13, including 714 backend tests and
  the specified frontend behavior suite; no real source inputs supplied.
- Full credential-free Python selection: 2,469 passed, two skipped and three
  live Supabase tests deselected. The live-network module now carries the
  existing `requires_supabase` marker; its assertions remain unchanged.
- Full explorer frontend unit suite: 972 passed across 80 test files.
- Additional graph/data-boundary tests: 14 passed; recovery UI: 4 passed.
- All 80 changed JavaScript files pass lint; production build passes.
- Whole-app lint reports 15 errors/2 warnings in files unchanged from the public
  base. This remains visible debt, not an all-green lint claim.
- Docs hygiene: 9/9; tracked-data boundary: 14/14.
- Independent Google Gemini review of the sanitized methodology and cosmetic
  source/fixture delta: no blockers, through an existing subscription.
- Independent review of the live-network test-classification repair: no blockers.
- Content/history and remote checks confirmed publication commit `3a33bbc` on the
  dedicated branch. All three hosted CI jobs subsequently passed. Main was not merged.

Original raw stores, tags, rollback releases, dirty files and local refs must
remain unchanged throughout the publication. No paid acquisition or outreach is
part of this slice.
