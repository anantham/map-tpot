# TPOT Analyzer Documentation Index

This index separates actively maintained docs from historical/planning docs so
contributors have a clear source of truth.

Last reviewed: 2026-02-18

## Start Here

| Document | Purpose |
|----------|---------|
| [Quick Start](guides/QUICKSTART.md) | Local setup and first run |
| [Playbook](PLAYBOOK.md) | End-to-end daily workflow (backend, frontend, verification) |
| [Worklog](WORKLOG.md) | Timestamped implementation history and rationale |
| [Roadmap](ROADMAP.md) | Living backlog and future work |

## Canonical Operational Docs

| Document | Scope |
|----------|-------|
| [Testing Methodology](TESTING_METHODOLOGY.md) | Current testing strategy and execution guidance |
| [Browser Binaries](diagnostics/BROWSER_BINARIES.md) | Playwright/browser setup in restricted environments |
| [Backend API Implementation](reference/BACKEND_IMPLEMENTATION.md) | Backend architecture summary (historical context + modular layout) |
| [Database Schema](reference/DATABASE_SCHEMA.md) | Storage model and table contracts |
| [Engineering Guardrails](reference/ENGINEERING_GUARDRAILS.md) | Empirical bug patterns mapped to invariants, tests, and migration policy |
| [Features Intent](reference/FEATURES_INTENT.md) | Product/architecture intent for major behaviors |
| [Enrichment Flow](reference/ENRICHMENT_FLOW.md) | Enrichment pipeline behavior and data movement |

## Guides

| Guide | Purpose |
|-------|---------|
| [Quick Start](guides/QUICKSTART.md) | Setup and baseline commands |
| [GPU Setup](guides/GPU_SETUP.md) | Optional GPU acceleration setup |
| [Scrape Debugging](guides/SCRAPE_DEBUG.md) | Selenium/scraping troubleshooting |
| [Test Backend Workflow](guides/TEST_MODE.md) | Deterministic local backend data workflow |

## Architecture and Specs

| Area | Location |
|------|----------|
| ADRs | [docs/adr/](adr/) |
| Technical specs | [docs/specs/](specs/) |
| Diagnostics | [docs/diagnostics/](diagnostics/) |

Latest architecture decision:
- [ADR 007: Observation-Aware Clustering and Membership Inference](adr/007-observation-aware-clustering-membership.md) (Proposed, 2026-02-17)
- [ADR 006: Shared Tagging and Anchor-Conditioned TPOT Membership](adr/006-shared-tagging-and-tpot-membership.md) (Proposed, 2026-02-10)

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
