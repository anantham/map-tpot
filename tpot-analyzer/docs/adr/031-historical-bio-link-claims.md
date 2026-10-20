# ADR031: Source-backed historical bio-link mentions

Date:18 October2026. Status:approved local-consolidation contract.
Related:ADR025,ADR028,ADR030. No new schema,service or identity semantics.

## Issue and decision

Historical profiles retain website-like text inside bios, often without a scheme.
The existing writer can already represent URL mentions as profile_links_to edges,
but independent historical imports did not call it and the card had no consumer.

Reuse that relation,web_resource nodes,source snapshots and copied-batch adoption.
Opt in to a pinned offline URL recognizer for this source,including bare domains;
the existing explicit-HTTP behavior of other importers remains unchanged. Store
the literal mention,recognizer version,scheme-assumption flag and original bio
field/capture time/channel. HTTPS is added for a bare or protocol-relative mention,
explicitly an assumption,not a successful request or current-site verification.

Only independent historical profile channels qualify. Do not bind a shadow handle
to a numeric account or person. No same_person,works_at or has_contact_route is
created. Mentioning a site does not establish ownership,authorship,endorsement or
contactability. Website-like filenames and ambiguous text may remain candidates;
preserve the original wording instead of treating syntax recognition as truth.

Reject non-web schemes,credentials,literal non-global IPs,local hostnames and X
self-links. This is offline syntax/literal-address filtering,not DNS validation.
No destination is fetched,resolved or opened automatically. Existing Archive
visibility,tag access and numeric-profile rules remain unchanged.

## Consumer and preservation

Historical search returns typed link claims only from the exact displayed profile
observation:subject,snapshot,source field and date must match. An older bio cannot
lend its links to a newer displayed capture. Retained old claims remain in the
graph. Link literal,normalization qualifiers and target must agree;damaged claims
refuse instead of producing a plausible external link.

The card shows a safe HTTP(S) anchor,its saved text,an assumed-HTTPS notice when
needed and a separate source disclosure. Unsafe response URLs stay non-clickable
text. No-current-identity and historical-coverage caveats remain;tags stay locked
without an existing durable account identity. Absence of projected links is not
a completed contact check.

Backfill only on an exclusive graph copy. Retain all previous rows and snapshots,
check repeat import/FKs/integrity and source identities;adopt only positive net
observations after independent source/synthetic review and actual UI inspection.
Preserve raw stores,tags,prior graph,package/post index and rollback. Newly imported
historical profiles use the same writer so the gap does not immediately recur.

## Alternatives and remaining work

HTTP-only recovery misses scheme-free captured bios. Turning every mention into
verified identity/contact edges overstates the evidence. Read-time-only extraction
does not consolidate the typed graph. Qualified existing relations are the
smallest implementation that serves both evidence traversal and the UI.

Reciprocal identity confirmation,current-site checks,broader contact clues and
semantic ranking remain future work. No paid fetching or outreach is authorized.

## Recognition compatibility

Keep the established explicit-HTTP scanner behavior, including URLs adjacent to
prose, and use the pinned offline recognizer for scheme-free mentions. Preserve
the literal source token and its original bio pointer; normalization metadata
must not rewrite the captured bio or imply that an assumed HTTPS destination was
requested or verified.

## Amendment: retained provider bio destinations,19 October2026,01:32 IST

Saved public-provider profiles also retain structured entities.description.urls
with literal short and expanded destinations. Project both safe HTTP(S) fields
as profile_links_to with their exact original pointers. Do not resolve them again,
rewrite the bio, or turn a provider-expanded value into verified ownership,
employment or a reviewed contact route. Future provider/thread imports share the
same qualified writer. Existing website/entity URL and bio-text fields keep
their old attributes, pointers and timestamps.

The offline backfill may select already-retained provider-row snapshots only after
checking content hash, captured privacy, exact account/profile anchor, raw-row
agreement and original projected attributes. Other snapshot envelopes are outside
that backfill. Reuse the copied-graph pipeline and preserve prior rows, snapshots,
source bytes, tags and rollback. Do not read caches, request publication metadata,
or create source snapshots/profiles. A zero-addition run is not a delivered batch.

Exact private channel lookup displays matched URL/source field,observed and
captured dates and the historical-provider caveat while opening the exact account
dossier. An isolated profile URL is not yet a dossier website path; this slice
does not imply that every saved URL has cached page content or contactability.
