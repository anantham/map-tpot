# ADR029: Publisher-declared website link paths

Date:18 October2026. Status: bounded implementation of approved local sidecar
consolidation; independent review and private activation pending. Owner:Codex,
canonical clean-main/codex/curator-review-shell. Related:ADR025,ADR028.

## Issue and decision

Cached public pages already retain qualified rel=me and JSON-LD page-subject
sameAs/worksFor/affiliation/alumniOf observations. These clues should be queryable
as source-backed paths, without converting them into confirmed person identities,
current jobs or checked contact routes.

Reuse the three-table graph and page_links_to predicate: the page declares a URL.
Add claimKind for rel_me,sameAs,worksFor,affiliation or alumniOf. Retain the
publisher's page-subject name, JSON-LD block/field pointer, referenced organisation
name and existing cache/association evidence. Do not create same_person/works_at
edges, new person nodes, invented employer URLs or automatic account joins.
Name-only organisation observations remain searchable/visible page metadata.

The account→website association is evidence of a link, not proof that the site's
described Person owns the account. Preserve that uncertainty in storage and UI.
JSON-LD paths refer to the retained derived extraction and original script/field;
no website script executes and no network request occurs during projection.

## Boundaries and alternatives

Only already-visible exact-account cached observations qualify. New edges copy
the parent association's source-policy fields and reference that exact parent;
reader withdrawal checks apply to both. Independent sources remain usable while
Archive access is unavailable. No source visibility override or private disclosure.

Keep ordinary links and marked claims distinct even when URLs match. Different
claim kinds/person contexts must not collapse or corroborate one another. Show
unchanged marked claims once across captures, with stored-observation counts;
changed subject/organisation qualifications remain distinct. Order
declared claims before navigation in the bounded preview; truncation remains
explicit. Expose claim meaning and original source fields, not a confidence score.

Alternative:keep nested metadata only. Simpler, but downstream traversal loses
why a link was present. Alternative:verified person/employer graph now. Rejected:
the saved markup is insufficient evidence for identity/current employment.
Qualifier-bearing existing links are the smallest faithful implementation.

## Acceptance and consequences

Copied append-only import must retain all prior rows, raw sources, tags and rollback.
Verify repeat import, exact source fields/dates, wrong account, missing URL,
hidden parent/withdrawal, same URL with distinct meanings, shared-page subject
context and zero reviewed-contact or identity promotion. Independent code/synthetic
review and actual Review source opening precede private graph adoption.

This improves traversable evidence, not identity resolution. Reciprocal links,
stable platform IDs, organisation normalization, employment dates, contactability
and semantic retrieval remain future work. No paid fetching or outreach authorized.

## Private serving checkpoint,18 October2026,14:08 IST

Independent review/closure, source-shaped checks,441 backend/13 combined checks,
build and actual Review source opening pass.20 accounts/21 saved page observations
yield70 marked links(34 rel_me,34 sameAs,2 worksFor),27 URL nodes, no new snapshots.
Graph-only7f22o_c4 retains mnhrlba0/package/index and93 tags/events. Actual employer
path shows original page subject/date/fields and explicitly unknown current status.
Identical claims coalesce across captures; changed subject/meaning remains separate.
Full identity resolution, employment dates and broader coverage are not delivered.
