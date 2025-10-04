# TPOT Community Graph Analyzer

Python-based network analysis toolkit for exploring the TPOT (This Part of Twitter) community using the Community Archive dataset (6.9M tweets, 12.3M likes, follow relationships, and detailed profile metadata).

## Project Status

**Phase 1.1 (Complete):** Data pipeline with cached Supabase access
**Phase 1.2 (Planned):** Follow graph construction, status metrics (PageRank, Louvain, betweenness), and interactive visualization

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

### Graph Analysis (Phase 1.2 — In Planning)

Planned features:
- Directed follow graph construction with mutual-only view support
- Baseline metrics: Personalized PageRank, Louvain communities, betweenness centrality
- Interactive force-directed visualization (React + d3-force)
- Configurable status metric weights and graph filters
- CSV/JSON exports for reproducibility

See [ADR 002](./docs/adr/002-graph-analysis-foundation.md) for full specification.

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
pytest tests/ -v
```

Test coverage includes:
- Supabase connectivity and authentication
- Cache read/write/expiry logic
- DataFrame schema validation
- Error handling for network failures

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

- [ ] **Phase 1.2:** Graph builder, metrics computation, CLI analysis tool
- [ ] **Phase 1.3:** Interactive visualization with React + d3-force
- [ ] **Phase 2:** Temporal analysis (growth patterns, community evolution)
- [ ] **Phase 3:** Advanced metrics (heat diffusion, GNN embeddings)

## References

- [Community Archive Supabase Schema](https://fabxmporizzqflnftavs.supabase.co)
- [ADR 001: Data Pipeline Architecture](./docs/adr/001-data-pipeline-architecture.md)
- [ADR 002: Graph Analysis & Interactive Exploration](./docs/adr/002-graph-analysis-foundation.md)
- [NetworkX Documentation](https://networkx.org/documentation/stable/)

## License

No license file is provided. Add one before distributing or open-sourcing the project.
