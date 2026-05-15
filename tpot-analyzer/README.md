# TPOT Community Map

Discovers and maps the TPOT (This Part of Twitter) community using the [Community Archive](https://community-archive.org) dataset. Combines follow graph analysis, engagement signals, and label propagation to classify ~200K accounts into 15 named communities across 4 confidence bands.

**Live site:** [maptpot.vercel.app](https://maptpot.vercel.app)

The repo has three main surfaces:
- **Public site** (`public-site/`) — Lightweight React app for searching accounts and browsing communities
- **Graph explorer** (`graph-explorer/`) — Rich React + d3-force app with cluster view, labeling UI, gold label curation, account deep dive, and discovery
- **Flask API** (`src/api/`) — Backend powering the graph explorer with 11 blueprint modules (graph, analysis, discovery, accounts, communities, clusters, golden, labeling, etc.)

## How It Works

```
Community Archive (Supabase)
        │
        ├── follow edges (420K)
        ├── mention graph (10.5M mentions)
        ├── quote graph (683K quotes)
        ├── engagement weights (408K pairs)
        └── 17.5M liked tweets (topic modeling)
                │
                ▼
    ┌──────────────────────────┐
    │  15 Communities (NMF)    │  Human-curated seeds from
    │  317 seed accounts       │  spectral clustering + validation
    └───────────┬──────────────┘
                │
                ▼
    ┌──────────────────────────┐
    │  Label Propagation       │  Harmonic (CG solve on Laplacian)
    │  201K-node graph         │  with engagement weighting +
    │  T=2.0, balanced         │  class balancing + seed eligibility
    └───────────┬──────────────┘
                │
                ▼
    ┌──────────────────────────┐
    │  4-Band Classification   │  exemplar → specialist → bridge → frontier
    │  ~10K classified         │  based on membership confidence + degree
    └───────────┬──────────────┘
                │
                ▼
    ┌──────────────────────────┐
    │  Public Site Export       │  React app with search, community
    │  maptpot.vercel.app      │  pages, collectible cards
    └──────────────────────────┘
```

## Communities

| # | Community | Seeds | Description |
|---|-----------|-------|-------------|
| 1 | Core TPOT | 81 | The dense center of the network |
| 2 | Jhana Practitioners | 72 | Contemplative practice and meditation |
| 3 | Vibecamp Highbies | 63 | IRL gathering organizers and attendees |
| 4 | Qualia Researchers | 63 | Consciousness and phenomenology |
| 5 | Internet Essayists | 61 | Long-form writing and ideas |
| 6 | Relational Explorers | 51 | Relationships and social dynamics |
| 7 | Tech Philosophers | 49 | Philosophy of technology |
| 8 | AI Creatives | 48 | AI art, tools, and creative applications |
| 9 | Quiet Creatives | 48 | Artists, musicians, makers |
| 10 | Queer TPOT | 45 | LGBTQ+ community members |
| 11 | EA & Forecasting | 37 | Effective altruism and prediction markets |
| 12 | NYC Institution Builders | 32 | New York-based community builders |
| 13 | Regen & Collective Intelligence | 30 | Regenerative and metamodern movements |
| 14 | Sensemaking Builders | 28 | Tools for collective sensemaking |
| 15 | LLM Whisperers | 24 | AI prompt engineering and LLM exploration |

## Quick Start

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add your SUPABASE_KEY

# Core pipeline
.venv/bin/python3 -m scripts.propagate_community_labels --save    # propagation
.venv/bin/python3 -m scripts.classify_bands                       # band classification
.venv/bin/python3 -m scripts.export_public_site                   # site export

# Data fetches (long-running, resume-capable)
.venv/bin/python3 -m scripts.build_mention_graph     # ~3hrs, keyset pagination
.venv/bin/python3 -m scripts.build_quote_graph       # ~30min, keyset pagination

# Validation
.venv/bin/python3 -m scripts.verify_bootstrap_cv     # cross-validation metrics
.venv/bin/python3 -m scripts.verify_holdout_recall   # holdout set recall
```

## Prerequisites

- Python 3.9+
- Supabase anon key for the Community Archive
- ~500MB disk space (SQLite DB + propagation data)

## Configuration

Create a `.env` file:

```bash
SUPABASE_URL=https://fabxmporizzqflnftavs.supabase.co
SUPABASE_KEY=your_anon_key_here
```

See `.env.example` for all options.

## Project Structure

```
tpot-analyzer/
├── scripts/
│   ├── propagate_community_labels.py   # Core: harmonic label propagation
│   ├── classify_bands.py               # Core: 4-band classification
│   ├── export_public_site.py           # Core: generate data.json + search.json
│   ├── build_mention_graph.py          # Data: fetch mentions from Supabase
│   ├── build_quote_graph.py            # Data: fetch quotes from Supabase
│   ├── rank_frontier.py                # Analysis: prioritize enrichment targets
│   ├── resolve_band_usernames.py       # Utility: bulk username resolution
│   ├── verify_bootstrap_cv.py          # Validation: cross-validation metrics
│   ├── verify_holdout_recall.py        # Validation: holdout recall check
│   └── ...                             # ~25 more verify/utility scripts
├── src/
│   ├── config.py                       # Supabase configuration
│   ├── api/                            # Flask API backend
│   │   ├── server.py                   #   App factory + blueprint registration
│   │   ├── routes/                     #   core, graph, analysis, discovery,
│   │   │                               #   accounts, communities, golden,
│   │   │                               #   branches, extension
│   │   ├── cluster_routes.py           #   Cluster explorer endpoints
│   │   ├── snapshot_loader.py          #   Precomputed graph loading
│   │   └── labeling_context.py         #   Tweet labeling support
│   ├── graph/                          # Graph building, metrics, spectral,
│   │                                   # signal pipeline, community affinity
│   ├── shadow/                         # Shadow enrichment (Selenium + X API)
│   ├── data/                           # Data access layer, feed signals,
│   │                                   # golden store, community gold
│   ├── communities/                    # Community store, versioning, colors
│   └── archive/                        # Archive data fetching + threading
├── graph-explorer/                     # Rich analysis UI (React + Vite)
│   └── src/
│       ├── App.jsx                     #   Tab router (Graph, Clusters, etc.)
│       ├── GraphExplorer.jsx           #   d3-force interactive graph
│       ├── ClusterView.jsx             #   Spectral cluster visualization
│       ├── ClusterCanvas.jsx           #   WebGL cluster rendering
│       ├── Labeling.jsx                #   Tweet labeling interface
│       ├── Discovery.jsx               #   Account discovery tool
│       ├── AccountDeepDive.jsx         #   Per-account analysis
│       ├── AccountTagPanel.jsx         #   Account tagging
│       └── communities/               #   Gold labels, scorecard, editor
├── public-site/                        # Public-facing site (React + Vite)
│   └── src/
│       ├── App.jsx                     #   Router + data loading
│       ├── About.jsx                   #   Methodology documentation
│       ├── SearchBar.jsx               #   Handle search with suggestions
│       ├── CommunityPage.jsx           #   Community detail pages
│       └── CommunityCard.jsx           #   AI-generated collectible cards
├── data/
│   ├── archive_tweets.db              # Main SQLite database
│   └── community_propagation.npz      # Propagation results
├── docs/
│   ├── index.md                       # Documentation navigation
│   ├── WORKLOG.md                     # Development log
│   ├── ROADMAP.md                     # Planned work
│   ├── CONVENTIONS.md                 # Naming and coding standards
│   ├── adr/                           # Architectural decision records (14)
│   ├── modules/                       # Module documentation
│   ├── reference/                     # Schema, tuning, environment docs
│   └── guides/                        # Quickstart, GPU, debug guides
└── tests/
```

## Key Pipeline Scripts

| Script | Purpose | Runtime | Resume? |
|--------|---------|---------|---------|
| `build_mention_graph` | Fetch 10.6M user mentions from Supabase | ~3hrs | Yes (keyset cursor) |
| `build_quote_graph` | Fetch quote tweets from Supabase | ~30min | Yes (keyset cursor) |
| `propagate_community_labels` | Harmonic label propagation on full graph | ~15s | N/A |
| `classify_bands` | Assign exemplar/specialist/bridge/frontier bands | ~5s | N/A |
| `export_public_site` | Generate data.json + search.json for site | ~10s | N/A |
| `rank_frontier` | Score frontier accounts for API enrichment | ~5s | N/A |
| `resolve_band_usernames` | Bulk-resolve usernames via Supabase | ~2min | N/A |
| `verify_bootstrap_cv` | Bootstrap cross-validation (20 iterations) | ~5min | N/A |

## Graph Explorer (Development UI)

The graph explorer is the full-featured analysis interface for researchers and developers:

```bash
# Start Flask API backend
.venv/bin/python3 -m scripts.start_api_server

# Start graph explorer frontend (separate terminal)
cd graph-explorer
npm install
npm run dev
# Opens at http://localhost:5173
```

Features:
- **Graph view**: Interactive d3-force network with PageRank, betweenness, community coloring
- **Cluster view**: Spectral embedding visualization with Louvain communities
- **Labeling UI**: Tweet-level classification interface for golden dataset curation
- **Gold labels**: Community-account gold label editor with split management
- **Account deep dive**: Per-account analysis with membership panels and tag management
- **Discovery**: Subgraph exploration and account discovery tools

Requires the Flask API running with a populated `archive_tweets.db` and precomputed graph snapshots.

## Validation

The propagation system is validated through:

- **Bootstrap CV**: Hold out 20% of seeds per iteration, measure recall on held-out + external directory
- **Holdout set**: 217 TPOT directory accounts not used as seeds — measures discovery of accounts we didn't tell the system about
- **Cross-signal convergence**: 15 communities validated across follow graph, mention/quote engagement, and topic modeling

## Testing

```bash
.venv/bin/python3 -m pytest tests/ -v          # all tests
.venv/bin/python3 -m pytest tests/ -v -m unit   # fast unit tests only
```

## Documentation

- **[docs/index.md](./docs/index.md)** — Documentation navigation hub
- **[docs/WORKLOG.md](./docs/WORKLOG.md)** — Development history
- **[docs/ROADMAP.md](./docs/ROADMAP.md)** — What's shipped and what's planned
- **[docs/CONVENTIONS.md](./docs/CONVENTIONS.md)** — Naming, patterns, and standards
- **[docs/adr/](./docs/adr/)** — Architectural decision records

## License

No license file is provided. Add one before distributing or open-sourcing.
