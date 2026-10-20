# ADR032: Saved page contact clues,not inferred personal routes

Date18 October2026. Status:implementation of approved local consolidation.
Extends ADR025 without a schema/service change.

## Decision and meaning

The existing page parser retains literal email and message-form clues. Project
them into the same sidecar as page_lists_email and page_has_message_form. The
subject is a saved web resource,not a person. Email-address nodes preserve literal
spelling;form nodes identify the captured form,not a tested submission endpoint.
Reuse original snapshot,derived-array JSON pointer,capture date,observer/cache
observation and exact account→website association. No re-fetch or reclassification.

An organisation inbox or quoted third-party address stays a clue with its context.
Do not require the email to contain a person's name. Do not infer personal/work
ownership,deliverability,current validity or willingness to receive outreach.
Message-field markup may be a comment form;do not call it a tested contact form,
invoke its action,submit it or automatically create has_contact_route.

## Source and read boundaries

Reuse the existing qualified website observations,including parent visibility.
Expose all admitted bindings to the adapter without changing the default page
view's dedup contract. Backfill independent saved pages offline;Archive-only
source eligibility is not invented. Future page imports use the same clue writer.

The reader must bind each clue to the exact admitted page/observer/source and
derived item. Shared pages or inboxes never merge accounts. Repeated associations
to the same captured clue are not independent confirmations. Preserve different
literal kinds/context/qualifiers;show bounded source occurrences with counts and
truncation explicit. Raw snapshot/gzip and unrelated page fields remain private.

Attach clues only after search candidate qualification and result limits,so
they do not change word matching,ranking,network scopes or create account identities.
Return only the requested exact IDs;missing/partial projection is not no contact
method. Reviewed route summaries remain separate. Use native disclosure and safe
source-page links/plain address/form text in Review;no send/mailto/action control.

## Preservation and acceptance

Use existing exclusive copied-batch append/repeat/prior-row/FK/integrity checks.
Keep raw sources,tags,all previous graph rows and managed graph/package/index
rollback. No new table,service,paid call,fetch or outreach. Independently review
source/synthetic code;compare every added clue to retained source fields and
inspect real Review clues/context/date/source before graph-only private adoption
is counted delivered. This is affordance discovery,not a complete contact audit.

## Reprocessing retained cached pages

Re-extract exact retained cached HTML with the current parser on a copied graph.
Keep old observations/raw bytes and original capture dates;append new derived
snapshots and source pointers rather than rewriting historical evidence. Reuse
the existing source-qualified cached-page and publisher-link adapters with explicit
offline publication-unchecked access,which excludes Archive-only associations.
Do not require or synthesize new provider profiles merely to upgrade an existing
page. Preserve the same consumer and contact/identity meaning; use the existing
copied-graph rollback path.
