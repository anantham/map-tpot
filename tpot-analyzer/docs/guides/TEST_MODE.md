# Test Backend Workflow

## Overview

The old one-file API bootstrap script was an early prototype and is no longer the canonical backend.
Use `python -m scripts.start_api_server` for all current API routes.

If you want deterministic, small test data for local UI iteration, run the
backend against a generated fixture `cache.db`.

## Start a Deterministic Test Backend

From `tpot-analyzer/`:

```bash
# 1) Create a small deterministic cache database
python - <<'PY'
from pathlib import Path
from tests.fixtures.create_test_cache_db import create_test_cache_db

snapshot_dir = Path("data/test_mode")
snapshot_dir.mkdir(parents=True, exist_ok=True)
cache_db = snapshot_dir / "cache.db"
counts = create_test_cache_db(cache_db)
print(f"Created {cache_db} with rows: {counts.as_dict()}")
PY

# 2) Start backend using that fixture DB
SNAPSHOT_DIR="$PWD/data/test_mode" \
CACHE_DB_PATH="$PWD/data/test_mode/cache.db" \
python -m scripts.start_api_server
```

## Verify Backend

In another terminal:

```bash
curl http://localhost:5001/api/health
```

Expected response:

```json
{"service":"tpot-analyzer","status":"ok"}
```

## Notes

- This workflow exercises the same modern backend entrypoint as production.
- Cluster-specific endpoints may still require spectral snapshot sidecars
  (`graph_snapshot.spectral.npz`) depending on which UI flows you test.
- For full-stack operational workflow (backend + frontend + verification),
  use `docs/PLAYBOOK.md`.
