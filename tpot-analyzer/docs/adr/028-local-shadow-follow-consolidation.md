# ADR 028: Additive consolidation of saved historical evidence

- Date: 2026-10-17
- Status: Approved local-consolidation direction; copied-batch workflow
- Related: ADR 025/026/027

## Decision and scope

Consolidate already-retained evidence in bounded batches before new acquisition
or ranking expansion. Reuse ADR 025's three-table sidecar and existing copied
import/rollback path. A caller supplies a copied graph and transaction; imports
are idempotent, preserve previous rows and raw stores, and report exclusions or
deferred aliases rather than treating them as absent evidence. No source fetching,
paid acquisition, automatic entity merge, tag mutation or outreach is introduced.

For numeric follow records, import exact numeric endpoints and qualify endpoint
profiles only from eligible independent observations or explicitly public saved
provider objects. Do not use Archive profiles as a fallback when that source is
unavailable. Preserve producer direction (including follower→followed for inbound
captures), raw table/primary-key pointers and original date strings. Stored rows
are not invented transport receipts; naive dates remain timezone-unspecified.
Never merge handle-only identities with numeric accounts by matching names.

Handle-only rows use separate unresolved-account nodes, historical profile
observations and directed follow edges. Their dossier section is separate from
numeric-account evidence; current-handle links may lead to a changed owner. A
handle-rooted search may traverse only imported historical follows, preserving
typed endpoints and capture metadata. Missing captured outgoing coverage is a
refusal, not zero; the corpus is a partial historical selection, not a complete
network.

Saved API post and typed-edge rows qualify only when exact source author/post
identity agrees and the saved API source is eligible. A public provider profile
may be required under the existing policy; hidden or unavailable Archive profiles
are not fallback evidence. Unknown targets remain exact numeric references, not
guessed handles. Thread imports attribute only outer posts to their exact embedded
author; quoted text is not recursively assigned to the quoting author. Structured
reply, quote and mention references retain separate types and source pointers;
missing IDs remain unresolved. Repeated captures preserve provenance while path
counts use distinct posts per typed pair.

Standalone saved API text may be imported only from explicitly supported saved
API sources, excluding Archive-origin and flat thread-context rows. Exact author
qualification and post-ID conflict checks still apply. Searchable fields are
allowlisted; raw fields remain private. Flat handles do not create numeric edges.

Publisher/page and provider observations retain their own types and exact source
qualification rather than being mislabeled as follows or posts. Historical search
may use explicitly imported independent profile fields, bio-link mentions and
cached-page claims, but never makes a same-name join, current identity, site
ownership or contact-route claim. URL recognition and contact clues remain
source-qualified and non-fetching as specified in ADR 029–033.

## Deterministic row batches and consumers

An explicit historical-row mode may select incident shadow rows in source-table
composite-key order with a bounded limit/offset. The domain excludes self-loops;
report that exclusion separately. Malformed selected identities, directions,
times or metadata refuse the copied transaction. Offset is tied to the exact
saved-source state, not an external crawl cursor. Report selected/qualified rows
and net-new observations separately; a no-new-observation batch is not adoptable.

Search and dossier consumers expose the channel, direction, capture basis,
source fields and partial coverage. An account with imported incident edges but
no selected-root scope may show a partial neighborhood with unknown total, not
an invented complete list. Incoming exploration reverses traversal, never the
stored edge. Paths do not establish friendship, agreement, expertise, current
identity, affiliation or membership probability.

Copied imports must preserve prior graph rows, snapshots, raw stores, tags/events
and rollback releases. Adoption remains a separate gated action after source and
synthetic review and consumer verification. No service/schema expansion or
automatic identity binding is implied.
