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

Private comparisons produced uneven results across layers. This motivates
investigating interaction evidence, not declaring a universal winner. Actual
curator labels, account-level results and source contents are not published;
the repository cannot reproduce the private measurements without those inputs.

Verification: synthetic engine, real temporary-source API, refusal/auth, current
eligibility, direction, live-tag refresh, tied ranks and UI cancellation tests;
required combined Research Notes acceptance and private browser evidence flow.

The public synthetic checks establish implementation contracts, not the
validity of a particular social boundary. Private serving status is separate
from this source publication.
