# TPOT Community Graph Analyzer

Python-based network analysis toolkit for exploring the TPOT (This Part of Twitter) community using the Community Archive dataset (6.9M tweets, 12.3M likes, follow relationships, and detailed profile metadata).

## Project Status

**Phase 1.1 (Complete):** Data pipeline with cached Supabase access
**Phase 1.2 (Complete):** Follow graph construction, status metrics (PageRank, Louvain, betweenness), CLI analysis tool
**Phase 1.3 (Complete):** Interactive visualization with React + d3-force graph explorer
**Phase 1.4 (In Progress):** Shadow enrichment pipeline with policy-driven refresh logic

See [docs/WORKLOG.md](./docs/WORKLOG.md) for detailed progress and [docs/adr/](./docs/adr/) for architectural decisions.

## Data Snapshot

<!-- AUTO:GRAPH_SNAPSHOT -->
_Directed graph snapshot pending — run `python -m scripts.analyze_graph --include-shadow --update-readme` to populate this section._
<!-- /AUTO:GRAPH_SNAPSHOT -->

## Prerequisites

- Python 3.9+
- Supabase anon key for the Community Archive (public read-only access)
- ~50MB disk space for SQLite cache

## Setup

1. **Create virtual environment and install dependencies:**

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure environment variables:**

Create a `.env` file in the project root or export variables:

```bash
SUPABASE_URL=https://fabxmporizzqflnftavs.supabase.co  # Default Community Archive endpoint
SUPABASE_KEY=your_anon_key_here                        # Required: anon key for read access
CACHE_DB_PATH=./data/cache.db                          # Optional: defaults to ./data/cache.db
CACHE_MAX_AGE_DAYS=7                                   # Optional: defaults to 7 days
```

See `.env.example` for a template.

3. **Verify setup:**

```bash
python3 scripts/verify_setup.py
```

Expected output:
- ✓ Supabase connection successful
- ✓ Found 280+ profiles in Community Archive
- ✓ Cache initialized at `data/cache.db`
- Sample accounts list

## Architecture

### Data Pipeline (Phase 1.1)

The analyzer uses an API-first architecture backed by local SQLite caching:

- **`src/config.py`**: Environment configuration loader for Supabase credentials and cache settings
- **`src/data/fetcher.py`**: `CachedDataFetcher` class providing pandas DataFrames for:
  - `fetch_profiles()` — account profile metadata
  - `fetch_accounts()` — account-level stats (followers, tweet counts)
  - `fetch_followers()` — follower edges
  - `fetch_following()` — following edges
  - `fetch_tweets()` — tweet content and metadata
  - `fetch_likes()` — like interactions

All data is cached in SQLite for 7 days (configurable). Cache expires automatically and refreshes from Supabase when stale.

### Graph Analysis (Phase 1.2 — Complete)

Features:
- Directed follow graph construction with mutual-only view support
- Baseline metrics: Personalized PageRank, Louvain communities, betweenness centrality
- CLI analysis tool (`scripts/analyze_graph.py`) with JSON output
- Configurable seed selection via presets (`docs/seed_presets.json`)
- Support for shadow enrichment integration (`--include-shadow` flag)

See [ADR 002](./docs/adr/002-graph-analysis-foundation.md) for full specification.

### Interactive Visualization (Phase 1.3 — Complete)

The graph explorer (`graph-explorer/`) is a React + Vite application using d3-force for interactive network visualization:

- Force-directed layout with configurable physics parameters
- Real-time metrics display (PageRank, betweenness, community assignments)
- Shadow enrichment toggle to show/hide expanded network
- Node filtering, edge styling, and interactive controls
- Persistent parameter state and export capabilities

Run the explorer:
```bash
cd graph-explorer
npm install
npm run dev
```

Generate analysis data:
```bash
python -m scripts.analyze_graph --include-shadow --output graph-explorer/public/analysis_output.json
```

#### macOS launcher

On macOS you can automate the dual-terminal startup with `StartGraphExplorer.command`:
1. `chmod +x StartGraphExplorer.command` (one-time to mark it executable)
2. Double-click the file in Finder or run `./StartGraphExplorer.command`

The script opens Terminal windows for the Flask API (`scripts.start_api_server`) and the Vite dev server, then launches your browser at `http://localhost:5173`.

### Shadow Enrichment Pipeline (Phase 1.4 — In Progress)

Shadow enrichment expands the graph beyond Community Archive’s 275 indexed accounts by scraping follow/follower lists with Selenium and backfilling metadata via the X API v2 when available. Data lives in dedicated `shadow_account` / `shadow_edge` tables so provenance stays explicit.

```
┌──────────────────────┐
│ scripts/enrich_shadow│  --cookies, --preview-count, --auto-confirm-first
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐   ┌──────────────────────┐
│  SeleniumWorker      │→→│ followers_you_follow │ (optional, on by default)
│  - captures lists    │   └──────────────────────┘
│  - reads profile tab │
│  - samples bios      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Human confirmation   │  preview top N (default 10) with coverage ratios
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ HybridShadowEnricher │  merges captures, resolves IDs, writes shadow tables
└──────────────────────┘
```

During the confirmation gate you’ll see:
- Seed profile metadata (display name, bio, location, website, claimed counts)
- Coverage per list (`captured / claimed` with percentage)
- A preview of the first *N* profiles (set with `--preview-count`, default 10)

Use `--auto-confirm-first` only after verifying the preview looks accurate. Disable the reciprocal list scrape with `--no-followers-you-follow` if you need to minimise requests.

Core components:
- **`scripts/enrich_shadow_graph.py`** — runs the hybrid pipeline (cookies + optional bearer token required)
- **`src/shadow/`** — Selenium worker, X API client, and enrichment coordinator
- **`src/data/shadow_store.py`** — typed access to the shadow cache tables
- **`scripts/verify_shadow_graph.py`** — reports ✓/✗ status for cached shadow data and analysis output

`scripts/enrich_shadow_graph.py` launches Chrome in visible mode by default and applies human-like delays (4–9 s) between actions. Use `--headless` only if you know X’s UI renders correctly without an interactive browser; pass `--chrome-binary` when you want to point at a custom Chrome install.

Example run:

```bash
# Setup cookies (one-time)
python -m scripts.setup_cookies --output secrets/twitter_cookies.pkl

# Run enrichment (default: fast, no API fallback)
python -m scripts.enrich_shadow_graph \
  --center adityaarpitha \
  --skip-if-ever-scraped \
  --auto-confirm-first \
  --max-scrolls 20

# With API fallback (slower but enriches accounts with missing bios)
python -m scripts.enrich_shadow_graph \
  --enable-api-fallback \
  --bearer-token "$X_BEARER_TOKEN" \
  --center adityaarpitha

# For long-running enrichment (macOS): prevent system sleep with caffeinate
caffeinate -disu .venv/bin/python3 -m scripts.enrich_shadow_graph --center adityaarpitha

# Analyze and verify
python -m scripts.analyze_graph --include-shadow --output analysis_output.json
python -m scripts.verify_shadow_graph
```

**Key flags:**
- `--center USERNAME` — Prioritize this user's following list
- `--skip-if-ever-scraped` — Skip accounts with sufficient existing data
- `--max-scrolls N` — Max stagnant scrolls before stopping (default: 6, use 20+ for 1000+ following)
- `--enable-api-fallback` — Use X API to enrich accounts with missing bios (slow, rate-limited)
- `--auto-confirm-first` — Skip preview confirmation
- `--quiet` — Minimal console output, full DEBUG to disk

**Logging:** All runs write DEBUG logs to `logs/enrichment.log` by default. Console shows INFO level unless `--quiet` is used.

In the explorer UI, toggle "Shadow enrichment" to show or hide shadow nodes. Shadow edges render as dashed slate lines; tooltips and detail cards display provenance plus scrape metadata.

## Usage

### Fetching Data

```python
from src.data.fetcher import CachedDataFetcher

with CachedDataFetcher() as fetcher:
    # Fetch profiles (uses cache if fresh, otherwise queries Supabase)
    profiles = fetcher.fetch_profiles()
    print(f"Loaded {len(profiles)} profiles")

    # Force refresh from Supabase
    fresh_profiles = fetcher.fetch_profiles(force_refresh=True)

    # Check cache health
    status = fetcher.cache_status()
    for table, info in status.items():
        print(f"{table}: {info['row_count']} rows, {info['age_days']:.1f} days old")
```

### Cache Management

- **View cache status:** `python3 scripts/verify_setup.py`
- **Force refresh:** Pass `force_refresh=True` to any fetch method
- **Bulk sync:** `python -m scripts.sync_supabase_cache` (add `--force` to bypass cache age checks)
- **Clear cache:** Delete `data/cache.db` and re-run fetcher
- **Adjust freshness:** Set `CACHE_MAX_AGE_DAYS` in `.env`

### Graph Snapshot Management

The API and frontend use precomputed graph snapshots for fast startup (see [ADR 004](./docs/adr/004-precomputed-graph-snapshots.md)).

**Refresh the snapshot after enrichment:**

```bash
python -m scripts.refresh_graph_snapshot --include-shadow
```

This generates:
- `data/graph_snapshot.nodes.parquet` — node table
- `data/graph_snapshot.edges.parquet` — edge table
- `data/graph_snapshot.meta.json` — freshness manifest
- `graph-explorer/public/analysis_output.json` — frontend JSON

**Automated refresh:** Add `--refresh-snapshot` to enrichment commands:

```bash
python -m scripts.enrich_shadow_graph --center adityaarpitha --refresh-snapshot
```

**Verify snapshot health:**

```bash
python -m scripts.verify_graph_snapshot
```

**Update README data snapshot (legacy):**

```bash
python -m scripts.analyze_graph --include-shadow --update-readme
```

## Testing

```bash
# Canonical local entrypoints (always use project .venv interpreter)
make verify-louvain-contract
make test-smoke
make test

# Run all unit tests (fast)
.venv/bin/python -m pytest tests/ -v -m unit

# Run integration tests (includes Selenium, slower)
.venv/bin/python -m pytest tests/ -v -m integration

# Run with coverage report
.venv/bin/python -m pytest --cov=src --cov-report=term-missing tests/

# Run specific test file
.venv/bin/python -m pytest tests/test_shadow_enrichment_integration.py -v
```

Test coverage (~68% overall, see `docs/test-coverage-baseline.md` for module-level stats):
- ✅ Supabase connectivity, authentication, and cache expiry safeguards
- ✅ DataFrame schema validation and network error handling
- ✅ Shadow enrichment policy logic (age/delta triggers, skip behavior)
- ✅ Profile extraction (Selenium selector parsing, JSON-LD fallback)
- ✅ Hybrid shadow store persistence (retry logic, coverage conversion)
- ✅ Flask API endpoints powering the graph explorer
- 🧪 191 pytest cases spanning unit, integration, and Selenium parsing suites

Test suite follows the behavioral testing principles captured in `docs/test-coverage-baseline.md`.

## Development Workflow

1. **Make changes** to `src/` modules
2. **Run tests:** `pytest tests/ -v`
3. **Verify integration:** `python3 scripts/verify_setup.py`
4. **Document decisions:** Add ADRs to `docs/adr/` for architectural changes
5. **Update WORKLOG:** Log progress in `docs/WORKLOG.md`

## Project Structure

```
tpot-analyzer/
├── data/
│   └── cache.db                  # SQLite cache (gitignored)
├── docs/
│   ├── BACKEND_IMPLEMENTATION.md
│   ├── DATABASE_SCHEMA.md
│   ├── ENRICHMENT_FLOW.md
│   ├── ROADMAP.md
│   ├── WORKLOG.md
│   └── adr/
│       ├── 001-data-pipeline-architecture.md
│       ├── 002-graph-analysis-foundation.md
│       └── 003-backend-api-integration.md
├── graph-explorer/
│   ├── README.md
│   ├── package.json
│   └── src/
├── scripts/
│   ├── analyze_graph.py
│   ├── enrich_shadow_graph.py
│   ├── verify_shadow_graph.py
│   └── verify_setup.py
├── src/
│   ├── api/
│   │   └── server.py
│   ├── data/
│   ├── graph/
│   ├── shadow/
│   ├── ui/
│   └── logging_utils.py
├── tests/
│   ├── test_api.py
│   ├── test_shadow_enrichment_integration.py
│   └── ...
├── .env.example
├── requirements.txt
└── README.md
```

## Troubleshooting

### "SUPABASE_KEY is not configured"
Export the anon key in your shell or add it to `.env`:
```bash
export SUPABASE_KEY=your_key_here
```

### "Supabase connection failed"
- Check network connectivity
- Verify the anon key is valid and has read access to the Community Archive
- Confirm `SUPABASE_URL` points to the correct instance

### Cache keeps refreshing
- Check `CACHE_MAX_AGE_DAYS` setting (default 7 days)
- Inspect cache metadata: `python3 scripts/verify_setup.py`
- Ensure `data/cache.db` is writable and not being deleted

### Import errors
Activate the virtual environment:
```bash
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

## Roadmap

- [x] **Phase 1.1:** Data pipeline with cached Supabase access ✅
- [x] **Phase 1.2:** Graph builder, metrics computation, CLI analysis tool ✅
- [x] **Phase 1.3:** Interactive visualization with React + d3-force ✅
- [ ] **Phase 1.4:** Shadow enrichment with policy-driven refresh (in progress, 91 tests passing)
- [ ] **Phase 2:** Temporal analysis (growth patterns, community evolution, edge history tracking)
- [ ] **Phase 3:** Advanced metrics (heat diffusion, GNN embeddings, engagement analysis)

## Documentation Guide

- **[README.md](./README.md)** (this file) — Project overview, setup, architecture, and usage
- **[CENTER_USER_FIX.md](./CENTER_USER_FIX.md)** — Fixes for center user prioritization and Twitter DOM changes (Oct 7-8, 2025)
- **[BUGFIXES.md](./BUGFIXES.md)** — Graph Explorer MVP bug fixes (Oct 7, 2025)
- **[TEST_MODE.md](./TEST_MODE.md)** — API server test mode for fast UI development
- **[docs/BACKEND_IMPLEMENTATION.md](./docs/BACKEND_IMPLEMENTATION.md)** — Flask backend implementation summary (Option B)
- **[docs/WORKLOG.md](./docs/WORKLOG.md)** — Detailed development log
- **[docs/ROADMAP.md](./docs/ROADMAP.md)** — Forward-looking backlog (testing, features, infra)
- **[docs/adr/](./docs/adr/)** — Architectural decision records

## References

- [Community Archive Supabase Schema](https://fabxmporizzqflnftavs.supabase.co)
- [ADR 001: Data Pipeline Architecture](./docs/adr/001-data-pipeline-architecture.md)
- [ADR 002: Graph Analysis & Interactive Exploration](./docs/adr/002-graph-analysis-foundation.md)
- [NetworkX Documentation](https://networkx.org/documentation/stable/)

## License

No license file is provided. Add one before distributing or open-sourcing the project.

#### Cookie Sessions

Run `python -m scripts.setup_cookies` to capture each account's cookies. The script now stores sessions as `secrets/twitter_cookies_<label>_<timestamp>.pkl`. When you launch enrichment without `--cookies`, you’ll be prompted to pick from the available files (the first file is used automatically in `--quiet` mode).

#### Profile-only Backfill

Use `python -m scripts.enrich_shadow_graph --profile-only --delay-min 5 --delay-max 40` to backfill profile metadata for seeds that already have follower/following edges. Pass `--profile-only-all` if you really want to refresh every seed regardless of status.

## Cluster View quickstart

- Precompute artifacts (small fixture example):
  ```bash
  PYTHONPATH=tpot-analyzer python3 tpot-analyzer/scripts/build_spectral.py \
    --data-dir tpot-analyzer/data \
    --output-prefix tpot-analyzer/data/graph_snapshot \
    --limit-nodes 500 --n-dims 10 --maxiter 500 --tol 1e-6
  ```
- Verify artifacts:
  ```bash
  PYTHONPATH=tpot-analyzer python3 tpot-analyzer/scripts/verify_clusters.py \
    --base-path tpot-analyzer/data/graph_snapshot --granularity 25
  ```
- Medium fixture (2000 nodes) lives at `tests/fixtures/medium_graph/graph_snapshot.*` and is exercised in CI.
- Start backend after precompute: `PYTHONPATH=tpot-analyzer python3 tpot-analyzer/scripts/start_api_server.py`
- Frontend: use the Cluster View tab (in `graph-explorer`) to hit `/api/clusters` with granularity and Louvain weight slider.
