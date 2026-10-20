# Historical profile counts in Review

## Journey and source meaning

Search a historical account and show following/follower counts only when saved in
that exact profile capture. Open the same snapshot/date/source disclosure.
Unknown is not zero. These are reported historical counts, not imported edges,
current values, verified identity, selectivity confidence or community membership.

Append enriched observations using the existing `shadow_profile_observation`
predicate on an exclusive copy and retain prior observations/snapshots. Bind
numeric fields to the same source row, alias, channel and capture date; never
borrow from another capture or Archive-sync row. A newer profile with missing
counts stays unknown. Future imports use the same optional fields.

Accept only nonnegative exact integers in JavaScript's safe range. Zero is valid;
null/absent is unknown. Reject booleans, strings, floats, negative or unsafe
values rather than coercing them. Do not infer counts from observed graph degree.
Existing bio links, paths and other predicates remain unchanged.

## Boundaries and acceptance

Check known/zero/unknown values, malformed fields, source identity/date/hash/
channel, unchanged originals, repeat imports, prior-row retention and copied
integrity. Independently review source and synthetic behavior, then adopt only a
positive net batch through existing graph-only rollback. Inspect known and
unknown source disclosures in Review. No paid fetching, outreach, tag writes,
identity resolution or ranking change is implied.

The reader retains its existing most-recently-inserted allowed observation; this
does not introduce a timestamp precedence policy. Coverage is sparse: missing
values must not become zero or estimated current follows. Neighborhood-preview
consistency and use of counts in a ranker remain separate decisions.
