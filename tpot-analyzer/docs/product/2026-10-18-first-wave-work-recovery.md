# Recover the original20 saved public-work cards

18 October2026. Owner:Codex/root,canonical clean-main,codex/curator-review-shell.
Implements the already-approved ADR025 saved-profile/work extension;no new schema.

Read-only reconciliation found264 earlier research files. Their101 differing work
projections all refer to account/URL pairs already represented;many simply omit a
normalized evidence alias. Do not import them as new works. Separately,the first
wave's cards.json contains20 exact account/work URLs absent from the graph. The
original importer selected batch-*.json and therefore missed this different name.

Add explicit repeatable work-source selection to the existing copied saved-capture
verification CLI. Require the exact already-retained original profile capture,
numeric card ID and matching captured handle. Append only research_associates_with
observations/web resources/raw snapshots,not profiles,identity claims or contacts.
Keep original byte-exact sources and pointers,unknown observation dates,and literal
work dates. Retain card-level caveats with their own source pointer and the explicit
evidence_url when it differs from the work URL. Never mistake a homepage account of
a project for inspected project-page text. Do not project event fit,drafts,outreach,
availability,travel or willingness fields into work attributes or search ranking.

The existing private Review search and work dossier are the consumer. Show matching
passages,source URL/source pointer and qualifications. When evidence_url differs
from the work URL,offer a distinct safe Inspected source link in search and dossier.
Reuse reviewed local-copy,
repeat/integrity/prior-row/adoption/rollback machinery. Reject false-ready/no-new
imports. Source validation/refusal/auth and a real before/after work search plus
account opening are acceptance checks. Keep raw stores,tags,index/package and the
old graph intact. No paid fetch,outreach,push or public deployment.
