# Graph Explorer for TPOT Analyzer

Interactive frontend for visualizing the TPOT community graph. Built with Vite + React + `react-force-graph-2d` with a Flask backend for dynamic metric computation.

## Prerequisites

- Node.js 18+
- Python 3.10+ with virtualenv
- Access to the `tpot-analyzer` Python project and its data cache

## Architecture

The graph explorer uses a **client-server architecture**:

```
React Frontend (port 5173) ←→ Flask API (port 5001) ←→ SQLite cache.db
        │                             │
        │                             ├─ Load graph structure
        │                             ├─ Compute PageRank (personalized)
        │                             ├─ Compute Betweenness
        │                             ├─ Compute Engagement
        │                             └─ Return composite metrics
        │
        └─ Interactive controls for seeds, weights, layout
```

**Key Features:**
- ✅ **Dynamic seed-based PageRank**: Change seeds in UI → metrics recompute
- ✅ **All three weight sliders functional**: α (PageRank), β (Betweenness), γ (Engagement)
- ✅ **Shadow node support**: 7,706 enriched accounts from API scraping
- ✅ **Sub-second response** for common queries (with future caching)

## Setup

### 1. Install Frontend Dependencies

```bash
cd tpot-analyzer/graph-explorer
npm install
```

### 2. Install Python Dependencies

```bash
cd tpot-analyzer
source .venv/bin/activate  # or activate your virtualenv
pip install -r requirements.txt
```

## Refresh data from the CLI

A helper script regenerates `analysis_output.json` inside `public/` using the Python analyzer. By default it runs in mutual-only mode with the "Adi's Seeds" preset.

```bash
npm run refresh-data
```

Options:

```
# Use a different preset (from DEFAULT_PRESETS in GraphExplorer.jsx)
npm run refresh-data -- --preset "Adi's Seeds"

# Supply custom seeds (handles or account_ids)
npm run refresh-data -- --seeds nosilverv DefenderOfBasic 1464483769222680582

# Disable mutual-only filter and change min followers
npm run refresh-data -- --no-mutual --min-followers 2
```

The script invokes `python -m scripts.analyze_graph` from the project root and places the JSON output into `graph-explorer/public/analysis_output.json`.

## Running the Application

You need to start **both** the backend API server and the frontend dev server.

### Terminal 1: Start Backend API

```bash
cd tpot-analyzer
source .venv/bin/activate
python -m scripts.start_api_server

# Server will start on http://localhost:5001
# You should see: 🚀 Starting Flask API server on http://localhost:5001
```

**Options:**
```bash
# Run on different port
python -m scripts.start_api_server --port 5002

# Enable debug mode
python -m scripts.start_api_server --debug

# Bind to all interfaces (for network access)
python -m scripts.start_api_server --host 0.0.0.0
```

### Terminal 2: Start Frontend Dev Server

```bash
cd tpot-analyzer/graph-explorer
npm run dev

# Frontend will start on http://localhost:5173
```

Open `http://localhost:5173` in your browser.

**The UI will show an error banner if the backend is not running.** Make sure both servers are active.

### What Happens When You Use the UI

1. **Initial Load**: Frontend fetches graph structure (nodes/edges) from backend
2. **Seed Changes**: Typing new seeds triggers PageRank recomputation via `/api/metrics/compute`
3. **Weight Slider Changes**: Adjusting α, β, γ triggers metric recomputation with new weights
4. **"Recompute Metrics" Button**: Manually triggers metric refresh

## API Endpoints

The Flask backend exposes the following endpoints:

### `GET /health`
Health check endpoint.

**Response:**
```json
{"status": "ok"}
```

### `GET /api/graph-data`
Load raw graph structure (nodes and edges).

**Query Parameters:**
- `include_shadow` (bool, default: true) - Include shadow nodes
- `mutual_only` (bool, default: false) - Only mutual edges
- `min_followers` (int, default: 0) - Minimum follower filter

**Response:**
```json
{
  "nodes": { "account_id": { "username": "...", "num_followers": 123, ... } },
  "edges": [ {"source": "id1", "target": "id2", "mutual": true} ],
  "directed_nodes": 8000,
  "directed_edges": 18000,
  "undirected_edges": 5000
}
```

### `POST /api/metrics/compute`
Compute graph metrics with custom seeds and weights.

**Request Body:**
```json
{
  "seeds": ["username1", "account_id2"],
  "weights": [0.4, 0.3, 0.3],
  "alpha": 0.85,
  "resolution": 1.0,
  "include_shadow": true,
  "mutual_only": false,
  "min_followers": 0
}
```

**Response:**
```json
{
  "seeds": ["username1", ...],
  "resolved_seeds": ["account_id1", ...],
  "metrics": {
    "pagerank": { "account_id": 0.123 },
    "betweenness": { "account_id": 0.456 },
    "engagement": { "account_id": 0.789 },
    "composite": { "account_id": 0.555 },
    "communities": { "account_id": 2 }
  },
  "top": {
    "pagerank": [["account_id", 0.123], ...],
    "betweenness": [["account_id", 0.456], ...],
    "composite": [["account_id", 0.555], ...]
  }
}
```

### `GET /api/metrics/presets`
Get available seed presets.

**Response:**
```json
{
  "adi_tpot": ["username1", "username2", ...]
}
```

## Testing

### Test Backend API

```bash
cd tpot-analyzer
source .venv/bin/activate
pytest tests/test_api.py -v
```

### Test Frontend Linting

```bash
cd graph-explorer
npm run lint
```

## Build for Production

```bash
cd graph-explorer
npm run build
npm run preview  # Preview production build locally
```

---

## Troubleshooting

**Backend not responding:**
- Check that Flask server is running on port 5001
- Verify cache.db exists at `tpot-analyzer/data/cache.db`
- Check terminal for error messages

**Frontend shows "Backend API not available":**
- Start the backend server first
- Verify backend is accessible at http://localhost:5001/health
- Check browser console for CORS errors

**Metrics not updating:**
- Wait for "Computing metrics..." indicator to disappear
- Check backend terminal for computation errors
- Try refreshing the page

**Empty graph:**
- Ensure shadow enrichment has run (`python -m scripts.enrich_shadow_graph`)
- Check that cache.db has data (`sqlite3 data/cache.db "SELECT COUNT(*) FROM shadow_account;"`)

---

For additional presets, update the `DEFAULT_PRESETS` object in `src/GraphExplorer.jsx` or add them to `docs/seed_presets.json`.
