# TPOT Community Map

Explores TPOT (This Part of Twitter) using Community Archive data, locally
captured shadow data, typed interaction edges, and content signals. The
repository is moving from a legacy fixed community map toward raw-first,
human-in-the-loop retrieval. Its historical named communities, scores, and
display bands are exploratory artifacts—not calibrated membership claims.

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
    │  16 Legacy Communities   │  Mixed NMF + LLM-ensemble seed rows;
    │  361 seed accounts       │  not a fully human-curated ontology
    └───────────┬──────────────┘
                │
                ▼
    ┌──────────────────────────┐
    │  Directed PPR + Lift     │  298K-account active artifact;
    │  independent affinities  │  uncalibrated, solver audit pending
    └───────────┬──────────────┘
                │
                ▼
    ┌──────────────────────────┐
    │  Legacy Display Bands    │  unbound rows are quarantined regardless
    │  export suppresses them  │  of score mode; classic classifier is local
    └───────────┬──────────────┘
                │
                ▼
    ┌──────────────────────────┐
    │  Public Site Export       │  React app with search, community
    │  maptpot.vercel.app      │  pages, collectible cards
    └──────────────────────────┘
```

## Historical 15-Community Snapshot

The table below documents the March-era NMF snapshot. The current database and
active propagation artifact contain 16 legacy names, so this table is not a
canonical current taxonomy and must not be used as golden membership data.

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
.venv/bin/python3 -m scripts.classify_bands                       # classic mode only; independent fails closed
.venv/bin/python3 -m scripts.export_public_site                   # suppresses unbound bands; classified-only fallback
.venv/bin/python3 -m scripts.verify_independent_band_entropy      # inspect entropy/band contract

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
│   ├── propagate_community_labels.py   # Directed PPR + Lift propagation
│   ├── classify_bands.py               # Legacy classic bands; independent fails closed
│   ├── export_public_site.py           # Core: generate data.json + search.json
│   ├── build_mention_graph.py          # Data: fetch mentions from Supabase
│   ├── build_quote_graph.py            # Data: fetch quotes from Supabase
│   ├── rank_frontier.py                # Historical ranker; quarantined pending exact binding
│   ├── resolve_band_usernames.py       # Historical resolver; quarantined
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
| `propagate_community_labels` | Directed PPR + Lift propagation on the graph | ~15s | N/A |
| `classify_bands` | Assign legacy bands for classic artifacts; reject independent Lift | ~5s | N/A |
| `export_public_site` | Generate site JSON; suppress unbound bands and use classified-only fallback | ~10s | N/A |
| `rank_frontier` | Historical enrichment ranker; blocked until bands have an exact artifact receipt | blocked | N/A |
| `resolve_band_usernames` | Historical band-driven resolver; fails closed pending artifact binding | blocked | N/A |
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
