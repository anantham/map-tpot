# ADR 021: Independent Overlapping Membership and Evidence Semantics

- Status: Accepted
- Date: 2026-07-26
- Group: Research semantics / Personal ontology
- Decider: Aditya (direction approved 2026-07-26; computational peers drafted
  the record)
- Related ADRs: 006, 009, 014, 016, 017, 018, 019, 020

## Issue

The repository currently uses the word “membership” for several different
quantities:

1. NMF shares that are normalized to sum to one;
2. graph-propagation scores and Lift values;
3. human account/community judgments;
4. content, posture, and simulacrum descriptors; and
5. confidence derived partly from how much evidence happens to be available.

These quantities do not have the same semantics. The 2026-07-26 frozen audit
also rejected the predictive and calibration claims needed to call the current
scores probabilities. Meanwhile, the intended communities genuinely overlap:
someone may participate in contemplative practice, local LLM work, forecasting,
and interface design at the same time.

The system needs one explicit target meaning before changing the producer,
calibration, API wording, or interface.

## Decision

### Use a shared evidence substrate and user-scoped ontologies

Research generations and observation history are additive and versioned.
Operational caches may use append/replace semantics, but a run consumes an
immutable snapshot \(E_t\). Explicit deletion, redaction, and tombstone events
remain possible; absence alone never implies deletion. Typed views and
graph-blind semantic descriptors are separately versioned. Each analyst \(u\)
owns:

- a versioned ontology \(O_u^v\);
- immutable judgments \(J_u\) that may supersede earlier judgments;
- task-specific models and calibration records; and
- private or explicitly shared notes and boundary definitions.

Changing a group definition, splitting a group, or merging groups creates a new
ontology version. It does not silently reinterpret historical judgments.

### Keep the target quantities separate

For account \(i\), group \(g\), and user \(u\), estimate separate task heads:

\[
\begin{aligned}
p_u(M_{ig}\mid V_t,S_i,Q_i,O_u^v,J_{u,\mathrm{train}}^{<t}),\\
p_u(C_{ig}\mid V_t,S_i,Q_i,O_u^v,J_{u,\mathrm{train}}^{<t}),\\
p_u(R_{ig}\mid V_t,S_i,Q_i,O_u^v,J_{u,\mathrm{train}}^{<t})
\end{aligned}
\]

where:

- \(M_{ig}\): affiliation or participation in group \(g\);
- \(C_{ig}\): observable domain competence or contribution;
- \(R_{ig}\): publicly expressed participation interest, not inferred
  availability or readiness;
- \(V_t\): separately typed content, interaction, graph, profile, artifact, and
  temporal-context views of snapshot \(E_t\);
- \(S_i\): separately versioned observable topic, stance, cadence, posture,
  and message-level descriptors; and
- \(Q_i\): observed coverage, provenance, freshness, and missingness metadata
  on which task estimates are conditioned; and
- \(J_{u,\mathrm{train}}^{<t}\): only training judgments available before the
  prediction time, never development or test judgments.

The group-specific quantities are independently overlapping. They do not sum to
one. A high score for one group does not mathematically reduce another.

Until a task head is calibrated on untouched account-level labels, its output
must be called an **affinity**, **score**, or **evidence estimate**, not a
probability.

### Preserve ambiguity and missingness

- Missing evidence is unknown, not negative evidence.
- `abstain` is distinct from missing and from `out`.
- Multiple high affiliations may describe a bridge rather than uncertainty.
- Coverage confidence must not be folded into affiliation or competence.
- A model may preserve multiple plausible interpretations instead of forcing a
  dominant label.

### Separate representation from decision

Semantic descriptor extraction receives neither current graph communities,
user labels, nor the answer it will later help predict. Graph remains a
separate typed view. Graph-aware and ontology-aware reasoning belongs in task
heads.

This prevents “the model guessed the community because the prompt told it the
community” from being stored as independent content evidence.

### Make human judgments inspectable and reversible

Every judgment records:

- user/reviewer and ontology version;
- account, group, task, and `in | out | abstain` judgment;
- confidence and notes;
- evidence snapshot and context hash;
- observation and judgment timestamps; and
- the prior judgment it supersedes, if any.

Corrections append history. They do not overwrite the earlier take.

### Protect evaluation integrity

- Splits remain per stable account identity across every group, task, and
  ontology version.
- Training may use only train judgments.
- Development labels support selection and calibration.
- A test generation is released once, only after every model, policy, stopping,
  and continuation decision for the run is final.
- Explicit negatives, hard near-misses, bridges, and abstentions are required.
- Repeated inspection invalidates the run; further work requires a fresh,
  independently sealed test generation.

## Rationale

This semantics matches the product need: discover evidence-backed candidates
for a user's contingent community-building objective while allowing another
user to carve the same public evidence differently.

It also makes disagreements diagnostic. Social proximity, authored content,
taste, interaction style, competence, and participation interest can disagree
without one of them being an error.

## Assumptions

1. Communities overlap in ways a simplex cannot represent.
2. Affiliation and competence can correlate but are not interchangeable.
3. A user's operational boundary can be useful without becoming universal
   ground truth.
4. Explicit negatives and abstentions can be collected at sufficient volume to
   calibrate useful task heads.
5. Shared descriptors can remain useful across ontology versions when their
   extraction is blind to those ontologies.

## Constraints

- Do not infer private belief, intelligence, gender identity, developmental
  attainment, enlightenment, or “Kegan stage” from public posts.
- Simulacrum is a probabilistic annotation of an observed message in context,
  not a fixed trait of an account.
- Competence requires domain-specific observable evidence such as shipped code,
  resolved forecasts, technical artifacts, sustained public work, or
  independently reviewed contributions. Centrality and fluent prose are not
  substitutes.
- Competence evaluation uses future or withheld artifacts and blinded quality
  judgments that were unavailable to the model; input artifacts cannot also be
  outcome truth.
- The frozen propagation bundle remains a reproducible control, not current
  membership truth.

## Positions Considered

### Compositional NMF shares

Retained as an interpretable exploratory view and baseline. Rejected as the
universal membership semantics because unrelated communities compete for a
fixed total.

### Hard clustering

Retained for navigation and visualization. Rejected as the account ontology.

### Graph proximity as membership truth

Retained as one observation and retrieval baseline. Rejected as a universal
definition because graph capture is source-biased and social proximity differs
from intellectual orientation.

### One combined talent score

Rejected. It hides the distinction between affiliation, contribution,
availability, and evidence coverage and creates unsafe false precision.

### Independent user-scoped task heads

Accepted. It preserves overlap, provenance, correction history, and multiple
legitimate maps over shared evidence.

## Falsifiers

Reconsider the **semantic decision** if reliable blind human judgments show
that the target groups are operationally mutually exclusive; reviewers cannot
reliably distinguish affiliation, competence, public participation interest,
and coverage; or an equivalent-evidence simplex or hierarchy is consistently
better calibrated than independent overlap.

The following falsify a model or experiment, not the semantics by themselves:
failure to beat prevalence, degree, graph-only, content-only, and compositional
baselines; unusable calibration after explicit negatives; collapse under seed
deletion, time/source/ontology splits, or degree-biased censoring; failed
competence retrieval against independently reviewed artifacts; or poor
descriptor transfer across ontology versions.

## Consequences

### Positive

- Membership copy and API fields gain a precise meaning.
- Different users can maintain different maps without duplicating raw evidence.
- Bridges, abstentions, corrections, and coverage are first-class.
- Evaluation can distinguish model uncertainty from missing evidence.

### Costs and risks

- More task heads and version identifiers increase schema and UI complexity.
- Explicit negatives and domain-specific competence review require human time.
- Existing outputs need migration labels so compositional shares, Lift, and
  calibrated probabilities cannot be confused.

### Reuse and migration boundary

- Extend `src/data/community_gold/` through a versioned migration with user,
  ontology, task, and evidence-version fields; do not create a competing
  account-judgment store.
- Reuse `GoldLabelPanel.jsx`, `GoldLabelHistory.jsx`, `GoldScorecard.jsx`, and
  `AccountDeepDiveLeftColumn.jsx` for account-level candidates, blind judgment,
  history, and evaluation.
- Keep `src/data/golden/` for message-level style annotations.
- Keep `AccountTagStore` and `AccountTagPanel` as ego-scoped working-label
  compatibility surfaces, not gold truth.
- Use local SQLite for the pilot. Shared storage and tenancy require a separate
  decision.

## Relationship to Earlier Decisions

- Adopts ADR 006's per-ego labeling and explanation concept, but does not
  approve its proposed shared-Postgres migration. It supersedes ADR 006's
  single binary `p_tpot` target.
- Implements ADR 016's evidence-view-descriptor-task-head architecture.
- Uses ADR 014's account-level split and immutable judgment contract.
- Reuses ADR 009's normalized immutable message-label pattern; its
  tweet-simulacrum queue remains a baseline for that separate task.
- Partially supersedes ADR 017's graph-only detection and 100%-recall claims.
- Partially supersedes ADR 018's concentration/agreement interpretation as
  confidence. Its frozen engine remains a control.
- Requires ADRs 019 and 020 provenance for every evidence and model generation.
