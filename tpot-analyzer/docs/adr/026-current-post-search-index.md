# ADR 026: Current post search index

- Status at decision: approved; derived local index
- Date: 2026-10-15
- Group: Data and discovery

## Decision

Build a separate, rebuildable SQLite FTS5 index from the current checksum-verified
Community Archive package. The package remains authoritative; the index is a
derived retrieval structure, not a new graph or source of identity. Preserve
exact author/post IDs, text, timestamps, typed references and raw row provenance.
Published indexes are read-only. Interrupted, invalid or unqualified builds must
not become ready indexes.

Reply, quote, repost, conversation and mention references retain distinct
meanings. A reference does not establish agreement, friendship, competence or
membership. Aggregate favorite counts are not individual like events. Fields
whose meanings have not been mapped remain in the raw source.

## Search and source policy

All query words must occur in an account's indexed posts, though not necessarily
in one post. Show supporting posts for matched terms, original links and typed
context. Candidate ordering is an explicit retrieval heuristic, never a
membership probability. Reuse exact-account Review and optional directed-follow
scope.

Before display, check the current publication, file checksums, export and exact
author eligibility. Withdrawn, superseded or uncheckable Archive evidence is
hidden, not reported as zero matches. Independent profile/work search remains
available. A new publication invalidates the prior Archive-backed layer until
refreshed; no stale permission cache or automatic refresh may bypass that gate.

An operator-run refresh may reuse qualified source/index pairs, create a private
release and replace a managed binding only after source revalidation. Keep prior
releases, serialize refreshes, refuse unmanaged/regular-file targets, and preserve
the old binding on failure. This does not authorize a scheduler or paid request.

## Typed reference and working-tag consumers

The derived index may project typed post-reference adjacency. Resolve quote/repost
targets only through exact referenced-post authors; unknown targets remain
unresolved. Exclude self-references from discovery while retaining their audit
status. Incoming exploration reverses traversal, not the original edge. Only
eligible nodes may participate. Show a deterministic shortest example path, not
affinity or membership probability; conversation roots alone are not social edges.

The existing tag consequence panel may use the approved current post projection
as a separate discovery channel. Count distinct IN examples, exclude accounts
already judged for that tag, and show NOT IN adjacency only as contextual evidence,
never as an automatic negative label. Missing eligible examples remain visible in
coverage. Retrieval controls such as direction, type, support threshold, date
window and own-post lexical filter do not encode calibrated membership beliefs.
Filter changes reset the comparison baseline; requests reread current tags.

An optional all-word own-post filter applies to the full reference-qualified pool
before display limits. The content window is independent of interaction recency;
use the same closed UTC interval for qualification and displayed support. Show
accounts lacking eligible posts rather than treating them as negative evidence.
Words/window are explicitly applied, not queried on every keystroke. Plain post
search remains historical by default.

Saved API references may be selected as a separate historical channel only when
already admitted by their source policy. Preserve original arrows, exact IDs,
dates, typed paths and missing-source status. Do not silently apply unsupported
Archive filters to this channel; reject unsupported combinations. No HTTP call,
tag mutation or source-policy override occurs.

## Alternatives and acceptance

Parquet-only scans repeatedly decode the corpus; a graph service or external
search system adds operations before a proven consumer. Keep the local derived
index and measure build/query behavior. Acceptance covers exact IDs, schema and
checksum refusal, complete cross-post matching, typed context, source withdrawal,
auth, cancellation/retry, scope and preservation of existing judgments.

Ranking remains lexical and heuristic. A tested BM25 replacement exceeded the
existing query budget and exposed a NOT IN example, so it is rejected and must
not be activated. A bounded all-words-in-one-post co-occurrence comparison is a
separate proposed experiment, not an accepted serving change. No tuned synonyms,
semantic score or membership probability is introduced.
