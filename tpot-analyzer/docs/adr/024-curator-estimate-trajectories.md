# ADR 024: Curator Estimate Trajectories

- Status: Accepted for trajectory capture; stabilization policy pending
- Date: 2026-08-23
- Group: Research semantics / Curator experience
- Decision basis: curator review-workflow discussion, 2026-08-23
- Related ADRs: 014, 019, 020, 021, 022, 023

## Issue

The binary `IN` / `NOT IN` working-tag projection cannot express a curator's
uncertainty or how a boundary judgment changes after reviewing more evidence.
The existing nullable `account_tags.confidence` field has no approved semantic
contract. Reinterpreting it
would collapse confidence, membership, and eventual convergence into one
number and would erase the distinction between one review and a stabilized
opinion.

The Review queue will eventually rank work by expected information, but no
honest numeric bit value exists until a target-specific model has calibrated,
generation-bound priors. The product first needs to record the human trajectory
that later calibration will be evaluated against.

## Decision

### Record a subjective estimate and plausible eventual range

For curator (u), account (i), and working tag (g), each deliberate review
may append:

- (q_t \in [0,1]): the curator's current membership estimate after the
  evidence reviewed at time (t);
- \([l_t,h_t]\): the curator's plausible range for the estimate they expect to
  hold after substantially more review, with
  (0 \leq l_t \leq q_t \leq h_t \leq 1);
- a review-session identifier, timestamp, source, and evidence-binding status.

This range is a subjective forecast of an eventual stabilized membership
estimate. It is not a statistical confidence interval, a model posterior, or
evidence coverage. The interface must call it a **plausible eventual range**.

The estimate stream is append-only and separate from the existing mutable
`IN` / `NOT IN` projection. Corrections add events. Retraction of a coarse tag
does not delete its estimate history. Existing working tags receive no
synthetic estimate or range; their estimate state remains unknown until the
curator explicitly records one.

### Treat convergence as a trajectory, not the next sample

A single later review is never the calibration target. The system preserves
the ordered estimates and their review-session identities so movement,
interval width, and eventual stability can be inspected over time.

An endpoint becomes eligible for calibration only through a later explicit
freeze/stabilization action covering multiple review sessions. That endpoint
must be immutable and identify the exact trajectory events it closes. If the
curator later changes their view, the system opens a new trajectory epoch; it
does not rewrite the old stabilized endpoint.

This ADR does not select an automatic stopping rule, minimum elapsed time, or
minimum number of sessions. The first implementation therefore captures and
visualizes trajectories but does not label any endpoint `stabilized` and does
not compute curator calibration scores.

### Keep information accounting receipt-bound

Future expected information gain for a review may be computed only when the
queue item carries a frozen, target-specific prior (p), model generation,
evidence snapshot, and acquisition policy. A later human update (q_t) may
support model-relative shift diagnostics, but it is not by itself the value of
the review and must not be reported as calibrated information.

Newly invented tags expand the ontology. They are recorded as ontology work,
not assigned fake bit values. Until the calibrated acquisition contract exists,
the queue may show review/estimate counts and `information estimate unavailable`
but must not sort by fabricated numeric bits.

## Rationale

An append-only trajectory preserves the curator's changing view and creates
the observations needed to learn whether stated ranges are informative. It
also avoids deciding today that the most recent opinion is truth. Separating
the soft estimate from the compatibility projection keeps current retrieval
consumers stable while the richer review contract is tested.

## Assumptions and Predictions

- Confidence `0.91`: curators can give a useful point estimate and plausible
  eventual range without interpreting it as model confidence. Predicted signal:
  repeated reviews sometimes move (q_t) while ranges narrow or shift.
- Confidence `0.94`: an additive event table can preserve all existing
  projection and event rows byte-for-byte. Predicted signal: source-table row
  digests are identical before and after a migration on a copied database.
- Confidence `0.84`: keeping estimate controls attached to the active tag will
  add less attention load than displaying sliders for every tag. Predicted
  signal: the default Review surface shows one compact summary and reveals the
  controls only for the selected tag.

Fallback: keep the new tables unpopulated and hide the controls while retaining
the existing binary workflow and append-only tag history.

## Constraints

- No live database migration occurs without a digest-backed dry run and a
  separate human gate.
- Range values must be finite and satisfy the invariant above.
- Session identifiers distinguish repeated review occasions; they are not
  proof of reviewer independence or elapsed-time sufficiency.
- Estimate history stays private and curator-scoped.
- `confidence`, `probability`, `credible interval`, `converged`, and
  `stabilized` are forbidden UI/API claims unless their corresponding later
  validation contract has passed.
- Evidence remains `unbound` until structured evidence receipts are added.

## Positions Considered

### Reuse `account_tags.confidence`

Rejected. It has no trajectory, range, session, or supersession semantics and
would silently reinterpret legacy data.

### Overwrite one current estimate

Rejected. It cannot show convergence, revision, or whether a frozen endpoint
was assembled from multiple reviews.

### Append estimate events and derive the current value

Accepted. It is the smallest reversible persistence model that keeps every
sample and supports a later explicit stabilization table without guessing the
stopping rule now.

## Validation and Migration Gate

The first implementation must prove on temporary databases that:

1. no estimate is created merely by opening an account or loading legacy tags;
2. valid point/range submissions append events and the latest event is derived
   without overwriting history;
3. invalid, non-finite, or misordered ranges fail with descriptive errors;
4. curator, account, tag, and review session remain isolated;
5. the UI exposes one active-tag estimate editor, explains the range, and shows
   prior samples without calling the latest sample converged;
6. the existing account-tag tables and their row digests are unchanged by the
   additive schema migration; and
7. a verifier prints counts, digests, samples, failures, and the exact next
   step for a human to approve or decline the live migration.

## Consequences

The system can begin measuring trajectories and later range calibration, but
it still cannot rank the queue by calibrated expected bits. Stabilization,
evidence receipts, ontology versions, calibrated priors, and ROC/calibration
views remain explicit later phases rather than simulated outputs.
