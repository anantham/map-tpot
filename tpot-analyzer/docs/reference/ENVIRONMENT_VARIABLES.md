# Environment Variables Reference

All environment variables used by the TPOT Analyzer, their defaults, and where they apply.

## API Server

| Variable | Default | Used In | Purpose |
|----------|---------|---------|---------|
| `PORT` | `8000` | `server.py` | HTTP port for dev server (`app.run`) |
| `FLASK_DEBUG` | `false` | `server.py` | Enable Flask debug mode (dev only, never in production) |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | `server.py` | Comma-separated allowed CORS origins. Set to your production domain in deployment. |
| `API_LOG_LEVEL` | `INFO` | `server.py`, `cluster_routes.py` | Log level for API and cluster routes. Options: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `CLUSTER_LOG_LEVEL` | (falls back to `API_LOG_LEVEL`) | `cluster_routes.py` | Override log level for cluster routes specifically |
| `TPOT_LOG_DIR` | `<project_root>/logs` | `server.py`, `log_routes.py` | Directory for API and frontend log files |
| `SNAPSHOT_DIR` | `data` | `config.py`, Dockerfile | Directory containing graph snapshots (parquet/npz files) |
| `ARCHIVE_DB_PATH` | `data/archive_tweets.db` | `branches.py`, `communities.py` | Path to the archive tweets SQLite database |

## Rate Limiting

| Variable | Default | Used In | Purpose |
|----------|---------|---------|---------|
| `RATE_LIMIT_DEFAULT` | `200 per minute` | `server.py` | Global rate limit per IP across all endpoints |
| `RATE_LIMIT_INTERPRET` | `10 per hour` | `server.py` | Rate limit for `/api/golden/interpret` (LLM calls, costs money) |
| `RATE_LIMIT_CLUSTER_BUILD` | `30 per minute` | `server.py` | Rate limit for `/api/clusters` (spectral computation) |
| `RATE_LIMIT_SEARCH` | `60 per minute` | `server.py` | Rate limit for `/api/accounts/search` |
| `RATE_LIMIT_DISCOVERY` | `20 per minute` | `server.py` | Rate limit for `/api/subgraph/discover` (PageRank computation) |

## Authentication & Secrets

| Variable | Default | Used In | Purpose |
|----------|---------|---------|---------|
| `TPOT_EXTENSION_TOKEN` | (none) | `golden.py`, `extension_utils.py` | Token for authenticating the Chrome extension and LLM interpret endpoint. When set, `/api/golden/interpret` requires this token via `X-TPOT-Extension-Token` header. |
| `OPENROUTER_API_KEY` | (none) | `golden.py`, `classify_tweets.py` | API key for OpenRouter LLM calls (tweet interpretation and classification) |
| `SUPABASE_URL` | (none) | `.env` | Community Archive Supabase project URL |
| `SUPABASE_KEY` | (none) | `.env` | Community Archive Supabase anon key (read-only, publicly safe) |
| `X_BEARER_TOKEN` | (none) | scripts | Twitter/X API v2 bearer token for shadow enrichment and account data refresh |

## Golden Dataset / LLM Interpretation

| Variable | Default | Used In | Purpose |
|----------|---------|---------|---------|
| `GOLDEN_INTERPRET_ALLOW_REMOTE` | (unset = disabled) | `golden.py` | Set to `1`/`true`/`yes` to allow `/api/golden/interpret` without a token. Use only for fully open instances. |
| `GOLDEN_INTERPRET_ALLOWED_MODELS` | `moonshotai/kimi-k2, ...` | `golden.py` | Comma-separated list of allowed LLM model IDs for interpretation. Overrides the built-in default list. |

## GPU / Performance

| Variable | Default | Used In | Purpose |
|----------|---------|---------|---------|
| `USE_GPU_METRICS` | (unset) | `gpu_capability.py` | Set to `true`/`1` to enable GPU-accelerated graph metrics |
| `FORCE_CPU_METRICS` | (unset) | `gpu_capability.py` | Set to `true`/`1` to force CPU even when GPU is available |

## Scripts / Enrichment

| Variable | Default | Used In | Purpose |
|----------|---------|---------|---------|
| `TEST_MODE` | `0` | `scripts/api_server.py` | Set to `1` to use deterministic test dataset instead of real data |
| `TPOT_EXTENSION_FIREHOSE_PATH` | (none) | `extension_runtime.py` | Override path for extension firehose NDJSON file |

## Fly.io Deployment

These are set via `flyctl secrets set` or in `fly.toml`:

```bash
# Required for production
flyctl secrets set OPENROUTER_API_KEY=sk-or-v1-...
flyctl secrets set TPOT_EXTENSION_TOKEN=your-secret-token
flyctl secrets set CORS_ORIGINS=https://your-domain.com

# Already in fly.toml (don't duplicate)
# SNAPSHOT_DIR=/app/data
# TPOT_LOG_DIR=/app/logs
# API_LOG_LEVEL=INFO
```

## .env.example

For local development, copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
# Edit .env with your API keys
```

The `.env` file is gitignored and will never be committed.
