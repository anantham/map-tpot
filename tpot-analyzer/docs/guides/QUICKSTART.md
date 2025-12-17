# Quick Start Guide

Get the TPOT Analyzer running locally in under 10 minutes.

---

## Prerequisites

| Tool | Version | Check Command |
|------|---------|---------------|
| Python | 3.9+ | `python3 --version` |
| Node.js | 18+ | `node --version` |
| npm | 9+ | `npm --version` |
| Git | Any | `git --version` |

**macOS**: Install missing tools with Homebrew:
```bash
brew install python@3.11 node git
```

---

## 1. Clone & Setup Python Environment

```bash
# Clone the repository
git clone https://github.com/yourusername/tpot-analyzer.git
cd tpot-analyzer

# Create Python virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Verify installation
python -c "from src.api import server; print('✅ Python setup complete')"
```

---

## 2. Setup Environment Variables

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your credentials (optional for basic usage)
# Required only for:
# - SUPABASE_URL, SUPABASE_KEY: Cloud data sync
# - X_BEARER_TOKEN: Twitter API access
```

**Minimal .env for local-only usage:**
```env
FLASK_ENV=development
FLASK_DEBUG=1
```

---

## 3. Initialize Data

The analyzer needs either:
- **Option A**: Import from existing data (recommended for quick start)
- **Option B**: Build from scratch (requires Twitter credentials)

### Option A: Use Sample Data (Quick)

```bash
# If you have a data dump:
cp /path/to/your/shadow.db data/shadow.db

# Or create minimal test fixtures:
python scripts/create_test_fixtures.py
```

### Option B: Build Graph from Twitter (Slow)

```bash
# Setup Twitter cookies for scraping
python scripts/setup_cookies.py

# Enrich graph starting from a seed account
python -m scripts.enrich_shadow_graph --center your_twitter_handle --max-seeds 50
```

---

## 4. Build Graph Snapshot

The API serves precomputed graph data for performance:

```bash
# Build spectral embedding and cluster hierarchy
python scripts/build_spectral.py

# Verify snapshot was created
ls -la data/graph_snapshot.*
# Expected files:
#   graph_snapshot.nodes.parquet
#   graph_snapshot.edges.parquet
#   graph_snapshot.meta.json
#   graph_snapshot.spectral.npz
```

---

## 5. Start the Backend API

```bash
# Start Flask server (port 5001)
python -m scripts.start_api_server

# Verify it's running
curl http://localhost:5001/api/health
# Expected: {"status": "ok"}
```

Keep this terminal open. The API logs will appear here.

---

## 6. Start the Frontend

Open a **new terminal**:

```bash
cd graph-explorer

# Install Node dependencies (first time only)
npm install

# Start Vite dev server (port 5173)
npm run dev
```

---

## 7. Open in Browser

Visit: **http://localhost:5173**

You should see:
- **Discovery page**: Find interesting accounts to follow
- **Cluster view**: Explore community structure
- **Graph Explorer**: Navigate the social graph

---

## Quick Commands Reference

```bash
# Start everything (after initial setup)
cd tpot-analyzer
source .venv/bin/activate
python -m scripts.start_api_server &  # Background
cd graph-explorer && npm run dev

# Or use the convenience script (macOS)
./StartGraphExplorer.command
```

### Common Operations

| Task | Command |
|------|---------|
| Run tests | `pytest tests/ -v` |
| Rebuild graph | `python scripts/refresh_graph_snapshot.py` |
| Check API health | `curl localhost:5001/api/health` |
| Frontend E2E tests | `cd graph-explorer && npm run test:e2e:mock` |
| Lint Python | `ruff check src/` |
| Lint Frontend | `cd graph-explorer && npm run lint` |

---

## Troubleshooting

### "Module not found" errors
```bash
# Ensure you're in the virtualenv
source .venv/bin/activate
# Reinstall dependencies
pip install -r requirements.txt
```

### "Port already in use"
```bash
# Find and kill process on port 5001
lsof -i :5001
kill -9 <PID>
```

### "No graph data" in frontend
```bash
# Rebuild the snapshot
python scripts/build_spectral.py
# Restart the API
python -m scripts.start_api_server
```

### Frontend won't start
```bash
cd graph-explorer
rm -rf node_modules
npm install
npm run dev
```

### Database locked errors
```bash
# Stop all Python processes
pkill -f "python.*api_server"
# Remove WAL files
rm -f data/*.db-shm data/*.db-wal
```

---

## Project Structure

```
tpot-analyzer/
├── src/                    # Python source code
│   ├── api/                # Flask routes and server
│   ├── data/               # Data fetching and storage
│   ├── graph/              # Graph analysis, clustering
│   └── shadow/             # Twitter scraping
├── graph-explorer/         # React frontend
│   ├── src/                # Components, pages
│   └── e2e/                # Playwright tests
├── scripts/                # CLI tools
├── tests/                  # Python tests
├── docs/                   # Documentation
│   ├── guides/             # How-to guides
│   ├── reference/          # API docs, schemas
│   └── tasks/              # Implementation task docs
└── data/                   # Runtime data (gitignored)
```

---

## Next Steps

1. **Explore the UI**: Navigate clusters, search accounts
2. **Read the docs**: `docs/reference/` for API details
3. **Run tests**: `pytest tests/ -v` to verify setup
4. **Customize**: Edit `config/graph_settings.json` for your preferences

For GPU-accelerated spectral computation, see [GPU Setup Guide](GPU_SETUP.md).

---

## Getting Help

- **Documentation**: `docs/` directory
- **Issues**: GitHub Issues
- **Architecture**: `docs/adr/` for design decisions
