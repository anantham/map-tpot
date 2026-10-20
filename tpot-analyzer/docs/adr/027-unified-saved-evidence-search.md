# ADR 027: Unified saved-evidence search

- Status: Approved user journey; source-specific channels remain independently gated
- Date: 2026-10-16
- Group: Retrieval and presentation; extends ADR 025/026

## Decision and rationale

Make All saved evidence the default Review search. All words may be supported
across the same exact numeric account's admitted profile, saved work, cached page
and indexed posts. Preserve profile/page and post-only controls. Do not join
same-handle records or describe an account record as a verified person.

Collect per-word candidates from complete existing sources, combine by exact
account ID, require all words and only then truncate. Combining only the first
page of each earlier search would miss split-source matches and lower-page hits.
Reuse existing readers, FTS, source gates, post context and exact-account dossier.
Publication metadata checks must not include the query, tags or local profiles.

## Evidence, ordering and limits

Cards show which words matched which dated post or saved passage, with source
link and original row/snapshot reference. Work association is not verified
authorship; cached page and anchor text may describe third parties or boilerplate.
Replies, quotes and reposts retain their typed context, not inferred agreement.
Opening a dossier rechecks source access and exact account identity.

Missing or hidden channels have explicit partial/unavailable status. If no source
can be searched, total is unknown, not zero. A selected network scope never
silently falls back to unscoped retrieval. Independent historical sources may
remain available during Archive refusal, without implying a currently verified
profile.

Profile/work/page fragments use case-insensitive literal matching, with one
deliberate exception: normalized ASCII alphanumeric terms of 1–3 characters use
whole-word matching, treating punctuation and underscores as separators. Simple
plurals are accepted for 2–3-letter terms not ending in “s”. Other terms remain
literal fragments. Full handles and four-or-more-character partial names retain
lookup; short partial-name recall is deliberately reduced. Candidate filtering
and explanations use the same rule and preserve original Unicode offsets. Posts
retain their existing FTS word matching. This is lexical retrieval, not semantic
relevance, interest or competence.

An optional historical channel uses its own exact saved-profile reader, not a
handle join. Every term must match one historical handle; result counts, sources
and status remain separate from numeric accounts. A numeric-account network
scope must not silently return unscoped historical results. A handle-rooted
captured walk is an explicit separate mode. Missing historical data or reader
failure is not zero; Archive policy failure may hide only its own evidence.

Within existing exact-handle and full-display-name tiers, distinct query words
in the selected visible profile bio may precede combined profile/work/page
support; then use alphabetical handle and exact-ID ties. A bio is self-description,
not verified expertise or current truth. Linked-page text is not direct bio support.
No candidate is filtered by this ordering.

Expose additive per-word coverage separately for each result domain, counting
distinct qualified records before all-word intersection and display limits.
Unavailable domains carry unknown counts; zero is distinct from unknown. Never
combine domains into people or expose hidden-source support. State that every
term must match the same account/handle for a result.

The historical channel may show all-word support, source paths and existing
typed evidence without turning retrieval order into a score. A proposed BM25
post-ranking experiment was rejected after exceeding the existing time budget
and surfacing an explicit NOT IN example. The bounded co-occurrence comparison
that followed is a research proposal only, not a serving decision. No continued
parameter search or aggregate known-label regression is authorized here.

## Alternatives and acceptance

A unified materialized index could harmonize tokenization but adds refresh and
source-policy lifecycle work. Retain existing stores/readers and measure first.
Semantic reranking, source-role classification and cross-platform resolution are
separate decisions. Acceptance covers split-source matches, exact identity,
complete candidate pools before limits, withdrawal/refusal, partial sources,
scope, auth/cancellation, safe links and query→evidence→dossier behavior. No paid
acquisition, source rebuild, judgment writes or outreach is authorized.
