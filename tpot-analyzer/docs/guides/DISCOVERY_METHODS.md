# Mapping communities by example

Reusable methods and lessons from Map TPOT, 20 October 2026. All examples here
are invented. Private research, account-level results and contact lists are not
included. This is an exploratory discovery system, not a validated psychological
classifier or a calibrated community-membership model.

## 1. Start with a decision someone wants to make

The ambitious vision is a source-visible map of overlapping interests, work and
relationships that helps people find collaborators and build communities. The
useful question is smaller than “what are the true communities on this platform?”:
**who has relevant evidence for this project, and why should I investigate them?**

Write a brief: purpose, intersecting interests, useful contributions, practical
constraints, exclusions and what would make a result unhelpful. Event fit,
affiliation, expressed interest and demonstrated competence are different claims.
A historical location string is not proof of current residence or travel ability.
Do not substitute inferred intelligence, religion or developmental stage.

## 2. Let examples define a working boundary

A curator can independently tag an account IN or NOT IN for several tags, add
notes, and later retract a judgment. Unknown is not NOT IN; retraction is not an
exclusion. Tags overlap and do not sum to 100%. A word such as “builders” is a
starting hint, not a necessary-and-sufficient definition.

Put posts and sources beside the tag controls. Show current decisions and make
correction cheap. Suggestions extracted from notes remain proposals until a
person confirms them; model output must not silently become human evidence.
Preserve revisions. Freeze an extension only for a particular comparison; later
boundary changes create a new evaluation target, not a rewrite of old results.

Example: a curator tags `@river_example` for community tooling, excludes
`@meadow_example` from that tag, and leaves both unjudged for teaching. The
unjudged pair is not negative training data for teaching.

## 3. Model observations, not a single flattened person row

| Observation | Useful for | Does not establish |
| --- | --- | --- |
| A followed B in a capture | A directed investigation path | Friendship, agreement, current follow or introduction |
| A replied/reposted/quoted/mentioned B | Typed interaction and its context | Endorsement or competence |
| A profile links to a website | A destination and a publisher claim | Verified ownership or identity merge |
| Saved research associates A with work | An artifact to inspect | Authorship or current employment |
| A page lists an inbox or form | A possible route with stated purpose | Personal ownership, delivery or consent |
| A curator tags an account | That curator's current example | Objective community truth |

Keep person, platform account, organisation, post, page, artifact and contact
route distinct. A card can join observations without merging identities. Names,
similar handles and shared domains are weak identity evidence. Record who made
a claim, the exact source, capture/publication times, confidence and contradictions.
Multiple copies of one claim are not independent confirmation.

## 4. Inventory and consolidate before fetching

For each source, record account coverage, direction, time window, schema and
source-use eligibility. Count profiles, entities, posts and edges separately.
An empty query may mean missing coverage, unavailable source, failed import,
no literal match or a genuinely empty eligible neighborhood. Do not collapse them.

Consolidation means admitting existing observations into a consistent view with
their provenance intact. It does not mean guessing missing capture dates,
deduplicating people by name, or declaring every saved URL a verified identity.
Missing source qualifications can make rows inadmissible even when they exist.

Keep raw captures and curator corrections separate from rebuildable SQLite
relationship and full-text indexes. Stage a small batch, inspect its joined card,
compare before/after coverage, then activate it with a retained rollback version.
Independent saved sources can remain usable when another platform is unavailable;
do not silently fall back to a withdrawn or superseded source.

## 5. Compare simple graph methods honestly

Begin with distinct seed support: one vote from each IN seed observed connecting
to a candidate. Repeated captures or repeated posts must not manufacture votes.

Source-side selectivity weights an outgoing seed by `1 / effective_degree`.
The follow-frontier scorer uses the larger valid claimed and observed degree, so
an incomplete capture does not automatically look selective. This is different
from target popularity correction, which downweights widely followed targets.

The graph-only recovery experiment also compares popularity, direct shared
neighbors, inverse **observed walk degree**, and a fixed half-one-step plus
half-two-step walk. It uses no claimed counts. A reversed incoming walk measures
a different quantity from outgoing follow selectivity. The bounded walk is not
PPR: there is no restart or convergence, and dangling second steps lose mass.

Compare follow, reply and repost layers and each direction separately before
tuning a blend. Show original arrows, dates and source pointers. A few displayed
witness paths explain inspectable connections, not every additive score term.

### Hide a label and try to recover it

1. Freeze source identities, eligible candidates, current tag revision and methods.
2. For a tag with at least three IN examples, hide one IN label at a time.
3. Use the other IN examples as seeds. Keep the hidden account and its edges.
4. Rank candidates and compare Recall@K with a seed-independent popularity baseline.
5. Report ties, missing-edge coverage, seed reachability and low-rank misses separately.

This is retrospective, transductive recovery of known examples, not prospective
precision on strangers. The experiment does not remove edges attached to the
hidden account. NOT IN exposure is descriptive; it is not a held-out false-positive
rate. Unjudged candidates remain unknown. Equal-score rank bounds are tie
sensitivity, not statistical confidence intervals. Overlapping tags are not
independent samples. Choosing the best layer afterward is exploratory selection.

Falsifier: if a method cannot beat popularity on the declared examples, retain
that negative result. If an example is outside graph coverage, do not “fix” the
ranker or relabel the account to hide the miss. Source code and exact contracts:
[graph recovery](../diagnostics/tag-seed-recovery.md),
[follow scorer](../../src/graph/source_selectivity.py),
[recovery verifier](../../scripts/verify_seed_recovery.py).

## 6. Join text and work without overselling semantics

Search profiles, saved work, cached websites and qualified authored posts on the
same exact account. Match every requested term before limiting the display pool.
Expose which source matched each word, with date and an opening link or exact row.
Distinguish an author's claim from a quote, joke, footer, repost or third-party mention.

Literal full-text search is not semantic understanding. A smaller dated result set
does not prove better fit. Recent capture, latest interaction and publication
date are different clocks. Start with cheap lexical baselines; evaluate embeddings
or LLM rerankers only against an explicit decision, cost and held-out comparison.

## 7. Lessons from approaches that did not reliably help

These are qualitative lessons from bounded private experiments, not public
benchmark results. Private inputs are not bundled, so readers cannot reproduce
the historical measurements from a clone alone. The code supports new comparisons
on your own permitted data; the synthetic suite checks contracts, not social validity.

| Tried | What we learned | What remains unproven |
| --- | --- | --- |
| Fixed NMF communities and membership-like percentages | A coherent visual map is not evidence of calibrated affinity | Whether a particular niche is recoverable from an adequately covered graph |
| Reciprocal-degree source weighting | It did not reliably beat raw support on known-member recovery | Novel-candidate usefulness and generalization |
| Cheap authored-post TF-IDF and a fixed fusion | This recipe did not reliably improve the declared top-K recovery | Semantic models, retweet taste and better text representations |
| One- versus two-hop typed networks | Two hops can nearly saturate a captured cohort | Whether the additional reach improves boundary precision |
| Separate follow and interaction recovery | Results differed by layer; no universal winner | Prospective precision and performance on other curators |
| Reusing cached website associations | Correct joins can restore evidence without another fetch | Ownership, current contactability or causal outreach impact |
| Narrow personal-email export | It discarded useful organisation routes and overstated absence | Whether any retained route is suitable or delivers |
| Mixed outreach cohorts and young messages | Backlog, sent and response denominators must be separated | A causal winning message style or channel |

## 8. Contact discovery must preserve context

Keep `not checked`, `incomplete/error`, `no clue in checked pages`, organisation
route, personal route claimed and delivery confirmed separate. A missing exported
email is not proof that no route exists. Preserve relevant organisation inboxes,
contact forms and public platform links even when the person's name is absent.

Read the route's stated purpose. A general inbox may support an honest request to
pass a note to someone; an abuse/support channel should not be repurposed. A form
may be a newsletter or comments box. Email-shaped examples in code are not contacts.
Do not infer private phone numbers or use restricted sources to bypass closed DMs.

## 9. Research in parallel; integrate and contact deliberately

Assign disjoint, small account batches to workers using the same output contract:
exact account ID, source URL, capture date, quoted basis, relationship type,
uncertainty and completion status. Reuse caches first. One integration owner checks
identity and source eligibility before writing the joined view. Workers must not
race writes, overwrite tags, or turn missing evidence into negative claims.

Separate research from drafting, approval and sending. Before contact, check
cross-channel history, duplicate identities, previous unanswered notes and opt-outs.
Public replies need a genuinely relevant opening; they are not a workaround for
platform restrictions or permission for an invitation blast.

Keep customization light and grounded. Invented example:

> Saw your accessible trail-map prototype on the library project page. We're
> bringing together people building community tools, so that approach seems like
> a good fit. Here's the event: [event link]. Would love to have you, or feel free
> to share it with someone who might enjoy it.

Specific artifact → why it fits → one low-pressure next step. Avoid generic
praise, invented benefits and expired event details. Better prose alone does not
establish a higher response rate.

## 10. Close the learning loop

Track discovered → eligible → reviewed → novel useful → history-cleared → sent →
replied → interested → applied → attended, each with cohort, denominator, channel,
date and elapsed time. Keep reusable evidence separate from event-specific fit.

Next experiment: freeze a small new candidate pool, interleave baseline rankings,
blindly review relevance/prior familiarity/glad-it-surfaced with abstention, and
measure useful finds per review minute. Sample some candidates outside the top
rankings so the model cannot define its own apparent success.

Acquire new data only when it could change the next decision. Estimate the specific
coverage deficit and cost, set a cap and stopping rule, and preserve failures.
Treat information gain or active-learning value as a hypothesis until validated;
uncalibrated rank scores do not justify “bits of membership certainty.”

The practical stopping rule is proportionality: enough checking for the cost of
being wrong, then a usable review loop. An empty corpus does not benefit from
unlimited integrity machinery. See [data boundary](DATA_BOUNDARY.md),
[Review setup](DISCOVERY_REVIEW.md) and [roadmap](../ROADMAP.md).
