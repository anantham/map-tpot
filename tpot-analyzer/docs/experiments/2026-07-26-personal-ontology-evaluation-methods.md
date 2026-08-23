# Personal-Ontology Evaluation and Sequential Methods Contract

- Date: 2026-07-26
- Status: Binding companion for the planned pilot; no spend authorized
- Parent:
  `docs/experiments/2026-07-26-budgeted-personal-ontology-local-first-pilot.md`

This document prevents a useful discovery exercise from being misreported as
population calibration or confirmatory science.

## Frozen evaluation universe

Before labels or policy fitting, the run manifest defines \(U_0\), the eligible
account universe at evidence cutoff \(t_0\), with:

- an ordered account-ID list and digest;
- exact inclusion/exclusion and candidate-generation rules;
- source-frame and evidence-cutoff identities;
- graph node-order/topology digests and compatibility generation; and
- ontology/task versions.

\(U_0\) is fixed across batches. Before probability sampling, preregister fixed
training/challenge identities and define
\(U_{\mathrm{eval}}=U_0\setminus U_{\mathrm{train/challenge}}\). Every
\(U_{\mathrm{eval}}\) account has positive final-test inclusion probability.
Task metrics estimate performance conditional on labelability under the fixed
dossier within \(U_{\mathrm{eval}}\), alongside coverage; they never claim
unconditional risk, all-\(U_0\) performance, or prevalence on all of X.

Retrospective mask/reveal additionally defines and hashes
\(U_{\mathrm{rich}}\subseteq U_{\mathrm{eval}}\), the accounts with the required
preexisting
modalities. Offline policy claims apply to this subuniverse and are not
generalized to sparse shadow nodes.

## Prospective expansion cohort

The run separately freezes novel-candidate generation rules and records every
deduplicated account outside \(U_0\) as \(C_{\mathrm{new}}\). Before seeing
candidate labels, draw a source/action/coverage-stratified probability audit
with known inclusion probabilities and blind-label a fixed dossier. Report IPW
relevant-candidate precision, relevant new accounts per dollar, and source/
coverage diversity. These are prospective secondary endpoints, not evidence
for counterfactual trajectories of unexecuted policies.

The manifest freezes a representation-specific out-of-support statistic and
threshold using training accounts only. Outside-support or below-minimum-
coverage candidates receive `abstain` plus human/evidence review; task-head
scores cannot be extrapolated to them as calibrated probabilities.

## Four separate panels

1. **Training/challenge panel:** purposive seeds, near-misses, bridges, and hard
   negatives. Useful for training and stress tests, never probability
   calibration or prevalence-sensitive claims.
2. **Probability evaluation panel:** one stratified sample without replacement
   from \(U_{\mathrm{eval}}\), then a disjoint randomized development/test
   allocation.
   Partition-specific inclusion probabilities
   \(\pi_{i,\mathrm{dev}},\pi_{i,\mathrm{test}}>0\) are recorded and used for
   Brier, log loss, AUPRC, and calibration.
3. **Policy panel:** a stratified probability sample of
   \(U_{\mathrm{rich}}\) drawn through the joint role allocation, with
   inclusion probabilities, then split before masking into policy-development
   and untouched policy-evaluation partitions.
4. **Extraction panel:** message/context packets with human evidence spans for
   schema and representation benchmarking. Packets remain clustered by account.

Before any panel is opened, fixed training/challenge identities are removed,
then one joint randomized allocation assigns each \(U_{\mathrm{eval}}\) account
exactly one stable evaluation/development role. Roles are mutually exclusive
across every group, task, ontology version, message packet, and artifact
outcome. Role-specific inclusion probabilities are recorded for every sampled
role; purposive challenge identities cannot enter an evaluation role.

For each group that receives a calibration claim, both development and test
must contain at least 20 labelable `in` and 20 labelable `out` judgments after
sampling. If the human budget cannot meet that minimum, narrow the ontology
before label reveal or report retrieval/challenge results without probabilities
or group-level calibration.

## Judgments, abstention, and blinding

The reviewer sees a versioned evidence dossier before any model suggestion.
Model identity/order is hidden and randomized in comparative review.

- Affiliation metrics are defined on labelable `in/out` accounts.
- `abstain` is never dropped silently or converted to `out`.
- Report labelability rate by stratum and selective risk versus retained
  coverage.
- If a group/stratum lacks both classes or the registered minimum count, AUPRC,
  Recall@K, or calibration for that slice is `undefined`, not zero.
- Superseding judgments preserve reviewer, evidence hash, and timestamp.

## Two one-use evaluation gates

The frozen \(U_{\mathrm{rich}}\) policy-evaluation partition is opened once
after the entire offline action policy is frozen. It scores H1/AUAC and may
promote that unchanged policy to the live pilot. Its outcomes cannot tune the
policy; any policy change requires a fresh policy-evaluation partition.

The separately sealed \(U_{\mathrm{eval}}\) probability test opens once after
live spend stops. It estimates final fixed task-head selective AUPRC, Brier/log
loss, calibration, Recall@K, and labelability coverage under the fixed \(t_0\)
evidence package. It does not score acquisition AUAC and cannot authorize
another batch. Further learning requires a fresh independently sampled test.

## Primary endpoint and multiplicity

Each run freezes one scalar primary endpoint. For the first affiliation-policy
run define \(m_j\) as IPW macro-AUPRC at normalized cost \(j/10\), then:

\[
\mathrm{AUAC}_{11}=\frac{1}{11}\sum_{j=0}^{10}m_j
\]

Here \(B\) is the registered adaptive-spend interval. At each grid point use the
metric after the last atomic action whose cumulative cost is at most \(jB/10\),
with no interpolation. A valid registered early stop carries its final metric
through the remaining grid points; an invalid run has no AUAC. The strongest
comparator is selected using policy-development data before the one-use
evaluation partition opens.

H1 passes only when the paired, sampling-stratified account-bootstrap lower 95%
bound for
\(\Delta\mathrm{AUAC}\) is above zero and the point improvement is at least
0.03. Secondary endpoints are tested in a frozen hierarchy and cannot rescue a
failed primary endpoint. A policy also fails safety if IPW Brier loss increases
by at least 0.02 or IPW macro Recall@20 decreases by at least 0.05 at the
terminal \(j=10\) grid point versus the strongest comparator.

“Brier improvement” always means a reduction. Calibration intercept and slope
with uncertainty are reported. Ten-bin equal-mass ECE is descriptive on the
pooled eligible panel and never selects models on sparse per-group strata.

## Offline policy comparison

H1 is confirmatory only on the one-use offline policy-evaluation partition. In
each paired, stratified bootstrap replicate, resample policy-development and
policy-evaluation accounts separately; fit the complete policy only on the
resampled development data and score it only on resampled evaluation accounts.
Evaluation outcomes never enter fitting or cross-fitting.

Live randomized probes do not identify alternative global-retraining
trajectories. They estimate action cost, usable yield, schema behavior, and
capture bias unless a separate randomized head-to-head design gives every
compared atomic action positive probability.

## Live sequential design

An atomic live action is either one request/page or a preregistered bundle
`(cursor, max_pages, max_items, stop_rule)`. Selection propensity, worst-case
cost, actual usage, and reward all attach to that unit.

The adaptive tranche has four fixed maximum batches and an exact 20% stratified
random audit drawn from the same tranche. Interim ordinary bootstrap intervals
are descriptive. Performance-based futility may stop spending only through a
preregistered anytime-valid confidence sequence; without that implementation,
only operational safety/invalidity rules stop early. Final confirmatory
H1 inference remains the earlier one-use policy-evaluation gate; the terminal
one-shot test reports only fixed task-head evaluation.

Operational yield fails when more than 50% of paid actions in a batch are
empty, duplicate, or unusable, or schema failure exceeds 5%. The action-value
model is not used adaptively unless its policy-evaluation Spearman correlation
with realized loss reduction is at least 0.20 and its account-bootstrap lower
95% bound exceeds zero.

## Local-model benchmark

Two panels prevent “200–500 examples” from mixing incompatible units:

- **Extraction:** 200–500 existing or newly reviewed message/context packets,
  split by account into extraction-development and untouched routing-evaluation
  partitions; evaluate schema validity, span precision/recall, correction
  burden, latency, and throughput.
- **Account:** disjoint probability-sampled routing-development and untouched
  routing-evaluation subsets, never test accounts. Purposive challenge accounts
  are separate unweighted stress tests and cannot enter the routing gate.

The manifest freezes model/runtime/template/quantization digests, cold versus
warm load, batch/concurrency, context-length bins, prompt-cache state, peak
resident/Metal memory, thermal/power condition, timeout/retry behavior, and JSON
repair policy. Any change creates a new treatment.

The benchmark has two gates. Slice 3 spends USD 0 and may only shortlist a local
treatment on extraction-development after at least 98% schema validity and both
micro-averaged token precision and recall of at least 0.90 for cited evidence
spans. The manifest pins the span tokenizer and matching rule. If no
authoritative cached hosted receipts exist, Slice 3 does not claim
non-inferiority or enable production routing.

The authorized USD 10 microtrial then spends at most USD 2 first on a pinned
hosted treatment over untouched routing-evaluation packets. The local
treatment, prompt, and schema are already frozen. Local extraction is
non-inferior
only when the upper one-sided paired 95% bound for
\((1-F1_{\mathrm{local}})-(1-F1_{\mathrm{hosted}})\) is below 0.02, where
\(F1\) is micro token F1 against human spans. The upper bound for local-minus-
hosted human correction rate must also be at most 0.10. Failure keeps routing
unchanged but does not invalidate the remaining schema/yield microtrial.

On routing-evaluation, the local treatment must also repeat the absolute 98%
schema-validity and 0.90 span-precision/recall floors. Extraction intervals
resample account clusters, never individual packets as if independent.

A packet counts as corrected when blind human review changes any extracted
categorical field or adds, removes, or changes any cited span. Even after packet
non-inferiority, the feature pipeline and task head selected only on account
routing-development must be frozen before untouched account
routing-evaluation. Production routing requires a paired-bootstrap lower 95%
bound above zero and at least 0.01 point gain in IPW macro AUPRC over embeddings
alone, while the upper bound for IPW Brier-loss increase remains below 0.02.
Challenge results remain unweighted diagnostics, and the sealed test remains
untouched.

## Human and dollar budgets

The 180-minute human ceiling is allocated before review:

| Activity | Minutes |
|---|---:|
| Ten-dossier timing calibration | 20 |
| Extraction adjudication | 60 |
| Account judgments | 80 |
| Disagreement/safety reserve | 20 |

Random exploration is paid from the USD 10 microtrial or USD 70 adaptive
tranche. The USD 20 monetary reserve remains an unspent safety margin: it is not
available to the selector, randomized audit, test enrichment, or an invalid
run. Test accounts receive one fixed, nonadaptive evidence package declared
before comparison from the \(t_0\) local snapshot; paid actions never target
sealed test accounts.

## Competence outcome

Competence features stop at \(t_0\). Evaluation uses a withheld artifact set,
future artifacts after \(t_0\), or blinded quality judgments that were not model
inputs. Retrieving an artifact already shown to the model is leakage, not
competence validation.

## Falsification and invalidity

- Failure of the primary effect or any safety guard falsifies policy promotion.
- Inadequate class counts remove calibration claims; they do not justify
  lowering the minimum after labels are visible.
- Missing inclusion probabilities invalidate population-weighted metrics.
- Test release, cross-split account reuse, unregistered payload egress, or
  adaptive ordinary-bootstrap stopping invalidates the run.
- Invalid runs preserve receipts and negative lessons but cannot support model
  or acquisition claims.
