# ADR034: Exact saved channel lookup in private Review

Date:18 October2026. Status:approved local-consolidation consumer contract.
Extends ADR033/032/025.

## Decision and intent

Add an explicit exact email/profile-URL search mode to existing private Review.
Search existing catalogue mentions,page-listed emails,reviewed routes and saved
numeric-account profile→website links. Return separate saved account records and
source paths,not confirmed people,ownership,identity merges or contactability.
Do not change interest ranking or infer associations from domains,names or fuzzy
matches. Match literal values after trimming surrounding input whitespace only.
No fetching,outreach,paid calls,new schema,index,service or graph writes.

Send the value in an authenticated POST body,not a URL/access-log query string.
Use unchecked Archive access,excluding Archive-only evidence without any network
publication call. Retain independent local evidence and withhold hidden profile
labels. Historical unresolved handles/raw backups are outside this lookup scope.
Generic captured form actions and incomplete-check URLs are not positive channel
locators. Reviewed contact-form URLs remain eligible with their routing context.

## Consumer and limits

Qualify before presentation limits. A result beyond an account's ordinary preview
window must still surface. Show source families searched,missing/partial families,
source dates/pointers and catalogue binding. No match means no literal match in
these searched projections,not no person/contact or an exhaustive investigation.
Shared organisation addresses stay separate account records;source repetition is
not corroboration. Email text is inspectable,not a send/mailto control.

## Acceptance and proportionality

Test exact success,shared values,context,missing projection,refused source,invalid
input,auth,cancellation/retry and matches beyond preview limits using isolated
synthetic state. Independently review code/synthetic tests,run combined acceptance,
then verify fixed real local controls in actual private Review. Preserve raw/tag/
graph hashes and rollback. This is a code-only consumer slice;no data adoption.
Remaining source consolidation and explicit identity review stay on the roadmap.

## Amendment: bounded lookup ranking, 19 October 2026 00:36 IST

The general relationship CTE deduplicates every qualified path/contact claim before
the old lookup filters its value. Measured ranking dominates exact lookup latency.
For lookup only, filter complete matching claim partitions inside observations,
before window ranking. Subject/predicate/object keys are partition-constant; route
address is already in CONTACT_IDENTITY. Retain all matching observations, grouping
qualifiers/counts/date extrema and representative ordering. Keep publication and
cached-parent eligibility before ranking, and source availability global as before.

Use a fixed SQL builder/default EDGES for existing dossier/path/summary consumers;
only the lookup variant adds fixed SQL clauses with parameterized values. No generic
string substitution, index/schema/cache/service or DTO/status changes. Real nonempty
profile, email-route and form controls must match every old returned field; isolated
tests cover repeated/changed claims, shared values and hidden source refusal. Raw,
tags, active graph and rollback stay untouched. This is a read-only query repair.
