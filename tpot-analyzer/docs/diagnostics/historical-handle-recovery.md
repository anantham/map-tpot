# Shared historical handle targets

Status: research protocol, 22 October 2026. Not a live ranking method or an
identity-resolution policy. Account-level inputs and results remain private.

## Question and prediction

Can unresolved historical follow targets add useful overlap evidence without
joining them to present-day account IDs? Two numeric source accounts can share
a saved handle token even when we cannot establish that target's stable identity.
This is similarity of recorded features, not proof of a shared present-day person.

Use the unchanged co-follow arithmetic from `verify_cofollow_recovery.py`:
each seed divides mass across distinct observed targets; each target divides
that mass across observed numeric sources. Sum candidate contributions. Compare
three fixed views: already-qualified stable-ID follows, historical handle-target
features alone, and their union. The union is the primary view, not a winner
selected after seeing these results. Predict its definite top25 recovery exceeds
the best of the four existing stable-follow rankers in both directions. Report
gains and losses relative to stable co-follow as diagnostic, not a second primary.

## Source and identity boundaries

- Read only retained `shadow_follows_observed` relations from numeric source
  accounts to unresolved handle targets. Do not use alias-source edges or infer
  numeric identities from equal usernames, website text or later profiles.
- Require an independently admitted source profile. Reuse the existing numeric
  importer's severe flagged/protected/unavailable source exclusions. Missing
  provider metadata alone does not revoke an independently admitted source.
- Reconcile each selected original row, digest, pointer, capture time/channel
  and directed arrow. Inbound capture orientation already stores follower to
  followed; do not reverse it a second time. Repeated observations are one pair.
- Stable numeric targets and `shadow:handle` targets remain separate namespaces,
  even if they could represent one person. This may double-count a real-world
  relationship; there is no asserted identity merge or independence claim.
- Candidates and random-control seeds must be numeric IDs. Handle target tokens
  cannot be returned as people or used as random seed replacements.

## Measurement and falsifiers

Use the same extensional curator tags, hiding each IN label but not its edges.
Every IN remains in the denominator, including missing coverage. OUT is an
evaluation-only exposure check, not a fitted penalty or estimated precision.
No tag wording, other tags, keywords, content or NMF score enters ranking.

Keep conservative end-of-tie top25 recovery and possible beginning-of-tie counts.
Freeze labels, graph/metadata identities, code hashes and protocol before outcomes.
Run 16 deterministic observed-out-degree-stratified seed shuffles on the union,
using only numeric observed nodes and excluding the hidden target. These are
approximate controls, not calibrated p-values or an independent prospective panel.

The primary prediction fails if the union does not exceed the best stable
baseline. Retain zero gains and regressions without tuning. Small overlapping
labels, capture-center bias, unknown handle reuse and non-simultaneous historical
lists prevent broad community or membership claims even if recovery improves.

`scripts/verify_historical_handle_recovery.py` takes explicit private graph,
saved provider-metadata, tag and output paths. It isolates unused persistence
before application imports, reads sources only, retains per-fold original
arrows and writes a new private result directory. It never changes source data,
tags, identities, live graph bindings, Review defaults or contact routes.

## First fixed result, 23 October 2026

The exact candidate passes 30 focused/adjacent synthetic checks and independent
Google Gemini code/design review before outcomes. The reviewer retracts two
namespace-collision findings: their proposed numeric historical target cannot
pass the existing `shadow:` admission rule. Preserve the initial and corrected
reviews, rather than counting the contradictory first verdict as acceptance.

One frozen private run retains all 65 positive tag/account assignments across 46
distinct accounts and 10 tags. Stable co-follow recovers 6 definite top-25, handles
alone 9, and the predeclared union 10. The best old stable baseline recovers 9.
Thus the primary prediction is supported narrowly, not a broad validation of
community membership. Relative to stable co-follow the union gains four
assignments across three accounts/three tags and loses none. Recovered distinct
accounts rise from four to six; overlapping assignments are not distinct people.

The union uses 12,560 qualified historical pairs from 266 numeric source accounts,
plus 23,081 stable pairs, yielding 279 distinct outgoing source accounts. It cannot
rank the full profile inventory. Sixteen shuffled-seed totals are 4-8, median 6.5,
below the observed 10; approximate strata, reused overlapping labels and a small
control set do not justify a calibrated p-value or prospective claim.

The 65-assignment partition is 36 without usable outgoing follows, five with
outgoing evidence but no shared seed target, 14 reachable below 25 and 10 recovered.
The 36 missing assignments represent 27 accounts; this refers to the qualified
feature view, not proof no data exists elsewhere. Full per-fold original arrows,
dates, pointers, identities and code hashes remain private. No tuning, identity
merge, fetching, tag/source mutation, live promotion or push occurred. Next is an
explicitly experimental Review comparison with these source explanations, not
automatic adoption as a membership model or more integrity machinery.
