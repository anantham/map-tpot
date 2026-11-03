# Finding collaborators through public evidence

Method and lessons from Map TPOT, 19 October 2026. Examples below are invented;
aggregate results describe bounded historical experiments, not current campaign
performance. No private profiles, contact directory or dataset is bundled.

## Start with the job, not a universal community map

We began with fixed named clusters and membership percentages. The useful pivot
was to ask a smaller question: **who has public evidence relevant to this event,
conversation or project, and why should I investigate them?** An event candidate,
someone's social affiliation and their demonstrated skill are different targets.

Write a one-paragraph brief: purpose, two overlapping interests, useful contributions,
practical constraints and what would make a result unhelpful. Geography can be a
travel constraint; a historical location string is not proof of current residence.
Do not replace these questions with inferred personality or developmental stages.

Start with a few people whose work you know. Add reversible, overlapping tags by
example, including exclusions and uncertainty. You need not define every boundary
in prose first. Freeze the examples only when comparing methods; keep revisions.

## The workflow

1. **Inventory before buying data.** Separate profiles, follow captures, authored
   posts, typed references, webpages, work and contact observations. Record which
   accounts/time windows each source covers. Reuse saved research first.
2. **Expand from explicit seeds.** Inspect outgoing follows first, then incoming
   follows or one extra hop as separate scopes. Show every arrow and its source.
   A follow is attention, not friendship, agreement or an introduction.
3. **Require evidence for the overlap.** Find support for each requested interest
   on the same exact account. Terms can occur in a bio, a post and a project page.
   Search the complete qualified pool before applying display limits.
4. **Read the source.** Inspect the passage, author/context, date and adjacent text.
   Separate first-person work from a third-party mention, footer or passing joke.
5. **Review a small batch.** Ask whether it is relevant, whether you already knew
   the account, and whether you are glad it surfaced. Keep “uncertain” available.
6. **Find an appropriate route.** Follow the public website/link-in-bio to contact
   pages, organisation inboxes or forms. Preserve the route's actual context.
7. **Draft only after research.** Name the concrete artifact, explain its connection
   to the activity, and offer an easy, opt-in next step. Check prior contact first.
8. **Record outcomes and corrections.** Keep research, drafts, sends, replies and
   applications separate. Reuse person evidence without reusing an expired event.

Prepared, not activated: the tag panel's **Candidate evidence** selector can offer
**Saved API post references (historical)**. This uses existing tags
and admitted local references without Archive access. Set the direction, types
and minimum IN support, then open the supporting post path before the account.
This mode is partial and all-time; it has no recent-activity or content filter.
Changing the examples refreshes candidates, not a calibrated membership model.

## What the graph means

| Observation | Useful for | Does not establish |
| --- | --- | --- |
| A followed B in a capture | An explicit directed research path | Mutual friendship, current follow or endorsement |
| A replied/quoted/reposted/mentioned B | A typed interaction and its original context | Agreement or shared competence |
| Profile links to a website/platform | A destination to inspect | Ownership or cross-platform identity |
| Saved research associates an account with work | A candidate artifact and its source | Verified authorship/employment |
| A page lists an email or message form | A possible route with context | Personal ownership, delivery or consent |
| Curator applies a tag | That curator's current boundary/example | Objective community truth |

Keep platform accounts, people, organisations, posts, web resources and addresses
separate. Multiple observations can appear on one card without merging identities.
Matching names, handles, emails or domains alone are not enough to merge people.
An explicit publisher link is a qualified claim; preserve who made it and when.

The implemented readers cover partial saved follow networks and partial typed
post-reference networks. They are not a live crawl of every platform. Full
cross-platform person resolution and complete employment histories remain open.

## Ranking ideas we actually compared

The simple baseline is distinct positive-seed support:
`raw(candidate) = number of tagged IN seeds observed following candidate`.

Source selectivity instead adds `1 / effective_degree(seed)` per distinct edge.
Effective degree is the larger valid claimed following count and observed unique
out-degree. This avoids treating an incompletely captured broad source as highly
selective. It still cannot fix missing candidates or guarantee useful discovery.
Implementation: [source_selectivity.py](../../src/graph/source_selectivity.py).

| Experiment | Result | Lesson/limit |
| --- | --- | --- |
| EXP-053: raw support vs reciprocal-degree support, leave-one-positive-out, September 22 | Raw top 20 recovered 2/8 vs 1/8 niche positives, and 9/27 vs 4/27 broader positives | Raw won this known-member test; prominent known members may favor hubs. Not novel-candidate precision. |
| EXP-054: recent authored-post TF-IDF vs raw, on the same covered candidate pools | Niche top 20: raw 3/8, text 2/8, fusion 3/8; broader: raw 10/21, text 3/21, fusion 6/21 | This cheap text recipe did not improve top 20 recovery. It excluded `RT @` posts and did not test semantic LLMs or a retweet-taste model. |
| Typed reply graph, one vs two hops | Tested two-hop scopes reached 765 outgoing/803 incoming accounts in an 863-profile cohort | Two hops nearly saturated this cohort. More reach is not a sharper community boundary. |
| Tag-supported social candidates plus dated post terms | A complete 16-account pool narrowed to 2 for one recent two-topic query, vs 10 for any-date matching | Date windows matter; smaller sets alone do not prove better fit. Humor/reposts still match. |
| Fixed overlapping-interest + exact follow-path test, October 19 | One AI/design query found 11 saved path-qualified leads, including 6 reached through two hops | Source inspection found a substantive investigation lead and incidental matches. Not 11 verified experts or contacts. |
| Direct bio evidence before incidental page mentions | Explicit two-term bio moved third→first among the same 4 candidates | A concrete ordering repair, not calibrated semantic relevance. |
| Current copied Archive package, October 19, not active Review | Two fixed all-source literal-overlap queries returned 156 and 681 accounts. A post-only two-hop query returned 153, reaching 838 of 905 eligible profile IDs | Source coverage restored matches in the preparation, not verified expertise. This two-hop scope was nearly saturated. Broad searches took 27–29 seconds; the scoped post query took 1.7 seconds. Different source scopes make this diagnostic, not a controlled speed or ranking comparison. |

These historical comparisons use different corpora and denominators; do not
compare their percentages across experiments. Some post evidence was searchable
then but is currently hidden when its publication/source-access check fails.
Independent saved sources remain usable; old packages are not a silent fallback.

Reproducible local entry points, using only your authorized inputs:
[follow comparison](../../scripts/verify_research_notes_frontier.py),
[content comparison](../../scripts/verify_content_recovery.py),
[unified search contract](../adr/027-unified-saved-evidence-search.md),
[post-reference contract](../adr/026-current-post-search-index.md).
The comparison scripts require local data; the repository alone cannot recreate
private historical results. Inspect their CLI options before running them.

## Coverage often mattered more than a clever score

Named seeds sometimes had many follows on disk but no usable outgoing path in
the active graph. Missing dates, source qualifications or profiles can prevent
those rows from being used. A hypothetical overlay enlarged one fixed AI/design
pool from 11 to 96, but did not make an absent two-topic content match appear.
That was a diagnostic, not an activated graph or a recall measurement.

Other concrete findings:

- Stored evidence and current eligibility are separate. Two surfaced accounts had
  36,907 retained Archive posts, but their package was superseded. Refresh then
  stopped before the large post transfer because three of 905 eligible accounts
  had blank usernames. Exact numeric identity can exist without a handle; do not
  guess one or discard eligible IDs just to make a consumer pass. A tested repair
  preserves those unknown handles on an isolated branch. Independent code-only
  review completed without blockers; a later required verification run timed out,
  so main integration remains pending. The matching copied index contains 11,922,407
  posts from 894 authors, with 905 eligible profile records. Source reconciliation
  checked 179 distinct original Parquet rows and 41 saved-evidence pointers.
  This is validated private preparation, not an active Review refresh. A bounded
  current REST dossier worked independently; it is not a replacement full-text
  index or permission to expose the old package.
- Restoring existing website associations unlocked 8 cached pages without fetching
  again; one fixed search changed from 0 to 1 with its original source inspectable.
- Four fixed word variants for a two-interest query returned no exact-account
  overlap. One broad-prefix historical bio was not a verified expert. Per-word
  support now explains these empty intersections; it does not fix missing data
  or make literal matching into semantic search.
- Small exact-shared-URL and page-link probes returned no new paths for fixed
  roots. We did not build a product mode around those negative results.
- Higher-k graph factorization and content partitions need not describe the same
  thing. A visually coherent legacy cluster is not a validated niche or affinity.
- All-time vocabulary is broad. A recent post window is useful to test, but recent
  capture, latest interaction and publication date are different clocks.

The copied refresh also increased source-qualified cached-page coverage from
578 pages on 453 accounts to 588 on 463, measured under the same fresh eligibility
check. These are deduplicated displayed page associations, not newly fetched
sites, unique people or newly verified contact routes. The raw stores, tags and
live binding were unchanged. An earlier local command ran before its selection
file finished; it failed at setup, then the dependent step ran after that file
existed. Sequence prerequisites explicitly instead of calling that a source failure.

Before spending, ask which missing source could change the next actual decision.
Estimate the cost of completing that specific neighborhood or obtaining the
missing posts. Report captured/claimed coverage, request budget and a stopping
rule. More rows are not automatically more information. No paid call is implied
by a research plan or this guide.

## Contact discovery: the mistake worth avoiding

An earlier pass found organisation inboxes but exported only narrowly classified
personal emails. Empty exports then became “no route beyond X” (Twitter/X). That was wrong:
finding a route, classifying it, and finishing a search are different states.

In one subsequent ten-account recheck, five blank email fields were filled and
six public routes retained across six accounts; four checks stayed incomplete.
This selected repair batch is not a population-wide email-finding success rate.

Keep organisation inboxes and contact pages even when an address does not contain
the person's name. Check their stated purpose: a public general inbox may permit
an honest ask-for-the-person request; specialist support/abuse channels should
not be repurposed. A form may be comments or support, not a contact invitation.
Keep the original page and instructions. Do not automatically promote all found
addresses into verified personal routes. See [ADR 032](../adr/032-saved-page-contact-clues.md).

Distinguish `not checked`, `incomplete/error`, `no clue in checked pages`,
`organisation route`, `personal route claimed` and `delivery confirmed`.
An untested form, search result or email-shaped code example is not delivery.
If DMs are closed, another permitted route may exist. A public reply requires a
genuine relevant opening; do not turn unrelated threads into an invitation blast
or bypass platform restrictions.

## Light customization that a person can stand behind

Use one or two specific sentences, not “I like your work.” State where you found
the artifact and connect it to the event. Credit collaborators; avoid invented
claims about expertise, location, availability or what the person will gain.

Synthetic example:

> Saw your trail-map prototype on the library project page. We're bringing
> together people building community tools, and your approach to accessible maps
> seems like a good fit. Here's the event: [event link]. Would love to have you,
> or feel free to share it with someone who might enjoy it.

Our drafting preferences: casual, specific, no em dashes, no inflated praise, short
artifact→fit connection, one link and a low-pressure invitation/referral option.
This is a writing approach, not proof that customization increased response rates.
Recheck time-sensitive details such as Q&A links before reusing a draft.

Before a send, resolve identity and check channel history, prior unanswered contact,
opt-outs and duplicates. One canonical record should link all channel events.
Researching at scale does not authorize sending at scale or repeated messages.

## Cache for another project, not just another event

Keep source URL, original capture, date, exact account binding, typed relationship,
relevant excerpt, method/version and uncertainty. Derived indexes are rebuildable;
raw sources and curator corrections are retained separately. Avoid confusing
multiple copies of one claim with independent confirmation. Respect source-use,
access and removal requirements when reusing a capture.

Store event-specific fit, draft and outcomes separately from reusable work/profile
evidence. Retain organisation-level routes as such. Newer contradictory evidence
should supersede a view without silently deleting its earlier basis.

## Measure the useful thing

Report separate counts for discovered accounts, coverage-eligible candidates,
reviewed sources, novel useful leads, drafts, history-cleared recipients, actual sends,
replies, substantive interest, applications and attendance. State the denominator,
cohort, date and time elapsed since sending at every stage.

An old outreach snapshot mixed cohorts and counted people never invited in its
headline. Many invitations were less than 24 hours old. That supports a delivery/
backlog diagnosis, not a losing channel or poor audience. No causal winner for
message style, channel or final event conversion has been established.

For the next comparison, freeze a small prospective pool and interleave baseline
rankings. Ask relevance/prior familiarity/glad-it-surfaced with abstention. Track
review time and new useful finds. Keep unknowns and selection bias visible.
Test cheap baselines before embeddings or LLM rerankers; size verification to the
cost of error. Twenty reversible reviews can teach more than another empty schema.

## Sharing and reproducing

Share code, synthetic tests, this guide and bounded aggregate lessons. Do not share
raw captures, contact lists, private notes, tags or live credentials. The private
Review is not the public legacy map. See the [data and release boundary](DATA_BOUNDARY.md)
for ignore rules, local-only inputs, clean-checkout checks and history limitations.
