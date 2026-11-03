# ADR 026 Current post search index

- Status at decision: approved by Aditya on 15 October 2026; implementation pending
- Group: data and discovery
- Owner: Codex, canonical clean-main/tpot-analyzer

## Decision

Build a separate, rebuildable SQLite FTS5 index from the current checksum-verified
Community Archive package. Keep the relationship sidecar, original stores and
curator judgments unchanged. FTS5 is already available in the project runtime;
this introduces no database service or paid request.

The index stores post text, exact author/post IDs, timestamps, typed references
and raw Parquet row provenance. The original package remains the source. Reply,
quote, repost, conversation and mention references keep distinct meanings. A
reference does not establish agreement, friendship, competence or membership.
Aggregate favorite counts are not individual like events. Numeric nested media
and URL fields remain in the raw source until their meanings are mapped.

## Search behavior

All query words must occur in an account's indexed posts, not necessarily in the
same post. Show a supporting post for each matched word, its original link and
typed context. Candidate order is an explicit retrieval heuristic, not a
membership probability. Reuse Review's exact-account editor and optional directed
follow scope so evidence can lead to existing work, contact routes and judgments.

Before display, check current publication, file checksums, export and exact author
eligibility. A withdrawn, superseded or uncheckable source is hidden, not reported
as zero matches. Independent profile/work search remains available. Interrupted
or invalid builds never become ready indexes; published indexes are read-only.

## Alternatives and consequences

Parquet-only scans avoid an index but repeatedly decode the corpus for interactive
search. A graph database or external search service adds operations before a
proven consumer. A local derived index supports fast retrieval without making it
the authoritative graph or changing existing facts. Its storage/build cost and
query latency must be measured, not assumed. New nightly publications invalidate
the prior source until refreshed; automatic refresh remains separate work.

## Acceptance

Use realistic synthetic Parquet plus the verified real package. Reject checksum,
schema, author-ID, duplicate-post and source-visibility violations. Preserve exact
IDs above JavaScript's safe integer range. Prove across-post word matching,
nonmatches, source withdrawal/refusal, auth, follow scope, cancellation and retry.
Measure real rows, source authors, bytes, build and query time. Obtain independent
code/synthetic review, then verify search→supporting post→exact dossier in Review
before private activation. Preserve all existing tags and source files.

## Implementation checkpoint, 15 October 2026, 16:44 IST

Implemented and privately served in canonical clean-main. The ready index contains
10,812,754 posts by853 eligible source authors,7,490,117,632 bytes, built in385.969s.
This is not post coverage for every saved profile. Fresh publication checks hide
superseded or unavailable sources.204 backend tests/13 combined checks, focused
42 tests, lint/build and independent code/synthetic closure pass.

The real browser search→dated support→exact dossier→reload journey preserves the
existing tags; all93 tags/events and six protected source/store hashes are unchanged.
Screenshot capture is unavailable because the host pane reports width0, so physical
visual/operator acceptance is pending. No paid call, message, push or public deploy.
Automatic package/index refresh and typed interaction traversal remain follow-ups,
not claims of this implementation. The full Map TPOT discovery goal stays active.

## Refresh implementation intent, 15 October 2026

Complete the existing derived-index lifecycle with an operator-run refresh command.
Reuse the approved downloader/builders, prepare a private release containing both
the index and copied profile graph, and atomically replace a managed current
symlink after a fresh publication check. Retain prior releases and never replace a
regular file at that binding. Reuse the already verified package/index when first
adopting the managed path; unchanged publication is a no-download no-op. Failures
keep the old binding but never override its source-visibility gate. A process lock
prevents competing refreshes. No scheduled fetcher, new service or paid request.

## Refresh delivered, 15 October 2026, 17:09 IST

The operator command is `scripts/verify_current_archive_refresh.py`. It checks by
default without creating a release; `--refresh --source-db PATH` explicitly permits
bounded download/build/adoption. `--seed-bundle PATH --seed-index PATH` reuses the
existing verified pair for first adoption. The managed root is supplied explicitly:

```sh
python scripts/verify_current_archive_refresh.py --root PRIVATE_ROOT
python scripts/verify_current_archive_refresh.py --root PRIVATE_ROOT --refresh \
  --source-db PRIVATE_ROOT/current/graph/relationships.db
```

Review uses `PRIVATE_ROOT/current/index/posts.db` and
`PRIVATE_ROOT/current/graph/relationships.db` after one-time runtime configuration.
The current link changes only after both consumers qualify and publication is
rechecked. A missing/damaged managed release reports unhealthy and can be rebuilt
using an explicit intact source graph. Regular files and unmanaged targets are
refused. Seed package, index, manifest, counts and eligibility must agree exactly.

Real adoption reused10,812,754 posts/853 authors with0 downloaded bytes/no rebuild;
a repeat refresh was a no-op. Private browser search and exact dossier still work,
with all93 tags/events and six protected stores unchanged.28 focused cases and
223 backend/13 combined checks, independent review/closure pass. New-publication
replacement and failure recovery are verified synthetically, not observed live.
No scheduler or retention cleanup is installed; prior files must be retained for
seed reuse. The no-op relies on previously qualified index metadata rather than
rehashing the entire index. POSIX/local locking only. Crash-directory durability,
redirect-policy consistency and request-level graph/index path snapshots remain
documented lifecycle debt. Physical/operator visual acceptance remains pending
because the host pane is0×0. No paid data, outreach, push or public deployment.

## Typed-reference consumer intent, 15 October 2026

Use the already retained reference fields for a materialized adjacency projection
inside the derived index. Keep reply, quote, repost and mention distinct; conversation
roots alone are not social edges. Resolve quote/repost targets only through exact
referenced post authors. Unknown targets stay unresolved, not guessed identities.
Count distinct posts per typed account pair, exclude self-references from discovery
and preserve a representative post, target-post resolution and raw row references.
Incoming exploration reverses traversal, never the original edge direction.
Only currently eligible nodes can participate, including intermediate nodes. Show
one deterministic shortest example path, not affinity or membership probability.
Upgrade the existing index in a fresh copy and adopt through the managed binding;
original source/index and judgments stay intact. New refresh builds include the
projection. Text search remains available if an older index lacks this projection.

## Typed paths delivered,15 October2026,18:22 IST

Review now offers post-reference relationships, starting account, selected types,
incoming/outgoing traversal and1/2 hops. Default1 hop: the measured2-hop reply
neighborhood nearly saturates the current cohort, so the UI warns about breadth.
Path cards preserve original actor direction, distinct posts per typed pair,
source dates as reported, excerpt, source/target links and raw row/checksum context.
They do not report membership, endorsement or psychological-stage confidence.

The copied projection contains181,842 typed pairs/2,563,519 non-self reference
observations,839 outgoing sources inside863 eligible profiles. Typed totals can
overlap across targets/types. Build117.686s, maximum resident523,468,800B. Self
references are audited but excluded; conversation roots are not projected edges.
Missing reply-account IDs resolve only through exact referenced-post authors or
remain unresolved. Actual current package has0 such orphan replies, allowing the
already measured data to be reused without claiming a revised-builder benchmark.
Equal-date representative ties use exact-ID lexical order, not numeric chronology.

Upgrade the qualified old index without editing it, then adopt the copied seed:

```sh
python scripts/verify_current_archive_interactions.py --bundle BUNDLE \
  --index ORIGINAL_INDEX --output-dir NEW_PRIVATE_DIRECTORY
python scripts/verify_current_archive_refresh.py --root MANAGED_ROOT --refresh \
  --source-db CURRENT_GRAPH --seed-bundle BUNDLE \
  --seed-index NEW_PRIVATE_DIRECTORY/posts.db
```

Explicit replacement seeds are honored even for an unchanged publication and
must have a completed projection with physical pair/reference totals matching its
audit. Interrupted copies stay unadoptable. Default no-seed refresh remains a
no-op for a current qualified release; an already bound legacy text-only index
remains usable but reports referencePathsBuilt:false. New builds include paths.

Independent code/synthetic review and closure,56 focused tests,244 backend/13
combined checks, lint/build and real browser search→path→exact dossier pass.
Private adoption downloaded0 bytes and retained the previous release. Original
index identity, six protected store hashes and93 tags/93 events are unchanged.
Physical screenshot/operator visual acceptance remains pending on the0×0 host
pane. No paid data calls, outreach, push or public deployment. Recency/repetition,
working-tag relevance and mixed-source discovery remain future work; the larger
Map TPOT goal is not complete.

## Working-tag reference discovery intent,15 October2026

The existing tag consequence panel can read exact curator/tag examples and use
the approved current post projection directly. Count distinct IN examples linked
to each unreviewed candidate, not posts or multiple reference types as independent
examples. Offer outgoing/incoming one-hop discovery, selected types, minimum
lifetime posts per type/pair, a latest-reference cutoff and minimum IN support.
Lifetime repetition plus a recent latest post does not require that many recent
posts. Default3 lifetime posts/type/pair, latest within90 days, one IN example.
These are reversible retrieval controls, not calibrated membership assumptions.

Exclude accounts already judged IN or NOT IN for this exact tag. NOT IN example
adjacency is contextual support shown separately, never an automatic negative
label or penalty for its neighbors. Other tags/curators do not seed this target.
Show eligible/missing example counts; do not silently drop the missing coverage
from denominators. Hide withdrawn/changed/unavailable post evidence distinctly
from an empty candidate set. Keep the legacy stored-follow comparison separate.

Order by distinct IN support, latest qualifying reference, then exact account ID.
Show up to three source-backed example paths per candidate and open the existing
dossier/editor. Every request rereads working tags; successful revisions compare
loaded states under the same target/filters. Filter/channel changes clear that
baseline; failed requests cannot leave actionable stale cards. No schema change,
index rebuild, source edit, paid fetch or automatic judgment is involved.

## Working-tag discovery delivered,15 October2026,19:23 IST

The existing consequence panel defaults to the current post-reference channel.
Its controls select direction/types, lifetime posts/type/pair, latest-reference
window and distinct IN supports. Counts include all target examples and show
which are eligible/missing, plus candidate total/shown. Source paths lead to the
existing exact dossier and editor; stored-follow comparison remains separate.
Revision refresh, negative/retract and source refusal are covered by real temporary
tag stores and source-shaped indexes. No live human judgment was fabricated.

263 backend tests/13 combined checks,19 new backend/5 UI cases, lint/build and
independent code/synthetic closure pass. The real browser narrows56→16 candidates
with existing examples, opens saved work/website paths and retains prior tags.
All93 assignments/events, six protected store hashes and the active index identity
are unchanged. Data/query code remains read-only; no index rebuild or schema change.
Physical screenshot/operator visual acceptance is pending on the0×0 host pane.

Social references do not establish topic interest: a real supporting mention
concerned food rather than the target topic. Next combine the working neighborhood
with content constraints; keep heuristic retrieval separate from membership and
competence. The broader Map TPOT goal remains open. No paid data, messages, push
or public deployment occurred.

## Tag plus content intent,15 October2026

Allow an optional all-word query over each unreviewed candidate's own indexed
posts. Apply it to the complete reference-qualified pool before result limits.
Share the existing parser, FTS matching and supporting-post rendering with plain
post search; that existing search remains historical by default. No new index,
service, schema, model, paid fetch or judgment is introduced.

The tag panel's content query defaults to a90-day own-post window, independently
of interaction latest-date/repetition. All words may occur in separate posts.
Recent-window membership and displayed supports use the same closed UTC interval;
any-date explicitly removes both date bounds and retains dates as reported.
Show which reference candidates lack indexed posts in the requested window rather
than declaring negative topical evidence. Keep quotes, reposts and criticism visible.
This is lexical retrieval, not agreement, current interest or demonstrated expertise.

Words/window are drafts until Apply or Enter; do not run expensive queries on each
keystroke. Show the applied query, window, pre-content pool, searched/missing-post
counts and dated source posts. Clear restores reference-only discovery. Applied
query/window changes reset the comparison baseline just like other filters.

## Tag plus content delivered,15 October2026,20:51 IST

Implemented without a schema/index rebuild and privately served. Full reference
pool filtering precedes truncation; each word has dated source-backed support.
The tag form applies query/window drafts explicitly and clearing restores the
reference neighborhood. Supporting posts and missing-coverage counts use the same
time bounds; plain post search remains historical by default. One shared post
renderer keeps typed context and source-row links consistent in both views.

276 backend tests/13 combined checks,53 focused backend/24 UI cases, scoped lint/
build and completed independent code/synthetic review pass. Real UI16→2 recent
word matches, any-date10 and Clear16 lead to the exact existing dossier with the
active tag retained.93 assignments/events, six protected hashes and the index
identity remain unchanged; no live judgment was fabricated. Source posts include
humor/reposts, so counts are not evidence of expertise. Physical screenshot/operator
acceptance remains pending on the0×0 host pane. No paid data, outreach, push or
public deployment. Cached work/contact coverage, semantic quality, cross-platform
identity and legacy Map replacement remain open in the larger goal.

## Explained combined-search ordering,16 October2026

Operator approves improving ranking after private dataset activation. Activation
is independently held by an unavailable publisher pointer, not missing authority;
ranking can be prepared/tested without exposing unqualified Archive evidence.

Retain the complete existing all-word candidate set and source eligibility gates.
Before truncation, order exact handle words first, then full display-name word
matches, then distinct query words supported by profile/saved-work/cached-page
text. Alphabetical handle and exact ID resolve ties. Show each ordering reason;
do not export a numerical fit/confidence score. Source duplication and post volume
do not increase weight. This is a reversible lexical heuristic, not a semantic
model, identity confirmation, authorship, agreement or expertise. Cached pages
and saved work remain qualified associations; first-hand authorship is not inferred.

Tradeoff: saved-text-rich accounts can outrank stronger post-only candidates.
Retain those candidates and visible post context; evaluate later with curator
relevance judgments rather than claiming this heuristic establishes best fit.

## Independent saved API reference channel, 19 October 2026

The working-tag panel may explicitly select already-admitted saved API references
from the relationship sidecar. This is not an Archive fallback or new source-use
activation. Read current exact-curator/tag anchors on each request; count distinct
IN examples, exclude judged accounts, and show NOT IN adjacency without a penalty.
Reuse existing typed paths with original post/edge sources, unknown labels and
incoming arrows. Order by support then exact ID; show up to three example paths.
Types, direction and minimum supporting examples are supported. This channel is
historical/all-time, without the Archive recency, repetition or content filters;
reject unsupported filters instead of quietly ignoring them. No HTTP call occurs.
Missing source is unavailable, not zero relationships. Source changes reset the
comparison baseline; revisions reuse the existing refresh/correction loop.
No schema, index, raw source, tag mutation, identity or calibrated-score change.

Preparation checkpoint, 19 October 2026: synthetic and real-source checks pass,
but no independent reviewer answer is available. This channel is not accepted
for main/private activation; preserve the tested preparation separately.
