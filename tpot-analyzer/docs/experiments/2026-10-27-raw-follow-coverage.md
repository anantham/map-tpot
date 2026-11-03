# Raw follow coverage is not admitted graph coverage

Date: 27 October 2026. Private local-data investigation; no dataset activation.
This records aggregate methods and limits, not account-level research.

## Question and hypotheses

Can existing raw follow rows repair the missing outgoing coverage observed in
the tagged-account recovery experiment? H1 (0.65): some raw exact numeric pairs
are absent from the active graph. H2 (0.8): source/time/privacy qualification,
not an arithmetic bug, prevents treating those rows as interchangeable edges.

Three local research lanes independently compare rows, trace producer/consumer
contracts and audit source qualification. Root integrates in clean-main. Inputs
are read-only; the previous tag experiment supplies the exact 27-source cohort.
This cohort was selected after observing misses, not prospectively sampled.

## Exact reconciliation

The selected `account_following` domain contains 50,819 distinct stored pairs
and 34,625 target literals. Of these, 50,791 rows have exact numeric targets;
28 do not and are not resolved by name, handle or community similarity.
No numeric pair matches a same-direction active follow predicate. Four
reverse-only matches are different arrows and do not count as coverage.

Normalized `account_followers` supplies 1,191 rows; 1,134 overlap the first
family, leaving 57 additional structural pairs. The two-family union is 50,876
stored pairs before identity/privacy qualification, not 50,876 usable edges.

The active stable graph has 23,140 observations representing 23,081 distinct
directed pairs. Observation counts, pair counts and source accounts are separate
denominators. The raw cohort is not the whole raw database or all followed people.

The separate `cache.db.archive_following` staging table has 161,590 rows across
130 sources, but zero exact-source overlap with this cohort. It supplies no
corroborating source/date witness here. Even where present, `uploaded_at` and
`imported_at` describe upload/import metadata, not relationship capture time.

## What the rows cannot prove

The raw tables retain only endpoint IDs; repeated `INSERT OR IGNORE` imports
can accumulate them. A profile fetch time cannot date a follow. Existing typed
importers require receipt-bound responses or shadow-row capture metadata, so
neither can honestly ingest this source unchanged. Legacy matrix consumers
reading the raw table directly are not evidence it is connected to Review.

Privacy checks are distinct axes. There are 218 numeric pairs touching a
contact-cohort hold. Two historically protected source profiles account for
323 rows, partly overlapping that set; four metadata-absent sources account for
6,800 rows. These counts cannot be added as disjoint exclusions. Generic
graph-missing dispositions are not eligible-to-import dispositions.

An audit also catches a diagnostic trap: projected profile attributes omit
protection flags. Testing `attrs.get('protected') is True` then serializing false
does not establish explicit public status. Preserve the original diagnostic and
the correction; qualify actual saved provider objects instead.

## Bounded offline sensitivity protocol

Before outcomes, freeze the existing curator, tag rows, source identities,
exact selected raw pairs, scorer bytes and selection rules. Reuse unchanged
co-follow arithmetic; compare the current stable-plus-handle union with that
union plus the qualified raw delta. Both endpoints must have independent
non-Archive profile evidence and a qualifying saved provider object with
explicit `protected=false`; exclude known flags and contact holds. Missing
qualification is unknown, not an OUT judgment. Keep every eligible IN in the
evaluation denominator and report tied top-25 gains and losses without tuning.

Empty-delta and reversed-arrow synthetic controls precede the one outcome run.
Raw witnesses retain exact table/pair provenance and unknown relationship time;
they are not synthetic HTTP receipts. This is a retrospective sensitivity test,
not source permission, a prospective improvement estimate or membership
probabilities. No graph row, tag, curator event or Review default is changed.

## One frozen outcome, 27 October 2026

The raw selection admits 9,316 pairs from 21 source accounts; every admitted
pair is new to the baseline. First-failure exclusions reconcile all 50,819 rows:
34,406 lack an independent non-Archive endpoint profile, 6,690 fail the saved
profile decoder for missing raw data, 218 touch a contact hold, 159 fail for
protected-at-capture data, two touch the explicit protected-account set and
28 have nonnumeric endpoints. These are ordered selection counts, not separate
population estimates or complete current privacy assessments.

| Across the same 65 IN tag/account examples | Current union | Union plus raw delta |
| --- | ---: | ---: |
| Examples with observed outgoing features | 29 | 58 |
| Examples reachable from other same-tag seeds | 24 | 55 |
| Definite top-25 hide-and-recover hits | 10 | 31 |
| Possible top-25 hits including ties | 10 | 31 |
| OUT-tagged exposures in per-tag top-25 lists | 0 | 1 |

There are 24 newly recovered assignments across 20 accounts and three lost
assignments across two accounts. Overlapping tag examples are not distinct
people. All ten tag groups have rank changes; do not report the net gain while
hiding regressions or the increased OUT exposure.

Empty-delta and reversed-arrow controls pass before real preparation. Root
corrects a missing explicit flagged-account filter and a duplicate count/list
serialization key before freezing any real outcomes; both earlier helpers are
retained. No rerun or parameter selection follows the measured result.

This is evidence that more source-qualified outgoing coverage is worth pursuing,
not that the raw rows are fit for serving. Accumulated/undated pairs can create
overlap that did not coexist, and selection was driven by earlier tag misses.
Prospective recovery with newly admitted policy-aware data may differ. No
membership probability, precision estimate or independent validation follows.

## Serving dependency

The earlier [source-family decision](../diagnostics/tag-seed-recovery.md)
chooses policy-aware current Archive reads rather than a raw-table fallback.
Its personal key was not found in this turn's checked shell, project env files
or launcher chain; this is not a search of every possible credential location.
No network acquisition, paid call, outreach, restart or push occurs here. Other
saved-source contact-card work can continue independently.

## Saved target profiles: absence, eligibility and exact source delta

A later read-only check asks whether this same raw-target subset can supply
the next 100 profile imports without fetching. H1 (0.6) tests missing locators;
H2 (0.65) tests missing fields/source observations despite an existing locator.
Do not redefine the subset or its zero result to manufacture an import batch.

For context, the entire raw `account_following` table has 873,827 rows across
44,013 source IDs and 295,444 target literals. That is not the frozen 27-source
population and the table name does not establish every row's origin. In the
subset, 34,597 target IDs are numeric; no nonnumeric identifier is joined by name.

| Current local view of those numeric target IDs | Count |
| --- | ---: |
| Admitted profile locator | 5,774 |
| Only publication-gated profile evidence | 192 |
| Graph entity but no profile observation | 41 |
| No graph entity | 28,590 |

These are account-ID records, not distinct people or confirmed identities.
Publication is unchecked, not proof that the gated accounts are unpublished.
Another 399 IDs have both a published-source observation and an alternate
admitted locator; do not add these to the mutually exclusive table above.

The provider cache has 2,605 rows for the subset. The maintained decoder accepts
2,310; 204 lack raw JSON and 91 explicitly say protected at capture. Eleven
accepted rows remain curator-held. All remaining 2,299 already have visible
locators. Reproduce the importer in memory, then compare exact retained payload
bytes, `/raw` anchors, dates and field tuples: all 2,299 are already represented.
There is no missing-profile or substantive field/source delta here.

Units matter. The subset has 31,992 targets with no cache row. The ordered
disposition bucket says 31,976 because 16 are assigned first to hold/protection
states. Distinct cohort holds, explicit protected-account records and raw
protected-at-capture booleans are separate axes. Missing projected privacy
attributes are not explicit false/public clearance.

A separate whole-cache operational audit checks all 9,706 numeric rows, without
changing the subset experiment. Exclude 25 curator holds first, then 399 missing
raw payloads and 516 protected-at-capture rows. All 8,766 remaining profiles pass
the unchanged importer and already match the admitted graph byte-for-byte at
the exact source/anchor/date, with the same handle, name, bio, location, website,
follower/following counts and capture time. No new literal fields or distinct
source observations remain. The graph's 9,738 provider-profile IDs also include
other producers; aggregate counts alone would not prove cache completeness.

Do not create an empty graph derivative or call repeat importing new coverage.
Keep per-ID witnesses, exclusion dispositions, source identities and reproduction
recipes privately. This establishes consolidation of eligible rows in this cache,
not of all local source families, nor coverage of the public network. It does not
qualify undated raw follow edges or establish current group membership.

Code, raw stores, tags, journal, active graph/post/catalogue binding and rollback
remain unchanged. No acquisition, paid call, outreach, live restart or push.
The next release remains the separately prepared bio-email review journey after
its review/serving gates; further network coverage needs qualified source data,
not another copy of these already-imported profiles.

## Captured following-profile URLs: corrected producer, zero usable delta

A separate bounded follow-up removes an incorrect older-cache-row prerequisite
from a prior URL census. Receipt-bound following objects share a provider source
kind but do not require an unrelated Archive cache row. Reuse the existing source
verifier, exact raw ID/handle/public flags, snapshot, pointer, receipt and date;
never relabel unsupported historical occurrences to make them qualify.

The saved capture contains the exact 1,650-ID following cohort. Exclude all 48
holds before inspecting links; all 1,602 remaining profiles have their expected
observations. Of 6,163 inspected graph link observations, 671 are non-provider
sources and 3,940 are outside these following-object pointers. The remaining
1,552 pass source and receipt checks: 1,153 profile-URL values and 399 description
links, all opaque `t.co` destinations. Four capped previews are supplemented from
the same read-only relations rather than treated as exhaustive API results.

Compare original fields separately to avoid blaming an importer for missing
acquisition. All 1,153 direct raw URL fields have matching graph relations; the
captured objects contain no URL/description entity fields with expanded values.
There are zero useful new account/value pairs. Do not activate an empty copy or
interpret excluded opaque links as no website or no contact route. This does not
re-audit other source families or establish that every historical field is stored.

The private witness report initially renders an absent `unavailable` field as
false. Preserve original hashes and append the exact missing/not-true correction;
all audited profile objects omit the key. No selection or zero-yield result changes.
Source and semantic audits remain private. Existing catalogue, graph, post index,
raw sources, tags, journal and rollback are unchanged. No acquisition, paid call,
outreach, restart or push; the separate prepared bio-email journey keeps its gates.
