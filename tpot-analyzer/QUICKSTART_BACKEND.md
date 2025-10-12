# Quick Start: Graph Explorer with Backend

## TL;DR

```bash
# Terminal 1: Start Backend
cd tpot-analyzer
source .venv/bin/activate
python -m scripts.start_api_server

# Terminal 2: Start Frontend
cd tpot-analyzer/graph-explorer
npm run dev

# Browser: http://localhost:5173
```

---

## What Changed?

### ✅ Now Working:
1. **Dynamic seed-based PageRank** - Change seeds in UI → graph updates
2. **All three weight sliders** - α (PageRank), β (Betweenness), γ (Engagement)
3. **Fresh shadow data** - 7,706 enriched accounts from API scraping
4. **Real-time metrics** - Backend computes on-demand

### 🔧 Architecture:
```
React (5173) ←→ Flask (5001) ←→ SQLite cache.db
     │               │              ├─ 275 archive accounts
     │               │              └─ 7,706 shadow nodes
     │               │
     │               ├─ Compute PageRank
     │               ├─ Compute Betweenness
     │               └─ Return composite metrics
     │
     └─ Interactive UI with sliders
```

---

## First-Time Setup

### 1. Install Dependencies

```bash
# Backend (if not already done)
cd tpot-analyzer
source .venv/bin/activate
pip install Flask Flask-Cors  # Already in requirements.txt

# Frontend (if not already done)
cd graph-explorer
npm install
```

### 2. Verify Data Exists

```bash
cd tpot-analyzer
sqlite3 data/cache.db "SELECT COUNT(*) FROM shadow_account;"
# Should return: 7706

sqlite3 data/cache.db "SELECT COUNT(*) FROM account;"
# Should return: 275
```

If counts are 0, run enrichment first:
```bash
python -m scripts.enrich_shadow_graph --cookies ./secrets/twitter_cookies.pkl
```

---

## Daily Usage

### Start Both Servers

**Terminal 1 - Backend:**
```bash
cd tpot-analyzer
source .venv/bin/activate
python -m scripts.start_api_server

# You should see:
# 🚀 Starting Flask API server on http://localhost:5001
# * Running on http://localhost:5001
```

**Terminal 2 - Frontend:**
```bash
cd tpot-analyzer/graph-explorer
npm run dev

# You should see:
# VITE v7.1.7  ready in 234 ms
# ➜  Local:   http://localhost:5173/
```

### Verify It's Working

1. Open http://localhost:5173
2. You should see the graph load (wait 2-3 seconds)
3. If you see a red banner "Backend API not available" → check Terminal 1

---

## Testing the Features

### Test 1: Change Seeds

1. Scroll to "Seed presets" section
2. Enter new usernames in textarea (e.g., `eigenrobot`, `visakanv`)
3. Click "Apply seeds"
4. Watch for "🔄 Computing metrics..." indicator
5. Graph should update with new rankings

### Test 2: Adjust Weights

1. Find "Status weights" section
2. Move α slider (PageRank weight)
3. Move β slider (Betweenness weight)
4. Move γ slider (Engagement weight)
5. Each change triggers recomputation
6. Check "Total" sums to ~1.0

### Test 3: Shadow Nodes

1. Find "Shadow enrichment" section
2. Toggle checkbox on/off
3. Graph nodes should appear/disappear (grey/slate colored nodes)

---

## Troubleshooting

### Backend won't start

```bash
# Check if port 5001 is in use
lsof -i :5001
# If occupied, kill it: kill -9 <PID>

# Or use different port:
python -m scripts.start_api_server --port 5002
# Then update .env in graph-explorer: VITE_API_URL=http://localhost:5002
```

### Frontend shows "Backend API not available"

1. Check Terminal 1 - is Flask running?
2. Test backend directly:
   ```bash
   curl http://localhost:5001/health
   # Should return: {"status":"ok"}
   ```
3. Check firewall/CORS settings

### Metrics not updating

1. Wait 2-3 seconds for computation to finish
2. Check Terminal 1 for Python errors
3. Check browser console (F12) for JavaScript errors
4. Try "Recompute Metrics" button

### Graph is empty

1. Verify data exists (see "Verify Data Exists" above)
2. Check "include_shadow" toggle is ON
3. Check "min_followers" slider is at 0
4. Look at Terminal 1 for database errors

---

## Performance Notes

**Current (Option B):**
- Initial load: 300-500ms
- Seed change: 500-2000ms
- Weight change: 500-2000ms

**This is acceptable** for exploration. If you need faster:
- Run `BACKEND_IMPLEMENTATION.md` → "Future Optimization (Option C)"
- Adds caching → reduces to 50-200ms

---

## Testing

```bash
# Test backend API
cd tpot-analyzer
source .venv/bin/activate
pytest tests/test_api.py -v

# Expected output:
# tests/test_api.py::test_health_endpoint PASSED
# tests/test_api.py::test_graph_data_endpoint PASSED
# tests/test_api.py::test_compute_metrics_endpoint PASSED
# ... (10 tests total)
```

---

## Stopping the Servers

1. Terminal 1 (backend): `Ctrl+C`
2. Terminal 2 (frontend): `Ctrl+C`

---

## Next Steps

Once comfortable:
1. Read `BACKEND_IMPLEMENTATION.md` for architecture details
2. Read `graph-explorer/README.md` for API documentation
3. Explore Option C (caching) for performance optimization
4. Add custom seed presets to `docs/seed_presets.json`

---

## Need Help?

Check these files:
- `BACKEND_IMPLEMENTATION.md` - Detailed implementation doc
- `graph-explorer/README.md` - Full API reference
- `tests/test_api.py` - Example API usage
- `src/api/server.py` - Backend source code

**Common Issues:**
- "Backend not available" → Start backend first (Terminal 1)
- "Computing forever" → Check Terminal 1 for errors
- Empty graph → Verify data exists in cache.db
- Slow performance → Consider caching (Option C)
