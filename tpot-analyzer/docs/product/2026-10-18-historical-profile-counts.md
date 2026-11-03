# Historical profile counts in Review

Intent18 October2026. Owner:Codex,canonical clean-main. Implements the approved
local source consolidation under ADR028/030,not a new graph schema or ranker.

## Journey and source meaning

Search a historical account and see its following/follower counts when saved in
that exact profile capture. Open the same snapshot/date/source disclosure. Unknown
is not zero;these are reported counts,not imported edges,current values,verified
identity,selectivity confidence or community membership.

Append enriched observations using the existing shadow_profile_observation
predicate on an exclusive copy. Retain original observations and snapshots.
Bind numeric fields to the same source row,alias,channel and capture date;never
borrow from another capture or an Archive-sync row. A newer profile with missing
counts stays unknown. Future imports project the same optional fields.

Accept only nonnegative exact integers within JavaScript's safe range. Zero is
valid;null/absent is unknown. Reject booleans,strings,floats,negative/unsafe values
instead of coercing. No inference from observed graph degree. Existing bio links,
paths,counts of unique handles and all other predicates remain unchanged.

## Acceptance

Public import/search behavior and UI RED tests first. Check known/zero/unknown,
malformed fields,source identity/date/hash/channel,unchanged originals,repeat,
retained prior rows and copied integrity. Review source/synthetic code independently,
then adopt only a positive net batch through existing graph-only rollback. Inspect
known and unknown real accounts in Review,including source date and bio links.
No paid fetching,outreach,tag writes or identity resolution. Ranking is unchanged.

## Delivery checkpoint

Privately served18 October2026,18:29 IST after code/synthetic review,combined
acceptance and all1356 additions compared to their original cache rows. Known,
zero and unknown are tested;real known/unknown sources opened in Review. These
are enriched projections of existing captures,not new observations of the world.

Selection retains the existing reader's most-recently-inserted allowed observation,
not necessarily the greatest source timestamp. No new temporal precedence policy
is introduced. Count coverage is sparse;missing values must not become zero or
estimated current follows. Neighborhood-preview selection consistency and using
counts in a ranker remain separate follow-ups.
