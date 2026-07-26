# Publishing and Privacy Boundary

- Date: 2026-07-26
- Status: Active product boundary
- Parent: `docs/VISION.md`
- Governing decision: ADR 021

## Two user modes

**Power users** clone the repo, provide their own API keys where needed, and
shape a personal ontology. Local execution is the target default. Optional
remote inference and generation are explicit, record transmitted fields, and
must not be described as local-only.

**Casual users** may inspect a published snapshot containing explicitly
approved, non-sensitive affinity fields. Uncalibrated affinities are not
probabilities, and independently overlapping values need not sum to one.

## Casual snapshot experience

The intended lightweight flow is:

1. search for a handle;
2. look it up against a precomputed snapshot;
3. show separately scaled, clearly labeled affinities and the evidence-snapshot
   date;
4. optionally generate a shareable card; and
5. link to a simplified map.

An account can have strong affinity to both forecasting and local-LLM
communities. The interface must not force a sum-to-one percentage example.

If a handle is absent, the interface may explain how to contribute an X export
to Community Archive, contact the map owner, or run a separate local instance.
Contribution is voluntary; curiosity about a result must not become consent to
publish private analysis.

## Publishing workflow

Map production is intended to run locally. Current optional OpenRouter and
serverless generation paths can transmit selected prompt/context and must be
reported as remote actions. Publishing an approved snapshot consists of:

1. producing versioned analysis locally or through explicitly receipted remote
   actions;
2. exporting only approved fields with score semantics, ontology version,
   evidence version, community metadata, and layout identity;
3. serving a static/read-only lookup where possible; and
4. regenerating and redeploying a new immutable snapshot for updates.

Existing deployments may use site endpoints and optional serverless card
generation. These are operational APIs, not evidence that scientific inference
is local or that production has zero backend behavior.

## Publication gate

A field becomes publishable only after:

- explicit analyst approval;
- a non-sensitive construct and use;
- adequate calibration for the displayed semantics;
- evidence and model provenance checks;
- an ontology/evidence snapshot date; and
- review of licensing, platform policy, and deletion obligations.

Private dossiers, reviewer notes, competence estimates,
participation-interest evidence, sensitive ontologies, raw prompts, and
unapproved account judgments are excluded from the published snapshot. Any
authorized remote transmission must satisfy ADR 022's outbound-payload
allowlist and receipt.

## Artifact boundary

| Artifact | Published snapshot | Local analyst workspace |
|---|---|---|
| Approved community names and colors | Yes | Yes |
| Approved account affinities | Only after publication gate | Yes |
| Simplified layout | Optional | Full analysis |
| Public handles/display names | Only when approved | Yes |
| Raw tweet text and golden labels | No | Yes |
| Dossiers and reviewer history | No | Yes |
| LLM interpretation | No | Local or explicit remote provider |
| API keys and secrets | Never | Secret store/environment only |

## Open-source boundary

The current repository bundles framework and a specific TPOT analysis. If
multiple analysts need independent deployments, framework/data separation can
be proposed later. It is not required for the pilot and must not silently turn
one analyst's ontology into shared ground truth.
