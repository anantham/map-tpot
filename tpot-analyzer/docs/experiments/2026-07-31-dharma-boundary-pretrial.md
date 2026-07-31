# Dharma Boundary Pretrial Protocol

- Registered: 2026-07-31
- Status: Planned; evidence acquisition and human passes not yet run
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
`f795e1704f5d8bb0337f1d1deb3e81276750a98dd4485dac7285ff6f2f9dd2bb`.
Its maximum is 24 calls, 12 profiles, 240 tweets, 3,816 credits, or USD
0.03816 under a USD 0.05 hard cap. Plan SHA-256 is
`f352851ed285493445bb2baecc3ef69714bc9db71ab945b3abe63b0c360fb8ab`.
The plan says `authorizes_execution=false`; this amendment records the design,
not a paid call.

After the evidence is frozen, the pretrial permits no adaptive paid action.
Every actual preparation charge requires request/response and balance receipts.

## Completion boundary

Do not call either answer gold, fit a task head, expand the schema, or inspect
the second-pass comparison until both blinded passes and their immutable
receipt are complete. A failed falsifier is a useful negative result, not an
implementation failure.
