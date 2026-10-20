# ADR029: Publisher-declared website link paths

Date:18 October2026. Status: approved bounded implementation direction.
Related:ADR025,ADR028.

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
