# Dharma Boundary Pretrial Protocol

- Registered: 2026-07-31
- Status: Evidence acquisition halted fail-closed; human passes not run
- Parent protocol:
  [Budgeted Personal-Ontology Pilot](2026-07-26-budgeted-personal-ontology-local-first-pilot.md)
- Inferential status: formative and descriptive only

## Purpose

Before freezing the first real ontology task, run a non-confirmatory pretrial
over 12 purposively selected accounts from the dated takes snapshot. Test
whether the human can answer two proposed questions consistently and whether
they encode meaningfully different boundaries. These responses are not
Community Gold and must not train or score a model.

## Fixed questions

1. **Retrieval relevance:** “Should this person be surfaced when searching for
   people relevant to Dharma, meditation, or jhāna community-building?”
2. **Social affiliation:** “Based on public evidence, is this person socially
   affiliated with the Dharma community as Aditya uses that term?”

Retrieval relevance is a search-policy target, not
`participation_interest`. Social affiliation may later bind to the existing
`affiliation` target type. A distinct retrieval-relevance contract is
considered only if observed disagreement justifies it; this pretrial does not
authorize ontology/schema expansion.

## Panel and passes

Use four likely-positive controls, six boundary cases, and two likely
negatives selected before answer reveal from the private takes snapshot. Keep
ordered account identities, strata, and digest in a private run manifest.
Shuffle independently within each of two passes and hide all first-pass
answers and notes during the second.

For each account and pass, record:

- both `IN` / `OUT` / `ABSTAIN` answers;
- elapsed review time;
- whether external investigation was needed; and
- one typed evidence note.

The private `4/6/2` panel excludes every candidate found in the historical
TPOT directory holdout. Its selection-manifest SHA-256 is
`ce680f1a88fb9d4b2dd1af169c1ce741eaca3e9d3dcaa83f834f6d1cbfdc83ce`.
Only aggregate facts and hashes enter git.

## Falsifiers

The proposed task split survives only if at least two of 12 accounts receive
different non-abstain answers across the two questions. Fewer than two means
separate targets have not demonstrated useful resolution and the wording
should be revised or combined before schema work.

If more than 25% of answers abstain, the dossier or definitions are
inadequate. If either question has less than 75% exact repeat agreement across
the two passes, do not freeze it as a task. Report disagreement, abstention,
median time, external-search rate, and repeat agreement as descriptive counts
only. This purposive panel cannot estimate population prevalence or predictive
performance.

## Pre-data evidence amendment

A read-only coverage check found profiles for 5/12 panel accounts and authored
tweets for 1/12, so mutable local evidence cannot support a comparable pass.
Before pass one, materialize exactly one current public profile and at most 20
recent public tweets for every account.

This fixed evidence preparation is not adaptive: no answer, model output, or
returned content may alter the panel, questions, or action count. An
unavailable, protected, or identity-conflict case stops preparation and
requires a new pre-answer panel manifest.

The credential-free plan uses price card
`twitterapiio-2026-07-30`, semantic SHA-256
`eab5a0810df86593164562636d82f616947984c79a67ce9a32eccfe13d2a9ab2`.
Its revised maximum is 26 calls: 24 evidence calls plus two before/after
balance checks, 12 profiles, 240 tweets, and a 3,846-credit (USD 0.03846)
local reserve below the USD 0.05 planning ceiling. The executor can enforce
the call count and stop before an unreserved action, but twitterapi.io exposes
no provider-side dollar ceiling; balance telemetry detects rather than prevents
unexpected billing. The balance endpoint also has no published endpoint price,
so its 30-credit share is explicitly conservative and unverified. Plan SHA-256 is
`2470a84f7cb1867b26577118d0df42731c17accb7c8fe941ea8f971c9681d3a4`;
it supersedes the unexecuted `f352851e…` and `3c66b735…` plans.
The plan says `authorizes_execution=false`; this amendment records the design,
not a paid call.

After the evidence is frozen, the pretrial permits no adaptive paid action.
Every actual preparation charge requires request/response and balance receipts.
For this run, “cap” therefore means the maximum locally scheduled exposure at
the pinned price card, not a guarantee about provider billing behavior.

## Evidence acquisition result (2026-08-01)

The one authorized attempt remained bound to panel SHA-256 `ce680f1a…`, plan
SHA-256 `2470a84f…`, and price-card SHA-256 `eab5a081…`. It stopped fail-closed
after four HTTP-200 calls: before-balance telemetry, one validated profile, one
rejected recent-tweets envelope, and after-balance telemetry. No retry,
replacement, or content-adaptive request occurred, and balance telemetry
measured zero credits debited.

The rejected response placed 20 tweets under `data.tweets`; the strict parser
required a top-level `tweets` list. Aggregate private checks found an object
list, unique tweet IDs, and author identities consistently bound to the
validated profile. Existing repository endpoint documentation and an older
fetcher already describe this nested envelope, so the stop is registered as a
local response-contract test gap rather than demonstrated provider drift or an
account-level panel failure.

The ignored private run directory
`data/private/research-notes/dharma-boundary-pretrial-v1/run-20260801T045601Z-a4bb7a0/`
retains the exact sources, logical holdout snapshot, preflight receipt, aborted
execution receipt, self-hashed partial response artifact, and four durable
attempt/response/observation triples. Its receipt hash is `2b128d5e…` and its
partial-record artifact hash is `20f76028…`. No completed evidence artifact,
dossier snapshot, human answer, gold judgment, or model output was created.

This attempt must not be silently resumed. EXP-033 records behavior-first
support for the documented nested envelope and a complete post-key private-safe
console boundary. Human review rejected a generalized live-bundle verifier as
disproportionate to this four-call, zero-debit abort; that prototype is parked,
not a prerequisite for the next free experiment. Run the registered $0
ontology-boundary and ranking tests before reconsidering acquisition. A second
paid attempt still requires fresh explicit authorization under the no-retry promise.
The panel manifest does not need replacement solely for this schema-contract
failure; its registered replacement rule still applies to unavailable,
protected, or identity-conflicted accounts.

## Completion boundary

Do not call either answer gold, fit a task head, expand the schema, or inspect
the second-pass comparison until both blinded passes and their immutable
receipt are complete. A failed falsifier is a useful negative result, not an
implementation failure.
