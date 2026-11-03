# ADR 027 Unified saved-evidence search

- Status: approved user journey, implementation in progress,16 October2026
- Owner: Codex, canonical clean-main/codex/curator-review-shell
- Group: retrieval/presentation; extends ADR025/026, no schema/index change

## Decision and rationale

Make All saved evidence the default Review search. All words may be supported
across the same exact numeric X account's visible profile, saved work, cached
page and indexed posts. Preserve the older profile/page and post-only controls.
Do not equate account records with verified people or merge matching handles.

Collect per-word candidates from complete existing sources, combine by account
ID, require all words, and only then truncate. Merging the first25 results of
the older all-word searches would miss split-source matches and lower-page hits.
Reuse the existing FTS, saved reader, source gates, post context and dossier.
One fresh fixed-URL publication check qualifies both Archive-backed channels.
No query, tag or local profile is sent with that metadata check.

## Evidence and limits

Each account card shows which words matched each dated post or saved passage,
its source link and original row/snapshot reference. Work association is not
verified authorship; page/anchor text can include third parties or boilerplate.
Replies, quotes and reposts retain their typed context, not inferred agreement.
Opening a dossier rechecks source access and exact account identity.

Missing/hidden channels produce explicit partial status. If neither can be
searched, total is unknown, not zero. A selected follow scope never silently
falls back to unscoped retrieval. Independent historical sources can survive an
Archive refusal, without being described as currently verified profiles.

Profile/work/page fragments retain literal case-insensitive substring matching;
posts retain FTS word matching. Terms can occur in different passages. This is
lexical retrieval, not semantic relevance, current interest or competence.
Order is exact handle first, then alphabetical account/ID, not confidence.
Not every saved profile has indexed posts; coverage remains visible.

## Alternatives and acceptance

A single new materialized index could harmonize tokenization, but adds refresh
and source-policy lifecycle work before this consumer is demonstrated. Retain
existing indexes and measure query time first. Semantic reranking, source-role
classification and cross-platform person resolution remain separate work.

Acceptance covers split-source positives, no cross-account/handle joining,
complete candidate pools before limiting, exact IDs, source withdrawal/retry,
missing stores/empty data, directed scope/refusal, auth/cancellation, safe links,
source retention, independent code/synthetic review and real query→evidence→dossier.
No paid acquisition, source rebuild, judgment writes or outreach is authorized.

## Implemented acceptance checkpoint,16 October2026

The composed reader, curator endpoint and default UI are implemented. Complete
source-shaped tests cover split-source terms and a match beyond50 saved candidates.
Membership probes use the existing indexed account+word intersection without
aggregating all matching post rows. Real fixed queries complete in1.56–4.86s;
systems thinking734 accounts. Literal matches are not quality/competence estimates.
347 backend/13 combined checks, build/lint and independent code/closure pass.
Private serving and actual source opening remain the next acceptance checkpoint.

## Privately served,16 October2026,00:29 IST

f7497c1 serves the new default search on the existing local Review runtime. Actual
systems thinking query734/show25, mixed page/post source disclosures and exact
dossier opening are verified; cached snapshot agrees. Source files/index/archive
and93 judgments remain unchanged. Health200/auth401/console errors0. Physical
layout acceptance remains pending because the host pane reports0×0. No paid
fetching, source rebuild, push or public deployment. The broader goal stays active.

## Bounded short-word amendment,18 October2026

Supersedes the saved-fragment substring rule above only for normalized ASCII
alphanumeric terms of1–3 characters: match whole words, treating underscores and
punctuation as separators. Simple plurals are included for2–3-letter terms not
ending s. Other terms remain casefolded literal fragments. Full handles and4+
partial names retain lookup; short partial-name recall is deliberately traded
away and explained before search. Archive FTS remains its existing word index.

Candidate filtering and explanations share the same rule and original Unicode
source offsets. Source gates, exact-account intersection, graph scopes and
ordering bonuses remain; no term-count/model score becomes membership confidence.
Stored corrections are still evidence, not automatic human judgments. No graph,
schema, index, tag, source or acquisition changes are required.

## Short-query serving checkpoint,18 October2026,12:21 IST

418 backend/13 combined checks, scoped UI/lint/build and independent source/
synthetic review pass. Fixed same-graph comparison reduces incidental AI/EA/ML/
LLM hits while long-query controls/full lookup remain. Actual Review distinguishes
IvanVendrov's AI-discourse post from an incidental certainly match, while the
original remains retrievable by certainly. Source record/date opened; health200,
auth401/browser errors empty. Graph/tag hashes and93 assignments/events unchanged.
EA remains polysemous and no result count is a community-size or fit estimate.
No paid fetching/outreach/push/public deploy. Full-post context and semantic/source-
role relevance remain next; broader rich-graph goal remains active.

## Retained-post text amendment and checkpoint,18 October2026,12:36 IST

Existing private search payloads add storedText only to already-admitted API post
matches and eligible Archive supporting posts. Keep excerpts for scanning. Both
renderers reuse a native disclosure displaying the exact retained field as text,
with line breaks, reported post date and capture time where supplied. Missing
text is explicit; never label a snippet or a potentially truncated source capture
as the complete original tweet. No media loading/HTML rendering, additional fetch,
endpoint, schema, source write, graph adoption or tag edit is introduced.

The eager additive field avoids a lazy-fetch API/state machine: existing readers
already select it and requests remain bounded by accounts/supporting terms. Current
API corpus max6510/mean162.9 characters per observation; larger future captures may
justify another approach only with measured payload/consumer need.

61 focused backend/22 UI,425 backend/13 combined checks, scoped lint/build and
independent code/synthetic review pass. Full-repo lint still fails on unchanged
legacy components, not this slice. Live independent API post opens272 retained
characters versus123-char excerpt, exact source/DOM hash agrees. Archive-index
success/refusal remains synthetic while its live source cannot be qualified.
Health200/auth401/browser errors empty; graph/tag hashes and93 assignments/events
unchanged. Local private serving, no push, paid acquisition or outreach. Broader
consolidation and source-role/contextual relevance remain active, not completed.

## Historical channel amendment,18 October2026

Extend the approved one-query journey to imported historical profiles while
preserving the exact-account intersection above. The existing numeric fields,
total,status,sources and result order remain numeric-channel contracts. Add a
separate historical DTO using the existing shadow reader,not a handle join.
No word can be supplied by one domain to qualify the other. Do not deduplicate
same-handle records or sum their counts into unique accounts or people.

Global searches run both channels with independent bounded result windows.
Historical fragments keep their literal query and visible whole-word/partial
tiers;this is not the FTS tokenization rule or semantic-fit evidence. Missing
historical data and reader failure remain explicit,not a manufactured zero.
Archive policy failure can hide its own evidence without hiding independent
historical matches. Existing current-publication checks and source gates remain.

A selected numeric-account network scope must not silently return unscoped
historical matches. Mark that channel not searched in this scope;use the existing
historical mode for a handle-rooted captured walk. From a historical result,
Explore changes to that mode with the query retained and the chosen handle set;
the next search is deliberate. No account-ID or human judgment is inferred.

Two native pressed-state buttons expose result groups and their separate counts.
Prefer historical results when numeric results are empty and historical hits
exist;otherwise keep the existing numeric default. The same historical cards
retain dates,sources,counts,bio links and unknown identity. Legacy responses stay
usable. Check both success and source/scope refusal,cancellation/retry,identity
separation and real query→evidence→captured-path flow before private serving.
No schema,index,graph,raw source,tag,acquisition or outreach change is required.

## Historical channel privately served,18 October2026,18:51 IST

558 backend/13 combined checks,42 focused backend/16 UI,lint/build and independent
source/synthetic review pass. Fixed same-graph offline-Archive comparisons retain
the numeric contract and exactly reproduce the historical reader;16 preservation/
consumer checks pass. New control queries take1.91–2.47s versus0.92–1.27s before.
Result counts are per-domain and cannot be added into unique accounts or people.

Actual default query shows both groups while post source is unavailable. Historical
snapshot/count/date opens;Explore selects the explicit handle-rooted mode,then a
deliberate query opens both original directed sources along a captured two-hop
path. Current graph/package/index,raw sources,93 assignments/events and rollback
remain unchanged. Private code-only serving,no paid acquisition/outreach/push or
public deployment. This delivers access/composition,not calibrated discovery fit,
verified identity,semantic overlap or full project completion.

## Direct-bio ordering amendment, 19 October 2026

Within the existing exact-handle and full-display-name tiers, prioritize distinct
query words found in the selected visible profile bio, then retain combined
profile/work/page word support and alphabetical/exact-ID ties. Match the full
already-admitted bio using the existing query-word rules, not a bounded set of
displayed excerpts. Repeated words and observations add no weight.

Expose bioWords and a plain ordering explanation. A bio is self-description, not
verified expertise, current truth, social affiliation or membership confidence.
Linked pages may describe other people; they remain useful leads but are not
equivalent to direct bio support. No candidate is filtered out by this amendment.

Candidate matching/intersection, source gates, exact network scopes, contact
semantics and all source fields remain unchanged. No schema, index, model,
graph import, source/tag mutation, paid fetching or outreach is introduced.
Acceptance compares fixed-case counts and complete small-case evidence against
the committed baseline, checks hidden-source and exact-identity priority through
public synthetic search, and verifies the actual private result order/source.

Privately verified19 October11:01: explicit two-word bio moves third→first with
the same four candidates and original evidence. Fixed query counts/scopes remain;
703 backend/frontend/all13 checks and independent source/synthetic review pass.
Graph/raw/tag hashes and93assignments/events preserved. This repairs one observed
ordering failure, not calibrated discovery quality or the broader project goal.

## Narrow source-reading amendment,19 October2026

At the existing1180px single-column breakpoint,the saved-results list uses normal
page flow instead of the desktop40vh inner scroll cap. Larger panes retain the
bounded list. No retrieval,source,auth,identity,ranking or tag behavior changes.
Physical319px evidence:801px result fits its801px container;expanded sources fit
1276/1276,without horizontal overflow.1180/1181/1280boundary checks,existing combined
acceptance/build and independent code/synthetic review pass. This is source
readability acceptance,not evidence of discovery quality.

## Per-word support amendment,19 October2026

Report additive termCoverage within each existing result domain. Numeric entries
contain term/matchingAccounts;historical entries contain term/matchingHandles.
Counts are distinct qualified records matching that word in the selected scope,
before all-word intersection and display limits. Unavailable domains keep each
term with a null count. Do not combine domains into people or expose hidden
source support. Repeated observations do not multiply a record's support.

This uses the reader's existing admitted matches,without another source scan,
query,store,index,identity merge or score. Existing result matching,ordering,
sources and paths stay unchanged. Render zero separately from Unknown and state
that all terms must match the same account/handle for a result. Explain literal
wording without automatically substituting related words. Edits clear diagnostics
with the old result. Private source parity and actual zero/overlap/source flow
are acceptance,not proof of semantic relevance or membership calibration.

## Best-passage ranking experiment,20 October2026

The operator requests improved search ordering, testing against existing tags and
visible reasons. Preserve exact identity, visible-bio and saved-text coverage
tiers. Replace the final alphabetical-only post tie with the strongest eligible
Archive passage's native FTS5 BM25 rank, then retain alphabetical/exact-ID ties.
Rank the full qualifying pool before limiting. BM25 adjusts word rarity, frequency
and passage length; it is not an interest, competence or membership probability.
Use one best passage rather than summing over post volume. More writing can still
provide more opportunities for a good passage; this bias is not eliminated.
Repeated posts also affect corpus-wide word frequencies used by native BM25;
the claim is no summed per-author volume bonus, not invariance to corpus changes.
After the complete candidate set qualifies, skip scoring strictly lower tiers
that cannot enter the display window; score the entire cutoff tier, including
accounts beyond its alphabetical first page. Keep the existing query-time budget.

Show the exact ranking passage with its supported words, date, typed context,
post link and original row/checksum, alongside the existing per-word supports.
The ranking passage need not contain all query words; qualification still requires
all words across the same exact account. Reposts/criticism remain possible matches.
Source refusal cannot contribute hidden text or ranking. No model, paid call,
index rebuild, tag input, schema change or personal-identity inference is added.

Before serving, compare frozen tag-name queries for tags with at least three IN
examples against the prior algorithm. Only replace hyphens with spaces; no tuned
synonyms. Report known-IN recovery at10/25 and explicit-NOT-IN exposure, source
coverage and per-tag changes. Unjudged is unknown; do not report precision. This
small retrospective proxy is not a sealed or independent holdout. Do not activate
an aggregate known-label regression; report the negative result and keep baseline.

### BM25 rejected; bounded co-occurrence comparison,20 October2026

The BM25 experiment above is not adopted. Real queries exceeded the unchanged
15-second budget; tier pruning still timed out in supporting evidence and exposed
an explicit NOT IN example. Preserve those negative results; no timeout increase.

Compare one materially different replacement: within unchanged identity/bio/
saved-text tiers, a multi-word query with every word in one retained Archive post
precedes a query supported only across separate passages. Use the existing FTS
AND membership probe with one deterministic source-row example, not BM25, counts
or post frequency. Keep the entire cutoff tier; no pre-limit alphabetical bias.
Single-word searches retain prior ordering. Show the exact all-word passage with
its date, typed context, link and source row. It need not be the newest or best
passage and does not establish agreement or domain competence.

Use the same frozen tag-name diagnostic and unchanged source/coverage checks.
This is the final bounded comparison in this slice, not a continuing parameter
search. Do not serve an aggregate known-label regression. Full semantic retrieval
and tag-guided ranking are separate decisions, not silently substituted here.

## Historical profile-passage amendment,20 October2026

Search all already-admitted profile observations belonging to the same exact
account,not only the profile chosen for display. Apply the existing publication
gate to every row before fragment projection;hidden Archive text cannot supply
query words. No new source admission,identity merge,schema or graph mutation.

Keep the selected display identity and its bio-ordering tier unchanged. Older
text supplies ordinary distinct saved-word support only. Identical field/text
uses one representative in the existing source order;raw captures remain intact.
This is not a new timestamp normalization or recency adjudication policy.

Profile matches show their original date or unknown,source qualifications and
an optional literal retained-field disclosure. Treat them as historical account
claims,not current location,employment,expertise or verified person identity.
Words can span different capture dates;this does not prove concurrent interests.

This candidate is narrowly/synthetically verified and independently source-
reviewed,but required combined acceptance timed out under high host load.
Keep it unmerged/unserved until that existing gate passes;no timeout increase.


## Private delivery amendment, 20 October 2026

Required combined acceptance now passes. Approved source 6ce1df7 is merged as
ec2c364 and served privately, with sidebar repair 7cbb81c. Actual historical
field/source -> exact dossier -> separate newer profile passes; no tag/data
change or push. Earlier pending status is historical, not the current state.
