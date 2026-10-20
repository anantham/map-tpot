# Public worklog

This publication ledger is intentionally not the private operational diary.
Personal observations, account-level evaluations, contact records and local paths
remain outside this branch. See [methods](guides/DISCOVERY_METHODS.md).

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
- Final content/history and remote-identity checks remain the publication gate.

Original raw stores, tags, rollback releases, dirty files and local refs must
remain unchanged throughout the publication. No paid acquisition or outreach is
part of this slice.
