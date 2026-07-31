# Budgeted Personal-Ontology and Local-First Acquisition Pilot

- Date registered: 2026-07-26
- Status: Planned; no paid action authorized by this document
- Decision basis: ADR 021 and ADR 022
- Binding methods:
  `docs/experiments/2026-07-26-personal-ontology-evaluation-methods.md`
- Maximum external-spend budget: USD 100
- Provisional human-attention ceiling: 180 minutes

## Research question

Given a biased, partially observed multiplex social graph, public post content,
and an Aditya-specific ontology, which next action most improves out-of-sample
discovery of overlapping niche-community members per dollar and human minute?

This is not a prevalence study of X. Archive contributors have unknown inclusion
probabilities, and the scraped graph is capture-centered. The estimand is
performance within a declared, multi-source discovery universe, reported by
source and evidence stratum.

## Decisions frozen before the first paid call

The following must be written into the run manifest before execution:

- ontology ID/version and operational definitions;
- ordered \(U_0\) account universe, eligibility/candidate rules, cutoff, and
  identity digests;
- fixed training/challenge identities and the resulting
  \(U_{\mathrm{eval}}\) probability frame;
- separate probability-sampled evaluation, purposive challenge, rich-policy,
  and extraction panels, with inclusion probabilities wherever population
  metrics are claimed;
- seed, explicit-negative, bridge, and abstain identities;
- account-level train/dev/test assignment;
- sealed one-shot test hash and terminal release condition;
- human-attention ceiling after a ten-dossier timing calibration;
- current provider price-card identities and worst-case cost formulas;
- local and hosted model weight/provider identities;
- prompt, schema, context-packet, and task-head versions;
- scalar primary endpoint, comparator, cost grid, practical effect, and
  stopping thresholds;
- the randomization seed and 20% exploration allocation;
- a complete outbound-payload allowlist covering evidence text/media,
  system/user prompts, ontology/schema, labels or derived features, and
  metadata; secrets are prohibited; and
- the loss-reduction estimator or exclusive information surrogate, including
  its cross-fitted predictive-model identity.

Changing one of these fields creates a new run. It does not mutate this
preregistration or a completed run.

## Initial ontology panel

The purposive training/challenge panel should contain contrasting, genuinely
overlapping groups:

1. forecasting;
2. local/open-source LLM practitioners;
3. contemplative practice, meditation, and jhana; and
4. interface-design or second-brain practice.

Aditya supplies known-positive seeds and boundary examples. This panel must also
include topical near-misses, structurally nearby explicit negatives, bridges,
and insufficient-evidence accounts. Affiliation and competence are labeled
separately. It does not support prevalence or calibration claims. Those use the
probability-sampled panel defined by the binding methods contract.

The first run may narrow to two groups if the timing calibration shows that four
cannot obtain minimum positive/negative coverage within the human ceiling. That
choice must be made before fitting or test inspection.

## Formative Dharma boundary pretrial (registered 2026-07-31)

Before freezing the first real ontology task, run a non-confirmatory,
zero-spend pretrial over 12 purposively selected accounts from the dated takes
snapshot. Its purpose is to test whether the human can answer two proposed
questions consistently and whether they encode meaningfully different
boundaries. Its session drafts are not Community Gold and must not train or
score a model.

The two questions are fixed as:

1. **Retrieval relevance:** “Should this person be surfaced when searching for
   people relevant to Dharma, meditation, or jhāna community-building?”
2. **Social affiliation:** “Based on public evidence, is this person socially
   affiliated with the Dharma community as Aditya uses that term?”

Use four likely positive controls, six boundary cases, and two likely
negatives selected before answer reveal from the private takes snapshot. Put
their ordered account IDs, strata, and digest in a private run manifest rather
than this repository. Shuffle within each of two passes and hide the first-pass
answer during the second. Record `IN`/`OUT`/`ABSTAIN`, elapsed review time,
whether external investigation was needed, and the evidence note.

The proposed task split survives this pretrial only if at least two of 12
accounts receive different non-abstain answers across the two questions. If
fewer than two differ, there is weak evidence that separate targets buy useful
resolution and the questions should be revised or combined before schema work.
If more than 25% of answers abstain, the dossier or definitions are inadequate;
improve evidence/wording before interpreting disagreement. If either question
has less than 75% exact repeat agreement across the two passes, do not freeze
it as a task. Report disagreement, abstention, median time, external-search
rate, and repeat agreement as descriptive counts only; this purposive panel
does not estimate population prevalence or predictive performance.

The retrieval question is a search-policy target, not
`participation_interest`. The affiliation question may later bind to the
existing `affiliation` target type. A distinct retrieval-relevance contract is
considered only if the observed disagreement justifies it; this pretrial does
not authorize an ontology/schema expansion.

## Evidence identities at registration

- Frozen control graph: `frozen-tpot-control-20260726`; the run manifest must
  bind its ordered-node and topology digests.
- Current Community Archive tweet snapshot:
  `20260726T045149Z-37a97fa3e057`,
  SHA-256
  `99e93da98bb9fbdbddaa46a9e7f00da7ae501144294c123155e4d56447a8e9bd`.
- This frozen control generation contains 95,057 nodes and 319,771 directed
  stored edges; it is not the incompatible 298K-node propagation universe.
- Known structural warning: 1.731% capture centers touch 100% of shadow edges;
  80.336% of graph nodes have degree one.
- Current account-community gold warning: the active set is positive-only and
  cannot calibrate binary membership without explicit negatives.

The tweet snapshot does not refresh following/follower topology. Paid
observation begins only after a per-action local-evidence deduplication check.

## Action space

Candidate actions are:

- reveal or acquire outgoing followings;
- reveal or acquire incoming followers/IDs;
- acquire profile metadata when not included elsewhere;
- acquire a temporally stratified authored-tweet window;
- acquire parent, reply, quote, or thread context;
- acquire a targeted historical/time-window probe;
- compute local embeddings;
- run fast local structured extraction;
- run a stronger local disagreement pass;
- run a pinned hosted-model audit; or
- ask a human to judge a dossier.

Each queue row names one atomic account-action: a single request/page or a
precommitted cursor/max-pages/max-items/stop-rule bundle. “Enrich account” is
too ambiguous to price, randomize, or evaluate.

## Local-first inference treatments

At planning time the machine was reported to contain:

- `qwen3-embedding:0.6b` for retrieval and shared representations;
- `gemma4` 8B Q4 for fast structured extraction; and
- `qwen3.6` 35B/A3B-class Q4 for selected complex cases.

These weights and runtimes must be verified before the benchmark; their
presence is not evidence that local generation is integrated or accurate. The
experiment records immutable model digests rather than these mutable names.
Local semantic extraction is blind to graph communities and user labels. It
returns observable fields and evidence spans under a schema; graph remains a
separate task-head view. It does not directly declare identity, competence, or
psychological stage.

Before production routing, run the separate message/context extraction and
account-level panels defined in the methods contract. Slice 3 uses cached hosted
receipts only; any new hosted call waits for the authorized microtrial.

Structured output guarantees shape, not truth. Same-family or repeated-prompt
agreement is not treated as calibrated independence.

## Budget tranches

| Tranche | External spend cap | Purpose |
|---|---:|---|
| Retrospective | USD 0 | Mask/reveal rich local accounts; measure attainable gains and variance |
| Microtrial | USD 10 | Up to USD 2 hosted reference, then randomized schema/yield/cost probes |
| Adaptive | USD 70 | Four small sequential batches selected by the registered policy |
| Safety reserve | USD 20 | Unspent margin; unavailable to selection, audit, test enrichment, or invalid runs |

Hosted-model inference is capped inside these tranches, not added on top. Local
inference has near-zero external spend but still records compute time and
latency. The optimizer decides the evidence-type allocation; this table is not
an endpoint quota.

This protocol does not itself authorize spend. Once Aditya authorizes a
specific tranche, registered batches inside it may proceed without per-action
or per-batch approval while every identity, privacy, reserve, and stopping gate
passes. Request attention only when the frozen policy cannot decide, a stop
condition fires, or scope/budget would expand.

## Experimental arms

Evaluate cost-matched policies:

1. local/archive evidence only;
2. uniform random account-action selection;
3. degree-first selection;
4. current frontier/entropy heuristic;
5. topology-only estimated value of information; and
6. full multiplex graph/content/context value of information with local-first
   inference.

Retrospective mask/reveal runs all feasible arms. Exactly 20% of eligible live
actions use randomized, stratified exploration and record selection
propensities.

## Frozen decision thresholds

The binding methods contract freezes one normalized
IPW-macro-AUPRC-versus-cost endpoint, strongest comparator, 0.03 minimum
primary effect, secondary safety guards, class-count requirements, local-model
non-inferiority margin, and sequential rule. No secondary metric can rescue a
failed primary endpoint. If retrospective variance makes a threshold
unresolvable, stop and register a new design rather than changing it after
results are visible.

## Hypotheses and inferential status

H1 is the sole confirmatory hypothesis for this run. H2–H8 are ordered
secondary/exploratory questions: report their effect sizes and uncertainty, but
do not turn them into additional pass conditions or familywise claims without a
new preregistration.

| ID | Hypothesis | Falsifier |
|---|---|---|
| H1 | Adaptive multiplex policy improves the frozen primary cost-curve endpoint on untouched offline policy evaluation | Lower paired-bootstrap bound is not above zero, point gain is below 0.03, or a safety guard fails |
| H2 | Outgoing followings add more development membership value per cost than incoming lists or generic timelines | Equal-cost gain interval includes zero or favors the comparator |
| H3 | Authored content adds value beyond typed graph evidence | Graph+content fails to improve preregistered proper score/retrieval |
| H4 | Time-correct thread/event context improves over post-only evidence | Matched wrong-time/placebo context performs equally or better |
| H5 | Local structured features justify their compute/review cost beyond embeddings | No practical untouched-panel improvement or correction burden increases |
| H6 | The probability-audited novel-candidate cohort has measurable relevance/yield in non-center and low-coverage strata | Relevant-new-account precision/yield is negligible or coverage remains concentrated |
| H7 | Independent overlapping affinities beat compositional shares | No proper-score/retrieval gain on sealed Aditya judgments |
| H8 | Pre-\(t_0\) competence evidence predicts future/withheld independently reviewed artifacts | Retrieval is no better than affiliation, centrality, or prevalence baselines |

## Outcomes

Primary:

- the frozen IPW macro-AUPRC-versus-cost primary endpoint;

Safety guards:

- IPW Brier-loss and Recall@20 non-degradation; and
- labelability/selective-risk coverage.

Secondary:

- IPW Recall@K, log loss, calibration slope/intercept, and descriptive ECE;
- metric-versus-human-minute curves;
- low-degree, non-center, source, community, and time-stratum performance;
- realized versus predicted action value;
- IPW relevant-new-account precision, relevant yield per dollar, support rate,
  and source/coverage diversity for \(C_{\mathrm{new}}\);
- usable new edges/tweets/contexts per actual dollar;
- duplicate, empty, malformed, and stale return rates;
- dossier minutes and correction/supersession rates;
- competence Recall@K against future/withheld artifact review; and
- sensitivity to MCAR, degree, community, and capture-center masking.

Untouched offline policy intervals refit or cross-fit the full policy inside
each paired account bootstrap. Live ordinary intervals are descriptive; an
anytime-valid confidence sequence is required for performance futility.
Development data supports every choice. The sealed test opens once after all
spend and continuation decisions are final.

News, trend, and conversational context is reconstructed as of the post
timestamp. Later knowledge is excluded unless it is declared as a retrospective
feature and evaluated separately against time-matched and wrong-time controls.

## Stopping and failure rules

Stop without spending the remaining budget when:

- a registered anytime-valid futility boundary is crossed; without one,
  performance does not trigger early stopping;
- duplicate/empty/unusable yield breaches its frozen threshold;
- schema, endpoint, price, model, prompt, or ontology identity drifts;
- low-degree or non-center performance degrades materially;
- the next action can breach the reserve under worst-case cost;
- test leakage or provenance failure occurs; or
- the human-attention ceiling is reached.

Scientific falsification is a successful experiment outcome. Runtime,
identity, leakage, or serialization failure is an invalid run and must fail
loudly.

Opening the sealed test terminates the run and cannot authorize another batch.

## Batch report

After each batch, publish:

- actions attempted, selected probabilities, and exact receipts;
- evidence yield, duplicates, failures, dollars, compute time, and human time;
- remote/local execution, every transmitted payload component, and egress
  authorization;
- predicted and realized value by action type;
- development metrics with confidence intervals and stratified slices;
- examples that changed rankings and examples that changed nothing;
- remaining budgets and stopping-rule status; and
- the next queued batch and whether the current tranche authorization covers
  it.

No result is written to `docs/EXPERIMENT_LOG.md` until a measurement actually
runs. Negative results receive the same record as positive ones.
