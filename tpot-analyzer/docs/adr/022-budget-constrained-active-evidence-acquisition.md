# ADR 022: Budget-Constrained Active Evidence Acquisition

- Status: Accepted
- Date: 2026-07-26
- Group: Research acquisition / Inference
- Decider: Aditya (direction approved 2026-07-26; computational peers drafted
  the record)
- Related ADRs: 009, 014, 016, 019, 020, 021

## Issue

Community Archive contributors are a self-selected sample. The locally scraped
graph extends beyond them but is capture-centered: a small number of observed
accounts touch nearly every shadow edge, while most shadow nodes have only one
stored relationship.

Public X evidence can fill gaps, but it costs money. Human dossier review costs
time. Local and hosted model inference costs compute, latency, or money.
Existing acquisition ranks accounts using a fixed mixture of normalized NMF
entropy, boundary score, degree, novelty, coverage, and expected scrape time.
That heuristic does not choose an evidence type, price actual actions, or prove
that a purchase improves held-out discovery.

The system therefore needs an adaptive experimental policy, not a larger crawl.

## Decision

### Distinguish observation, interpretation, and judgment actions

Every candidate action is typed as one of:

1. **Observe:** acquire missing public evidence such as outgoing followings,
   incoming followers, profile, authored tweets, replies, quote/thread context,
   media, or a temporal refresh.
2. **Interpret:** transform existing evidence using embeddings, a local model,
   a hosted model, a reranker, or a statistical task head.
3. **Judge:** ask a human to review a dossier, investigate externally, or
   adjudicate a disagreement.

A local model may reduce representation uncertainty, but it does not create a
missing follow edge or recover a tweet that was never observed.

An atomic action is one request/page or a precommitted bundle with cursor,
maximum pages/items, and stop rule. Its record names target, action class,
evidence type, direction, window, context, provider/endpoint/model, and policy
version. Cost, propensity, and realized reward use this same unit.

### Optimize validated decision value under multiple budgets

Let \(D_t\) be evidence available after step \(t\), and let
\(L_{\mathrm{dev}}\) be repeatedly queried **development loss**, not a held-out
test statistic. Estimate each action's loss reduction:

\[
\widehat{G}_{\mathrm{loss}}(a)=
L_{\mathrm{dev}}(D_t)
-\mathbb{E}[L_{\mathrm{dev}}(D_t\cup X_a)]
\]

When target-loss reduction cannot yet be estimated, conditional mutual
information \(\lambda I(Z;X_a\mid D_t)\) may be used as a cheaper surrogate. It
is not added to loss reduction when \(Z\) is the same target, because that can
double-count information under proper log loss. The predictive distribution
for unobserved \(X_a\) is fit only on policy-development data or cross-fitted.

Select a small batch using an estimated knapsack/batch-policy approximation:

\[
\widehat{A}_t \approx \arg\max_{A}\sum_{a\in A}\widehat{G}_{\star}(a)
\]

subject to hard USD, compute-time, human-attention, provider, randomized
exploration, coverage/diversity, and deduplication constraints.

- The first term is positive only when expected development loss falls.
- \(\widehat{G}_{\star}\) is either registered loss reduction or its registered
  information surrogate, never both for the same target.
- The scalar development loss, surrogate choice/weight, strongest comparator,
  normalized cost interval, batch size, budgets, and stopping thresholds are
  frozen in the experiment manifest.
- Coverage, diversity, and redundancy remain constraints unless weights are
  learned entirely on policy-development data.

Entropy and disagreement may prioritize candidates, but success is measured by
proper scores, retrieval quality, calibration, robustness, and coverage on
development labels. The sealed test is opened once after every run decision is
final. An overconfident wrong model can lower entropy while making the map worse.

### Test and, if justified, use local-first inference

Where the benchmark passes registered quality/cost thresholds, route from local
embeddings to a fast graph-blind local extractor, calibrated statistical heads,
a stronger local model for selected ambiguity, a pinned hosted model for
measured failures/audits, and finally human review when it has higher expected
value.

Specific model names and prices live in versioned registries and experiment
manifests, not this ADR. A mutable tag such as `latest` is never sufficient
provenance.

### Exhaust local evidence before buying it again

Before a paid observation:

- reconcile the current versioned Community Archive snapshot;
- query local authored tweets, likes, replies, retweets, quotes, mentions,
  profiles, following/follower observations, and cached thread context;
- compute a content hash and duplicate estimate;
- identify the exact missing field or time window; and
- estimate worst-case cost from the current versioned price card.

The policy may still buy a duplicate-detection sample, but it must identify that
purpose explicitly.

### Keep evidence typed through evaluation

Following, followers, likes, retweets, replies, quotes, mentions, co-follows,
authored content, profile text, media, and temporal context are separate
modalities. Direction is preserved. Reply and quote stance is modeled rather
than treating interaction as endorsement.

Fixed weighted collapse remains a baseline. It is not assumed to be the
scientifically optimal graph.

Accounts discovered outside the frozen evaluation universe enter a separate
probability-audited prospective cohort. They do not expand the current test
set, and outside-support task predictions abstain pending evidence/human review.

### Preserve a randomized audit arm

Reserve a nonzero fraction of eligible actions for randomized exploration
across source, degree/capture-center, community/semantic, modality/direction,
and archive-coverage strata.

The exact fraction, strata, randomization seed, and batch size are frozen in
each experiment manifest. Record the probability with which each action was
selected. This estimates cost, yield, and capture bias and exposes a greedy
policy that deepens blind spots. It does not identify counterfactual trajectories
of whole adaptive policies with global retraining; confirmatory policy
comparison stays in untouched offline mask/reveal data unless a live
head-to-head design guarantees positivity.

### Record authoritative receipts

Every action attempt records target/modality/direction/window/cursor; policy,
score, and propensity; resolved provider/endpoint/model/runtime/output schema;
worst-case and actual usage; counts, yield, latency, and failure; response,
content, prompt, input/context, output, and snapshot identities; downstream
evaluation generation; and egress purpose, transmitted fields, policy, and
authorization, including prompts, schemas, labels/features, media, and metadata.
Weight digest, quantization, decoding, and seed are recorded
when exposed, otherwise explicitly `unavailable` or `not_disclosed`.

Estimated cost never substitutes for actual usage when the provider reports it.

### Recompute in small batches and stop early

Stop before the hard budget when:

- a preregistered anytime-valid confidence sequence crosses its futility
  boundary; otherwise interim performance intervals are descriptive and batch
  count is fixed;
- duplicate, empty, or unusable yield exceeds its threshold;
- response schema or pricing changes without a new manifest;
- low-degree or non-center performance degrades materially;
- the next action could breach the reserve under worst-case cost; or
- evaluation leakage or provenance failure invalidates the run.

Ordinary paired bootstrap intervals are reserved for untouched offline
evaluation, with the entire fitted policy rerun or cross-fitted inside each
replicate. They are not reused for adaptive live stopping.

## Local human-review flywheel

The review interface presents a provenance-rich dossier and hides model
recommendations until an initial judgment is saved. It supports search,
investigation notes, save/resume, `in | out | abstain`, confidence, and
superseding corrections.

After a judgment it may show development-set learning curves, prior/posterior
changes, realized surprise, and affected rankings. It must not repeatedly
reveal the sealed test set or claim progress when no measured improvement
occurred.

Historical interpretation reconstructs news, trend, and thread context as of
the post timestamp. Later knowledge is excluded unless explicitly registered
as a retrospective feature. Time-matched, wrong-time, and placebo ablations
test whether contextual gains are real rather than leakage.

The policy may optimize only the public constructs permitted by ADR 021.
Public availability does not authorize publishing private dossiers, reviewer
notes, sensitive inferred attributes, or unapproved account scores.

## Assumptions

1. Rich local accounts can support retrospective mask/reveal simulations.
2. Action cost and usable yield can be estimated well enough to rank small
   batches.
3. A randomized allocation is worth its opportunity cost because purely greedy
   collection reinforces current capture bias.
4. Local structured representations may add conditional value beyond ordinary
   embeddings, but this is unproven.
5. Human attention is likely to become binding before the nominal API budget.

## Positions Considered

Exhaustive crawl was rejected for cost/bias; degree/frontier-first and
entropy-only remain baselines but cannot choose modality or distinguish overlap
from uncertainty; fixed endpoint quotas cannot react to yield; and a
heterogeneous GNN does not repair missingness or leakage. Sequential value of
information was selected because its costs and stopping rules are falsifiable.

## Falsifiers

Reconsider or replace the policy if:

- on untouched offline policy evaluation it fails to beat random, degree-first,
  entropy-only, current frontier, and equal-cost fixed policies on the frozen
  performance-versus-cost endpoint;
- predicted gain fails the registered correlation threshold against realized
  loss reduction;
- most paid observations duplicate local evidence or return unusable pages;
- adaptive selection worsens low-degree, non-center, or source-stratified
  recovery;
- contextual local/hosted model features add no held-out value after latency
  and review cost;
- results are unstable across model, prompt, quantization, or taxonomy
  versions; or
- apparent context gains disappear under time-matched placebo or wrong-context
  controls.

## Consequences

### Positive

- Dollars, compute, and human review share an inspectable framework.
- Hosted inference may be replaceable if benchmark thresholds pass.
- Registered stopping and randomized audit make learning/bias visible.

### Costs and risks

- Queues, propensities, receipts, and sealed evaluation add complexity.
- Offline simulations can misestimate live API yield.
- Local models may be systematically wrong; valid JSON is not truth.
- Randomized exploration spends some budget on apparently suboptimal actions.

### Reuse and thin-slice boundary

- Keep `frontier_ranking` and `scripts/rank_frontier.py` as baseline candidate
  features.
- Extend `scripts/active_learning.py` as the first orchestrator instead of
  creating a parallel scheduler.
- Extend `enrichment_log` and existing budget guards with actual credits,
  modality, propensity, usable yield, egress, and provenance.
- Put existing fetchers and the thread cache behind typed action adapters.
- Reuse the Community Gold account deep-dive as the first dossier surface.

## Relationship to Earlier Decisions

- Implements ADR 016's undeveloped `cheapest_upgrade` task-head concept.
- Uses ADR 014 and ADR 021 for target semantics and sealed evaluation.
- Extends ADRs 019 and 020 provenance from data artifacts to acquisition and
  inference actions.
- Reuses ADR 009's immutable normalized labels; its entropy queue remains the
  baseline for tweet-level simulacrum curation.
- Supersedes the scientific acquisition policy in the 2026-03-23 Active
  Learning Loop spec. That document remains historical implementation context.

## Amendment — Plan / execute boundary (2026-07-31)

Before another paid action, acquisition is split into two artifacts:

1. a credential-free, read-only plan that pins target/action identities, the
   dated semantic price-card hash, worst-case integer-credit reserves, a hard
   USD cap, input-manifest hashes, and its own canonical hash; and
2. a separate executor that may run only an explicitly accepted plan hash and
   must record balance-before/after, HTTP/schema status, cursor, returned and
   usable counts, response hash, actual charge, and output snapshot identity
   per action.

A plan always contains `authorizes_execution=false`; possessing a valid plan
does not itself authorize network or spend. Price, schema, identity, holdout,
balance, reserve, or plan-hash drift stops before the next action. This closes
the observed failure mode in which a nominal dry run performed paid identity
lookups or a later page crossed an account-level cap.

The first concrete plan targets only the formative ontology test: 12 fixed
public profiles plus at most 20 recent tweets each, with a USD 0.03816
worst-case reserve under a USD 0.05 cap. Broad relationship acquisition waits
until the human questions and dossier evidence pass their registered
labelability/repeatability gates.

## Amendment — Unpriced balance telemetry reserve (2026-07-31)

The provider documents its balance endpoint but publishes no endpoint-specific
price. The revised plan therefore reserves 15 credits for each of the required
before/after checks without asserting that this is the actual charge. This
the current plan is `2470a84f…`: 3,846 credits (USD 0.03846); earlier unexecuted
plans `f352851e…` and `3c66b735…` remain superseded.

## Amendment — Inferred attributes stay local (2026-08-03)

- Status: Accepted by Aditya (same session as ADR-021's inferred-attribute
  amendment)

ADR-021 (as amended 2026-08-03) permits inferred attribute hypotheses.
This ADR's egress boundary is explicitly UNCHANGED by that: inferred
attributes — sensitive or not — remain in local private dossiers. They are
never published, exported, embedded in shared snapshots, or used for
automated outreach. Acquisition policy may use them to prioritize evidence
purchases; any outreach action remains a human reading a dossier and
deciding.
