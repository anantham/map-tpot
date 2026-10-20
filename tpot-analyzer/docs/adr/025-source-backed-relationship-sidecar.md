# ADR 025: Source-backed relationship sidecar

- Status: Approved direction; additive local sidecar
- Date: 2026-10-15
- Group: Data and discovery

## Issue and decision

Accounts, websites, public work, organisations and contact routes are distinct
entities. A link is evidence that a source connected two records, not proof of
ownership. Shared inboxes do not merge accounts; a page describing a person does
not verify that the linked account belongs to them.

Use an additive SQLite sidecar with three append-only concepts:

| Record | Meaning |
| --- | --- |
| Entity | Typed account, unresolved account, web resource or contact route |
| Evidence snapshot | Exact source bytes, digest, source reference and capture time |
| Relation | Directed predicate, endpoints, snapshot/pointer, observed time, reported status and qualifiers |

Identical source bytes are idempotent; changed observations append and preserve
history. History does not establish which claim is true or imply that a missing
relation ended. Keep original stores and curator judgments in their existing
systems; derive algorithm-specific account matrices only from selected relations.

## Projection and supported semantics

The initial projection covers profile website mentions, saved website
observations, extracted outbound links and typed contact-route claims. Preserve
actual source fields and decoded-item pointers, dates, qualifiers and routing
instructions. A path can traverse account → website → linked page or account →
route → reported source page; it must retain every predicate and source.

The sidecar has subsequently been extended through source-specific adapters for
saved work associations, contact checks, directed follows, typed post references,
publisher-declared page links, historical bio links, saved-page clues, channel
catalogue mentions and research citations. These remain typed, source-qualified
observations; they do not verify authorship, current employment, identity,
contactability, agreement, expertise or membership. Missing dates stay unknown.
Repeated evidence is not independent corroboration. No matching URL, name, inbox
or handle may merge account identities.

Retained snapshots are custody, not current-source eligibility. Each reader must
apply the source's visibility and privacy policy, expose only account-scoped
curator-filtered projections and keep raw snapshots private. Independent evidence
may remain eligible when an Archive-backed layer is hidden; it must not reveal a
hidden profile label or use that layer as a fallback. No psychological inference,
outreach or paid acquisition follows from this decision.

## Alternatives and limits

Keeping JSON/CSV requires each consumer to rebuild joins and route distinctions.
Extending account-only sparse matrices mixes non-account nodes and loses source
records. A graph service adds operational burden before a proven need. The local
sidecar is additive and queryable, but requires typed readers and derived views;
it is not a universal graph importer or replacement for existing stores.

Full identity resolution, source coverage, temporal co-occurrence, current-state
interpretation and richer employment semantics remain separate work. Consumers
must distinguish a source-backed mention from verification and must report
partial or unavailable evidence rather than manufacturing a zero.

## Related decisions

ADR 019 preserves source versions; ADR 020 binds derived graph artifacts; ADR 021
separates membership meanings; ADR 023 defines the shared Review/Map workspace.
This decision adds neither a new labeling substrate nor a replacement for those
contracts.
