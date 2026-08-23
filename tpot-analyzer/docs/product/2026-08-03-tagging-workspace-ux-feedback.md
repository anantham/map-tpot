# Tagging Workspace — Operator UX Feedback (2026-08-03)

Verbatim operator feedback from first real contact with the extensional-tagging
workspace, translated into an ordered spec. Recorded before any implementation
so the design intent survives in the operator's own words.

## Operator quotes (grounding — do not paraphrase away)

- "Why is the working extension on the right side? Shouldn't it be in the
  center so it's easy for me to use?"
- "I'm not able to see positive, negative tags as sort of like clear … we need
  to improve the design of this so it's easier for me to know this is the
  current [state] — think from my perspective."
- "If suggestions are done then I should be able to collapse the suggestions."
- "[The tag input] should auto show me a drop-down of similar semantic fuzzy
  search over existing tags so I can quickly search through the space of tags."
- "I need to be able to write meta notes on what I mean by that tag somewhere
  so that I keep tracking and clarifying what I mean when I say that tag …
  even to myself."
- "What is model position, current frontier? That is not making a lot of
  sense."
- "The recent changes, all this stuff should be the last."

## Design principle the feedback implies

Order the page by the curator's workflow, not the system's architecture:

1. **Evidence** (dossier: bio, tweets, provenance) — what I read
2. **Judgment** (working extension: tags, add/remove) — what I do → CENTER
3. **Consequence** (frontier delta: what my click changed) — what I observe
4. **Audit** (event history / recent changes) — what I rarely need → LAST

The current layout centers evidence and pushes judgment to a sidebar; the
operator's action surface should hold the primary position.

## Ordered changes

### P1 — frontend only, no schema (do first)

1. **Move the working-extension panel to the center column.** Dossier left,
   judgment center, consequences right (or below). The tag panel is the
   product; the rest is context.
2. **Split the active-tag display into two visually distinct groups: IN and
   NOT IN.** Color-coded (green/red family), grouped, labeled. A flat chip
   list of mixed polarity is unreadable at a glance.
3. **Collapsible "Suggested from your Takes" section**, default-open until
   every suggestion for the account is accepted or dismissed, then
   auto-collapse with a count badge ("3 suggestions · collapsed").
4. **Rename the two jargon labels:**
   - "Current frontier" → "Candidates this tag surfaces"
   - "Model position" → "Model opinion — none yet (needs more tags)"
5. **Move event history / "recent changes" to the bottom** of the panel,
   collapsed by default.

### P2 — frontend + existing read APIs

6. **Tag-input autocomplete.** On focus/typing, dropdown over the existing
   ego-scoped tag vocabulary (`listDistinctTags`), substring match first;
   fuzzy (edit-distance) second. Purpose: stop vocabulary sprawl — the
   operator's own stated fear ("I might be using slightly different words for
   different nuances"). Batch-1 evidence: builder / ai-ml-builder /
   entrepreneur were three spellings of one idea.
7. Optional stretch: semantic similarity over tag names via local embeddings —
   only if trivially cheap; substring+fuzzy covers the stated need.

### P3 — needs a small schema addition (Codex's store)

8. **Per-tag meta-notes ("working intension").** A note attached to
   `(ego, tag_key)` — "what I currently mean by this tag" — editable, with
   append-only history like every other judgment surface. ADR-021's
   extensional amendment already sanctions this exactly: "Free-form evidence
   notes may remain optional; they are not more authoritative than the
   reviewed examples." The note is a mirror for the operator's own drift,
   not a definition the machine enforces.
   Suggested shape: `tag_meta_notes(ego, tag_key, note, created_at)` append-
   only; current note = latest row. Display beside the tag in the palette.

## Constraints that must survive the redesign

- Suggestions remain inert until accepted (no auto-write).
- No calibrated percentages anywhere until a per-tag producer exists
  (ADR-021). The renamed "Model opinion" box keeps saying "none yet" honestly.
- Event history stays append-only and inspectable — deprioritized visually,
  never removed.
- Curator-identity gating stays; consider persisting the ego in localStorage
  so the operator sets it once, not per visit.

## Non-goals (explicitly out of scope for this pass)

- Confidence sliders / percentage inputs on judgments (operator asked; the
  answer for now is abstain + investigation note; calibrated numbers are a
  model output later, checked against binary verdicts).
- Any change to tag/event storage semantics beyond the P3 note table.

## Addendum (2026-08-03 evening) — two live findings from the first real session

1. **P1 bug — hash-mismatch blast radius.** Appending two accounts to the takes
   file broke the ENTIRE `/api/research-notes/source` endpoint ("proposals do
   not match the configured source"), taking the queue down with it. Fail-closed
   is right for the *proposals*; it is wrong for the *queue and source text*.
   Degrade gracefully: serve source + queue, mark proposals
   `stale — bound to <old hash>`, offer regeneration. The operator's corpus
   file must remain editable without breaking the workspace.
2. **P1 gap — pasted queue additions are session-only.** "Add to queue" writes
   React state only; refresh loses it. Either persist pasted additions to a
   durable side store or append them to the takes file (with provenance
   marker) after operator confirmation. Until then the operator loses work on
   refresh, which violates the "every move durable" expectation the tag store
   already meets.

## Implementation amendment (2026-08-03 night)

The operator-centered slice now implements the requested evidence → judgment →
consequence → audit sequence:

- Evidence remains first in document order. The working extension occupies the
  center action column on wide screens; the consequence view is right/below,
  and the collapsed audit trail is last. Responsive layouts preserve that DOM
  order rather than visually reordering the workflow with CSS.
- Current assignments are split into named `IN` and `NOT IN` regions. Changing
  polarity and retracting a judgment are distinct actions; color is not the
  only polarity signal.
- Takes suggestions remain inert, can be dismissed for the current session,
  auto-collapse when resolved, and can be reopened. Dismissal never writes an
  account tag.
- The tag picker shows the existing curator vocabulary and performs exact,
  prefix, substring, and bounded edit-distance matching. A retracted tag stays
  in the vocabulary so minor spelling variants do not recreate it silently.
- Each `(ego, tag_key)` can now hold an optional append-only working-intension
  note. Saving a new meaning or explicitly clearing it appends a version; it
  does not rewrite prior notes or enforce the prose as a membership rule.
- "Current frontier" is now **Candidates this tag surfaces**. The separate
  **Model opinion — none yet (needs more tags)** statement remains empty rather
  than laundering the source-selective candidate order into calibrated soft
  membership.
- Pasted accounts and edited account notes now use a versioned browser-local
  queue. They survive refresh/remount and retain manual/frontier provenance;
  corrupt or full browser storage produces a visible warning and keeps the
  current work in memory instead of crashing the review.
- A Takes/proposal hash mismatch now quarantines only the stale suggestions.
  Current source text and its full account queue remain available, the UI
  shows the old/current receipt, and an explicit reload rechecks the source.
  Proposal generation itself is not automated in this screen yet.

### Data-safety and verification boundary

`scripts/verify_tagging_workspace_ux.py` opens the live tag database through a
SQLite `mode=ro` URI plus `query_only`, reports judgment/event counts and row
digests, and runs the additive note-schema migration only on a consistent
temporary backup. At the implementation checkpoint it observed `93` current
assignments and `93` append-only events across `52` accounts and `31` tags;
the temp migration preserved both core counts and digests. Focused contracts
passed `24` backend and `47` frontend tests. The full repository checks passed
`1,698` Python tests (5 skipped) and `786` frontend tests, plus a production
build. The verifier spends `$0` and makes no network, model, or external API
call.

### Explicit limitations (not hidden behind the UI)

- Search is lexical fuzzy matching, not semantic embedding similarity. It
  helps with typos and near spellings but will not infer that two unrelated
  words are synonyms.
- Suggestion dismissal is scoped to the current browser session. Pasted queue
  additions and account investigation notes survive refresh in browser-local
  storage, but are not server-synced, versioned as judgments, or multi-device;
  clearing browser data removes them.
- Stale/invalid Takes suggestions are visibly quarantined, but proposal
  regeneration remains an external step; **Reload Takes source** only refetches
  and never claims to run a model or spend money.
- The tag-note read returns recent history (currently at most 50 versions in
  the route's default read), not an unbounded browser rendering.
- Candidate movement is a source-selective follow-graph retrieval diagnostic.
  It is not confidence, cluster existence, competence, affiliation, or a
  calibrated probability.
- The automated verifier covers storage and behavioral contracts. A curator
  still needs to inspect the responsive layout in the live browser after the
  current frontend/backend runtime serves this revision.
