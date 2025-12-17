# TPOT Analyzer Documentation

TPOT Analyzer is a social graph analysis tool for exploring Twitter/X community structure through spectral clustering and interactive visualization.

---

## Quick Start

**New here?** Start with the [Quick Start Guide](guides/QUICKSTART.md) to get running in 10 minutes.

---

## Guides

Step-by-step instructions for common tasks:

| Guide | Description |
|-------|-------------|
| [Quick Start](guides/QUICKSTART.md) | Get up and running locally |
| [GPU Setup](guides/GPU_SETUP.md) | Enable CUDA for faster spectral computation |
| [Scrape Debugging](guides/SCRAPE_DEBUG.md) | Troubleshoot Twitter scraping issues |
| [Test Mode](guides/TEST_MODE.md) | Run with mock data for development |

---

## Reference

Technical documentation and specifications:

| Document | Description |
|----------|-------------|
| [Database Schema](reference/DATABASE_SCHEMA.md) | SQLite table structures |
| [Enrichment Flow](reference/ENRICHMENT_FLOW.md) | How Twitter data flows through the system |
| [Backend API](reference/BACKEND_IMPLEMENTATION.md) | Flask routes and endpoints |
| [Features Intent](reference/FEATURES_INTENT.md) | Design rationale for features |
| [Performance](reference/PERFORMANCE_PROFILING.md) | Profiling and optimization |

---

## Architecture

Design decisions and specifications:

- **ADRs**: [Architecture Decision Records](adr/) — Why we built things this way
- **Specs**: [Technical Specifications](specs/) — Detailed feature specs
- **Plans**: [Historical Plans](plans/) — Past planning documents

---

## Tasks (for AI/Codex)

Implementation task documents with copy-paste code:

| Task | Effort | Status |
|------|--------|--------|
| [Clustering Features](tasks/CLUSTERING_FEATURES.md) | 8-12h | Ready |
| [E2E Tests](tasks/E2E_TESTS.md) | 6-8h | Ready |
| [UI Aesthetics](tasks/UI_AESTHETICS.md) | 10-14h | Ready |

---

## Testing

- [Test Audit Report](TEST_AUDIT.md) — Analysis of test suite health
- [Test Plans](test-plans/) — Detailed test specifications

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for planned features and priorities.

---

## Archive

Historical documents moved to [archive/](archive/) for reference.
