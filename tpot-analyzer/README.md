# TPOT Community Graph Analyzer

Python-based network analysis toolkit for exploring the TPOT (This Part of Twitter) community using the Community Archive dataset (6.9M tweets, 12.3M likes, follow relationships, and detailed profile metadata).

## Project Status

**Phase 1.1 (Complete):** Data pipeline with cached Supabase access
**Phase 1.2 (Complete):** Follow graph construction, status metrics (PageRank, Louvain, betweenness), CLI analysis tool
**Phase 1.3 (Complete):** Interactive visualization with React + d3-force graph explorer
**Phase 1.4 (In Progress):** Shadow enrichment pipeline with policy-driven refresh logic

See [docs/WORKLOG.md](./docs/WORKLOG.md) for detailed progress and [docs/adr/](./docs/adr/) for architectural decisions.

## Prerequisites

- Python 3.10+
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
python -m scripts.setup_cookies --output secrets/twitter_cookies.pkl
python -m scripts.enrich_shadow_graph \
  --cookies secrets/twitter_cookies.pkl \
  --include-followers \
  --preview-count 12 \
  --chrome-binary "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --delay-min 4 --delay-max 9 \
  --bearer-token "$X_BEARER_TOKEN"

python -m scripts.analyze_graph --include-shadow --output analysis_output.json
python -m scripts.verify_shadow_graph
```

In the explorer UI, toggle “Shadow enrichment” to show or hide shadow nodes. Shadow edges render as dashed slate lines; tooltips and detail cards display provenance plus scrape metadata.

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
- **Clear cache:** Delete `data/cache.db` and re-run fetcher
- **Adjust freshness:** Set `CACHE_MAX_AGE_DAYS` in `.env`

## Testing

```bash
# Run all unit tests (fast)
pytest tests/ -v -m unit

# Run integration tests (includes Selenium, slower)
pytest tests/ -v -m integration

# Run with coverage report
pytest --cov=src --cov-report=term-missing tests/

# Run specific test file
pytest tests/test_shadow_enrichment_integration.py -v
```

Test coverage (54% overall, see `docs/test-coverage-baseline.md`):
- ✅ Supabase connectivity and authentication
- ✅ Cache read/write/expiry logic with staleness detection
- ✅ DataFrame schema validation
- ✅ Error handling for network failures
- ✅ Shadow enrichment policy logic (age/delta triggers, skip behavior)
- ✅ Profile extraction (Selenium selector parsing, JSON-LD fallback)
- ✅ Integration tests for enrichment workflow (91 tests total)

Test suite follows behavioral testing principles (see `AGENTS.md` TEST_DESIGN_PRINCIPLES).

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
│   ├── .gitkeep
│   └── cache.db          # SQLite cache (gitignored)
├── docs/
│   ├── WORKLOG.md        # Development log
│   └── adr/              # Architectural decision records
├── scripts/
│   └── verify_setup.py   # Setup verification and diagnostics
├── src/
│   ├── __init__.py
│   ├── config.py         # Environment configuration
│   └── data/
│       ├── __init__.py
│       └── fetcher.py    # Cached Supabase data access layer
├── tests/
│   ├── __init__.py
│   └── test_connection.py
├── .env.example          # Environment template
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
