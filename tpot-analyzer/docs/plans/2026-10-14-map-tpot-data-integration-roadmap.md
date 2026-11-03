Build Map TPOT into a reusable community-building discovery system. Consolidate existing on-disk profiles, public work, relationships and contact routes into a source-backed rich graph. Support searches across overlapping interests and multiple hops, with explanations of why each person surfaced and how you could contact them. Preserve your tags, corrections and research.

# Map TPOT data integration roadmap

Date: 14 October 2026, Asia/Kolkata.
Status15 October: implementation80418fe restored privately;93/93 intact. UI
feedback is not a gate to copied M2 preparation. Rich graph M2–M5 not delivered.

Build a map where an account's content, relationships, public identity links,
employment claims and contact routes can be inspected together. The first useful
result is a small account dossier, not a complete graph of everyone on X.
Retreat research and drafting are paused. Reusable evidence remains available;
event-specific fit, drafts and contact history stay separate from person data.

## Ownership and existing decisions

- Integration owner: Codex in this execution chat. Aditya approves new schema,
  live migrations, paid acquisition and product acceptance.
- Authoritative code destination:
  `/Volumes/AirBackup/home/Documents/Ongoing Local/Project 2 - Map TPOT - clean-main/tpot-analyzer`.
  Planning baseline: `codex/curator-review-shell`, commit `3dcc3cf`, dirty.
- Preserve the original checkout, raw-first-retrieval worktree, all captures,
  research files, browser-local notes and judgment/event stores. Do not clean up
  those trees until source custody and the integration diff are established.
- Reuse ADRs 019, 020, 021, 022, 023 and 024. Review and Map remain the two main
  workspaces. Working tags define overlapping categories through examples.
- This plan does not approve a database migration, new provider budget, deployment,
  external disclosure, outreach restart or inferred psychological classification.

## Starting evidence

The 14 October read-only audit found these quantities across the inspected stores:

| Observation | Count and scope |
| --- | --- |
| Numeric X IDs encountered | 1,681,690; not a unique-person count |
| Observed follow identifier-pairs | 2,834,409 across archive, shadow and October captures; aliases remain unresolved |
| Main archive tweets | 5,553,430 from 327 accounts |
| Main like and retweet records | 17,501,243 likes from 257 accounts; 774,266 retweets from 315 accounts |
| Shadow records | 95,138 accounts; 94,797 use `shadow:` IDs |
| Shadow graph sparsity | 77.6% of connected identifiers have degree one |
| October capture | 18,510 numeric account IDs, 20,582 seed-follow pairs, 11 sources |
| Website enrichment | 2,114 records; 1,894 cached HTML responses |
| Working tag store in raw-first worktree | 93 assignments, 52 accounts, 31 tags; keep separate from 167 legacy gold rows |

The newest saved bulk manifest located is July 30. The live Community Archive
pointer inspected on October 14 advertises an October 13 consent-managed package:
10,735,983 tweet rows across 787 authors and 797 profiles. These are publisher
manifest counts, not a newly downloaded or locally verified package. The new
schema and eligible population differ from the old export.

Sources: `data/archive_tweets.db`, `data/cache.db`, existing private October capture
and tracker, the original checkout's July 30 manifest, and the raw-first worktree's
`account_tags.db`. Main archive and cache counts are direct read-only SQL results.
The old `docs/DATA_INVENTORY.md` is a February baseline, not current authority.

## Milestones

### M0 Establish data custody and a reproducible inventory

Outcome: know which physical stores contain evidence, which consumers read them,
and which records are aliases, accounts, people or derived interpretations.

Reuse existing inventory/snapshot verification tools. Record source path, schema,
capture time, evidence time, coverage and consumer for each dataset. Preserve
content hashes and copy-tested recovery for the 93 working assignments/events.
Identify browser-local notes without clearing storage. Check the existing project
runtime before installing dependencies; the bundled Python lacks PyArrow.

Acceptance: reproduce scoped counts; identify duplicate copies without summing
them; leave every source unchanged; show a failed/missing store as unavailable,
not an empty successful dataset. Confirm the actual configured runtime paths
before any later UI or import change.

Dependency: none for read-only work. Next checkpoint: custody list and a fixed
20-account pilot drawn from tagged, archive-rich, shadow-alias, October-only and
cross-platform cases. This pilot is an integration sample, not a population study.

### M1 Show one joined account dossier using existing evidence

Outcome: open a pilot account and see its bio, source websites, stored posts,
typed relationships, contact routes, judgments and explicit gaps in one place.

Use numeric X IDs for exact joins. Present handle-based aliases as unresolved
candidates, not automatic same-person merges. Reuse the shared account editor and
cached website HTML. Contact routes retain personal/company/form distinctions;
dates separate post time, capture time and claimed employment period. Apply source
eligibility rules before exposing archive content in the product.

Acceptance: inspect all 20 pilot accounts; compare displayed evidence with source
rows; reject wrong-ID joins; display missing, stale and failed evidence distinctly;
preserve tags/events; prove the dossier does not trigger paid calls or send actions.
One missing source must not disable the rest of the account view.

Dependency: M0 source paths and eligibility checks. New persisted schema is not
required for this first read-only join. Next checkpoint: a private working UI with
five representative dossiers, followed by all 20 and operator review.

### M2 Add explicit identity and evidence relationships

Outcome: reusable cross-platform identity, website, employment and contact facts
no longer live only in event-specific CSV columns or prose.

Propose the smallest additive SQLite representation compatible with existing
stores. Distinguish person, platform account, organisation, website, post and
contact route. Represent identity links and `works_at`/`worked_at` as source-backed
claims with time and uncertainty, not destructive entity merges. A website-owned
link is stronger than a name match; conflicting handles or ownership stay open.

Acceptance: a copied-database pilot preserves every existing field and event;
re-import is idempotent; ambiguous same-name records do not merge; past employment
does not become current employment; a company inbox remains a forwarding route.
Only after that evidence and architecture review may a live migration be approved.

Dependency: schema choice and copied-data validation, then explicit migration
approval. Next checkpoint: the 20 dossiers using reversible typed relationships.

### M3 Refresh eligible archive evidence and repair graph consumption

Outcome: recent eligible archive posts and existing interaction evidence become
usable without overwriting the historical baseline.

Adapt the existing snapshot workflow to the current pointer, profiles/tweets
package, checksums and eligibility metadata. Keep original timestamps while
normalizing parsed times for recency. Old lexical `MAX(created_at)` over mixed
Twitter date strings is not a valid latest-post measurement.

Build graph node sets from the selected evidence types, not just following rows.
Keep reply, like, retweet, quote and mention views distinct. Wire compatible API
edge records into their appropriate views. Count unresolved liked-post authors and
retweet targets rather than losing them silently in joins. Missing follow records
do not prove unfollows. Withdrawn/ineligible archive evidence must not enter a new
active product or public export; historical retention needs an explicit policy.

Acceptance: copied import matches manifest scope and schema; invalid timestamps,
withdrawal, interrupted download and changed-source cases are handled; source
tables remain intact. Report retained/excluded edges per type with reasons.
Fixtures include interaction-only accounts absent from the follow node set.

Dependency: M2 identity contract, current source-policy mapping and a compatible
Parquet reader. M1 can proceed while this is prepared. Next checkpoint: before and
after coverage for the same pilot, not merely a larger edge count.

### M4 Pilot cross-platform and targeted public enrichment

Outcome: confirmed public identity links lead to profiles and activity on other
platforms, with public company and employment evidence available in the dossier.

Start from saved website links and inspected HTML. Pilot at most 20 existing linked
accounts per platform, using actual available identities rather than manufacturing
quota matches. Bluesky uses stable DIDs; Mastodon retains the instance-qualified
account identity and public visibility limits. LinkedIn initially supplies public
links and sourced employment claims; broad profile API access is not assumed.
Previous employers can be forwarding leads, never proof of current contactability.

Acceptance: two platforms' similar handles do not automatically match; protected,
deleted, rate-limited and failed sources stay distinguishable; cached observations
are reused; provenance and current/past employer distinctions appear in the UI.
No private-source import, message, form submission or hidden paid call occurs.

Dependency: M2 relations and platform permissions. Missing LinkedIn access does
not block Bluesky, Mastodon or public website work. Any paid X pilot needs a new
Map TPOT spending cap; the paused retreat cap is not repurposed.
Next checkpoint: review useful evidence gained per account and actual fetch cost.

### M5 Connect tags to explained discovery

Outcome: reviewing an account changes the candidates surfaced for that tag, and
the curator can see what changed and why.

Reuse source-selectivity and typed-graph retrieval where current contracts pass.
Compare graph-only, profile/content-only and combined retrieval on a fixed pilot.
Keep tag overlays and candidate order responsive while map coordinates remain
stable. Existing judgments can start the loop; do not demand new abstract tag
definitions. Freeze an extension only when evaluating a particular version.

Acceptance: add/remove/retract a tag, refresh and reopen the account without losing
state; show candidate changes and supporting posts/relationships; distinguish
retrieval relevance from affiliation and competence. Do not force tags to sum to
one or display heuristic scores as calibrated membership probabilities.

Dependency: M1 usable dossiers and M3 compatible evidence views. Numerical
calibration waits for adequate per-tag positive/negative evaluation labels; it
does not block ordinary tagging or candidate discovery. Next checkpoint: a user
can review an account, change a tag and inspect newly surfaced candidates.

## Blockers and decisions

| Boundary | Who resolves it | Work that can continue |
| --- | --- | --- |
| No blocker to read-only custody and pilot selection | Codex | M0 immediately after implementation direction |
| New identity/employment/contact schema and live migration | Codex proposes and tests; Aditya approves | M0 and M1 read-only joins |
| Current archive consent scope and obsolete importer contract | Codex maps public policy/schema; unresolved retention choices go to Aditya | Private custody, website evidence and judgments |
| Existing runtime dependency compatibility | Codex checks project environment; do not change global tooling | Metadata and SQLite work |
| Broad LinkedIn ingestion access | Permitted access or narrower scope | Public links, owned websites, Bluesky and Mastodon |
| Paid X acquisition scope and cap | Aditya before spending | All local and permitted public evidence work |
| Sparse and uneven graph/content coverage | Measure it; bounded acquisition where useful | Discovery with visible gaps |
| Eligible independent review, serving and user acceptance | Codex prepares coherent slice; approval/access waits are separate | Local validated implementation within approved scope |

## Forecast and stopping rule

Initial planning forecast: M0 custody and pilot selection take 2–4 focused hours.
M1's usable 20-account dossier takes a further 1–3 focused workdays after source
paths are established. These ranges exclude approval, independent review,
dependency recovery and deployment waits. Refresh the forecast at M0's checkpoint
and preserve the prior estimate with an explanation if it is missed.

Later milestone effort is unknown until M1 exposes real join and source-policy
failures. Do not promise a completion date for enriching 1.68 million accounts.

Finish each visible user journey before starting optional machinery. Reuse current
stores and verification tools. No new general-purpose ontology, crawler framework,
graph database or model orchestration layer is justified merely by this roadmap.
Leave bulk enrichment, automatic outreach, psychological profiling and calibrated
information-gain dashboards deferred. The retreat goal remains paused.


## Execution checkpoint: scoped custody/pilot, 14 October 2026

At the initial checkpoint M0 was in progress, not fully accepted. The standalone
script `scripts/verify_map_data_sources.py` produces a private read-only derived
report and optional copied tag backup. It imports no application state and makes
no network calls. Current report: 20 dossiers across 143 inspected source files,
with missing data and unresolved handle aliases explicitly retained.

Reproduce with new exclusive output names, from canonical tpot-analyzer:

```bash
python scripts/verify_map_data_sources.py \
  --archive data/archive_tweets.db \
  --shadow data/cache.db \
  --tags '/Volumes/AirBackup/home/Documents/Ongoing Local/Project 2 - Map TPOT/.codex-worktrees/raw-first-retrieval/tpot-analyzer/data/account_tags.db' \
  --captures data/private/retreat-follow-expansion-20261006-merged/candidates.json \
  --research data/private/retreat-invite-wave-20261007-next50 \
  --output data/private/map-integration-20261014/new-custody-pilot.json \
  --tag-backup data/private/map-integration-20261014/new-account-tags-backup.db
```

Five isolated behavioral tests: `python tests/test_map_data_sources.py`.
The CLI deliberately refuses to overwrite an output or backup. JSON and copied
DB contain private contacts/judgments and must not enter Git/public exports.
The current reader does not yet inventory browser-local notes or every Takes/
historical source, refresh eligibility, migrate data or render in the Review UI.
Those remain required work; current source-review checkpoint is recorded below.

The existing Review endpoint and evidence pane now consume the pilot through
`MAP_TPOT_DOSSIER_PATH`. All20 real exact-ID requests succeeded. New source reader
handles archive-profile gaps, source failures and identity refusal; UI renders
stored work/sites, typed contacts and limits without changing the tag schema.
The combined verifier and build pass; synthetic desktop/narrow render passes.
Takes57 subjects confirmed. In-app localhost5184:1 queue item backed up, no note
drafts;5183 keys absent. Tailnet/other profiles remain unverified, not empty.

Before activation, canonical `data/account_tags.db` was absent and custody awaited
operator choice. That gate is now resolved below. The first Gemini request returned401; later configured
provider authentication succeeded without changing project.env. Source review
supplied no actionable findings; unsupported live-state praise was discarded.
One clarification was truncated, not acceptance evidence. Reported charges$0.252768
under$1; no further review calls. Tag binding and served acceptance remain pending.

## Active-source checkpoint, 14 October 2026

Direct publisher pointer and manifest agree on October13 export and797 eligible
IDs. Exact pilot comparison:5 listed,12 not listed,3 unresolved. Absence does not
establish withdrawal; independent public website/API evidence has separate scope.
Membership alone does not revalidate historical nested-author content. The
publisher rejects reuse of historical enriched-Parquet copies; current package
splits profiles/tweets and lacks username/singular archive_upload_id expected by
our older reader. The raw-archive public-blob fetcher is also obsolete.

Private metadata, publisher guide and query-only comparison are saved under
data/private/map-integration-20261014/archive-policy-checkpoint. No Parquet data
or paid API was fetched at that checkpoint. Operator-approved REST is now the
default Review source, with private append-only observations, no old-post fallback.
20 exact-ID dossiers:13 current profiles/37 posts,7 joined-only;43 source reads200,
39 captures. REST population differs from the bulk list, not a consent classifier.
Combined verifier14/14 with72 backend tests, frontend suite and build passed.
Original93/93 tags/events unchanged; no server, migration, push or deployment.
Activation checkpoint21:44 IST: operator approved the checked copy as authoritative.
Canonical data/account_tags.db now holds93 assignments/93 events, mode0600;
original and checked backup remain unchanged. Live localhost5184/5001 is loopback
only, owned screen tpot-review-20261014; private launcher/receipts in tag-activation.
Five browser account views checked; prior all20 API evidence reused. Disposable
full-app IN→NOT IN→retract persisted across reloads;8 closure checks preserved
all original rows. Test5002/5185 stopped; no synthetic tags entered canonical.
Pointer/dropdown interaction and reviewer/account reload reset remain UX debt.
Next: operator accepts the live journey, then M2 schema proposal/copied validation;
no live migration, paid acquisition, push or public deployment. M2–M5 incomplete.

## References

- [Vision](../VISION.md) and [existing personal ontology plan](2026-07-26-personal-ontology-active-discovery-implementation.md).
- [ADR 019](../adr/019-versioned-research-data-and-artifact-manifests.md),
  [ADR 021](../adr/021-independent-overlapping-membership-and-evidence-semantics.md),
  [ADR 023](../adr/023-task-focused-curator-review-and-map.md) and
  [ADR 024](../adr/024-curator-estimate-trajectories.md).
- [Community Archive access guide](https://www.community-archive.org/llms.txt).
- [Bluesky public API guidance](https://bsky.network/docs/api-directory/).
- [Mastodon account API](https://docs.joinmastodon.org/methods/accounts/).
- [LinkedIn profile API restrictions](https://learn.microsoft.com/en-us/linkedin/shared/integrations/people/profile-api).
