# ADR 023: Task-Focused Curator Review and Map

- Status: Accepted
- Date: 2026-08-23
- Group: Curator experience / Personal ontology
- Decision basis: curator UI review, 2026-08-23
- Related ADRs: 011, 013, 014, 019, 020, 021

## Issue

The current Research Notes page puts source setup, a Takes-backed queue,
evidence, mutable tags, suggestions, free-form notes, retrieval consequences,
and audit context on one screen. It also presents six legacy analysis views as
peer navigation. This makes the active task ambiguous and asks the curator to
interpret system architecture before making an account-level judgment.

The desired workflow is iterative and non-binary. The curator investigates an
account on X and the wider web, returns with several overlapping tag judgments,
attaches the specific evidence that motivated each judgment, and revises those
judgments later as opinions change. The same editor must eventually be
available from both a review queue and a spatial community map.

## Decision

### Expose two primary workspaces

The product shell exposes **Review** and **Map** as its primary destinations.
Legacy Discovery, Graph Explorer, Cluster View, Communities, and Label Tweets
remain available under an accessible **Tools** disclosure while they are still
needed for development and analysis.

Review is the focused evidence-and-judgment loop. Map is the exploratory view
of fixed account positions with user-scoped tag overlays, model affinities,
uncertainty, and evidence coverage. A quick-add disclosure inside Review
accepts handles, links, and free-form notes; it is not a third workspace.

### Reuse one account judgment editor

One account judgment editor is shared by the Review queue and the future Map
drawer. It shows the account evidence, current working judgments, optional
notes, source-bound suggestions, consequences, and history. Review embeds the
editor in its task flow; Map opens it as a non-destructive side drawer without
moving the underlying account layout.

The first implementation slice extracts and simplifies this editor without
changing the current binary working-tag schema. A later schema phase may add a
curator membership estimate, a subjective plausible range, abstention, and
structured evidence attachments only after migration and evaluation contracts
are separately approved.

### Reveal information at the moment it is useful

The default Review surface keeps the queue, selected account evidence, current
tag state, and tag action visible. Curator setup, quick add, account notes,
source suggestions, retrieval consequences, method detail, and audit history
use accessible progressive disclosure unless an error needs immediate action.

Suggestions remain inert and collapsed by default. A healthy browser-local
save is a quiet status, while persistence failure remains an alert. Unknown tag
state stays distinct from reviewed-and-unclassified state, but the queue need
not repeat full system-language explanations on every row.

### Preserve changing opinions and frozen studies separately

Working judgments are mutable projections over append-only events. Adjusting a
judgment, explicitly judging against a tag, and retracting a judgment remain
different actions. A future soft-membership migration follows the same
supersession rule rather than overwriting history.

Frozen study judgments never change when the working judgment changes. A
study task may use the Review shell with fixed accounts, evidence, order, and
controls, while hiding suggestions and model consequences. Importing completed
study judgments into working tags requires a separate explicit action.

## Rationale

Review, exploration, and capture have different cognitive costs but share the
same account-level evidence and judgment object. Two primary workspaces plus a
shared editor preserve continuity without mixing evaluation, curation, and
legacy tooling. Progressive disclosure keeps epistemic safeguards available
without making every safeguard compete for attention on every account.

## Constraints

- Human evidence and judgments remain private and locally authoritative.
- Evidence, curator interpretation, model output, and coverage remain separate.
- Model affinity is not a probability until target-specific calibration passes.
- Map position must remain stable across label edits; overlays may update.
- Brightness or any other visual channel encodes only one named quantity.
- Hover-only controls require keyboard-focus and touch equivalents.
- Existing assignments and append-only events must survive UI work
  byte-for-byte; this ADR authorizes no live-data migration.

## Consequences

### Positive

- The active curator task becomes legible before the first judgment.
- Review and Map can share editing behavior and history.
- Legacy analytical views remain reachable without dominating the product.
- Later soft labels and evidence receipts have an explicit migration boundary.

### Costs and risks

- The UI needs responsive navigation and a reusable editor seam.
- Hidden information can become undiscoverable if disclosures lack clear labels.
- The existing binary tag store temporarily limits the richer approved UX.
- Map editing, soft-membership storage, evidence objects, and frozen-study
  persistence remain separate phases rather than being simulated in the UI.

## Validation

The first slice must demonstrate:

1. Review and Map are the only persistent primary destinations.
2. Every legacy view remains keyboard- and touch-accessible through Tools.
3. Quick add, notes, suggestions, consequences, method, and audit remain
   discoverable but do not all render expanded by default.
4. Existing tag mutations, retraction, source quarantine, browser-local notes,
   and failure states retain their behavioral contracts.
5. Desktop and narrow layouts avoid horizontal overflow in the product shell.

The later data/model phase requires its own ADR amendment or successor with a
dry-run migration, current/event digest preservation, calibration semantics,
and a human-readable verification script.
