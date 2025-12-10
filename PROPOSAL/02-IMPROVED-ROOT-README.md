# Twitter/X Network Analysis Tools

A toolkit for exploring Twitter/X social networks, community structures, and LLM memorization of social media content. Built for researchers, community archivists, and curious explorers.

---

## What's Inside

### [tpot-analyzer](./tpot-analyzer/) — Community Graph Explorer

Visualize and analyze the TPOT (This Part of Twitter) community network:

- **Interactive Graph Explorer** — Force-directed visualization with real-time metric computation
- **PageRank & Betweenness** — Identify influential accounts using network centrality metrics
- **Community Detection** — Discover clusters using Louvain algorithm
- **Shadow Enrichment** — Expand the graph beyond the base dataset via Selenium scraping

Built on the [Community Archive](https://communityarchive.org) dataset: 6.9M tweets, 12.3M likes, and 275+ fully archived accounts.

**Quick start:**
```bash
cd tpot-analyzer
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.start_api_server &
cd graph-explorer && npm install && npm run dev
# Open http://localhost:5173
```

### [grok-probe](./grok-probe/) — LLM Memorization Tester

Test whether Grok-family language models can regurgitate archived tweets when prompted with partial text. Uses LLM memorization as a novel interface for extracting Twitter data from model weights.

**Quick start:**
```bash
cd grok-probe
npm install
OPENROUTER_API_KEY=sk-or-... npm start
# Open http://localhost:5173
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Community Archive                            │
│                    (Supabase PostgreSQL, public)                     │
│         6.9M tweets • 12.3M likes • 275 archived accounts           │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         tpot-analyzer                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Data Fetcher │→→│ SQLite Cache │→→│ Graph Builder + Metrics  │  │
│  │ (Supabase)   │  │ (cache.db)   │  │ (NetworkX)               │  │
│  └──────────────┘  └──────────────┘  └────────────┬─────────────┘  │
│                                                    │                 │
│  ┌──────────────────────────────────┐             │                 │
│  │ Shadow Enrichment (Selenium)     │─────────────┤                 │
│  │ Expands graph via web scraping   │             │                 │
│  └──────────────────────────────────┘             ▼                 │
│                                        ┌──────────────────────┐     │
│                                        │ Flask API (:5001)    │     │
│                                        └──────────┬───────────┘     │
└─────────────────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Graph Explorer (React + Vite)                     │
│                         http://localhost:5173                        │
│    Interactive visualization • Seed selection • Metric sliders      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.9+ | Backend, analysis |
| Node.js | 18+ | Frontends |
| Git | Any | Clone repository |
| Chrome | Latest | Selenium (optional) |

---

## Documentation

### Getting Started
- **[Getting Started Guide](./GETTING-STARTED.md)** — From zero to graph explorer in 15 minutes
- **[Glossary](./GLOSSARY.md)** — Project terminology explained

### Architecture & Design
- **[ADR 001: Data Pipeline](./tpot-analyzer/docs/adr/001-data-pipeline-architecture.md)** — Why API-first + SQLite cache
- **[ADR 002: Graph Analysis](./tpot-analyzer/docs/adr/002-graph-analysis-foundation.md)** — Metric computation design
- **[ADR 003: Backend Integration](./tpot-analyzer/docs/adr/003-backend-api-integration.md)** — Flask API decisions

### Technical Reference
- **[Database Schema](./tpot-analyzer/docs/DATABASE_SCHEMA.md)** — Complete data model documentation
- **[Enrichment Flow](./tpot-analyzer/docs/ENRICHMENT_FLOW.md)** — Selenium scraping pipeline
- **[Backend Implementation](./tpot-analyzer/docs/BACKEND_IMPLEMENTATION.md)** — API endpoints and performance

### Operations
- **[Test Coverage](./tpot-analyzer/docs/test-coverage-baseline.md)** — Current test status
- **[Roadmap](./tpot-analyzer/docs/ROADMAP.md)** — Planned features and improvements
- **[Worklog](./tpot-analyzer/docs/WORKLOG.md)** — Development history

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

Quick contribution path:
1. Fork the repository
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Make changes with tests
4. Submit a pull request

---

## Security

This project handles sensitive data (cookies, API tokens). See [SECURITY.md](./SECURITY.md) for:
- Secrets management
- Safe scraping practices
- What NOT to commit

---

## License

No license file is currently provided. Add one before distributing or open-sourcing.

---

## Acknowledgments

- **Community Archive** — For making TPOT data accessible
- **TPOT Community** — For being interesting enough to map
- **NetworkX** — Graph analysis foundation
- **d3-force** — Visualization engine

---

*Built with computational peers and human collaborators.*
