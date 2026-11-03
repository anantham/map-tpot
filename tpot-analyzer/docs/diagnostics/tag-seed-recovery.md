# Graph-only tag recovery

Status: implemented experiment, 20 October 2026. Private data and account-level
results remain off Git. The comparison is exploratory, not a membership model.

## Question and fixed methods

Can examples supplied through the curator's working tags recover *other* examples
through observed graph connections, without matching tag names or post words?

For every exact curator/tag with at least three IN examples, hide each IN label
in turn. The remaining IN accounts are seeds. The hidden account stays in the
graph and candidate universe: this is transductive label recovery, not prediction
of a previously unseen node. No other curator, other tag, NOT IN label, keyword,
NMF community or hand-written account list is a ranker input.

The four methods are fixed before the local comparison:

1. **Popularity:** distinct incoming neighbors in the selected walk graph,
   independent of seeds. Incoming exploration reverses the graph first, so this
   becomes observed outgoing popularity in the original graph.
2. **Shared neighbors:** one vote per distinct seed with a direct edge to a
   candidate. Repeated captures and repeated posts never create additional votes.
3. **Selective neighbors:** each seed contributes `1 / observed_walk_degree` to
   each direct neighbor. Reuses the source-selectivity scorer without a claimed
   total. Partial captures can exaggerate selectivity; this is not the claimed
   number of accounts someone follows. Incoming mode is inverse observed incoming
   degree, not a statement about the original account's selectivity.
4. **One + two-hop walk:** sum across seeds of half one-step and half two-step
   mass, each step divided by observed distinct walk degree. Dangling second
   steps lose mass. No restart, infinite iteration, fitted weights or PPR claim.

Follows, Archive replies, Archive reposts, saved API replies and saved API reposts
are independent layers, each tested outgoing and incoming. No cross-layer weight
tuning. Current Archive uses every retained date and one observation per pair,
not the legacy frontier's repetition or recency filters. Quotes/mentions, likes,
co-follow similarity and semantic features are deferred, not silently blended.

## Measurement and falsifiers

- Every IN example stays in the denominator, even outside the observed graph.
  Report incident-edge coverage and reachability from other IN seeds within two
  hops separately. Two-hop reachability is a ceiling only for these bounded seed
  methods, not the global popularity baseline or a future longer walk.
- Display ties by exact ID. For Recall@10/25/50, a definite hit requires the end
  of its equal-score block within K. Also report possible hits using the block's
  start. This interval is tie sensitivity, **not a confidence interval**.
- NOT IN is evaluation-only: count its exposure in the deterministic full-seed
  top 25. This is not held-out false-positive rate. Unjudged people are unknown;
  precision cannot be estimated from these tags.
- Full-seed candidate previews are separate from held-out recovery. Only the
  review queue omits current IN/OUT examples; fold rankings omit training seeds
  only. Otherwise the hidden example could be excluded by its own hidden label.
- Failure to beat popularity is a negative result, not permission to tune until
  it wins. A positive outside recorded coverage diagnoses a data gap, not OUT.
  Improvement on these small, overlapping examples does not prove a community
  exists, that a connection implies agreement, or that new candidates will fit.
- A future frozen prospective panel / seed-shuffle null / parameter robustness
  check is needed before claiming generalization. The present comparison is not
  independent confirmation; picking its best layer is exploratory selection.

## Evidence, privacy and reproduction

`scripts/verify_seed_recovery.py` takes explicit tag, relationship and post-index
paths plus a new private output directory. It saves the configuration and labels
before running, then one private report per tag/layer/direction and a summary.
It refuses acceptance if source identities, human tags or current publication
qualification change during the comparison. Source versions must accompany any
interpretation; an old result is not evidence about a new data release.

All source databases are opened read-only. Existing current-publication policy
gates Archive profiles/edges before ranking; unavailable Archive reads do not
become zero recovery or an unscoped fallback. Independent saved layers remain
usable. Cache keys include resolved source identity and the eligible cohort;
judgment-independent graph contributions are reused, never label-derived scores.

Private Review's authenticated `/api/research-notes/recovery` computes a chosen
tag/layer/direction on demand, compares all four methods and shows unreviewed
candidates using the chosen method. Defaults favor the exploratory reply-walk
lead from this first comparison, not a declared universally winning model.
Each candidate exposes representative original-direction source paths, dates,
snapshot pointers or exact retained post rows. Up to three paths are witnesses,
not an exhaustive additive explanation of every two-step contribution.

The initial local run covered ten tags / 65 overlapping positive assignments.
Archive outgoing replies: definite top-25 recovery was 18/65 for popularity and
26/65 for the bounded walk. Outgoing follows: 8/65 and 5/65 respectively. These
uneven outcomes favor investigating interaction evidence, not declaring that
follows or source selectivity universally solve recovery. Account-level labels,
candidate names and source contents are not included in this document.

Verification: synthetic engine, real temporary-source API, refusal/auth, current
eligibility, direction, live-tag refresh, tied ranks and UI cancellation tests;
required combined Research Notes acceptance and private browser evidence flow.

Delivery checkpoint,20 October2026: independent source/synthetic-only Google
Gemini3.8Flash review completed with NO BLOCKERS after two source-contradicting
findings were falsified locally and retracted. Total review cost$0.0658938/$0.50;
no profiles, real tags or experiment outputs left the host. Exact reviewed source
is served on loopback private Review; a candidate opens its exact dossier and
original witness/source record. Local commit only, no push. Original data,
working judgments and active/rollback dataset releases remain unchanged.

## Independent evidence comparison (prepared,20 October2026)

Under an active tag,open **See what this tag currently surfaces**,then **Can the
graph recover your examples?**,then **Compare evidence types**. The selected
method and direction apply to all five existing layers;the Recovery evidence
selector still controls only the original single-layer test.

The comparison keeps each layer's top25 hide-and-recover count separate. Archive
replies remain the visible baseline,not a claimed universally best method. Open
each candidate disclosure for incident coverage,two-hop reachability,known OUT
exposure and its own unjudged candidate order. A person appearing in several
lists is not several independent confirmations. There is no combined ranking or
membership score. Quotes,mentions,likes and content are not added by this view.

Every channel resolves independently. A hidden Archive source,unimported layer
or failed read is not zero recovery and does not erase healthy saved evidence.
Cancel retains finished channels;Compare again refreshes them. After initial
opt-in,tag/method/direction/judgment changes refresh the comparison and abort old
requests. Reads are independent,not a frozen simultaneous cross-channel snapshot.

Each candidate retains original-direction witness paths and source pointers.
Review opens its exact account dossier,where already-saved work,websites and
contact routes remain inspectable. No new fetching,messaging or tag mutation is
performed by comparison. Existing IN and OUT examples are omitted only from
candidate queues,not retrospectively erased from evaluation.

`scripts/verify_recovery_channels.py` runs synthetic UI and qualified-engine/API
checks with disposable persistence/lease/Takes roots. The isolated browser also
verifies path->receipt->large exact ID->organisation forwarding source while
Archive is forced offline. This slice is tested/reviewed on the isolated branch;
canonical private serving still requires approval. It is not evidence that the
five-layer mixed union improves recovery;that experiment was negative.


Delivery amendment,20 October2026: human-approved UI8f32d53 is merged into
canonical local main and served by existing private UI hot reload. The actual
existing-tag comparison -> original dated source witness -> exact dossier journey
passes. API/UI processes,data binding,raw sources and93/93 judgments/events remain
unchanged. Pending-serving prose above records the preparation checkpoint,not
current status. No quote/mention UI expansion,paid request,outreach or push.

## Saved quote/mention extension, 22 October 2026

This amendment extends the existing recovery consumer, not the frozen October20
protocol or its outcomes. `saved_quote` and `saved_mention` use the already
admitted saved-API reference reader as two additional independent graphs.
Archive quote/mention layers remain outside this extension. The original five
layers, four rankers, tie rules and default selected layer remain unchanged.

Both the single-layer selector and Compare evidence types expose the new
channels. Each retains its own IN denominator, incident/reachable coverage,
held-out ranks, unjudged queue and original-direction post/source witnesses.
No aggregate of these lists is a confidence, affiliation or membership score;
a quote or mention can be criticism, context or incidental reference.

Current-source results must name their graph and tag snapshot. A saved-only
local comparison can proceed while Archive is unavailable; it cannot reuse an
old eligible Archive result as a current baseline. Sparse or zero new recovery
is a result, not permission to tune or replace the existing default. Existing
raw sources, tags, decisions and rollback stay unchanged. Preparation, review
and private serving are separate release states in ROADMAP and WORKLOG.

## Fixed shared-followee experiment, 22 October 2026

This is a standalone offline experiment, not an additional live ranker or a
change to the quote/mention comparison. `scripts/verify_cofollow_recovery.py`
uses only the existing qualified stable-ID saved follow graph. For each seed,
walk outward uniformly to an observed followee, then backward uniformly to an
observed follower. Sum mass `1 / (out_degree(seed) * in_degree(followee))` for
each candidate. Original observations remain `seed -> followee <- candidate`;
the reverse traversal is not a reversed observed follow.

Fix the scorer before examining real outcomes. Compare leave-one-IN-out
definite top25 recovery to all four existing follow methods in both directions.
The primary prediction requires at least one hit beyond their best aggregate.
Keep every positive in the denominator, including absent/isolated accounts;
use end-of-tie ranks for definite hits and start-of-tie ranks for possible hits.
NOT IN is evaluation only. No keywords, tag connotations, other tags or fitted
weights enter ranking. These are extensional curator examples, not objective
affiliation, competence, membership probabilities or a sealed future holdout.

Run16 deterministic shuffled-seed controls with the same0,1-9,10-99,...
observed-out-degree stratum counts per fold. Exclude the hidden target, sample
distinct replacements and allow original seeds by chance. Do not widen a
stratum after outcomes. Approximate degree matching, overlapping tags and
capture bias prevent treating the null distribution as calibrated significance.
Candidates need observed outgoing follows; report that restricted universe.

The CLI requires explicit private graph, tags, reviewer and a new output folder.
It isolates unused persistence roots before application imports, freezes logical
tag rows plus file/code hashes before outcomes, and retains private per-tag
folds, all baseline/control results and original-arrow witnesses. It reads no
Archive service, Takes, contacts or posts and writes no input, tag or live state.
Synthetic arithmetic and importer-shaped CLI checks plus independent code/design
review precede the real run. Negative results are retained without retuning;
any later production integration is a separate reviewed product decision.

## Saved outgoing coverage audit, 22 October 2026

The negative co-follow result identifies 34 distinct tagged accounts without
qualified outgoing follows. Audit exact numeric IDs against saved shadow rows
and provider receipts before calling this lost data or buying another capture.
Disjoint account outcomes: 27 have no outgoing shadow rows, four have alias-only
rows, one has three admissible numeric pairs, one has a pair without an independent
qualifying profile and one has a protected-at-capture endpoint pair. All 304
alias observations across seven accounts already retain their original source
rows in the separate shadow layer. A matching handle is not a stable-ID join.
None of these 34 seeds an outgoing-list receipt in the examined API captures;
appearing as a target in the curator's following list does not supply that list.

Reuse `scripts/verify_shadow_follow_batch.py` on a private graph copy. The
selected contiguous numeric window adds three directed observations, preserving
original row bytes, dates, source digest/pointer and all predecessor rows.
Repeat import, integrity and authenticated search-to-path consumers are checked;
the old missing-coverage response stays explicit rather than an empty success.
Historical naive timestamps remain timezone-unspecified. Source eligibility is
not proof of a complete current list, friendship, agreement or group membership.

Measure the derivative with unchanged labels, scorer and protocol without
retuning. This target-selected post-hoc repair increases outgoing coverage
from 17 to 19 positive assignments and reachability 12 to 13, but co-follow top25
falls 7 to 6/65; the best old baseline remains 9. True added observations can alter
observed-degree normalization in either direction. Retain this sensitivity,
not a prospective validation claim. Preparation, graph-only adoption and
actual private serving remain separate states in ROADMAP and WORKLOG.

## Raw Archive source-family amendment, 26 October 2026

The later27-account no-outgoing cohort has no source-position shadow-cache rows,
but the raw Archive store has50819 account_following rows and1191 account_followers
rows read in their actual follower-to-followee direction. These families may
overlap. This is not a new recovery result or a claim of50819 unique current edges.

The active graph has no qualified outgoing follow observations for these accounts.
Its saved-shadow importer expects capture time,channel,direction and metadata;
the raw Archive tables contain only exact endpoint pairs. Archive import uses
INSERT OR IGNORE,so the retained set can accumulate across imports. There is no
edge-level date or complete-list receipt; profiles.fetched_at is not that date.

Local-data consolidation must investigate this separate source family before
buying a replacement capture. A future candidate adapter must preserve exact
table/pair provenance,unknown relationship time,possible accumulation and source
admission/privacy uncertainty. Do not impersonate a saved-shadow capture or use
the raw rows as a fallback around Archive publication policy. Existing frozen
results and live defaults remain unchanged; source contract,testing,review and
private adoption are separate next checkpoints in ROADMAP.

## Current API source choice, 26 October 2026

The raw-table proposal above is not adopted. Source-admission inspection finds
no retained edge-level release/permission receipt qualifying those accumulated
pairs for visible serving. A current allowed-profile list does not authorize
old raw edge bytes; a default-allowed non-Archive kind is not a policy loophole.

The human chooses the current policy-aware Community Archive API for this graph
gap. Its public contract uses analytics.community-archive.org/v1, a server-side
personal key and cursor-paginated account following; this is archive-derived,
not a live X following list. Follow next_cursor until null, even after a short
or empty page. Legacy REST retirement is documented for19 November2026; do not
start a replacement on that route. Source: https://www.community-archive.org/llms.txt.
Public OpenAPI metadata is saved/inspected; no fresh account-follow data has
been fetched and the personal key is pending. Keep all frozen experiments and
live defaults unchanged. This dependency does not stop saved person-card work.
