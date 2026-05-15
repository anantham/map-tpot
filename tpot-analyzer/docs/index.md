# TPOT Analyzer Documentation Index

This index separates actively maintained docs from historical/planning docs so
contributors have a clear source of truth.

Last reviewed: 2026-03-26

## Start Here

| Document | Purpose |
|----------|---------|
| [Quick Start](guides/QUICKSTART.md) | Local setup and first run |
| [Playbook](PLAYBOOK.md) | End-to-end daily workflow (backend, frontend, verification) |
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
| Implementation plans | [docs/superpowers/plans/](superpowers/plans/) |
| Diagnostics | [docs/diagnostics/](diagnostics/) |

### Design Specs (superpowers)

| Spec | Date | Status |
|------|------|--------|
| [Active Learning Loop](superpowers/specs/2026-03-23-active-learning-loop-design.md) | 2026-03-23 | In progress — pipeline built, first 5 accounts labeled |
| [Prior Improvement Roadmap](superpowers/specs/2026-03-22-prior-improvement-roadmap-design.md) | 2026-03-22 | Tier A+B complete, Tier C in progress |
| [Community Detail Pages](superpowers/specs/2026-03-21-community-detail-pages-design.md) | 2026-03-21 | Shipped |
| [JIT Collectible Cards](superpowers/specs/2026-03-19-jit-collectible-cards-design.md) | 2026-03-19 | Shipped |
| [Find My Ingroup](superpowers/specs/2026-03-19-find-my-ingroup-design.md) | 2026-03-19 | Shipped — maptpot.vercel.app |

### ADRs

- [ADR 015: Data Pipeline Architecture](adr/015-data-pipeline-architecture.md) (Accepted, 2025-09-05)
- [ADR 014: Account-Community Gold Labels](adr/014-account-community-gold-labels-and-held-out-evaluation.md)
- [ADR 013: Probabilistic Cluster Color Contract](adr/013-probabilistic-cluster-color-contract.md) (Accepted, 2026-03-06)
- [ADR 012: Community-Seeded Cluster Navigation](adr/012-community-seeded-cluster-navigation.md)
- [ADR 011: Content-Aware Fingerprinting](adr/011-content-aware-fingerprinting-and-community-visualization.md)
- [ADR 010: Labeling Dashboard and LLM Eval Harness](adr/010-labeling-dashboard-and-llm-eval-harness.md)
- [ADR 009: Golden Curation Schema](adr/009-golden-curation-schema-and-active-learning-loop.md)
- [ADR 008: Tweet-Level LLM Classification](adr/008-tweet-classification-account-fingerprinting.md)
- [ADR 007: Observation-Aware Clustering](adr/007-observation-aware-clustering-membership.md)
- [ADR 006: Shared Tagging and TPOT Membership](adr/006-shared-tagging-and-tpot-membership.md)
- [ADR 005: Blob Storage Import](adr/005-blob-storage-import.md) (Implemented, 2025-11-08)
- [ADR 004: Precomputed Graph Snapshots](adr/004-precomputed-graph-snapshots.md)
- [ADR 003: Backend API Integration](adr/003-backend-api-integration.md)
- [ADR 002: Graph Analysis Foundation](adr/002-graph-analysis-foundation.md)
- [ADR 001: Spectral Clustering Visualization](adr/001-spectral-clustering-visualization.md) (Proposed, 2024-12-05)

### Handover & Session Context

| Document | Notes |
|----------|-------|
| [Session 8 Handover](HANDOVER_SESSION8.md) | Comprehensive state — 18+ commits, Tier A+B, propagation fix |
| [Session 8 Ideas Inventory](SESSION8_IDEAS_INVENTORY.md) | 70+ ideas captured during session 8 |
| [Iconography System](TPOT_TAROT_ICONOGRAPHY_v2.md) | Community tarot/symbol system for card generation |
| [Vision](VISION.md) | Product vision and distribution model |

## Testing and QA Docs

| Document | Notes |
|----------|-------|
| [Testing Methodology](TESTING_METHODOLOGY.md) | Primary testing guide |
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
- `docs/plans/` and `docs/archive/` are historical context, not canonical run
  instructions.

## Doc Hygiene

- When adding or moving docs, update this index and `docs/WORKLOG.md`.
- Prefer subfolders under `docs/` over adding new root-level markdown files.
- Mark superseded docs here explicitly rather than leaving silent drift.
