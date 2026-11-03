# ADR 025 Source backed relationship sidecar

- Status: Direction approved by Aditya; independent review pending; copied-data experiment only
- Date: 2026-10-15
- Group: Data and discovery
- Integration owner: Codex, canonical clean-main/tpot-analyzer

## Issue

Map TPOT must connect accounts, websites, public work, organisations and contact
routes without treating them as the same kind of object. A company inbox can
reach several people without proving that their accounts belong to one person.
A page linking to a Bluesky profile is evidence of a link, not verified ownership.

The current TypedGraph uses account-to-account sparse matrices. It is useful for
social retrieval, but is not a store for source documents or contact semantics.
The joined dossier already holds exact account IDs and source-backed observations;
the next step is making those relationships queryable beyond an event's CSV.

## Proposed decision

Use an additive SQLite sidecar for source-backed relationships. Keep archive,
shadow, current curator tags and event correspondence in their existing stores.
Derive algorithm-specific account matrices from selected relationships later.
The operator approved this direction and the existing Review consumer on15 October,
conditional on independent review. No live binding changes before that review.

The prototype has three tables:

| Table | Meaning |
| --- | --- |
| entity | Typed source identity: X account, unresolved shadow account, web resource or contact route |
| evidence_snapshot | Exact private input bytes, SHA256, source path and report capture time |
| relation | Directed predicate, endpoints, source snapshot and JSON pointer, observed time, reported status and qualifiers |

Repeated imports of identical bytes add nothing. A changed observation creates
new source-backed rows, retaining the old version. That history does not choose
the newest claim as true or imply that a missing relationship ended.

## First queryable projection

Project profile website links, website observations, extracted outbound links and
typed contact routes from the existing private dossier snapshot. An extracted
JSON-string link points to its actual source field plus its decoded item index.
The whole source document remains available, including fields not projected yet.

Two example paths are `account → profile website → linked page` and
`account → contact route → reported source page`. The returned path must retain
the predicates, dates, source references and forwarding instructions. Reaching
the same inbox or website must not merge accounts or infer social membership.

Routes retain their explicit type. Organisation forwarding, work email and
contact forms are not personal email aliases. Missing dates stay unknown. Free
text about an employer is not automatically converted into current employment.

## Alternatives and tradeoffs

| Option | Benefit | Cost or limit |
| --- | --- | --- |
| Keep JSON and CSV only | No migration and easy source inspection | Each consumer must rebuild joins, relationship traversal and route distinctions |
| Extend sparse account matrices directly | Reuses current ranking machinery | Mixes account and non-account nodes; cannot carry source records or qualifiers cleanly |
| SQLite sidecar | Local, additive, queryable and compatible with existing deployment | Requires a relationship reader and derived graph views; prototype is not a production importer |
| Adopt a graph database | Rich traversal and graph tooling | New service, operations and migration burden before a proven consumer |

Recommendation: SQLite sidecar, confidence0.80. The bounded fallback is the
existing joined dossier while the schema is revised; never overwrite raw stores.

## Boundaries and remaining work

The first projection covers websites and contact routes, not full rich-graph
delivery. Public-work text, employment periods, platform identity confirmation,
social interactions and curator corrections still need dedicated typed adapters.
Contact route changes will need revisions and a useful current-state view.

The source snapshot is historical custody, not current archive eligibility.
Active product/export readers must apply each source's eligibility and privacy
rules. Working tags remain curator-scoped in their current event store; source
snapshots and contact details stay private. Readers must expose account-scoped,
curator-filtered views, never the whole retained source blob. No psychological trait inference,
calibrated membership estimate, outreach or paid acquisition is implied.

## Verification and next consumer

Run `python tests/test_map_relationship_pilot.py`, then:

```bash
python scripts/verify_map_relationship_pilot.py \
  --snapshot data/private/map-integration-20261014/custody-pilot.json \
  --output-db data/private/map-relationship-pilot-20261015/new-prototype.db
```

The CLI refuses existing outputs and nonprivate output directories. Synthetic
checks cover explicit identity, shared inboxes, source pointers, date preservation,
retained versions, idempotence, no-evidence refusal and no-overwrite behavior.
A successful copied pilot does not authorize live adoption or prove full coverage.

After approval, the first consumer should be the existing Review dossier: show
an account's typed routes and source paths from this store alongside current
public evidence, preserving the shared account editor. Only then expand imports
and build multi-view retrieval over social and content relationships.

## Related decisions

ADR 019 preserves source versions; ADR 020 binds derived graph artifacts;
ADR 021 separates membership meanings; ADR 023 defines the shared Review/Map
workspace. This proposal adds neither a new labeling substrate nor a replacement
for those contracts.

## Preparation checkpoint, 2026-10-15,09:12 IST

The optional exact-account reader and authenticated dossier API field are prepared
but unserved. It exposes bounded typed contacts and source-bearing two-hop paths,
not the retained raw snapshots or curator tags. Combined verification passes96
backend tests and13 checks; direct copied-data reads retain7 routes/6 paths for
20 accounts with unchanged bytes. No current-contactability claim follows.
Independent review is still pending; existing-Review path display, private binding
and browser acceptance are not complete. This does not amend the approval gate.

## Review repair amendment, 2026-10-15

The initial independent Claude review completed with findings. Repairs preserve
the three-table append-only storage: every snapshot observation remains stored;
the reader collapses unchanged link claims and identical contact qualifiers before
applying limits. Changed contact claims stay separate. The representative is from
the latest recorded capture, not a declaration of current truth; counts are stored
observations, not independent confirmations. Per-edge source dates remain visible.

A recorded source-URL/resolved-URL difference becomes a reported page_resolves_to
edge, not URL-based person equivalence. Shared-page traversal remains valid across
dossiers/captures; the observing account is exposed for newly imported link claims.
This does not establish ownership, contemporaneous co-membership or affiliation.

An explicit current archive tombstone must not become a historical dossier
fallback through this archive-backed endpoint. Simple not-found is not withdrawal.
Independent public sources remain retained and have separate eligibility; future
independent-only views must not inherit a blanket person-level exclusion.

Joined contact/check evidence is retained unless an identical route is rendered
from the sidecar; different qualifiers remain visible. Failed fresh pilot creation
cleans up only its own exclusive output. Projection-gap persistence and historical
observation drill-down remain follow-up work, not implemented by this repair.

## Initial private adoption, 2026-10-15,11:14 IST

The reviewed website/contact consumer is active in the private Review dossier.
Timezone-aware captures normalize to UTC; legacy read dates are compared/displayed
at millisecond precision, and undated representatives are explicitly unordered.
Observer metadata describes only the representative observation, not all captures.
Explicit or unvalidated restriction flags disable historical archive fallback in
this endpoint. After supported repairs, independent closure review found no
blocking defects.109 backend tests/13 verifier checks and five browser cases pass.

The fresh20-account sidecar contains84 entities/78 reported relations,7 routes and
17 path variants, including11 redirects. Those are not17 people or corroborations;
publisher navigation links remain a known discovery-quality issue. Original
stores/candidates remain intact. Full platform identity, employment and discovery
coverage are still open; this adoption does not certify the broader graph.

## Approved saved-profile/work extension,2026-10-15

The operator approved projection of the full saved October18,510-profile capture
and931 public-work observations, plus local evidence search in the existing Review.
Use the same three tables: profile_observation account→profile and
research_associates_with account→web resource. The latter means saved research
associates the account with that work, not verified authorship or competence.
Exact sources/JSON pointers remain retained; searchable fields are allowlisted.
Event fit, drafts, send history and derived geographic routing are excluded.
Publication/credit/inspection qualifications stay attached; missing observation
time remains unknown. No mtime/preparation-date substitution or person merge.

First search is all-word literal matching across historical public profile and
saved work text, exact handle first then alphabetical. No confidence/semantic
ranking claim. Opening a result pins the string account ID, preserves existing
contacts and tags, and may separately request current public Archive evidence.
Current Archive restrictions retain the existing dossier refusal behavior;
mere absence is not withdrawal. Raw snapshots remain private, not API responses.
The fresh candidate must pass independent review and browser acceptance before
replacing the private runtime binding. Existing files remain recoverable.

## Broader private adoption,2026-10-15,11:56 IST

Independent Claude review and focused closure completed; four supported defects
were fixed and closure found no blockers.117 backend tests/13 combined checks,
lint/build and real browser search→exact dossier acceptance pass. Active private
sidecar:18,510 profiles,931 work observations across890 accounts,33,133 relations
and128 byte-exact sources. Original7 contact cards and canonical93/93 judgments
remain intact. Existing sources/pilots and new active file remain unchanged.

Search results retain self-described historical location labels, work association
and context; every entered substring has a shown explanation before result trim.
Structured credit/publication dates remain qualifications, not observation times.
Different qualifiers do not collapse. Configured read failure is visible and
distinct from no matches/not imported. Exact-ID conflicts remain refusals.
Representative source references, historical handle aliases and other-source
coverage are explicitly incomplete; no person merge, semantic fit or probability
claim. This is local private adoption, not publication or completion of the map.

## Saved contact research reuse,2026-10-15

Reuse the same sidecar for existing explicit public route reviews and partial
checks. has_contact_route/reported_at retain route type, published source, date,
evidence and routing instruction. contact_check links the exact account to each
inspected page with the original reason/date and incomplete outcome; it is never
a no-contact claim. Full source bytes remain private. Shared inboxes do not merge
accounts, and primary_email/event selection/send history are not person facts.
Search exposes counts/types only; route contents and partial-check sources are
read through the existing curator-only exact-account dossier. This implements
the approved reusable-contact direction without a new store or outreach workflow.

## Contact-aware private adoption,2026-10-15,12:25 IST

All13 saved contact source files are projected, including the first non-batch
file:114 sourced routes/90 accounts and32 incomplete-check records. The existing
18,510 profiles/931 work observations remain, now33,431 relations/141 snapshots.
Source parity/pointers, independent review/closure,132 backend tests/13 checks,
lint/build and real private browser acceptance pass.93/93 judgments preserved.

Search routeCount counts distinct typed route entities, while dated/qualified
claims remain visible in dossiers. Coverage is limited to searchable profiles.
Incomplete checks are source records keyed by snapshot and original record pointer;
a carried-forward record is retained, never a new inspection or corroboration.
This chosen observation unit is explicit in code/UI and tested across snapshots.
Source-specific Archive restrictions/auth are unchanged; no outreach or new paid
data acquisition. Remaining shared-inbox traversal/normalization/legacy data gaps
stay on ROADMAP. This private adoption does not complete the full rich graph.

## Historical directed-follow consumer,2026-10-15

Reuse the same store for follows_observed between exact X account IDs. Import
only existing candidate targets and explicitly public captured source profiles;
raw omitted observations remain private, not silently restored into evaluation
or operational scopes. Each edge references response bytes/row plus its receipt
request and timezone-aware capture time. No new fetching or completeness claim.

The existing Review search gains an optional outgoing1/2-hop filter. It returns
a deterministic representative shortest path, not reversed edges, friendship,
expertise or membership confidence. Missing source coverage refuses explicitly;
text search remains independent. Source profiles/counts and partial network scope
are visible. Multiple capture times are not proof that a path coexisted at once.
No new service/schema, account merge or judgment-store change is introduced.

Adopted privately13:18 after independent review/closure,144 backend tests/13
combined checks, raw source parity and real browser acceptance. Counts:
18,521 profiles,20,593 scoped follows from11 sources,54,040 relations/270
snapshots. Search separates whole-corpus and selected-scope coverage, including
how few first-hop nodes have outgoing evidence. Source following counts use
receipt-bound public profiles; failed declarations never expand eligibility.
Existing93 tags/events and raw/prior stores preserved; no outreach/public export.

## Current post context consumer,2026-10-15

Current public REST observations already include parent-post, parent-account,
quoted-post and conversation IDs. Preserve them as exact string references/nulls
in the Review DTO and show investigation links; do not infer social agreement or
membership from them. Raw observations remain in the existing private REST cache.
This adds no relationship schema, fetch, account merge or probability. Broader
historical interaction backfill still needs current source eligibility and the
actual package schema; offline custody counts are not active graph evidence.

Adopted privately14:30 after independent review/closure,154 backend tests/13
checks and real browser context links. Current response semantics/auth/capture
and all93 existing judgments preserved. This-post/context links do not fetch or
republish referenced content; X may refuse it. No broad typed backfill claimed.

## Published-profile bridge copy,2026-10-15

Current publisher pointer/manifest/profile Parquet validated into an additive
copied graph using the same schema. Original JSON metadata and clearly derived
decoded-row JSON retain refs to raw Parquet SHA/row/URL; raw Parquet stays private
and unchanged. Preserve observedAtField=latest_observed_at and sourceKind/export
on both profile and website facts. This is not field-level capture or live consent.
Independent review/closure and168 backend/13 checks support copied-only scope;
current-source gate/consumer is required before any active binding. No tag changes.

## Current-source profile consumer,2026-10-15

Before reading imported profiles or their website roots, Review checks fixed public
latest/manifest metadata for matching publication, export, file checksum and exact
eligible account IDs. There is no stale permission cache. Source failure hides
only this layer, with visible source status; independently saved facts remain.
Independent follow paths can name an exact account ID when its profile is hidden,
never reuse the hidden handle. Withdrawal is not absence or an identity conflict.
Every new export invalidates the older layer until refreshed; no automatic paid
fetch or bulk re-import follows. Latest-account observation is not field-level
capture, verified authorship, contactability or membership confidence.

Adopted privately15:42 after188 backend/13 checks, independent review/closure and
real search→new exact-ID dossier/website/posts acceptance.19,256 profiles include
863 currently eligible package observations; old graph/contact/work/tag state
preserved. No paid acquisition, public export or completion of the full map.
