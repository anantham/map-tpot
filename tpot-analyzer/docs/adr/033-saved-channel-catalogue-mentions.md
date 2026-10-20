# ADR033: Saved channel catalogue mentions,not verified identity or contact routes

Date18 October2026. Status:implementation of approved local consolidation.
Builds on ADR025 and ADR032.

## Decision

Retain the existing private channel catalogue unchanged. Project only email,
LinkedIn,Instagram and the explicitly supported other public-URL lists. These are
literal exported research mentions,not rechecked sites,current identities,owned
addresses,deliverable mailboxes or willingness to be contacted. Never promote them
to same_person or has_contact_route. Source platform labels may be wrong;preserve
them as labels rather than correcting them by guesswork.

Bind a catalogue row only through a unique handle in an explicitly selected frozen
profile capture already retained in the graph. Require its exact profile-observation
witness. This records the historical dataset association,not a current-handle match.
Reject ambiguous,missing or conflicting witnesses rather than silently rebind a row.

Append account→contact_catalog_entry via contact_catalog_observation and entry→
email_address/web_resource via research_mentions_channel. Each edge retains the
original snapshot and JSON pointer. Keep empty entry observations:an empty export
under the old name filter is unknown,not a completed contact-negative investigation.
Catalogue generation text is approximate;retain it literally and do not assign an
exact observation or verification time. Do not use filesystem times.

## Read boundary and consumer

Queryable attributes and Review DTOs exclude Beeper,shared-group/private lookups,
drafts,outreach status and event-fit fields. The original full file remains in the
private source store and is not exposed by the API. Clean code/synthetic review
packets never include the real file. Existing curator auth remains unchanged.

Attach bounded mention metadata after search qualification/ranking/limit,for the
requested exact numeric IDs. Do not make contact values a ranking or membership
signal. Group repeated literal values while retaining source categories/pointers.
Show frozen binding,source pointers,approximate time,legacy-filter/ownership caveats
and explicit missing projection. No mailto,send,form-submit or acquisition controls.

## Acceptance and consequences

Reuse the existing exclusive copied-batch/adoption path. Preserve raw sources,
tags,all prior rows and previous graph/package/index. Require nonempty real mention
additions;zero exports cannot manufacture readiness. Test success/refusal/privacy/
empty/partial/repeat/limit/auth cases and actual Review. Independently review source
and synthetic fixtures,then reconcile every real addition to its original source.
No new table,service,paid fetch,outreach or public deployment. This makes existing
research inspectable;it does not complete identity resolution or contact validation.
