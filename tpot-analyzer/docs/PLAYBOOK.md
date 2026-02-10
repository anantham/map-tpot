# TPOT Analyzer Playbook

Operational workflow for day-to-day development and verification.

## 1) Backend

From `tpot-analyzer/`:

```bash
source .venv/bin/activate
python -m scripts.start_api_server
```

Health check:

```bash
curl http://localhost:5001/api/health
```

Expected:

```json
{"service":"tpot-analyzer","status":"ok"}
```

## 2) Frontend

From `tpot-analyzer/graph-explorer/`:

```bash
npm install
npm run dev
```

Open:

- `http://localhost:5173`

## 3) Deterministic Test Dataset (Optional)

From `tpot-analyzer/`:

```bash
python - <<'PY'
from pathlib import Path
from tests.fixtures.create_test_cache_db import create_test_cache_db

snapshot_dir = Path("data/test_mode")
snapshot_dir.mkdir(parents=True, exist_ok=True)
cache_db = snapshot_dir / "cache.db"
counts = create_test_cache_db(cache_db)
print(f"Created {cache_db} with rows: {counts.as_dict()}")
PY
```

Run backend against this dataset:

```bash
SNAPSHOT_DIR="$PWD/data/test_mode" \
CACHE_DB_PATH="$PWD/data/test_mode/cache.db" \
python -m scripts.start_api_server
```

## 4) Verification Commands

Backend API smoke:

```bash
.venv/bin/python -m pytest tests/test_api.py -q
```

Discovery endpoint smoke (requires backend running):

```bash
.venv/bin/python -m scripts.verify_discovery_endpoint
```

Frontend/backend route contract audit:

```bash
.venv/bin/python -m scripts.verify_api_contracts
```

API route/service regression bundle:

```bash
.venv/bin/python -m scripts.verify_api_services_tests
```

Firehose relay verifier (local mock endpoint):

```bash
.venv/bin/python scripts/verify_firehose_relay.py
```

Continuous firehose relay (spectator streams -> Indra endpoint):

```bash
.venv/bin/python scripts/relay_firehose_to_indra.py
```

Override endpoint if needed:

```bash
.venv/bin/python scripts/relay_firehose_to_indra.py \
  --endpoint-url http://localhost:7777/api/firehose/ingest
```

Frontend unit:

```bash
cd graph-explorer
npx vitest run
```

Frontend E2E (mock):

```bash
cd graph-explorer
npm run test:e2e:mock
```

Frontend E2E (real backend):

```bash
cd graph-explorer
npm run test:e2e:real
```

## 5) Logs and Diagnostics

- API logs: `tpot-analyzer/logs/api.log`
- Frontend log events: `tpot-analyzer/logs/frontend.log`
- Vite logs (if started via dev script): `tpot-analyzer/logs/vite.log`

Useful helper:

```bash
.venv/bin/python -m scripts.tail_cluster_logs --help
```

## 6) Common Reset Steps

If backend is stuck on port 5001:

```bash
lsof -nP -iTCP:5001 -sTCP:LISTEN
kill <PID>
```

If frontend cache/state causes stale behavior:

```bash
# restart Vite server
cd graph-explorer
npm run dev
```

## 7) Docs Release Checklist

When shipping doc updates:

1. Run docs hygiene verification:

```bash
python3 -m scripts.verify_docs_hygiene
```

2. Update `docs/index.md` for new docs, moved docs, or superseded docs.
3. Add a timestamped entry in `docs/WORKLOG.md` with file paths, line numbers, and verification command results.
4. For historical docs under `docs/tasks/` or `docs/archive/`, add or refresh modernization/historical notes when legacy commands are mentioned.
