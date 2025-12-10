# Getting Started with map-tpot

Welcome! This guide will get you from zero to exploring the TPOT community graph in under 15 minutes.

---

## What is this project?

**map-tpot** is a collection of tools for analyzing Twitter/X social networks, specifically focused on the TPOT (This Part of Twitter) community. It includes:

1. **tpot-analyzer** — Graph analysis toolkit that builds and visualizes social networks using data from the Community Archive (a public dataset of ~275 Twitter accounts who opted to share their data)

2. **grok-probe** — Experimental tool for testing whether AI models (Grok) have memorized tweet content

Most users will focus on **tpot-analyzer**.

---

## Prerequisites

Before you begin, ensure you have:

- **Python 3.9+** with pip
- **Node.js 18+** with npm
- **Git** for cloning the repository
- ~200MB disk space for dependencies and cache

Optional (for enrichment beyond the base dataset):
- Twitter/X account with cookies
- X API bearer token (for metadata enrichment)

---

## Quick Start (5 minutes)

### Step 1: Clone and Enter the Repository

```bash
git clone https://github.com/anantham/map-tpot.git
cd map-tpot/tpot-analyzer
```

### Step 2: Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Configure Environment

Create a `.env` file with your Supabase credentials:

```bash
# .env file in tpot-analyzer/
SUPABASE_URL=https://fabxmporizzqflnftavs.supabase.co
SUPABASE_KEY=your_anon_key_here
```

> **Note:** The Community Archive is publicly readable. Get the anon key from the project maintainers or Community Archive documentation.

### Step 4: Verify Setup

```bash
python3 scripts/verify_setup.py
```

Expected output:
```
✓ Supabase connection successful
✓ Found 280+ profiles in Community Archive
✓ Cache initialized at data/cache.db
```

### Step 5: Run the Graph Explorer

**Terminal 1 — Backend:**
```bash
python -m scripts.start_api_server
# Output: 🚀 Starting Flask API server on http://localhost:5001
```

**Terminal 2 — Frontend:**
```bash
cd graph-explorer
npm install
npm run dev
# Output: ➜ Local: http://localhost:5173/
```

**Open your browser:** Navigate to http://localhost:5173

You should see an interactive force-directed graph of the TPOT community!

---

## What Can You Do Now?

### Explore the Graph
- **Drag nodes** to reposition them
- **Scroll** to zoom in/out
- **Click nodes** to see details
- **Hover** for tooltips

### Adjust Parameters
- **Seed Accounts:** Change which accounts seed the PageRank algorithm
- **Weight Sliders:** Adjust α (PageRank), β (Betweenness), γ (Engagement)
- **Shadow Toggle:** Show/hide accounts discovered via enrichment
- **Mutual Only:** Filter to only show mutual follows

### Export Data
- **CSV Export:** Download rankings for external analysis
- **JSON Export:** Full graph data for custom visualizations

---

## Next Steps

### Learn More
| Topic | Document |
|-------|----------|
| How the data pipeline works | [ADR 001: Data Pipeline](tpot-analyzer/docs/adr/001-data-pipeline-architecture.md) |
| Understanding the graph metrics | [ADR 002: Graph Analysis](tpot-analyzer/docs/adr/002-graph-analysis-foundation.md) |
| Database schema | [DATABASE_SCHEMA.md](tpot-analyzer/docs/DATABASE_SCHEMA.md) |

### Expand the Dataset
The base dataset includes ~275 Community Archive accounts. To discover more of the network:

```bash
# Set up Twitter cookies (one-time)
python -m scripts.setup_cookies --output secrets/twitter_cookies.pkl

# Run enrichment (adds followers/following of seed accounts)
python -m scripts.enrich_shadow_graph \
  --center your_twitter_handle \
  --auto-confirm-first \
  --skip-if-ever-scraped
```

See [README.md](tpot-analyzer/README.md#shadow-enrichment-pipeline-phase-14--in-progress) for full enrichment documentation.

### Run Tests

```bash
# All unit tests
pytest tests/ -v -m unit

# With coverage
pytest --cov=src --cov-report=term-missing tests/
```

---

## Common Issues

### "SUPABASE_KEY is not configured"
Add the key to your `.env` file or export it:
```bash
export SUPABASE_KEY=your_key_here
```

### "Backend API not available" in browser
Ensure the Flask server is running in Terminal 1:
```bash
python -m scripts.start_api_server
```

### Graph is empty
1. Check that `data/cache.db` exists and has data:
   ```bash
   sqlite3 data/cache.db "SELECT COUNT(*) FROM account;"
   ```
2. If empty, run `python3 scripts/verify_setup.py` to populate cache

### ImportError on startup
Ensure your virtual environment is activated:
```bash
source .venv/bin/activate
```

---

## Project Structure

```
map-tpot/
├── AGENTS.md                    # AI agent operational guide
├── README.md                    # Project overview
├── grok-probe/                  # LLM memorization testing tool
│   └── README.md
└── tpot-analyzer/               # Main graph analysis toolkit
    ├── README.md                # Detailed tpot-analyzer docs
    ├── data/                    # SQLite cache (gitignored)
    ├── docs/                    # Documentation
    │   ├── adr/                 # Architecture Decision Records
    │   ├── DATABASE_SCHEMA.md   # Data model documentation
    │   ├── ENRICHMENT_FLOW.md   # Scraping pipeline docs
    │   └── WORKLOG.md           # Development log
    ├── graph-explorer/          # React + Vite frontend
    ├── scripts/                 # CLI tools
    ├── src/                     # Python source code
    │   ├── api/                 # Flask backend
    │   ├── data/                # Data access layer
    │   ├── graph/               # Graph algorithms
    │   └── shadow/              # Enrichment pipeline
    └── tests/                   # pytest test suite
```

---

## Getting Help

- **Documentation:** Start with the [tpot-analyzer README](tpot-analyzer/README.md)
- **Issues:** Report bugs at https://github.com/anantham/map-tpot/issues
- **Terminology:** See the [Glossary](GLOSSARY.md) for project-specific terms

---

*Last updated: 2025-12-10*
