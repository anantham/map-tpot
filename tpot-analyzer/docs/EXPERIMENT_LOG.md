# Experiment Log

> Hypotheses tested, results observed, lessons learned. This is institutional memory — what we tried, what worked, what didn't, and why. Each entry records the question, the method, the data, and the verdict so future sessions don't re-run failed experiments or miss validated insights.

*Last updated: 2026-08-01 (first live dossier attempt)*

---

## EXP-032: Does the frozen dossier contract survive its first live response?

**Date:** 2026-08-01

**Question:** Can the exact 12-account dossier plan complete its first bounded
live acquisition without a schema, identity, privacy, durability, or cost
falsifier?

**Hypothesis:** The 145 focused tests, six-check synthetic verifier, real dry
preflight, and adversarial audit are sufficient for plan `2470a84f…` to produce
a completed evidence artifact and blind snapshot. A rejected provider envelope,
identity mismatch, missing durable event, retry, private console disclosure, or
debit above the accepted local reserve falsifies it.

**Method:** Executed the frozen plan once from commit `a4bb7a0` with its exact
4/6/2 private panel, price card, 3,846-credit/USD 0.03846 local reserve, 26-call
maximum, and no-retry transport. The executor persisted every attempt, full
credential-free JSON response, and sanitized observation before proceeding.
After its fail-closed stop, inspected only aggregate structure, hashes, modes,
and booleans; no account identity, account/tweet ID, or post text was printed.

**Result:** **COMPLETION HYPOTHESIS REJECTED; FAIL-CLOSED BOUNDARY CONFIRMED.**
The run made four HTTP-200 calls: before-balance telemetry, one profile, one
recent-tweets request, and after-balance telemetry. The profile validated. The
recent-tweets response was durably captured but rejected because the new parser
required a top-level `tweets` list while the provider returned `data.tweets`.
This was not demonstrated provider drift: `docs/TWITTERAPI_ENDPOINTS.md` and
the existing `fetch_tweets_for_account.py` already described and parsed the
nested envelope. The captured list contained 20 structurally valid, uniquely
identified tweets whose authors all bound to the validated profile; content was
not interpreted.

No retry, replacement, or adaptive action occurred. Before/after balance
telemetry completed and measured **0 credits debited**. The private run retained
four attempt/response/observation triples, a validated self-hashed aborted
receipt (`2b128d5e…`), and a validated self-hashed partial-record artifact
(`20f76028…`). It correctly produced no completed evidence artifact or dossier
snapshot.

**Lesson:** Synthetic HTTP-shaped fixtures are not enough when an existing
repository contract already records the real envelope. Before live execution,
the strict parser must be tested against the documented `data.tweets` shape,
and legacy endpoint knowledge must be searched rather than guessed. Fail-closed
execution limited this preventable error to one evidence request and preserved
an auditable negative result.

**Data stored:** Ignored mode-0700 private bundle
`data/private/research-notes/dharma-boundary-pretrial-v1/run-20260801T045601Z-a4bb7a0/`
with mode-0600 exact sources, holdout snapshot, preflight/aborted receipts,
partial raw records, and four durable event triples. Git contains only this
aggregate account-free report.

**Next step:** Do not rerun this attempt. First add a behavior test and parser
support for the observed nested envelope, make every post-network transform
failure private-safe, and add a reusable privacy-safe live-bundle verifier. A
second paid attempt requires fresh explicit authorization under the same
no-retry promise; the panel need not change because no account was unavailable,
protected, or identity-conflicted.

---

## EXP-031: Does the first executor remain safe under adversarial interruption?

**Date:** 2026-07-31

**Question:** Is the synthetically green acquisition chain ready for its first
paid call when privacy, process interruption, holdout renames, provider
overbilling, and replay are treated as falsifiers rather than happy-path edge
cases?

**Hypothesis:** The EXP-030 executor is already safe to run because its final
receipt, fixed plan, and no-retry transport are sufficient. It is falsified if
private bodies can enter a trackable path, a paid response can disappear on
process death, a renamed holdout account can pass by handle, dry preflight can
green-light a malformed plan, or the advertised dollar cap is not enforceable.

**Method:** Three computational peers independently traced the frozen inputs,
HTTP boundary, receipts, raw evidence, and snapshot transform. Each finding was
converted into a behavior-first regression. The corrected chain was then run
through 145 focused tests, the six-check human verifier, and the real
credential-free panel/archive preflight.

**Result:** **INITIAL READINESS REJECTED; HARDENED CHAIN CONFIRMED LOCALLY.** The
audit found all five registered falsifiers plus a cross-account duplicate-tweet
gap. Output is now confined to resolved ignored `data/private`; exact inputs and
logical holdout exclusions are copied before credential access; every attempt
and credential-free JSON response is atomically fsynced per call; dry preflight
validates the full plan; resolved provider IDs are checked against 288 frozen
holdout IDs before tweets; and snapshot-wide tweet IDs are unique. The real
read-only holdout snapshot contains 368 normalized handles and 288 IDs under
logical SHA-256 `364cb3df…`, with panel overlap zero.

The broader local suite passed 1,648 tests with two skips. Its only three
failures were unmarked live Supabase connection tests under restricted DNS;
that isolation debt is recorded separately rather than attributed to this
experiment.

The pricing audit also rejected one phrase, not the 26-call design:
twitterapi.io exposes no provider-side dollar ceiling. The executor enforces a
26-call no-retry schedule and a 3,846-credit local reserve at the pinned price
card; final balance telemetry can detect, but cannot prevent, provider
overbilling or an undisclosed balance-call price.

**Lesson:** A final receipt is not crash durability, a handle is not a stable
identity, and a local cost guard is not a provider billing guarantee. These
distinctions belong in the executable boundary before the first paid datum.

**Data stored:** Tracked code/tests/docs and read-only aggregate holdout facts.
No credential, provider request/response, model call, human answer, or paid
credit was used.

**Next step:** Commit the hardened chain, then execute plan `2470a84f…` once.
Any unavailable identity, holdout-ID collision, schema drift, journal failure,
or other mismatch stops without a replacement or retry.

---

## EXP-030: Can the exact dossier plan reach a frozen snapshot fail-closed?

**Date:** 2026-07-31

**Question:** Before spending, can one independently accepted plan travel from
local artifact preflight through HTTP-shaped responses, receipts, raw evidence,
and a blind immutable dossier snapshot without retries, identity drift, hidden
model fields, or an unrecorded paid attempt?

**Hypothesis:** A small executor with an injected transport can stop before the
next action on any hash, price-age, cap, holdout, schema, identity, timestamp,
or response mismatch while retaining enough private evidence to reproduce the
displayed dossier. Any silently accepted mutation, missing attempted-call
receipt, retry, leaked post text in the receipt, or non-reproducible snapshot
falsifies it.

**Method:** Wrote behavior-first contracts for explicit plan acceptance,
ordered calls, balance observations, profile/tweet identity, decimal X IDs,
canonical timestamps, HTTP origin/parameter allowlists, response capture,
receipt reconciliation, raw-evidence hashing, and snapshot transformation.
Ran 120 focused tests and a six-check human verifier with fake responses. Then
ran the filesystem/SQLite preflight against the actual private panel, revised
price card, exact plan hash, and canonical archive in read-only mode.

**Result:** **CONFIRMED SYNTHETICALLY; LIVE OUTCOME STILL UNKNOWN.** All 120
tests and 6/6 verifier checks pass. The real credential-free preflight confirms
12 panel and plan targets, 4/6/2 strata, 12 profile plus 12 recent-post calls,
240 posts maximum, required holdout table present, and zero overlap. The
executor has no retry path; reserves/logs an attempt before parsing; preserves
sanitized per-call timestamps, response hashes, counts, and balance delta; and
builds a content-addressed private evidence artifact plus blind snapshot.

**Lesson:** The receipt and raw evidence are different artifacts. A sanitized
receipt is safe to inspect but cannot reproduce a dossier; the separately
private response artifact is what lets the display snapshot be recomputed.

**Data stored:** Source, tests, and read-only aggregate preflight results only.
The private plan remains unexecuted; no credential was read by the verifier and
actual provider/OpenRouter spend remains USD 0.

**Next step:** Commit this exact executable chain, then run plan `2470a84f…`
once at its exact 3,846-credit (USD 0.03846) reserve. Unavailable identity,
schema drift, or any other mismatch ends the run without replacement or retry.

---

## EXP-029: Does the price card bind the canonical profile reference?

**Date:** 2026-07-31

**Question:** Is every source identity inside the dated price card still a
retrievable canonical provider document before preflight treats its hash as
authoritative?

**Hypothesis:** The stored `get_user_info` documentation slug remains the
provider's canonical profile reference. A different canonical slug in the
official endpoint index falsifies that provenance identity even if the endpoint
and price themselves are unchanged.

**Method:** Reopened the official profile and last-tweets references, compared
their published paths and response envelopes with the card, then pinned the
canonical profile source string and semantic card hash in a behavioral test.

**Result:** **SOURCE-IDENTITY HYPOTHESIS REJECTED; PRICES UNCHANGED.** The
profile route is still `/twitter/user/info` at 18 credits, but its canonical
documentation slug is `get_user_by_username`. Correcting only that source
changes the semantic price-card SHA-256 to
`eab5a0810df86593164562636d82f616947984c79a67ce9a32eccfe13d2a9ab2` and
the unexecuted private plan SHA-256 to
`2470a84f7cb1867b26577118d0df42731c17accb7c8fe941ea8f971c9681d3a4`.

**Lesson:** Human-readable provenance is part of a content-addressed plan, not
decoration. Correcting it must invalidate downstream hashes before execution.

**Data stored:** The prior unexecuted private plans remain explicitly marked
superseded. No credential, API response, model call, or paid credit was used.

**Next step:** The live preflight may accept only plan `2470a84f…`, the revised
card hash, the exact selection file hash, and zero historical-holdout overlap.

---

## EXP-028: Does the dossier plan reserve every call needed for a receipt?

**Date:** 2026-07-31

**Question:** Can the first dossier plan honestly guarantee its USD 0.05 cap
when its required before/after balance observations were not in the reserve?

**Hypothesis:** The documented account-information endpoint is free telemetry,
so excluding its two calls does not weaken the cap. It is falsified if no
authoritative endpoint-specific price can be found, because “free” would then
be an assumption rather than a verified bound.

**Method:** Rechecked the provider's official pricing page and balance-endpoint
reference, then added a boundary test at a 3,830-credit cap. The old planner's
3,816-credit evidence-only reserve was predicted to pass that cap; a safe plan
reserving two telemetry calls at one published 15-credit tweet-call minimum
each was predicted to reject it.

**Result:** **HYPOTHESIS REJECTED; PLAN SUPERSEDED BEFORE EXECUTION.** The
official balance reference documents `GET /oapi/my/info` and
`recharge_credits`, but not an endpoint-specific charge. The boundary test
failed against the old implementation and passes after adding a clearly marked
30-credit `conservative_unverified` telemetry reserve. The revised maximum is
26 calls, 3,846 credits, or USD 0.03846. Its plan SHA-256 is
`3c66b7353e393bb0b266000261204345bfce2031dbc617301e5ae600bc07fd56`.

**Lesson:** Observability is part of the acquisition budget. An undocumented
price must widen the reserve, not silently become zero. The executor's actual
before/after balance delta will tell us whether the reserve was conservative.

**Data stored:** The original private plan was retained as explicitly
superseded; a new mode-0600 ignored plan was generated. No credential, network
request, response, human answer, or paid credit was created.

**Next step:** Permit an executor only for the revised exact plan hash and make
schema, identity, balance, or cap drift stop before the next evidence action.

**Supersession note:** EXP-029 replaced this still-unexecuted plan after fixing
the canonical profile-documentation slug; its reserve and targets did not move.

---

## EXP-027: Can the formative Dharma panel start from local evidence alone?

**Date:** 2026-07-31

**Question:** Does the canonical local archive contain comparable recent
profile-and-post dossiers for a fixed 12-account Dharma boundary panel, and if
not, what is the fail-closed worst-case cost of standardizing those dossiers
before any answer is revealed?

**Hypothesis:** Most purposively selected accounts from the dated takes
snapshot will already have a profile and recent authored posts locally, so the
two-pass wording test can begin without an external observation. It is
falsified if substantial panel coverage is absent or temporally incomparable.

**Method:** Selected four likely-positive controls, six boundary cases, and two
likely negatives into a private manifest before pretrial answers. Candidates
present in the historical TPOT directory holdout were excluded. Queried the
canonical SQLite archive in read-only mode for profile and tweet coverage.
Then verified the current official twitterapi.io price card and built a
credential-free, content-addressed plan for exactly one profile request and at
most 20 recent tweets per account. The plan reserves the worst billable return
for every action, is capped at USD 0.05, and explicitly cannot execute.

**Result:** **FALSIFIED for local-only start; CONFIRMED for bounded planning.**
Only 5/12 panel accounts have a local profile and only 1/12 has any local
authored tweet row; the one populated timeline is historical rather than a
comparable current dossier. Standardizing all 12 accounts requires at most 24
requests, 12 profiles, and 240 returned tweets. At 18 credits/profile and 15
credits/tweet, the worst-case reserve is 3,816 credits, or USD 0.03816. The
private selection has zero overlap with the historical holdout table. The
plan's semantic SHA-256 is
`f352851ed285493445bb2baecc3ef69714bc9db71ab945b3abe63b0c360fb8ab`.

**Lesson:** NMF is not the immediate blocker for this test; evidence coverage
is. A tiny, fixed, pre-answer dossier fill is more informative than purchasing
broad follow graphs before we know whether the proposed questions are stable.
Uniformly materializing the same profile-plus-20-post view also avoids giving
positive controls systematically richer evidence than boundary cases.

**Data stored:** A mode-0600 private panel and plan under ignored
`data/private/`; tracked pure pricing/planning contracts, tests, and verifier.
No private identity, response body, credential, API request, database write,
model call, human answer, or paid credit was created.

**Next step:** Review and implement a receipt-producing executor that can run
only this exact plan hash, then freeze the returned dossiers before the first
answer. Any schema, identity, holdout, price, balance, or cap mismatch must stop
without spending the next action's reserve.

---

## EXP-026: Can paired boundary judgments be made while reading a real dossier?

**Date:** 2026-07-31

**Question:** Does the Research Notes layout let the curator compare raw posts
with separate retrieval-relevance and social-affiliation questions without
losing drafts or mistaking formative answers for gold?

**Hypothesis:** Two visibly separate `IN`/`OUT`/`ABSTAIN` probes, keyed by
account and question, will preserve disagreement and remain usable beside the
existing 20-post dossier. It is falsified if navigation erases an answer or
note, the UI collapses both answers into one status, the labels look durable,
or the questions are not reachable while inspecting evidence.

**Method:** Added a behavior-first two-account navigation test, then inspected
the live local UI against the existing read-only archive dossier for one public
account. Selected different answers for the two probes and checked the queue
status and `aria-pressed` state. No answer was persisted. The first and amended
layouts were inspected at the same desktop viewport.

**Result:** **PARTIALLY FALSIFIED, THEN REPAIRED.** State behavior passed: both
answers and the edited note survived account switching, and the queue reported
`2/2 drafted`. The first visual pass failed the reachability condition because
20 long posts placed the questions several screens below the evidence. Moving
review controls into a sticky side panel kept both the dossier and questions
visible; narrower viewports stack the questions above the dossier. The UI
continues to say `Unbound preview`, `session-only`, and `not gold labels`, and
the save control remains disabled.

**Lesson:** A correct state machine is not a usable labeling interface. The
evidence and the action must be spatially co-present, especially when the
dossier itself is long. Layout inspection is a required signal for this slice,
not a cosmetic afterthought.

**Data stored:** Session-only browser state plus source/tests. The local dossier
route opened the existing SQLite archive read-only. No gold row, raw response
artifact, external request, or paid credit was created.

**Next step:** Run the registered 12-account/two-pass formative protocol after
timing, external-investigation, and blinded-repeat capture exist. Do not infer
task validity from this one UI exercise.

---

## EXP-025: Can the real takes snapshot be imported without losing rationale or inventing subjects?

**Date:** 2026-07-31

**Question:** Does the line-oriented Research Notes parser preserve enough of
the user's actual notes to support review, and does every extracted handle
refer to an intended subject rather than an account merely cited inside the
subject's bio or rationale?

**Hypothesis:** Treating standalone profile references as block boundaries,
keeping explicit co-subjects with the preceding claim, and storing exact
source spans will recover the intended 57 subjects. It is falsified by a lost
multi-paragraph rationale, by `@cisco` or `@ai4bharat` becoming subjects, by
missing `meaningaligned` or `chrislakin`, or by any stored span that is not an
exact slice of the input.

**Method:** Added behavior-first parser cases for multi-paragraph blocks,
standalone employer citations, a `same with @meaningaligned` co-subject, and a
display-name-plus-handle header. Ran the old parser to establish the RED
result, implemented block parsing with immutable `sourceStart`, `sourceEnd`,
and `sourceText`, then ran the same parser read-only over the private takes
snapshot. The private text was not copied into the repository.

**Result:** **CONFIRMED for this dated snapshot.** The old parser returned 59
subjects, reduced each note to one line, and incorrectly promoted `@cisco` and
`@ai4bharat`. The amended parser returned 57 subjects, retained both explicit
co-subject/display-name cases, produced zero false subjects from those cited
employers, and produced zero source-span mismatches. The checked snapshot was
10,311 bytes with SHA-256
`b9e9d616c0a79933f7f6a33dbf6cad0990e4ca1611fe48af5904a7d610e30cc0`.

**Lesson:** Handles inside evidence are not automatically labeling subjects.
The import boundary is part of the methodology: exact immutable source
provenance must remain separate from the editable investigation note. An
explicit “same with” statement is a co-subject sharing context, not an empty
one-line account block.

**Data stored:** Parser code/tests and the optional read-only takes check in
`scripts/verify_research_notes_inbox.py`. No raw takes content, database row,
network response, or paid acquisition was stored.

**Next step:** Add account- and question-keyed provisional drafts for the two
Dharma boundary probes. Keep them out of Community Gold until a canonical
task, snapshot-bound dossier, and idempotent scoped write exist.

---

## EXP-024: Does independent-Lift entropy support the displayed account bands?

**Date:** 2026-07-30

**Question:** Is the entropy used by `classify_bands` a valid, useful
concentration measure for unbounded independent PPR Lift? Are the stored
specialist/bridge/frontier labels compatible with the active propagation
artifact, and can they safely steer public export or acquisition?

**Hypotheses:**

1. A quantity advertised as normalized entropy lies in `[0,1]` and is
   invariant when every affinity in a row is multiplied by the same positive
   constant.
2. The entropy predicate changes at least one active band; otherwise it adds
   no information to the classifier.
3. Two or more qualified high community signals are not overwritten as a
   specialist merely because their absolute Lift scale is large.
4. Stored bands and their downstream memberships come from the same
   propagation run.
5. Replacing the bad calculation with mathematically normalized entropy is a
   numerical repair that preserves classifications.

**Method:** Opened the active propagation NPZ and archive database read-only.
The selected NPZ has SHA-256 prefix `1d12f3371205260d`, mode `independent`,
298,347 rows, and 16 community Lift columns plus synthetic `none`. Reproduced
the historical formula `-Σx log(x)/log(K)`, compared it with
`p=x/Σx; -Σp log(p)/log(K)`, applied a 7x scale transformation, and inspected
stored entropy/count/timestamp rows. Recomputed the historical classifier in
memory under three counterfactuals: deleting its entropy predicate, swapping
in correct compositional entropy, and examining bridge/specialist overlap. No
NPZ, database, public export, ranking, or API state was written.

**Result:** **All five hypotheses were falsified. Independent display bands
are undefined and are now fail-closed.**

- Historical “entropy” ranged from `-1190.1798` to `1.9756`; 30,434 rows were
  outside `[0,1]`. Rescaling a synthetic `[10,2,0]` row to `[5,1,0]` changed
  it from `-22.2209` to `-7.3249`.
- Correct row-normalized entropy ranged from `0` to `0.975667`, with zero
  values outside `[0,1]` and maximum delta `0` after multiplying the artifact
  by seven.
- Removing the historical entropy predicate changed exactly zero active
  bands. It was computationally present but empirically inert.
- Correcting only entropy changed 1,793 bands: 659 specialist-to-bridge and
  1,134 specialist-to-frontier. Therefore a silent formula swap is a
  classification/taxonomy change that requires evaluation.
- A synthetic row with two equal high affinities satisfies the bridge rule but
  is overwritten by the later specialist rule. On the active artifact, 900
  rows satisfy both the corrected specialist predicate and the independent
  bridge predicate.
- Stored counts are bridge `1,451`, exemplar `361`, frontier `10,018`,
  specialist `6,964`, and unknown `279,553`. All stored specialists have
  negative entropy; 16,065 stored rows are negative overall.
- Every stored row was created at `2026-04-09T03:12:20Z`, matching an archived
  propagation run. The active NPZ is a newer run and recomputes different
  counts (`9,721` frontier, `7,096` specialist, `279,718` unknown). Public
  export was combining version-skewed band and affinity artifacts.
- Independent propagation uncertainty in the active artifact is identically
  zero. `rank_frontier` additionally treated synthetic `none` Lift as if
  `1-none_weight` were a probability factor and hardcoded 15 of 16
  communities. Its existing ranking cannot be a valid information-value
  acquisition policy.
- The local database contains 8,727 unversioned `frontier_ranking` rows.
  Automatic `active_learning` selection and the paid frontier-following fetch
  both consumed that table directly, so guarding only `rank_frontier.py`
  would not stop an already-materialized stale ranking from steering spend.

**Lesson:** Correct mathematics is necessary but not sufficient. Entropy of a
row-normalized Lift composition measures relative spread; it does not measure
evidence amount, membership probability, posterior uncertainty, or whether a
person is a bridge. Thresholds and precedence encode ontology decisions.
Artifact identity is also load-bearing: even a valid classifier cannot be
paired with a different propagation run.

**Action taken:** Centralized a bounded, scale-invariant entropy primitive;
made independent `classify_bands` fail loudly; rejected every unbound
`account_band` consumer even when paired with a valid classic artifact; made
public export suppress those rows and use its classified-only fallback; also
blocked the historical frontier-confidence analysis from
relabeling Lift spread as confidence; blocked every current automatic or paid
consumer of the already-materialized frontier table while preserving explicit
handle selection; required explicit propagation mode and coherent
node/community dimensions at band-consumer boundaries; retained classic-mode
bands as legacy heuristics; added behavioral regressions and
`scripts/verify_independent_band_entropy.py`; and corrected the public About
copy to call loaded bands quarantined legacy metadata. Existing SQLite and
hosted rows were not deleted or rewritten.

**Next step / falsification contract:** After at least 30 real task-scoped
judgments permit a frozen development/holdout split, compare explicit
specialist/bridge methods against Lift plus seed-neighbor baselines. Require
precision/recall@K, calibration where a probability is claimed, seed/topology
stability, threshold sensitivity, and exact artifact provenance. Restore a
band only if it adds stable holdout value; otherwise delete the concept from
the retrieval path.

---

## EXP-023: Do the named Dharma seeds already have enough local evidence to rank candidates?

**Date:** 2026-07-30

**Question:** Before buying more X data, do the latest Community Archive tweet
snapshot plus existing local/archive and shadow follow views contain usable
neighborhoods for RomeoStevens76, TVachaW, realityacid108, and SuttaSlime?
Can the project produce a source-selective candidate ranking without silently
turning stored-key counts into coverage or membership claims?

**Hypothesis:** A read-only, receipt-bearing union of direct and inverse
following observations will recover a nonempty neighborhood for every named
seed and make the Slice 1 source-selectivity primitive operational. The
stronger retrieval hypothesis remains that this ordering will beat raw support
on held-out judgments. A second hypothesis was that each follow batch could be
attributed to Community Archive, shadow scraping, or twitterapi.io.

**Method:** Refreshed the canonical Community Archive Parquet snapshot and
deep-verified its manifest and SHA-256. Pinned the four numeric account IDs and
profile-count observations in a versioned seed panel. Opened explicitly
selected SQLite inputs with `mode=ro`, `PRAGMA query_only=ON`, and WAL-aware
transactions; missing tables were represented as unavailable rather than
zero. For each seed, the report kept these stored sources separate before
deduplicating their identity keys:

1. `account_following` direct following rows;
2. `account_followers` rows inverted through `follower_account_id`;
3. direct shadow following rows;
4. inverse shadow following evidence where the seed appeared on another
   account's follower surface.

The report then ran `source_selectivity_v1`, inspected latest-snapshot authored
posts and incoming non-self replies, compared two independent local archive
database paths, and priced a complete twitterapi.io followings refresh from a
dated official price card. It made no network request while building the
report and made no paid API call. The earlier Community Archive refresh used
the public archive endpoint and cost USD 0.

**Result:** **Local retrieval is operational; acquisition provenance is
falsified, and retrieval quality remains untested.**

- The selected Community Archive snapshot is
  `20260730T045247Z-4913d0183e39`: 8,511,975 tweets, 34,917 accounts, newest
  event `2026-07-30T04:24:20Z`, 920,495,154 bytes, SHA-256
  `24843080391b664ed8a138cd65362a4c65756c95459858e19aca98ed7e87e471`.
- Stored-key following unions were RomeoStevens76 `957`, TVachaW `2,323`,
  realityacid108 `226`, and SuttaSlime `58`. These are not completeness
  percentages: mixed-time sources and unresolved numeric/`shadow:*` aliases
  can make a union exceed a current profile claim.
- Latest-snapshot authored rows were `14,542`, `290`, `7`, and `1`;
  incoming non-self reply rows were `2,947`, `360`, `6`, and `47`
  respectively.
- Source selectivity returned 3,305 candidates. The leading candidate,
  `danielbrottman`, had support from all four seeds; the next tranche included
  `chercher_ai`, `TPatbat`, and `rakkhasa_`. This is suggestive face validity,
  not precision evidence or a community assignment.
- Database selection changed the result materially. The stale project-root
  database produced unions of `735`, `225`, `1`, and `2`; the selected active
  local database produced `957`, `2,323`, `226`, and `58`, changing the
  candidate universe from `894` to `3,305`. Every seed target-set digest
  changed. This falsifies
  EXP-021's provisional sparse-coverage diagnosis as a path-dependent
  observation, not as a scoring failure.
- The active `account_following` table contains a contiguous later batch that
  closes the four named neighborhoods, but its schema stores no source,
  fetch time, or run ID. Neither stale `edge_fetch_state` nor
  `enrichment_log` can attribute it. The only honest source label is
  local follow rows without row-level provenance; they cannot be claimed as
  Community Archive or twitterapi.io data.
- At the verified 2026-07-30 price card, complete followings refreshes are
  estimated at USD `0.00800`, `0.02334`, `0.00260`, and `0.00177`, totaling
  USD `0.03571`. This prices full traversal, not the
  claimed-minus-observed gap. Actual spend in this experiment was USD `0`.

**Assumptions and falsifiers:**

- Current producer code and stored row metadata support interpreting direct
  and inverse shadow rows as following evidence. Historical
  `shadow_edge.direction` documentation is internally inconsistent; a writer-
  version or row-level provenance audit that shows mixed orientation would
  falsify that interpretation.
- Stored identity keys are treated as distinct accounts. Alias reconciliation
  can reduce counts and change scores.
- The two SQLite transactions are individually read-consistent but not
  mutually atomic, and the selected databases are mutable. The JSON is a
  frozen historical record of one query-time output and its input receipts;
  it cannot reproduce the exact ranking after either database or WAL advances.
- Follow observations are treated as durable attention signals despite unknown
  age, endorsement, list maintenance, and capture propensity.
- Profile follow counts are observations at one timestamp, not ground-truth
  denominators for mixed-time local edges.
- The retrieval claim is falsified if a frozen development/holdout evaluation
  fails to improve Recall@K, precision@K, or reciprocal rank over raw support,
  or if the gain disappears across seed-degree and evidence-source strata.

**Lesson:** The apparent absence of the Dharma neighborhood was primarily a
data-root/provenance problem, not evidence that source selectivity failed.
There is enough local topology to put real candidates in front of a reviewer
without spending money. The next constraint is human relevance judgment and
identity/provenance cleanup, not another inference substrate.

**Data stored:** `data/evals/dharma_seed_coverage_panel.json`,
`data/manifests/twitterapiio_price_card_20260730.json`, frozen report
`data/evals/dharma_seed_coverage_report_20260730.json`, implementation under
`src/evaluation/seed_coverage*.py`, behavioral contracts in
`tests/test_seed_coverage.py`, `tests/test_seed_coverage_contract.py`, and
`tests/test_seed_coverage_io.py`, and the human verifier
`scripts/verify_seed_coverage_triage.py`.

**Next step:** Show the frozen top candidates in a simple blind review surface
and collect relevance judgments without exposing legacy communities. Compare
source-selective order with raw support after a development/holdout split
exists. Do not purchase follow data until that zero-cost baseline is evaluated;
first add source/run/timestamp receipts to any future acquisition.

---

## EXP-022: Can messy takes become an honest raw-evidence review queue?

**Date:** 2026-07-30

**Question:** Can a curator paste informal account notes and inspect only
locally available raw profile/tweet evidence without seeing legacy community
recommendations or accidentally creating a false frozen-evidence claim?

**Hypothesis:** A separate Research Notes preview can preserve the first-seen
source line, hide legacy memberships, expose mutable-archive staleness, reject
caller-supplied frame binding, and keep draft `IN` / `OUT` / `ABSTAIN`
judgments session-only until the server can supply both a canonical task and
snapshot-addressed evidence. The stronger product hypothesis is that an
eventual evidence-and-correction flow will make real curation cheap and
motivating enough to reach 30 scoped judgments.

**Method:** Wrote behavior-first API, parser, client, and React contracts using
temporary SQLite and mocked fetches. The tests exercise curator
authentication, case-insensitive profile lookup, an explicit response
allowlist, invalid limits, explicit `frameId` rejection, capture-time
provenance, messy-text parsing and deduplication, session-only drafts, dossier
retry, mutable-client-target rejection, and unsafe profile-link rejection. A
disposable local database with two representative accounts was rendered in the
in-app browser for a visual pass. No real archive row, study, judgment, model,
API, or paid acquisition was used.

**Result:** **The synthetic interface contract is confirmed; the real curation
and learning hypotheses remain untested.**

- The mandatory verifier checks 23 backend contracts and 19 focused frontend
  tests in addition to static fail-closed boundaries.
- The graph-explorer suite passed 759/759 tests and its production build
  succeeded. Scoped ESLint completed with zero warnings.
- Operation is always visibly `Unbound preview`; no frontend write function
  exists, the save control is disabled, and pasted notes remain session-only.
- The raw API returns `source=mutable_local_archive`,
  `snapshotBound=false`, and profile/tweet capture times. It rejects every
  `frameId` instead of attaching frozen metadata to current rows.
- Client-supplied target labels/questions were removed. The preview states that
  the canonical target must later come from the frozen server task.

**Assumptions and falsifiers:**

- A pasted X handle or profile/tweet-author URL is assumed to identify the
  intended account. Alias changes and numeric/`shadow:*` reconciliation are not
  solved. Misidentification in a reviewed sample falsifies this parsing path.
- A profile plus at most 20 recent authored posts is assumed to be enough for
  an initial judgment. Replies, likes, quote context, network neighbors,
  deleted posts, contemporaneous news, and off-platform investigation are not
  yet assembled. High abstention or frequent external investigation falsifies
  that dossier sufficiency assumption.
- Content presence is evidence, not proof of competence, affiliation,
  endorsement, Kegan stage, simulacrum level, or durable intent. Those require
  separately defined targets and observable criteria.
- The preview is intentionally mutable and makes no historical cutoff claim.
  Real activation is falsified until the route reads an immutable snapshot or
  the server recomputes a context receipt against snapshot-addressed evidence.
- A real task label and question must be derived from the immutable task
  definition; editable environment strings are not sufficient.
- A real retry needs an idempotency key. A lost response must not create a fake
  superseding correction.
- Cumulative progress must be independent of hidden evaluation roles. A
  before/after `purpose=training` count would leak allocation membership and is
  deliberately absent.
- The product hypothesis is falsified if curators cannot reach 30 scoped
  judgments with acceptable time per account, correction rate, and abstention,
  or if a frozen development evaluation shows no improvement over the
  zero-label retrieval baseline.

**Lesson:** The smallest truthful UI is currently a raw dossier preview, not a
label writer. An initial synthetic write path was removed after adversarial
review showed that mutable rows could be mislabeled as snapshot-bound, mutable
client text could contradict the immutable task, and training-only progress
could reveal withheld roles. There is no real target, frame, saved judgment,
measured labeling cost, or prediction update. The next scientific work is
gathering and reviewing real takes, not adding Community Gold modules.

**Data stored:** UI/API code under `graph-explorer/src/researchNotes/`,
`graph-explorer/src/ResearchNotesInbox.jsx`, and
`src/api/routes/research_notes.py`; synthetic contracts under
`tests/test_research_notes_routes.py` and graph-explorer tests; human verifier
at `scripts/verify_research_notes_inbox.py`. The visual fixture lived only in a
disposable `/tmp` SQLite database.

**Next step:** Continue collecting takes toward 30, define one narrow target
and its observable boundary, then add server-derived task semantics,
snapshot-addressed evidence, role-independent progress, and idempotent writes
before enabling real saves. Measure review time, abstention, correction, and
held-out retrieval gain rather than counting labels alone.

---

## EXP-021: Does source-side selectivity recover niche candidates?

**Date:** 2026-07-30

**Question:** Does a follow from a selective seed carry more useful retrieval
signal than a follow from a seed that follows thousands of accounts?

**Hypothesis:** For each distinct seed-to-candidate follow, adding
`1 / max(observed_out_degree, claimed_following_count)` will rank candidates
supported by selective seeds above candidates supported only by broad seeds.
The scientific hypothesis is stronger: this ranking will improve held-out
Recall@K over unweighted distinct-seed support.

**Method:** Wrote behavior-first synthetic tests for duplicate observations,
self-follows, seed-to-seed follows, missing or invalid claimed counts,
determinism, and scores above one. The implementation exposes both the
uncalibrated score and per-seed degree diagnostics. An initial 556-line design
was rejected before integration because it added loaders and synthetic
infrastructure without a real consumer; the retained implementation, tests,
and verifier total 269 lines.

Then ran the pure scorer read-only against a point-in-time local
`data/archive_tweets.db` view of stored `account_following` edges and
`user_profile_cache` counts, using four named seeds: RomeoStevens76, TVachaW,
SuttaSlime, and realityacid108. The diagnostic did not freeze an output
artifact or database hash. No API, network, model, label, or database write was
used. Its account counts are therefore provisional observations, not a
reproducible empirical result.

**Result:** **The arithmetic hypothesis is confirmed; the retrieval hypothesis
is not yet tested.**

- RomeoStevens76 had 538 observed outgoing targets and a claimed count of 667,
  so each stored follow contributed `1/667 = 0.001499250`.
- TVachaW had 10 observed targets and a claimed count of 2,182, so each
  contributed `1/2182 = 0.000458295`.
- SuttaSlime and realityacid108 had neither stored outgoing targets nor a valid
  claimed count in this view and remained explicitly `degree_unknown`.
- The run produced 542 candidates. Five accounts supported by both covered
  seeds led with `0.001957546` and raw support two:
  `strangestloop`, `5matthewdub`, `taijitu_sees`, `vyakart`, and `AlexKrusz`.
- Raw-support ranking placed the same five accounts first. With four seeds,
  only two usable neighborhoods, and no frozen labels, this run supplies no
  evidence of a Recall@K improvement.

**Assumptions and falsifiers:**

- A stored directed follow is treated as one unit of attention, despite unknown
  recency, provenance, endorsement, list maintenance, or account compromise.
- Seed evidence is added as if sources were independent; correlated seeds can
  overcount one social neighborhood.
- `1 / degree` is a proposed discrimination function, not a derived optimum.
  Log-inverse, capped, learned, and time-decayed alternatives remain viable.
- `max(observed, claimed)` prevents partial capture from making a seed look more
  selective than either available count implies, but claimed counts can be
  stale and edge coverage is missing-not-at-random.
- Numeric and `shadow:*` identities are not reconciled in this primitive.
- The score is unbounded and is not membership, probability, confidence, or a
  confidence interval.
- The retrieval claim is falsified if time/topology-split held-out Recall@K,
  precision@K, or reciprocal rank fails to improve over raw distinct support,
  or if gains disappear across degree and community strata.

**Lesson:** Source selectivity is cheap and operational on current edges, but
current named-seed coverage is too sparse to validate discoverability. The
honest output today is a ranking signal plus coverage diagnostics, not a
community assignment.

**Data stored:** Code in `src/graph/source_selectivity.py`; behavioral tests in
`tests/test_source_selectivity.py`; human verifier in
`scripts/verify_source_selectivity.py`. The real-data run was diagnostic only
and wrote no artifact or database row. Its provisional counts must be rerun
against an identified frozen snapshot before use as comparative evidence.

**Next step:** Collect 30 real scoped judgments, freeze a development/holdout
split, reconcile seed identities, and compare source-selective ranking with raw
support on the same candidate universe. Do not tune the discrimination
function on the terminal holdout.

**2026-07-30 amendment:** EXP-023 compared independent database paths and
falsified this section's provisional real-data sparsity diagnosis. The
arithmetic result remains valid, but the `538/10/0/0` neighborhood observation
came from a stale project-root database. The active local database yielded
`957/2,323/226/58` stored-key unions and 3,305 candidates. Those later rows
still lack acquisition provenance, so the amendment increases usable topology
without establishing freshness, completeness, or source.

---

## EXP-018: Does the Slice 1 store enforce its holdout and identity claims?

**Date:** 2026-07-26; amended 2026-07-28

**Question:** Can a local versioned Community Gold adapter preserve legacy
meaning, keep global account roles stable, prevent terminal-label leakage,
separate predictions from human judgments, and make a terminal release
one-use and reproducible?

**Hypothesis:** An additive nullable migration plus immutable ontology/task,
global-role, evidence, head, prediction, and release records should preserve
legacy rows without invented scope. Purpose-gated SQL should exclude terminal
labels from training, and adversarial direct writes should fail or be detected
by stored digests.

**Method:** Built behavior-first SQLite tests and a synthetic, network-blocked
verifier. Falsifiers included reopening after corrections, stale/malformed
migrations and triggers, same- and cross-registry account reassignment,
ontology projection append, role alias collision, head deletion/rewind, empty
or partial terminal release, sibling-task writes after release, forged terminal
JSON/hashes, direct probability insertion, missing method output, terminal
reads through training SQL, live GRF probability/interval wording, table/index
name impersonation, post-write terminal actor/time tampering, a missing coverage
denominator, zero/missing public graph signals, and malformed graph-settings
JSON. The final hardening queue
also tests a post-cutoff terminal head, incomplete full-judgment/lineage
attestation, future-schema no-mutation, weakened partial-index predicates and
UNIQUE/CHECK clauses, a silent schema marker, fractional counts, and nullable
`TEXT PRIMARY KEY` columns. Three independent computational peers reviewed
migration, access, evaluator, construct validity, and public claims.

**Result:** **The seven hostile schema/release classes were reproduced and
repaired on synthetic data, and A1 idempotent terminal replay is green.
Real-use randomization, authenticated actor identity, and label-support gates
remain open.**

- Verifier: 6/6 checks passed with 12 global roles and nominal terminal
  probability at least `0.166667`. This is a quota probability conditional on
  uniform seed randomization, not proof that the caller-supplied seed was
  committed before outcome knowledge.
- Synthetic allocation: 4 model-development, 1 policy-development, 2 terminal,
  and 3 frame-only accounts, plus fixed training/challenge identities.
- Training returned only its development-role label at the raw SQL-query
  boundary. The terminal release required all four account/group heads for one
  reviewer, reported `in/out/abstain` and labelability coverage, and stored
  frame, role, receipt, and release digests.
- A second release and writes to any sibling frame sharing the global role
  generation failed. Prediction records remained separate from five human
  scoped-history rows.
- `calibrated_probability` remained unavailable through both the store API and
  direct SQL. Legacy diagnostics now report missing-score coverage and suppress
  Brier/ECE; the live GRF surface reports affinity, heuristic uncertainty, and
  coverage separately.
- Missing expected-following data previously fabricated `1.0` coverage; it now
  returns `value=null`, `status=unknown`. A zero public graph signal remains
  zero, while a missing signal is displayed as unavailable rather than as
  weakest evidence.
- Full structural migration validation at the earlier checkpoint rejected
  table/index impostors. The terminal access-envelope digest rejected
  post-write mutation of the caller-asserted actor or access time; it did not
  authenticate who supplied that actor.
- Final falsification produced nine expected-failing tests covering ten concrete
  hostile shapes (the weakened-CHECK test was parameterized). The shapes were a
  post-cutoff terminal head, incomplete full-judgment/lineage attestation,
  future-schema mutation, weakened partial index, weakened UNIQUE, two weakened
  CHECK forms, silent schema marker, fractional count, and nullable text primary
  key. After repair, the focused Community Gold suite passed 101/101.
- Red-to-green surfaces: trigger regression 3/3; schema/migration guard 8/8;
  adversarial head/prediction/migration/terminal/provenance 12/12; role/frame
  20/20; membership endpoint 5/5; graph-explorer membership panel 4/4;
  public EvidenceSummary 2/2; combined backend GRF/evaluator 17/17.
- Prior integrated checkpoint, now superseded by final hardening: focused
  backend 114/114; credential-free Python 1,425 passed and five skipped; public
  site 189/189; graph explorer 730/730; synthetic verifier 6/6.
- Final core handoff also passed the Slice 1 verifier 6/6 and its verifier unit
  test 1/1; `git diff --check` was clean. The largest scoped implementation file
  was 264 LOC and the largest regression file 260 LOC.
- **A1 idempotent terminal replay — GREEN:** the RED phase deliberately
  produced 11/11 expected failures across two focused files, covering
  lost-response recovery; exact payload/`accessedAt` replay; actor, reviewer,
  receipt, and frame conflicts; corruption; sealing; concurrent requests; no
  post-commit reload; and HTTP 409 with no leaked rows. Final delivery tests pass
  12/12, the broader Community Gold/Slice 1 surface passes 102/102, and the human
  verifier passes 6/6. The first release fully verifies before commit and its
  rollback test passes; an identical retry returns exact judgments/access
  metadata, preserves `accessedAt`, uses one row, and marks `replayed=true`;
  mismatches map to HTTP 409 with no rows; corruption fails closed; concurrent
  calls converge; and the route no longer reloads post-commit. Maximum route
  size is 270 LOC and the new delivery module is 262 LOC. `accessedBy` remains
  caller-asserted.
- The verifier test's socket hooks observed no network attempt; no real database,
  label, model, provider, or external state was changed.
- A separate architecture falsifier remains open: `list_anchor_polarities(ego)`
  aggregates polarity across all tag keys and the membership endpoint/cache has
  no ontology/task/community target. Synthetic binary endpoint results are
  valid smoke checks, but they do not test overlapping multi-subculture
  inference or cross-target isolation.
- A no-filesystem malformed-settings stub made the GRF verifier print the
  settings path and exact `JSONDecodeError` as a failed parse check; malformed
  JSON no longer silently becomes an empty settings dictionary.
- Independent final verification passed credential-free Python
  `1,449 passed, 5 skipped`, public site `190/190`, graph explorer `741/741`,
  Slice 1 `6/6`, documentation contracts `21/21`, documentation hygiene `9/9`,
  GRF affinity smoke checks `10/10`, and both production frontend builds.
  The graph explorer's repository-wide lint command separately exposed
  `15` errors and `2` warnings in existing unrelated frontend debt, so this
  experiment does not claim a clean full lint gate.

**Lesson:** Passing happy-path tests was insufficient. Restart-time index
recreation, mutable ontology/head/release state, caller-selected registry
escape, frame-local rather than generation-level sealing, late filtering, and
unverified payloads all survived the first implementation. A validated
transactional migration, one registry per stable account, complete release
coverage, and read-time recomputation are necessary to make “sealed”
operational rather than rhetorical.

**Next step:** Add a pre-allocation universe commitment plus independently
auditable seed/randomization receipt, then review real identity receipts,
strata, quotas, and negative/abstain labeling capacity before creating any
non-synthetic frame. Keep probability language disabled until a compatible
calibration record and untouched class support exist. Before live release,
derive actor provenance from an authenticated principal; A1 now supplies safe
idempotent lost-response replay. Before real membership inference, scope
anchors, cache, and responses by immutable target ID and pass
cross-target-isolation tests. Bind coverage numerator/denominator to compatible
generation/as-of data.

---

## EXP-019: Why did graph-explorer lose localStorage under the full suite?

**Date:** 2026-07-28

**Question:** Were 43 graph-explorer failures evidence of application
regressions, test contamination, or a runtime/toolchain mismatch?

**Hypothesis:** Node 26's experimental global web-storage accessor was
shadowing jsdom's `window.localStorage`. If true, disabling experimental web
storage should make the four affected files pass without application changes.

**Method:** Ran the ordinary full Vitest command, inspected the runtime/config,
then reran `storage`, `discoveryCache`, `ClusterTour`, and `ClusterView`
integration tests with `NODE_OPTIONS=--no-experimental-webstorage`. Added a
conditional, standards-shaped in-memory `Storage` in test setup only when
jsdom storage is unusable, then reran both the focused set and ordinary full
command.

**Result:** **Confirmed.** The initial ordinary run had 687 passes and 43
localStorage-only failures. Disabling Node's experimental web storage produced
107/107 focused passes. The conditional setup repair produced 107/107 without
the flag and 730/730 on the ordinary full suite. No application storage code
was changed.

**Lesson:** A new runtime global can shadow a browser emulator even though the
test environment is configured as jsdom. Patching product storage behavior
would have hidden the root cause; the correct seam was conditional test
environment setup.

**Next step:** Pin a supported Node version for CI/developer parity or remove
the shim after Vitest/jsdom no longer expose the Node 26 conflict. The runtime
still emits an experimental-webstorage warning before setup executes.

---

## EXP-020: Do primary UI and sharing surfaces imply calibrated membership?

**Date:** 2026-07-30

**Question:** Can the quarantined legacy community map remain inspectable
without presenting its mixed `weight` values as membership probabilities?

**Hypothesis:** Adjacent caveats, decimal score formatting, and exact producer
labels should remove the probability claim without hiding the legacy ranking.
The change is falsified if a primary internal list, public card, community
page, downloaded card, tweet share, or OpenGraph description still emits a
bare membership-like percentage.

**Method:** Added rendered and pure-function contracts before implementation.
The first RED run produced 11 expected public failures across 62 focused tests;
the graph helper initially failed at module resolution because it did not
exist. After the first implementation passed, an independent adversarial review
rejected it: generated-card prompts still said “community membership,”
downloaded cards could collide with the caveat when an account had the observed
maximum of 15 scores, cached/fullscreen art lost its surrounding caveat, and bar
geometry still assumed `weight` was bounded by one. The active export contains
23,575 values above one across 6,103 accounts, with a maximum of `73.3335`.

Added a second RED tranche for those falsifiers. It reproduced `7333%` geometry
for `73.3335`, four prompt failures across both client and server paths, missing
fullscreen context, and unconstrained export rows. Replaced magnitude geometry
with within-card relative widths, capped downloads at three ranked rows plus an
explicit omission count, reserved canvas space for the caveat, changed both
image prompts to rank-only exploratory motifs without numeric magnitudes, and
carried the caveat onto the homepage, gallery, and fullscreen views, with
viewport space reserved for the fullscreen note. The final verifier statically
inspects 18 production surfaces and executes 31 adversarial contracts in both
frontend projects.

**Result:** **Confirmed for the checked presentation surfaces; this does not
validate the underlying community assignments.**

- Human verifier: 18 production surfaces, 52 required markers, 31 forbidden
  patterns, and 31 executable contracts passed.
- Full graph-explorer suite: 746/746 passed; full public-site suite: 211/211
  passed. Both production builds completed.
- Legacy values now render as decimals such as `0.650`, accompanied by
  “not membership probabilities.” Share text and OpenGraph metadata publish
  rank-ordered names without numbers.
- Source badges preserve actual source names rather than mapping every
  non-human producer to NMF.
- Bar lengths are explicitly relative within each card and are bounded at 100%
  of the available track even for mixed-scale scores. They are not score
  percentages.
- Generated art receives only rank-ordered legacy affinity motifs and an
  explicit instruction that they are uncalibrated, not membership
  probabilities, and not verified facts.
- Downloaded cards show at most three ranked scores, report how many additional
  scores were omitted, and reserve a tested gap before their embedded caveat.
- Evidence copy no longer derives a “Bridge Account” or community count from
  the invalid `weight * 100 >= 5` threshold; it reports row count and tells the
  reader to compare ordering only.
- A browser visual pass caught insufficient light-theme warning contrast; the
  banner now uses the active text color at semibold weight and remained adjacent
  to the score table.
- No deployment, external write, API call, or data mutation occurred.

**Lesson:** A mathematically careful About page cannot repair a misleading
number, bar, or generated image at the point of use. “Invisible” geometry and
model prompts are also claims: both leaked the same invalid probability
assumption even after visible copy was repaired. A single legacy `weight` field
cannot support producer-specific semantics, so generic probability formatting
must remain disabled until the export carries method metadata.

**Next step:** Test raw-follow source-selective retrieval against unweighted
support, then evaluate Recall@K only after real held-out judgments exist.
Retain the legacy map as a labeled baseline, not a calibrated result.

---

## EXP-017: Can the imported Community Gold rows calibrate a versioned task?

**Date:** 2026-07-26

**Question:** What is actually present in the existing Community Gold tables,
and can migration safely attach a personal ontology or calibration meaning?

**Hypothesis:** Existing rows should migrate without loss, but their identity,
class balance, evidence provenance, and correction history must determine
whether they can enter a versioned task.

**Method:** Queried the local archive database read-only through SQLite's
immutable-URI connection mode. That mode prevented writes through the
connection; it did not prove that the source artifact itself was immutable.
Counted label/split/reviewer/judgment/history rows, inspected evidence keys and
creation times, classified account-ID forms, and checked available
alias-to-numeric mappings. No path-independent snapshot ID, size, mtime,
SHA-256, or query receipt was recorded.

**Result:** **The observed source shape was migration-compatible; calibration
eligibility was decisively rejected.**

- 167 label rows and 167 split rows, all active: 113 train, 25 development,
  and 29 test.
- All 167 judgments are `in`; there are zero `out`, zero `abstain`, and zero
  supersessions. The only reviewer is `curator:adityaarpitha`.
- Evidence contains only `handle` and `source`; creation spans less than one
  second on 2026-03-21.
- IDs comprise 81 `shadow:*`, 54 `handle:*`, and 32 numeric values. At least 61
  shadow and 4 handle identifiers have candidate numeric profile mappings, but
  no immutable resolution receipt binds them.

**Lesson:** These rows are imported positive membership evidence, not a
binary calibration or untouched evaluation set. Automatically assigning user,
ontology, task, stable account, evidence generation, or negative meaning would
fabricate semantics.

**Next step:** Preserve every row as `legacy_unbound`. Build explicit
identity-resolution receipts and collect blinded `out`/`abstain` judgments in
a frozen frame before estimating calibration or prevalence-sensitive metrics.
Capture a deep-hashed source/query manifest before reusing these point-in-time
counts; they are not evidence that the Community Archive corpus was latest.

---

## EXP-016: Do frozen soft memberships and graph discoverability satisfy their stated contracts?

**Date:** 2026-07-26

**Question:** Once the frozen graph-to-output chain is identity-compatible, do
its solver behavior, probability interpretation, threshold behavior, taxonomy
stability, and discoverability structure support the claims made about them?

**Hypotheses:** The historical uncertainty post-processing fingerprint should
reproduce; configured PPR controls and probability mass should behave as
declared; soft-target predictions should beat empirical-prior and uniform
baselines; top-class confidence should have ECE ≤ .05; propagation-heldout
calibration positives should usually be core rather than halo;
information-equivalent taxonomy splits should preserve selection; bounded edge
loss should preserve selection; and capture, direction, and degree mechanisms
should be measurable explicitly.

**Method:** Added three frozen-manifest-first evaluators with deterministic
fixtures, explicit falsifiers, stable ties, no-clobber outputs, and a shared
`0/1/2` exit contract. Measured a bounded solver cycle and dangling-node
control, the 55-account propagation-heldout calibration set, an equal split of
every taxonomy factor, ten fixed-seed edge-deletion repetitions at 1%/5%/10%,
directed versus undirected versus reciprocal components/reachability, the exact
18-handle seed panel, capture-center incidence, and degree-stratified selection.
Full methods and limitations are recorded in
`docs/experiments/2026-07-26-membership-discoverability-audit.md`.

**Predicted outcomes:** A valid solver must respect `max_iter=1` and conserve
mass within `1e-9`. Soft-target predictions must beat empirical-prior and
uniform Brier and soft-label log loss; hard dominant-class confidence must have
ECE ≤ .05. At least half of recalled calibration accounts must cross τ. Equal
factor splitting must keep core Jaccard ≥ .95 and core-count change ≤ 5%.
Selection Jaccard must remain at least .95/.90/.85 under the three edge-loss
levels.

**Result:** **The historical uncertainty fingerprint and bounded selection
stability survived; solver validity, soft-target agreement, hard-label
confidence calibration, calibration-set core interpretation, and taxonomy
invariance were falsified. Capture, direction, and degree mechanisms were
confirmed as material.**

- Legacy uncertainty reconstruction maximum error: `3.6783e-08`, with zero
  cells above `1e-6`.
- Requested `max_iter=1`, but all three probe classes reported 90 iterations.
- Dangling graph converged with mass `.21375`; reciprocal control retained `1`.
- Static documentation correspondence rejected the About page's independent
  overlapping-percent interpretation: the NMF producer explicitly
  row-normalizes `W` to sum to one.
- Holdout: top-1 `11/55`, top-3 `27/55`; model/prior/uniform Brier
  `.586815/.505926/.517078`, log loss
  `3.737831/2.620363/2.708050`, ECE `.094255`. The empirical prior is
  optimistically estimated from the evaluation holdout, but uniform also wins.
- Core/halo: `0/53/2` propagation-heldout calibration accounts were
  core/halo-only/missed. Because these accounts selected τ, this is
  retrospective behavior rather than threshold generalization.
- Equal split-all: core `175→71`, core Jaccard `.405714`; selection
  `8,984→5,179`, Jaccard `.576469`.
- Minimum selection Jaccards under 1%/5%/10% stored-edge deletion:
  `.990984/.961264/.922418`. Memberships were fixed, so this is not an
  end-to-end propagation result.
- Capture centers are 1.731% of nodes but touch 100% of shadow edges; 80.336%
  of nodes have degree one.
- Seed reachability is 39.944% forward, 66.780% reverse, 99.991% when
  undirected, and 6.425% on reciprocal-only edges.
- Published selection reconstructs exactly as 175 core + 8,809 one-hop halo;
  degree-one versus degree≥51 selection differs by 80.176 percentage points.

**Lesson:** Reproducible soft values can still have an unsupported probability
interpretation. The current output is a useful weak ranking/control artifact,
but its soft-target agreement and hard-label confidence calibration both fail
these diagnostics. The threshold result needs a second untouched validation
set. Near-total weak connectivity is also not network discoverability when
capture design, edge direction, reciprocity, and degree change the reachable
universe.

**Next step:** Keep the frozen bundle immutable. Fix the PPR contracts, choose
compositional versus independently overlapping membership semantics, collect
taxonomy-compatible positives and verified negatives, and evaluate
future-time/multi-center retrieval before generating a replacement.

---

## EXP-015: Did the Community Archive corpus advance, and did archive linkage keep pace?

**Date:** 2026-07-26

**Question:** Is the July 25 immutable snapshot stale relative to the mutable
bulk object one day later, and can the delta be measured without treating
missing linkage as known provenance?

**Hypothesis:** A changed source identity should add rows/accounts and advance
the newest-tweet cutoff. If archive linkage keeps pace, new linked rows should
cover the row delta and missing-upload-ID rows should not grow.

**Method:** Probed and downloaded the changed object into a new no-clobber
snapshot directory, then independently verified the full file hash and Parquet
metrics. Added a comparator that verifies both immutable snapshots before
reporting numeric deltas, samples, falsifiers, and optional exclusive-create
JSON.

**Result:** **Corpus advance confirmed; archive-linkage pace falsified.**

- Candidate `20260726T045149Z-37a97fa3e057`, SHA-256
  `99e93da98bb9fbdbddaa46a9e7f00da7ae501144294c123155e4d56447a8e9bd`.
- Rows `8,318,250→8,321,675` (`+3,425`); accounts
  `34,684→34,698` (`+14`); newest tweet advanced `87,038` seconds.
- Archive-linked rows changed by `0`; missing upload-ID rows grew by `3,425`;
  linked fraction declined by `.000333`.

**Lesson:** “Latest bulk export” and “latest fully archive-linked evidence” are
different claims. The new snapshot is the latest corpus observation made in
this experiment, but it does not refresh follower topology and its added rows
must not be silently asserted to have archive-upload provenance.

**Next step:** Bind this candidate snapshot by ID and hash to any downstream
tweet-corpus experiment. Keep graph/topology freshness and raw per-user archive
inventory as separate experiments.

---

## EXP-014: Do the graph, propagation, calibration, and frozen TPOT output belong together?

**Date:** 2026-07-26

**Question:** Can the existing graph artifacts safely support controlled
experiments on network discoverability and soft group membership, or are
positional arrays from different node universes being combined?

**Hypotheses:**

1. The bare 95,057 × 95,057 adjacency cache still represents the ordered
   `graph_snapshot.nodes.parquet` and `graph_snapshot.edges.parquet`.
2. The newer 298,347-node `community_propagation.npz` is a usable superset that
   can be reindexed to the full graph.
3. The 95,057-node training propagation is the artifact that generated the
   current calibrated 8,984-node TPOT output.

**Method:**

1. Reconstructed a directed binary CSR matrix from every graph edge under the
   Parquet node order and compared its shape, sparse structure, and values
   exactly with the cache.
2. Compared unique account IDs and order for both propagation candidates
   against the graph, and inspected every array dimension before permitting
   alignment.
3. Recomputed degrees, relevance, calibrated core + one-hop halo selection, and
   ordered selected-node identity at the saved threshold.
4. Compared the recomputed relevance vector with the producer's saved float32
   vector, then verified the selected mapping, exact induced node/edge Parquets,
   full and TPOT spectral row order, and TPOT runtime adjacency semantics.
5. Inspected membership score mode, community schema, solver convergence, and
   held-out-label leakage. Corrected the historical “F1” description: the
   threshold objective is the harmonic mean of positive holdout recall and
   graph compactness, not precision/recall F1 because no negatives were used.
6. Added behavioral tests for stale same-shape caches, duplicate IDs, partial
   overlap, caller-priority plus safe superset reindexing of every known
   node-indexed array, classic versus independent score semantics, malformed
   calibration provenance, exact relevance binding, output reservation, and
   spectral node/shape mismatches.

**Predicted outcomes:**

- If hypothesis 1 is true, all 319,771 edge rows reconstruct with zero ignored
  edges and zero differing sparse cells.
- If hypothesis 2 is true, all 95,057 graph IDs occur uniquely in the active
  propagation and can be reordered without truncation.
- If hypothesis 3 is true, training propagation has exact graph order and
  reproduces core=175, halo=8,809, total=8,984 and the frozen ordered node list.

**Result:** **H1 and H3 confirmed; H2 decisively rejected.**

- A committed compatibility record pins all 15 frozen scientific files:
  27,272,597 total bytes, with exact size and SHA-256 for graph Parquets,
  adjacency caches, selected propagation, calibration/holdout/relevance,
  mapping, both spectral pairs, and TPOT Parquets. Bundle ID:
  `frozen-tpot-control-20260726`.
- The adjacency cache exactly reconstructs: 95,057 nodes, 319,771 edge rows,
  319,771 nonzeros, and zero ignored edges.
- Ordered graph digest:
  `c5ba0e5e9ef297fe5e1ddc3790301df4d9a4f659a5332c340262a4b07384ee86`.
- Adjacency structure digest:
  `df84d5d1a3c596bb1eefa95b7d99ebdba0f7e71332be830e4fb835a93dd18d0f`.
- Adjacency value digest:
  `b9246583162bc508dc3c6e564e0a21e2ffbeefc2a498e4399510c713c78b61f3`.
- The active propagation matches only 358 graph IDs and omits 94,699. It is a
  larger, largely different node universe, not a safe superset. It declares
  `independent` Lift semantics, has 16 communities plus `none`, and cannot be
  passed into the probability-based TPOT relevance scorer even if its node
  domain were rebuilt to match.
- `community_propagation_train.npz` contains exactly the same 95,057 IDs in the
  same order. At `tau=0.05644444444444444`, it exactly reproduces the saved
  175 core + 8,809 halo = 8,984 total selection.
- The train artifact is legacy 14-community-plus-`none`; it has no saved mode,
  but its finite nonnegative rows sum to one within `2.38e-7`, so it satisfies
  the legacy classic probability contract and matches the certified file hash
  `610d59cfdae3e6f3bb1520b6a86e53c9df850ad3beeb01949bb1a768c4dbaab2`.
  New mode-less artifacts are rejected. Its community UUIDs have zero overlap
  with the active 16-community schema.
- All 15 train-artifact convergence flags are false and every recorded solver
  iteration count is 800. The downstream relevance scorer therefore applies
  its non-convergence factor of `0.3` to every dominant class. Compatibility is
  proven; solver validity is not.
- Recomputed relevance is exactly equal after the producer's float32 cast;
  saved-vector SHA-256:
  `e08d5a87fdf096f7c7751de2cedbc2a01871831e2afc72a6b7022da496b576dd`.
- The recomputed ordered selection matches the frozen mapping at compatibility
  digest
  `5b6a8bc27ccedcab9c6d10b676a5158543e9e044397f8a259d1615263a8beed2`.
- The TPOT node/edge Parquets are the exact induced subset (8,984 nodes,
  186,442 edge rows), both spectral artifacts have exact node-row binding
  (95,057 × 20 full; 8,984 × 30 TPOT), and the TPOT runtime adjacency exactly
  reconstructs with `directed_plus_mutual_reverse` semantics at structure
  digest
  `95ef9a4623d0a54b2f6e105faea7d9f05563f169e1d749d674e46983bb195e65`.
- The existing calibration predates provenance manifests, so it is explicitly
  labeled `legacy-runtime-validation-required`; its graph count and all saved
  selection counts are nevertheless reproduced at runtime.
- The recorded holdout declares 55 accounts and 243 training labels. All 55
  resolve, `labeled_mask.sum()` is 243, and none of the holdout accounts is
  labeled in the train propagation.
- The full frozen cache uses raw `directed_edge_rows`, while the API's current
  cache rebuild path adds reverse entries for mutual edges. Deleting the cache
  would therefore change construction semantics instead of reproducing this
  pinned digest.

**Lesson:** Filename recency and matrix dimensions are not compatibility
evidence. The prior builder preferred the active filename and would combine it
positionally with a different graph, producing a broadcast failure today and
potentially silent scientific corruption if dimensions happened to agree.
Account-ID coverage, explicit ordering, score semantics, topology
reconstruction, community schema, calibration identity, scorer identity, and
output reproduction must be one gate. Reproducibility alone does not establish
convergence, taxonomy currency, calibration validity, or topology freshness.

**Assumptions and confidence:**

- String account IDs are stable join keys across these artifacts: `0.99` for
  the frozen bundle.
- Exact reconstruction proves this cache belongs to these node/edge tables:
  `0.99`.
- The exact training-artifact reproduction identifies the frozen TPOT
  derivation: `0.99`.
- The frozen artifact is suitable as a deterministic control: `0.98`.
- The frozen soft memberships are scientifically calibrated current group
  probabilities: `0.20`, because the solver did not converge, the taxonomy is
  legacy, and the threshold sweep used no negatives.
- This proves current social-network freshness: `0.10`; the topology remains a
  frozen control and is not refreshed by the tweet-only Community Archive
  export.

**Fallback:** If any future artifact lacks full ID coverage, changes node
ordering, fails cache reconstruction, contradicts calibration provenance, or
changes the saved selection unexpectedly, fail closed and retain the certified
frozen bundle. Rebuild from a single source snapshot rather than truncating,
broadcasting, or choosing the newest-looking file.

**Next step:** Use this frozen, compatibility-checked bundle as the control arm.
First test solver convergence and taxonomy sensitivity in a new no-clobber
generation. Then design refreshed-topology, out-of-sample discoverability, and
proper probability-calibration experiments as new versioned bundles. Do not
overwrite, rebuild through the current cache path, or silently reinterpret this
control. Atomic generation publication remains required before deployment.

---

## EXP-013: Can the mutable Community Archive export be captured reproducibly?

**Date:** 2026-07-26

**Question:** Is the frozen local corpus stale relative to Community Archive,
and can the current mutable bulk export be identified and acquired without
overwriting the baseline or accepting a mid-transfer source change?

**Hypothesis:** The release-label date is not a sufficient freshness marker.
A HEAD probe should expose a newer object identity, and a versioned,
validator-bound, byte-capped, hash-verified workflow can capture it additively.

**Method:**

1. Read Community Archive's current `llms.txt`, API guide, release metadata,
   storage behavior, and upstream relationship-ingest schema.
2. Issued a HEAD-only probe against the canonical enriched-tweet Parquet object
   and bounded one-row REST freshness probes. No bulk body was downloaded.
3. Compared those dates with the certified local baseline's Snowflake-derived
   tweet cutoff.
4. Wrote behavioral tests first for metadata identity, strict validators,
   streaming caps, no-clobber publication, Parquet ID/schema checks, structural
   manifest invariants, immutable reuse, and probe-only CLI behavior.
5. Implemented ADR 019's snapshot acquisition and verifier modules, keeping
   every new code and test file below 300 lines.
6. Committed the acquisition code at `48f8daa`, downloaded the full object with
   a clean Git state, and ran the schema/coverage inspection.
7. When the strict timestamp-type assumption failed, inspected the actual
   schema and timestamp values, wrote canonical-string and Snowflake-quality
   regressions, then rescanned all 8.3 million rows.

**Result:** **CONFIRMED, with explicit upstream timestamp-quality warnings.**

- The canonical object is newer than both the frozen corpus and its GitHub
  release title. On 2026-07-26 its metadata was:
  - snapshot ID: `20260725T045122Z-4123f74b1a43`
  - `Last-Modified`: `2026-07-25T04:51:22+00:00`
  - size: `901,456,905` bytes
  - ETag: `"b07a2925eca027be751c5814fe3ddffe-54"`
- The release page said “updated 2026-07-13,” while the mutable object was
  modified on 2026-07-25. Release-title freshness is therefore rejected.
- The newest one-row REST tweet probe was tweet `2081177390386950643` at
  `2026-07-26T00:38:50+00:00`; the frozen archive's newest tweet is
  2026-03-22, about 124 days older.
- A bounded exact `all_account` count returned 502,629. An exact enriched-tweet
  count hit the database statement timeout, confirming that exact bulk counts
  should come from Parquet metadata rather than an expensive API count.
- The canonical object passed the 2,000,000,000-byte safety ceiling. Probe-only
  mode issued HEAD and changed no files.
- Attempt 1/3 transferred all 901,456,905 bytes with matching HEAD/GET
  validators and clean producer Git state, then correctly refused to write a
  manifest because live `created_at` is `string`, not Arrow timestamp. The
  incomplete candidate did not replace or activate anything.
- Actual schema inspection showed canonical UTC strings such as
  `2019-06-20 06:22:41+00`. The refined parser accepts that exact validated
  representation while retaining timezone-aware Arrow timestamp support.
- Full candidate scan:
  - 8,318,250 rows and 34,684 distinct account IDs
  - 6,728,898 archive-upload-linked rows and 1,589,352 rows with no upload ID
  - source `created_at` range: 1998-10-28 to 2026-07-25
  - Snowflake-derived eligible range: 2010-11-04 to 2026-07-25
  - 8,261,478 of 8,261,586 eligible IDs agree within one second
  - 108 disagree by more than one second; five source timestamps predate
    Twitter and are demonstrably wrong for their tweet IDs
- Focused regression surface: `23 passed`.
- Attempt 2/3, after commit `7b405bb`, reacquired and manifested the same
  still-current remote identity successfully:
  - local SHA-256:
    `f40645e181976558f2e107528e9eebf90d82038881fdb886d759e973c3fd3667`
  - acquisition code: `7b405bb5b56a83d2764ffb9598ae6279efd14a6f`,
    `git_dirty=false`
  - independent deep verification recomputed the same hash and rescanned all
    Parquet metrics with zero failed checks

**Lesson:** Community Archive provides mutable views, not immutable releases.
Freshness must use live validators and ingestion metadata; evidence must use a
locally recorded SHA-256. The tweet-only export does not establish social-graph
freshness, and a null `archive_upload_id` should be reported as missing linkage,
not asserted to be streamed without a stronger upstream invariant. Source
`created_at` also cannot be treated as infallible: retain it, expose anomaly
counts/samples, and use Snowflake-derived cutoffs for eligible tweet IDs.

**Assumptions and confidence:**

- HTTP validators change when the mutable object changes: `0.98`.
- Strict HEAD/GET validator equality plus byte count and SHA-256 detects an
  unsafe acquisition: `0.99`.
- The Parquet export preserves snowflake IDs as strings: confirmed, `0.99`.
- `created_at` is a timezone-aware Arrow timestamp: rejected. The observed
  contract is a canonical `YYYY-MM-DD HH:MM:SS+00` string; confidence `0.99`
  for this snapshot, while the verifier remains explicit about future drift.

**Fallback:** If the full download changes validators, violates the cap, or
fails schema/manifest checks, leave the frozen baseline active and keep the
candidate directory unmanifested. Re-probe rather than weakening validation.

**Data stored:** Gitignored immutable snapshot at
`data/community_archive/snapshots/20260725T045122Z-4123f74b1a43/`.
The manifest and Parquet file together are the evidence boundary; neither is a
replacement for the frozen control databases or social-topology artifacts.

**Next step:** Bind graph, adjacency, spectral, propagation, calibration, and
selection artifacts to explicit node-order/topology/source identities before
running refreshed network-discoverability or soft-membership comparisons.

---

## EXP-012: Can current main become a reproducible assumption-testing baseline?

**Date:** 2026-07-25

**Question:** Can we recover from the backup-synchronized conflicted checkout
without losing local work, reproduce the code gates, and attach the existing
research data without allowing experiments to mutate the source baseline?

**Hypothesis:** Current `origin/main` contains the intended source, while most
apparent local changes are upstream copies, CRLF/mode drift, and sync-conflict
artifacts. An isolated checkout on the CI toolchain plus an independent
copy-on-write data copy should produce a green code gate and a certifiable,
read-only handoff boundary.

**Method:**

1. Cloned current `origin/main` at `7cfb45fc6cf84115fdd9968064a962751983a55b`
   beside the old checkout and created `codex/community-archive-readiness`.
2. Compared 749 relevant paths after CRLF normalization and separately
   classified tracked content, file-mode changes, symlink flattening,
   non-conflict untracked files, and `sync-conflict` artifacts.
3. Tried the pinned Python dependencies on 3.12, then on CI's Python 3.11.
4. Ran the CI verifier surface before attaching production data, including the
   expected ignored-artifact cluster failure.
5. Created independent APFS copy-on-write files for the two core databases and
   active graph/propagation artifacts. Compared device/inode identity, sizes,
   SHA-256 hashes, schema/count probes, and SQLite `quick_check`.
6. Ran the credential-free Python suite and both frontend suites. The
   graph-explorer suite was deliberately repeated under Node 22 after Node 26's
   experimental unusable `localStorage` global caused a correlated failure.

**Result:** **CONFIRMED, with explicit freshness and runtime warnings.**

- Genuine local-only source/docs/tests: **0**. Of 749 relevant paths, 746 match
  current main after EOL normalization, one historical `AGENTS.md` was
  superseded upstream, and two old-only compatibility/server files were
  intentionally deleted upstream. The old checkout remains untouched.
- Python 3.12 was rejected by evidence: `pandas==2.1.0` fell back to a failing
  source build. Python 3.11.15 installed all 55 requirements and passed the
  backend suite.
- Clean-clone CI had a real contract defect: its granularity-25 cluster step
  required gitignored `data/graph_snapshot.spectral.npz`. Both granularity
  checks now use the committed deterministic medium fixture.
- The working `archive_tweets.db` and `cache.db` have distinct inodes from the
  source, equal byte sizes, matching SHA-256 hashes, zero-byte source WALs, and
  quiescent working WALs, with `quick_check: ok`. Eight required
  artifacts—including graph metadata sidecars—were bound into the certificate.
  Core hashes include:
  - `archive_tweets.db`: `c99b23fc83e1d01e64962124385674324a163ab6ccfee2a36d59cb995b894cd4`
  - `cache.db`: `4e04289dd6d86f7166f8cdfadb03443e6925f6b90b710393fc93a648baf8a552`
  - `graph_snapshot.meta.json`: `2f1692e62a92df497dba49abce1a7e55c3442d526336b7e50c1d4c1cfe321150`
  - `graph_snapshot.spectral.npz`: `05306f30c329bc7461c770228db77b39ac34144b0919e62070567e55e3796b8e`
  - `graph_snapshot.spectral_meta.json`: `854677cbf47d9c98758e0d9247add2c3c09c6bc15e8d7b5e8190d883f9e7018e`
  - `community_propagation.npz`: `1d12f3371205260d7808d1b01c6ecd66cb3cdb7013420cb9a591993d2082a830`
- Baseline volume: 5,553,430 tweets, 17,501,243 likes, 413 fetch-log usernames
  representing 334 distinct account IDs, and 95,057-node spectral metadata.
  Newest archived tweet is 2026-03-22; spectral topology is from 2026-02-26 and
  propagation is from 2026-04-10. This is a valid frozen baseline but not
  current network truth.
- Verification:
  - `make verify-baseline` under Node 22.23.1: pass; under Node 26: expected
    failure on the now-strict runtime contract
  - deep data certificate: `56 passed, 0 failed`
  - Python: `1210 passed, 5 skipped`
  - readiness verifier regressions: `3 passed`
  - public-site: `184 passed`
  - graph-explorer under Node 22.23.1: `729 passed`
  - graph-explorer under host Node 26: `43 failed`, all coupled to the
    experimental unavailable `localStorage`; this falsified the assumption that
    any newer Node runtime is an equivalent local test environment.

**Lesson:** Code recovery and data recovery are separate problems. Normalized
content comparison is necessary before trusting a dirty synchronized checkout;
CI must depend only on tracked fixtures; exact runtime majors matter; and
SQLite source data must be copied independently and certified before
experimentation. Freshness must be derived from Twitter Snowflake IDs—the
archive's textual `created_at` values cannot be ordered with SQL `MAX`.

**Data stored:** Clean checkout at
`Project 2 - Map TPOT - clean-main`; source data remains in the original
checkout; working data is gitignored under the clean checkout's `data/`.
Certification is reproducible with
`scripts/verify_assumption_baseline.py --require-data --source-data-dir PATH --hash-data --deep`.

**Next step:** Treat this as the frozen control dataset. Before drawing claims
about current network discoverability or soft membership, approve and implement
the snapshot-aware Community Archive refresh/manifest design, then rerun the
same evaluations on both frozen and refreshed snapshots.

---

## EXP-006: Does topic-seed ingestion actually hand off into active learning?

**Date:** 2026-04-15
**Question:** The new `fetch_topic_seeds.py` flow claims to (1) ingest advanced-search topic tweets, (2) stage authors in `frontier_ranking`, and (3) let `scripts.active_learning --round 1` fetch those authors next. Do the current helper contracts actually support that?

**Hypothesis:** The original implementation is broken at two contract boundaries: it logs API calls with the wrong function signature and stores raw `advanced_search` payloads without parsing them into the `enriched_tweets` schema. Even if corrected, the current round-1 selector will still suppress those authors because it excludes any account already present in `enriched_tweets`.

**Method:** Performed static review of `scripts/fetch_topic_seeds.py`, `scripts/fetch_tweets_for_account.py`, and `scripts/active_learning.py`. Added focused regression tests that simulate raw `advanced_search` rows, then verified selection behavior for accounts with only `topic_seed` rows versus mixed `topic_seed` + normal fetch rows.

**Result:** **CONFIRMED.** The initial implementation would fail on `log_api_call(...)` and fed `store_tweets(...)` the wrong data shape. After repair:
- raw search hits are parsed through `parse_tweet(...)`,
- search spend is logged through the real enrichment-log contract,
- staged authors land in `frontier_ranking`,
- accounts with only `topic_seed` rows remain eligible for round 1,
- accounts with any non-`topic_seed` enrichment remain suppressed.

**Lesson:** Topic-seed search hits are contextual preload data, not proof that an account has already gone through the account-level fetch/label loop. Dedup has to respect fetch provenance, not just table presence.

**Next step:** Run `scripts/verify_topic_seed_ingestion.py` against the real `archive_tweets.db` after the next topic-search batch to confirm staged-author counts and round-1 eligibility on production data.

**Supersession (2026-07-30):** EXP-024 showed that `frontier_ranking` is
unversioned and its active independent-mode information-value inputs are
invalid. The automatic handoff above is therefore quarantined. Topic searches
now store parsed tweets and resolvable profiles without assigning the
artificial `99.0` rank. Run the verifier with `--handles-output`, inspect the
result, and pass that file explicitly to `active_learning --accounts-file`.
Existing historical ranking rows remain intact but are ignored.

---

## EXP-001: Can higher-k NMF split ideological sub-communities?

**Date:** 2026-03-25
**Question:** EA & Forecasting contains mech-interp people, governance people, agent-foundations people, forecasters, and e/acc sympathizers. Can NMF at k=20 or k=24 separate them?

**Hypothesis:** If sub-communities have distinct follow patterns, higher k should produce factors that align with ideological facets.

**Method:** Ran NMF on the 800K-edge follow+like matrix (4,214 accounts × 268K targets) at k=16, k=20, and k=24. Compared factor compositions.

**Result:** **FAILED.** Higher k fragments existing communities into social sub-clusters (who follows whom within the group), NOT ideological facets. The same accounts appear across multiple factors. At k=24, EA doesn't split into mech-interp vs governance — it splits into "@bayeslord's cluster" vs "@torulane's cluster" vs "@strangestloop's cluster."

**Why:** Everyone in alignment follows @ESYudkowsky, @KatjaGrace, @tobyordoxford. The follow graph is identical across ideological facets. Mech-interp people and governance people attend the same conferences, follow the same accounts. They differ in what they WRITE about, not who they FOLLOW.

**Lesson:** Follow-graph NMF finds social clusters. Content analysis finds ideological facets. Don't conflate the two. See CLAUDE.md anti-pattern #9 (Signal Conflation).

**Next step:** Two-level labeling — LLMs tag sub-community facets (theme:mech-interp, theme:ai-governance) from tweet content. Cluster tags to discover sub-community boundaries.

---

## EXP-002: Do bio embeddings separate communities?

**Date:** 2026-03-25
**Question:** If we embed 15K account bios with sentence-transformers, do the embeddings cluster by community?

**Method:** Embedded 15,182 bios with `all-MiniLM-L6-v2` (384-dim). Computed community centroids from 343 seeds. Measured inter-community cosine similarity and intra-community coherence.

**Result:** **PARTIAL.** Some communities clearly separate by bio content:
- TfT-Coordination (0.51-0.69 similarity to others) — very distinct bios
- LLM-Whisperers (0.60-0.76) — technical bios stand apart
- AI-Safety (0.62-0.80) — quantitative/alignment language
- Highbies (0.51-0.78) — distinct voice

But others are nearly identical:
- Core-TPOT ↔ Internet-Intellectuals: 0.86 cosine — same vocabulary
- Contemplative ↔ Quiet-Creatives: 0.84 — overlapping language
- Core-TPOT ↔ Queer-TPOT: 0.83 — shared TPOT voice

Intra-community coherence: 0.38-0.53 (moderate). Tightest: Collective-Intelligence (0.53), TfT-Coordination (0.50). Loosest: Highbies (0.38), Qualia-Research (0.39).

**Lesson:** Bio embeddings are useful as a SECONDARY signal — especially for cold-start accounts without follow data. Not a replacement for graph structure. Best for: confirming community membership, distinguishing TfT/LLM-Whisperers from everyone else, bio-based search.

**Data stored:** `bio_embeddings` table (account_id, 384-dim BLOB, bio_source, created_at).

---

## EXP-003: What signal separates "famous-adjacent" from "TPOT member"?

**Date:** 2026-03-25
**Question:** @elonmusk scores 0.012 with 30 seed neighbors. @eigenrobot scores 0.058 with 92 seed neighbors. The graph can't tell them apart. What can?

**Tested signals:**

| Signal | Method | Result | Verdict |
|--------|--------|--------|---------|
| **Concentration** (seed_nbrs / inbound) | Computed for all placed accounts | @googlecalendar = 0.50, @eigenrobot = 0.66 | **FAILED** — low-degree noise inflates concentration |
| **Spread** (entropy of seed-neighbor vector) | Measured community entropy | @repligate = 0.952, @elonmusk = 0.927 | **FAILED** — TPOT communities overlap too much, everything is high-spread |
| **Score × neighbors composite** | Swept thresholds | @sama (0.56) = TPOT median | **FAILED** — popular tech people have many real TPOT connections |
| **Broadcast ratio** (following/followers) | From profile cache | @elonmusk = 0.000005, @eigenrobot ≈ 0.15 | **WORKS** but need follower counts (fetched for 9.3K accounts) |
| **Reciprocity** (mutuals / inbound from seeds) | Computed for accounts with outbound data | Famous < 0.06, TPOT > 0.17 | **CLEAN SEPARATION** — 3x gap, no overlap in samples |

**Key finding:** Reciprocity is the cleanest separator. Community membership is bidirectional — you're TPOT not because TPOT follows you, but because you follow TPOT back. Famous accounts are one-way: TPOT follows them, they don't follow TPOT.

**Limitation:** Only 14% of placed accounts have outbound edge data. The `check_follow` API endpoint can spot-check reciprocity for the rest (~10 per-pair checks per account).

**Decision:** Accept famous accounts as "adjacent/faint" rather than filter them out. TPOT IS tech-adjacent. Use celebrity concentration filter (follower-count based) for accounts with > 100K followers. Frontend UX fix (hide faint from community pages by default) is better than data-level filtering.

---

## EXP-004: Does NMF v2 (800K edges, k=16, with likes) validate v1 ontology?

**Date:** 2026-03-24 (Session 10c)
**Question:** Does doubling the graph and adding like signals destroy or confirm the 16-community structure?

**Method:** Re-ran NMF (k=16, follow+RT+like, like_weight=0.4) on 800K-edge graph (was 441K in v1). Formal factor alignment via feature overlap (greedy matching, threshold 0.1).

**Result:** **CONFIRMED.** 10/14 v1 factors survived with >= 17.5% overlap. 6 new births at k=16 that map cleanly to communities we already named by hand. 4 disappearances (Crypto/Web3 dissolved, Tools-for-Thought absorbed).

**Key shifts:**
- Core TPOT narrowed to @visakanv-adjacent nucleus
- Sensemaking split into essayist-flavored + builder-flavored
- Internet Essayists + Tech Philosophers merged at one level, split at another
- Crypto/Web3 dissolved — not a real TPOT community

**Lesson:** The 16-community ontology is real structure, not a sparse-data artifact. More data sharpens boundaries rather than blurring them. The community that disappeared (Crypto) was the weakest signal.

**Data:** v2 run saved as `nmf-k16-follow+rt+like-lw0.4-20260324-6f6f95` in `community_run` table. Not yet promoted to primary (v1 still active).

---

## EXP-005: Does tweet labeling agree with NMF graph placement?

**Date:** 2026-03-26
**Question:** If we label tweets for accounts already classified by NMF (graph-based), do the tweet-derived community assignments agree?

**Hypothesis:** If both signals capture the same underlying community structure, they should agree most of the time. Disagreements reveal accounts where social affiliation (follows) diverges from intellectual identity (content).

**Method:** Selected 15 NMF-only seeds (1 per community, weight > 0.3, no prior tweet labels). Ran through the enriched labeling pipeline (3-model LLM ensemble with bio, engagement partners, mention communities, RT source, sub-community facets, content profile). Compared NMF dominant community vs tweet-derived dominant community. 12 of 15 produced enough tags for comparison (3 had no tweets available).

**Result:** **42% exact match, 58% top-3 match.**

| Account | NMF (follows) | Tweets (content) | Verdict |
|---------|--------------|-------------------|---------|
| @NunoSempere | AI-Safety | AI-Safety | MATCH |
| @technoshaman | Collective-Intelligence | Collective-Intelligence | MATCH |
| @realpilleater | Core-TPOT | Core-TPOT | MATCH |
| @v01dpr1mr0s3 | LLM-Whisperers | LLM-Whisperers | MATCH |
| @Lithros | Highbies | Highbies | MATCH |
| @AnniePosting | Queer-TPOT | Highbies | partial (Queer-TPOT in top-3) |
| @taijitu_sees | Quiet-Creatives | Contemplative-Practitioners | partial |
| @rndmcnlly | AI-Creativity | Tech-Intellectuals | DIFFER |
| @sharanvkaur | Internet-Intellectuals | Highbies | DIFFER |
| @archived_videos | Qualia-Research | Highbies | DIFFER |
| @LChoshen | TfT-Coordination | Tech-Intellectuals | DIFFER |
| @petersuber | Tech-Intellectuals | TfT-Coordination | DIFFER |

**Pattern in disagreements:** All 5 "DIFFER" accounts follow one community but write content that fits another. @rndmcnlly follows AI art accounts but tweets about philosophy. @sharanvkaur follows essayists but posts highbie content. @LChoshen and @petersuber are mirror images — each assigned to the other's community by the opposite signal. These are genuine bridges where social scene ≠ intellectual identity.

**The 5 exact matches** are accounts where social and intellectual identity align perfectly — @NunoSempere IS EA through and through, @v01dpr1mr0s3 IS pure LLM Whisperers.

**Lesson:** Neither NMF (follows) nor tweet labeling (content) is "right" alone. They capture different dimensions:
- **Follows** = who you listen to, your social scene, where you hang out
- **Tweets** = what you think about, your intellectual identity, what you amplify

The combination is the truth. An account that follows Qualia researchers but tweets Highbie content is genuinely straddling both worlds. The disagreement IS the signal, not an error to resolve.

**Implication for seed criteria:** Accounts where NMF and tweets agree are the highest-confidence seeds (both signals converge). Accounts where they disagree should be flagged as bridges, not forced into one community. This suggests a confidence metric: `source_agreement = 1 if NMF_top == tweet_top else 0.5 if NMF_top in tweet_top3 else 0`.

**Data:** Cross-validation results for 12 accounts stored in tweet_tags + account_community_bits. NMF assignments in community_membership table (run `nmf-k16-follow+rt+like-lw0.4-20260324-6f6f95`).

---

## EXP-006: Can the local DB support a Phase 1 community-correctness audit without new fetches?

**Date:** 2026-03-26
**Question:** Can we build the first external-audit + human-review benchmark from the current local `archive_tweets.db`, or do we need another fetch pass first?

**Hypothesis:** Core and boundary TPOT accounts should mostly have enough local context already, but famous-adjacent hard negatives will often only exist as `profiles` rows without local tweet text.

**Method:** Queried `profiles`, `tweets`, `enriched_tweets`, `community_account`, and `account_community_gold_*` while assembling the Phase 1 pilot slate. Checked core candidates, boundary candidates, and famous-adjacent hard negatives for local text availability and current community assignments.

**Result:** **PARTIAL.** The local DB is sufficient to ship the pilot substrate now:
- core and boundary items generally have strong local tweet coverage
- current ontology / target-community IDs are all available locally
- `account_community_gold_*` tables already exist and can accept Phase 1 imports

But most hard negatives only have bios and profiles locally:
- `karpathy`, `pmarca`, `lexfridman`, `naval`, `hubermanlab`, `dwarkesh_sp`, and similar accounts are present in `profiles`
- most have `0` local `tweets` and `0` `enriched_tweets`

**Lesson:** The benchmark can start now, but the runner must degrade gracefully for hard negatives. Grok can still be used as an external auditor on bio-only rows, but those rows should be explicitly flagged as `missing_local_posts` so reviewers know the evidence basis is thinner.

**Data stored:** `data/evals/phase1_membership_audit_accounts.json`, `data/evals/phase1_membership_audit_review_sheet.csv`

**Next step:** Run the pilot with the current mixed-context slate, then decide whether Phase 1.1 needs a focused fetch pass for hard negatives before scaling the benchmark.

---

## EXP-007: Can archive-only active learning label what archive accounts talk about without spending Twitter API credits?

**Date:** 2026-03-26
**Question:** Can the active-learning pipeline use local archive tweets plus LLM labeling to infer content identity, while avoiding any new twitterapi.io spend for archive-backed accounts?

**Hypothesis:** Yes, if archive loading adapts to the real `tweets` schema and archive-only mode gates every paid context path, then locally archived tweets can drive LLM labeling with zero new Twitter API spend.

**Method:** Started with the archive-safe handle pool (`/tmp/tpot_archive_active_learning_handles.txt`) and ran `python -m scripts.active_learning --round 1 --archive-only`. First run failed on a schema mismatch (`like_count` assumed, real DB has `favorite_count`). Patched `load_archive_tweets()` to inspect `PRAGMA table_info(tweets)` and normalize real/archive-test schemas. A second smoke run exposed a second leak: reply tweets still called `thread_context` through twitterapi.io. Patched `src/archive/thread_fetcher.get_thread_context(... allow_api=False)` and threaded `allow_paid_api=not archive_only` through `scripts.active_learning.py`. Verified with smoke runs, then ran the only true archive-backed frontier tranche: `uh_cess`, `vyakart`, `vorathep112` with `--archive-only --archive-limit 5`.

**Result:** **Confirmed, with two hidden-paid-path fixes required.**
- `spent` stayed flat at `5.05`
- `reply_fetch_rows` stayed `0`
- `thread_context_cache` stayed flat at `310` after the final fixed runs
- `archive_enriched_rows` grew from `0` to `30`
- `archive_enriched_accounts` grew from `0` to `6`
- `label_sets_active_learning` grew from `1510` to `1527`
- `tweet_tags` LLM bits grew from `4005` to `4045`
- Frontier tranche outcome:
  - `uh_cess` → ambiguous (`LLM-Whisperers`, `highbies`, `Collective-Intelligence`)
  - `vyakart` → ambiguous (`Tech-Intellectuals`, `Collective-Intelligence`, `Core-TPOT`)
  - `vorathep112` → ambiguous (`highbies`, `Quiet-Creatives`, `Relational-Explorers`)

**Lesson:** "Archive-only" was not a single switch; it required closing three separate paid paths: timeline/search fetches, reply-community fetches, and thread-context fetches. Once those were all gated, the pipeline started using tweet content as intended. Also, only 3 not-yet-enriched archive accounts are currently in `frontier_ranking`, so a much larger archive sweep would be a bulk labeling job, not active learning.

**Data stored:** Results persisted in `data/archive_tweets.db` tables `enriched_tweets`, `tweet_label_set`, and `tweet_tags`. Smoke/probe account outcomes include `0xosprey`, `33asr`, `5matthewdub`; active-learning frontier tranche includes `uh_cess`, `vyakart`, `vorathep112`.

**Next step:** Decide whether to (a) keep using uncertainty-ranked archive tranches only, or (b) build a separate bulk archive-labeling queue for the remaining archive-backed accounts that are outside `frontier_ranking`. Also persist per-model label rows so `verify_active_learning` can report real agreement coverage.

---

## EXP-008: Multi-scale tweet clustering vs NMF communities

**Date:** 2026-03-29
**Question:** Does clustering tweet content at multiple scales discover structure that follow-graph NMF misses? Are NMF communities content-coherent, or purely social?

**Hypothesis:** NMF communities are defined by follow patterns (social tribes). Tweet content should capture a different dimension (intellectual interests). If so, AMI between the two should be low, and some NMF communities should scatter across many content clusters.

**Method:**
1. Exported 50K random authored tweets as CSV from archive
2. Embedded with `text-embedding-embeddinggemma-300m` (dim=768) on RTX 3080 via LM Studio
3. 23,808 tweets successfully embedded (model crashed twice at ~12K, used `--resume`)
4. K-means clustering at k=2,4,8,16,32,64 on L2-normalized embeddings
5. Rolled up tweet cluster memberships to 309 accounts
6. Cross-referenced against NMF primary community assignments
7. Computed cross-scale nesting purity and AMI/ARI

**Result:** **CONFIRMED — NMF and tweet content are nearly independent signals.**

Cross-scale nesting purity (tweet clusters):
- k=2→4: 0.928 (strong hierarchical structure)
- k=4→8: 0.841 (real sub-clusters)
- k=8→16: 0.666 (moderate)
- k=16→32: 0.518 (dissolving)
- k=32→64: 0.521 (noise)

NMF→tweet purity (does NMF community map to a tweet cluster?):
- At k=2: avg 0.61 — some signal. Quiet-Creatives 0.96, TfT 0.86.
- At k=8: avg 0.42 — most NMF communities scatter across content clusters.
- At k=16: avg 0.29 — near random. Core-TPOT, highbies, Internet-Intellectuals have no content coherence.

Adjusted Mutual Information (NMF vs tweet clusters):
- Peak AMI at k=16: **0.080** (0=independent, 1=identical)
- Peak ARI at k=16: **0.040**
- Both barely above random — these are genuinely orthogonal dimensions.

Communities with HIGH content coherence (social tribe ≈ intellectual tribe):
- Quiet-Creatives (0.96 at k=2), Queer-TPOT (0.45 at k=16), AI-Safety (0.47 at k=32)

Communities with LOW content coherence (social tribe ≠ intellectual tribe):
- Core-TPOT, highbies, Internet-Intellectuals — scatter everywhere. Defined by social position, not content.

Reverse analysis: tweet clusters are also NMF-diverse. At k=16, cluster_1 (n=43) mixes AI-Creativity, AI-Safety, and Qualia-Research — they write about similar things but are socially distinct.

**Lesson:** Follow graph and tweet content measure orthogonal dimensions of community structure. An account in AI-Safety (by follows) who tweets about contemplative practice is a bridge that only a multi-view system can detect. NMF alone would call them AI-Safety. Content alone would call them Contemplative. The truth is both. This validates the multi-view ensemble prior architecture from ADR 016.

**Data stored:** `data/embed_experiment.db` — tables: tweet_embedding (23,808 rows), tweet_cluster (6 scales), account_cluster_histogram (309 accounts × 6 scales), cluster_run (6 entries). Also tweets table with account_id for rollup joins.

**Next step:** Build multi-view account descriptor combining graph view (NMF/propagation), semantic view (tweet cluster histograms), taste view (like cluster histograms), and interaction view (quote/reply patterns). Fit ensemble prior on gold labels. This becomes the replacement for NMF-as-sole-prior.

---

## EXP-009: View agreement as confidence signal for holdout detection

**Date:** 2026-03-30
**Question:** Does graph-semantic agreement predict TPOT membership better than graph confidence alone? Should we boost confidence when views agree and penalize when they disagree?

**Hypothesis:** Accounts where graph-view and semantic-view agree on community assignment are more reliably classifiable. Agreement = higher confidence, disagreement = lower confidence or bridge account.

**Method:**
1. Used 238 seed accounts with both views (graph NMF weights + k=8 tweet cluster histograms) as training set
2. Trained separate KNN classifiers (k=5, cosine) on graph-only and semantic-only views
3. For 71 holdout TPOT members with both views, computed: graph community prediction, semantic community prediction, and whether they agree
4. Measured detection rate under different confidence strategies
5. Tested combined scoring: graph_conf * agreement_factor

**Result:** **HYPOTHESIS REJECTED — view disagreement is the signal, not agreement.**

82% of holdout TPOT members have views that DISAGREE (graph community ≠ semantic community). Only 18% agree.

Detection rates:
- Graph KNN conf > 0.3: 100% (all 71 detected)
- Propagation score > 0.05: 62% (44/71)
- Views AGREE + graph conf > 0.3: only 18% (13/71)
- Views DISAGREE: 82% (58/71)

The combined scoring (boosting agreement, penalizing disagreement) HURTS — it pushes real TPOT members down the ranking because they're bridges.

Bridge examples from holdout (all confirmed TPOT):
- @visakanv: graph=Internet-Intellectuals, semantic=Contemplative
- @repligate: graph=LLM-Whisperers, semantic=Core-TPOT
- @RomeoStevens76: graph=Contemplative, semantic=AI-Creativity
- @patio11: graph=Tech-Intellectuals, semantic=Collective-Intelligence
- @adityaarpitha: graph=AI-Safety, semantic=Quiet-Creatives

**Lesson:** TPOT is definitionally a cross-cutting meta-community. Its members follow one social tribe but intellectually range across several. View disagreement is a *feature* of TPOT membership, not noise. A "pure" account (follows and tweets about the same thing) is less likely to be TPOT — they'd be in a single-topic community instead.

This reframes the multi-view architecture:
- **Graph view's job**: detect proximity to TPOT seeds (works at 100% recall)
- **Semantic view's job**: characterize *what kind* of TPOT member (intellectual profile), NOT whether they're TPOT
- **View disagreement's job**: identify bridge accounts and multi-community members (the most interesting TPOT members)
- **Confidence**: should NOT penalize disagreement. Instead: graph confidence for TPOT membership, view disagreement for richness/bridge detection.

**Data stored:** Analysis run in-memory on `data/archive_tweets.db` + `data/embed_experiment.db`. No new tables created.

**Next step:** Revise ADR 017 to reflect that views serve different purposes (detection vs characterization vs bridge detection), not a single ensemble vote. The semantic view enriches the account description rather than replacing the graph-based community assignment.

## EXP-010: Can Blob-backed site data bypass gitignored public exports without fighting Vercel deploy limits?

**Date:** 2026-04-09
**Question:** Can we serve fresh `data.json` / `search.json` to the public site by uploading them to Vercel Blob and proxying them through site-owned API routes, instead of relying on gitignored files being present in each deployment?

**Hypothesis:** Uploading the two generated JSON files to fixed public Blob pathnames (`public-site/data.json`, `public-site/search.json`) will solve the stale-data problem cleanly. The only remaining risk is whether Vercel deployment of the new proxy routes is blocked by the project's `rootDirectory` behavior.

**Method:**
1. Inspected the frontend fetch path and confirmed it hardcoded `/data.json` and `/search.json`.
2. Added local code for:
   - shared frontend endpoint constants,
   - `GET /api/data` and `GET /api/search` Blob proxy routes,
   - a `node scripts/upload-public-site-data.mjs` uploader,
   - a human-readable verification script `scripts/verify_public_site_blob.py`.
3. Ran targeted frontend tests, the public-site build, and the Python export test suite.
4. Uploaded local `public/data.json` and `public/search.json` to Vercel Blob with stable pathnames and overwrite enabled.
5. Probed the direct Blob URLs and the public `amiingroup.vercel.app/api/data` and `/api/search` routes.
6. Tried three deployment paths for the new code: direct deploy from `public-site`, deploy from repo root, and local prebuild + prebuilt deploy.

**Result:** **PARTIALLY CONFIRMED.**

What worked:
- Blob upload succeeded.
- Direct Blob URLs serve the current export:
  - `data.json` = `25,637,670` bytes
  - `search.json` = `16,492,299` bytes
- Local code is sound:
  - frontend targeted tests: `43 passed`
  - `npm run build`: passed
  - `pytest tests/test_export_public_site.py -q`: `40 passed`

What failed:
- Public routes are still `404` because the new code is not yet deployed.
- Vercel CLI deploy attempts continue to recurse the configured project root:
  - from `tpot-analyzer/public-site`: path becomes `.../tpot-analyzer/public-site/tpot-analyzer/public-site`
  - from repo root: CLI ignores the existing link and tries to infer a new project from the workspace folder name
  - `vercel build --prod` only worked after locally nulling the ignored `.vercel/project.json.settings.rootDirectory`, but `vercel deploy --prebuilt --prod` still failed against the remote root-directory setting

**Lesson:** Blob is a valid fix for runtime data delivery; the remaining blocker is Vercel deployment mechanics, not the Blob approach or the app code. The project has a deploy-path mismatch between Git-integrated `rootDirectory=tpot-analyzer/public-site` and the Vercel CLI's local deploy resolution.

**Data stored:**
- Blob URLs:
  - `https://afob6mgxltjpsd5j.public.blob.vercel-storage.com/public-site/data.json`
  - `https://afob6mgxltjpsd5j.public.blob.vercel-storage.com/public-site/search.json`
- Verification output:
  - local `tpot-analyzer/scripts/verify_public_site_blob.py`
  - public URL probes against `https://amiingroup.vercel.app`

**Next step:** Ship the new code through the Git-integrated deployment path or reconfigure project-level deploy settings so the proxy routes can go live; once that deploy lands, `/api/data` and `/api/search` should immediately serve the already-uploaded Blob data.

---

## EXP-011: Parameterizing Directed Personalized PageRank for Subfield Resolution

**Date:** 2026-04-15
**Question:** If we parameterize the teleport probability (`alpha`) in Directed Personalized PageRank (instead of a globally hardcoded 0.15), can we force the math engine to isolate hyper-specific intellectual subfields inside dense macro-communities?
**Hypothesis:** Higher teleport probabilities force random walks to be shorter and more highly localized to the immediate seed neighborhoods, reducing the "washing out" smoothing effect across large macro hubs, solving our Subfield mapping boundary problem.
**Method:** 
1. Expose `alpha` parameter in `src/propagation/types.py` through to `compute_ppr`.
2. Ran `scripts.propagate_community_labels` at `alpha=0.15` (baseline wide), `alpha=0.45` (tight), and `alpha=0.85` (hyper-local).
3. Compared shadow-node assignments, "Seeds Absorbed Ratio", unassigned abstain count, and maximum Lift scaling.
**Result:** **HYPOTHESIS CONFIRMED.** Higher alpha creates extreme subfield localization:
- At `alpha=0.15`: 91.4% abstained. Max Lift for "LLM Whisperers" was 68.8x. Walk wandered deeply into generic graph.
- At `alpha=0.45`: 85.7% abstained. Max Lift for "LLM Whisperers" scaled to 388.5x. Tight clustered assignments.
- At `alpha=0.85`: 83.1% abstained. Max Lift for "LLM Whisperers" exploded to 5361.6x. Solved in 6 iterations instead of 55. We isolated purely the mathematically closest connections.
**Lesson:** The teleport probability `alpha` behaves directly like focal length for our clustering lens. By setting `alpha=0.15` for the global graph (identifying macro hubs) and then rerunning at `alpha=0.45` or higher solely inside the filtered subsets (e.g. `AI-Safety` only), we trivially slice granular subfields apart without Goodhart-ing or over-smoothing.
**Data stored:** Output logged to `docs/diagnostics/alpha_0.15.txt`, `_0.45.txt`, and `_0.85.txt`.
**Next step:** Integrate hierarchical propagation into the ingestion pipeline, ensuring AI-Safety / mechanistic interpretability seeds acquired via the topic search API are given high `alpha` localized propagation spaces.

---

## Template for future experiments

```markdown
## EXP-NNN: [Question in one line]

**Date:** YYYY-MM-DD
**Question:** [What are we trying to learn?]
**Hypothesis:** [What we predicted and why]
**Method:** [What we did — specific scripts, data, parameters]
**Result:** [What happened — with numbers]
**Lesson:** [What this means for future work]
**Data stored:** [Where the results live in the DB/filesystem]
**Next step:** [What this enables or blocks]
```
