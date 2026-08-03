# TPOT Analyzer Documentation Index

This index separates actively maintained docs from historical/planning docs so
contributors have a clear source of truth.

Last reviewed: 2026-08-01

## Start Here

| Document | Purpose |
|----------|---------|
| [Quick Start](guides/QUICKSTART.md) | Local setup and first run |
| [Playbook](PLAYBOOK.md) | End-to-end daily workflow (backend, frontend, verification) |
| [Vision](VISION.md) | Applied mission, evidence semantics, product and publication boundaries |
| [Publishing and Privacy Boundary](product/2026-07-26-publishing-and-privacy-boundary.md) | Publishable snapshot fields, local/remote disclosure, and private dossier boundary |
| [Personal-Ontology Implementation Plan](plans/2026-07-26-personal-ontology-active-discovery-implementation.md) | Current thin-slice sequence and entry/exit gates |
| [Worklog](WORKLOG.md) | Timestamped implementation history and rationale |
| [Roadmap](ROADMAP.md) | Living backlog and future work |

## Community Mapping & Labeling

| Document | Scope |
|----------|-------|
| [Labeling Model Spec](LABELING_MODEL_SPEC.md) | Operational guide for tweet tagging — dimensions, bits scale, community exemplars, ontology evolution |
| [Account Labeling Runbook](ACCOUNT_LABELING_RUNBOOK.md) | Step-by-step labeling workflow per account |
| [Twitter API Endpoints](TWITTERAPI_ENDPOINTS.md) | twitterapi.io endpoint map — tested endpoints, response structures, cost estimates |
| [Data Inventory](DATA_INVENTORY.md) | What data we have — archive, signals, engagement, holdout |

## Canonical Operational Docs

| Document | Scope |
|----------|-------|
| [Testing Methodology](TESTING_METHODOLOGY.md) | Current testing strategy and execution guidance |
| [Browser Binaries](diagnostics/BROWSER_BINARIES.md) | Playwright/browser setup in restricted environments |
| [Backend API Implementation](reference/BACKEND_IMPLEMENTATION.md) | Backend architecture summary (historical context + modular layout) |
| [Community Correctness Eval](reference/evals/phase1-community-correctness.md) | Phase 1 external-audit + human-review benchmark workflow |
| [Database Schema](reference/DATABASE_SCHEMA.md) | Storage model and table contracts |
| [Engineering Guardrails](reference/ENGINEERING_GUARDRAILS.md) | Empirical bug patterns mapped to invariants, tests, and migration policy |
| [Features Intent](reference/FEATURES_INTENT.md) | Product/architecture intent for major behaviors |
| [Enrichment Flow](reference/ENRICHMENT_FLOW.md) | Enrichment pipeline behavior and data movement |
| [Tuning Parameters](reference/TUNING_PARAMETERS.md) | Magic numbers and tunable constants across subsystems |

## Guides

| Guide | Purpose |
|-------|---------|
| [Quick Start](guides/QUICKSTART.md) | Setup and baseline commands |
| [GPU Setup](guides/GPU_SETUP.md) | Optional GPU acceleration setup |
| [Scrape Debugging](guides/SCRAPE_DEBUG.md) | Selenium/scraping troubleshooting |
| [Test Backend Workflow](guides/TEST_MODE.md) | Deterministic local backend data workflow |

## Module Documentation

| Area | Location |
|------|----------|
| Module docs index | [docs/modules/INDEX.md](modules/INDEX.md) |
| Formal proofs | [docs/proofs/](proofs/) |
| Conventions | [docs/CONVENTIONS.md](CONVENTIONS.md) |

## Architecture and Specs

| Area | Location |
|------|----------|
| ADRs | [docs/adr/](adr/) |
| Technical specs | [docs/specs/](specs/) |
| Design specs | [docs/superpowers/specs/](superpowers/specs/) |
| Current implementation plans | [docs/plans/](plans/) |
| Historical superpowers plans | [docs/superpowers/plans/](superpowers/plans/) |
| Diagnostics | [docs/diagnostics/](diagnostics/) |

### Design Specs (superpowers)

| Spec | Date | Status |
|------|------|--------|
| [Active Learning Loop](superpowers/specs/2026-03-23-active-learning-loop-design.md) | 2026-03-23 | Historical implementation context; scientific acquisition policy superseded by ADR 022 |
| [Prior Improvement Roadmap](superpowers/specs/2026-03-22-prior-improvement-roadmap-design.md) | 2026-03-22 | Tier A+B complete, Tier C in progress |
| [Community Detail Pages](superpowers/specs/2026-03-21-community-detail-pages-design.md) | 2026-03-21 | Shipped |
| [JIT Collectible Cards](superpowers/specs/2026-03-19-jit-collectible-cards-design.md) | 2026-03-19 | Shipped |
| [Find My Ingroup](superpowers/specs/2026-03-19-find-my-ingroup-design.md) | 2026-03-19 | Shipped — maptpot.vercel.app |

### ADRs

- [ADR 022: Budget-Constrained Active Evidence Acquisition](adr/022-budget-constrained-active-evidence-acquisition.md) (Accepted, 2026-07-26)
- [ADR 021: Independent Overlapping Membership and Evidence Semantics](adr/021-independent-overlapping-membership-and-evidence-semantics.md) (Accepted; amended 2026-08-01 with extensional working-tag, frozen-extension, and target-scoped-display boundaries)
- [ADR 020: Graph Artifact Compatibility](adr/020-graph-artifact-compatibility.md) (Accepted, 2026-07-26)
- [ADR 019: Versioned Research Data and Artifact Manifests](adr/019-versioned-research-data-and-artifact-manifests.md) (Accepted, 2026-07-26)
- [ADR 018: Propagation Engine and Confidence Scoring](adr/018-propagation-engine-and-confidence.md) (Accepted decision; amended 2026-07-28 and 2026-07-30; current solver contracts remain falsified, and independent display bands now fail closed after invalid entropy and artifact skew were measured)
- [ADR 017: Multi-View Account Descriptor](adr/017-multi-view-account-descriptor.md) (Revised; graph-only membership claims partially superseded by ADR 021)
- [ADR 016: Four-Part Epistemic Architecture](adr/016-four-part-epistemic-architecture.md)
- [ADR 015: Data Pipeline Architecture](adr/015-data-pipeline-architecture.md) (Accepted, 2025-09-05)
- [ADR 014: Account-Community Gold Labels](adr/014-account-community-gold-labels-and-held-out-evaluation.md)
- [ADR 013: Probabilistic Cluster Color Contract](adr/013-probabilistic-cluster-color-contract.md) (Accepted; amended 2026-07-28; probability/confidence semantics superseded by ADR 021; current chroma is a heuristic rendering score)
- [ADR 012: Community-Seeded Cluster Navigation](adr/012-community-seeded-cluster-navigation.md) (Proposed; amended 2026-07-28; probability/confidence portions superseded by ADR 021)
- [ADR 011: Content-Aware Fingerprinting](adr/011-content-aware-fingerprinting-and-community-visualization.md) (Proposed; amended 2026-07-28; probability/certainty semantics superseded by ADR 021; historical heading-number typo recorded)
- [ADR 010: Labeling Dashboard and LLM Eval Harness](adr/010-labeling-dashboard-and-llm-eval-harness.md)
- [ADR 009: Golden Curation Schema](adr/009-golden-curation-schema-and-active-learning-loop.md)
- [ADR 008: Tweet-Level LLM Classification](adr/008-tweet-classification-account-fingerprinting.md)
- [ADR 007: Observation-Aware Clustering](adr/007-observation-aware-clustering-membership.md) (Proposed; amended 2026-07-28; GRF semantics partially superseded by ADR 021; MAR/IPW assumption remains unvalidated)
- [ADR 006: Shared Tagging and TPOT Membership](adr/006-shared-tagging-and-tpot-membership.md) (Proposed; per-ego concept adopted and single-target semantics superseded by ADR 021; Postgres not approved)
- [ADR 005: Blob Storage Import](adr/005-blob-storage-import.md) (Implemented, 2025-11-08)
- [ADR 004: Precomputed Graph Snapshots](adr/004-precomputed-graph-snapshots.md)
- [ADR 003: Backend API Integration](adr/003-backend-api-integration.md)
- [ADR 002: Graph Analysis Foundation](adr/002-graph-analysis-foundation.md)
- [ADR 001: Spectral Clustering Visualization](adr/001-spectral-clustering-visualization.md) (Proposed, 2024-12-05)

### Handover & Session Context

| Document | Notes |
|----------|-------|
| [Session 8 Handover](HANDOVER_SESSION8.md) | Historical implementation state; four-band counts and export guidance are superseded by ADR 018's 2026-07-30 fail-closed amendment |
| [Session 8 Ideas Inventory](SESSION8_IDEAS_INVENTORY.md) | 70+ ideas captured during session 8 |
| [Iconography System](TPOT_TAROT_ICONOGRAPHY_v2.md) | Community tarot/symbol system for card generation |
| [Vision](VISION.md) | Product vision and distribution model |

## Testing and QA Docs

| Document | Notes |
|----------|-------|
| [Testing Methodology](TESTING_METHODOLOGY.md) | Primary testing guide |
| [Frozen Membership and Discoverability Audit](experiments/2026-07-26-membership-discoverability-audit.md) | 2026-07-26 methods, falsifiers, results, limits, and reproduction commands |
| [Budgeted Personal-Ontology Pilot](experiments/2026-07-26-budgeted-personal-ontology-local-first-pilot.md) | Planned local-first benchmark and USD 100 acquisition protocol; no spend authorized |
| [Dharma Boundary Pretrial](experiments/2026-07-31-dharma-boundary-pretrial.md) | Fixed 12-account, two-pass formative wording test and pre-data evidence cap |
| [Personal-Ontology Evaluation Methods](experiments/2026-07-26-personal-ontology-evaluation-methods.md) | Frozen universe, probability sampling, abstention, one-shot test, sequential inference, and benchmark contract |
| [Test Audit](TEST_AUDIT.md) | Historical audit snapshot (see note below) |
| [Test plans](test-plans/) | Feature-level testing plans |

## Historical / Planning Notes

- `docs/TEST_AUDIT.md` is a point-in-time audit and may not reflect current
  test counts or file inventory.
- `docs/tasks/E2E_TESTS.md` is a historical task brief; see its
  "Modernization Note (2026-02-09)" for current runnable commands.
- `docs/archive/BUGFIXES.md` records 2025-era fixes; use its 2026 historical
  note for current backend entrypoint guidance.
- `docs/tasks/` contains implementation task briefs and design plans; many are
  historical and should be cross-checked against current code/worklog.
- `docs/PROPAGATION_ANALYSIS.md`,
  `docs/SESSION10_IDEAS_INVENTORY.md`, and the four-band sections of
  `docs/HANDOVER_SESSION8.md` preserve March 2026 experiment/history. Their
  raw-score thresholds, “naturally calibrated” claim, band counts, and export
  instructions are superseded by ADR 018's 2026-07-30 amendment and EXP-024;
  do not use them to regenerate or publish independent-Lift bands.
- Older `docs/plans/` and `docs/archive/` entries may be historical. The
  2026-07-26 personal-ontology plan and its
  [refactor ledger](plans/2026-07-26-personal-ontology-refactor-ledger.md) are
  active.

## Doc Hygiene

- When adding or moving docs, update this index and `docs/WORKLOG.md`.
- Prefer subfolders under `docs/` over adding new root-level markdown files.
- Mark superseded docs here explicitly rather than leaving silent drift.
- `docs/PROJECT_STRUCTURE.md` is referenced by `AGENTS.md` but missing; the
  active refactor ledger tracks the repair without inventing a replacement.

- `product/2026-08-03-tagging-workspace-ux-feedback.md` — operator UX feedback on the tagging workspace, ordered P1–P3 (layout, polarity grouping, tag autocomplete, per-tag meta-notes). Recorded 2026-08-03, pre-implementation.
