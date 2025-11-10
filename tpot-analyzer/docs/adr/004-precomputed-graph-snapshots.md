# ADR 004: Precomputed Graph Snapshots for Explorer Startup

- Status: Accepted
- Date: 2025-11-07
- Authors: Computational Peer + Human Collaborator
- Phase: 1.4 — Shadow Enrichment & Explorer Ergonomics

## Context

The current Flask API rebuilds the full TPOT graph on every request:

1. `CachedDataFetcher` reads four archive tables (account/profile/followers/following) from `data/cache.db`.
2. `ShadowStore` injects ~70k nodes / 226k directed edges from enrichment tables.
3. NetworkX constructs the directed/undirected views before returning JSON (for `/api/graph-data`) or running PageRank/Betweenness/Louvain (for `/api/metrics/compute`).

This keeps the explorer fresh but pushes every page load through 10–12 s of redundant work, even when the underlying data has not changed since the last enrichment. The cost is visible in the logs (large gaps between cache reads and response emission) and blocks the “empty canvas → user-driven expansion” UX we want to build next.

We already have CLI tooling (`scripts/analyze_graph.py`) that emits a complete graph snapshot plus metrics. What is missing is a canonical workflow that promotes that snapshot to the default data source for the explorer/API so we only recompute when necessary.

## Decision

Adopt **Option 2 — Precomputed Snapshots** with the following contract:

1. A dedicated refresh script (wrapper around `scripts.analyze_graph.py`) emits:
   - `graph-explorer/public/analysis_output.json` — the public graph payload consumed by the React app.
   - `data/graph_snapshot.nodes.parquet` / `data/graph_snapshot.edges.parquet` — portable node/edge tables (Feather/Parquet) for the backend to reload quickly without pickle brittleness.
   - `data/graph_snapshot.meta.json` — manifest capturing `generated_at`, `cache_db_modified`, counts, and flags (e.g., `include_shadow`).
2. On API startup, read the manifest and compare `cache_db_modified` to the current mtime of `data/cache.db`. If the cache is newer, log a warning and fall back to the live SQLite rebuild; otherwise, serve `/api/graph-data` from the snapshot tables and reconstruct NetworkX graphs from the Parquet data on demand.
3. Keep the `GraphBuildResult` in memory only when metrics are actively being computed. For large future graphs we can reconstruct from the Parquet payload per request instead of pinning a 500k-edge graph in RAM.
4. Provide a verification script (`scripts/verify_graph_snapshot.py`) that reports ✓/✗ for manifest freshness, counts, and parity with the SQLite cache.
5. Automate refreshes: `scripts/enrich_shadow_graph.py` gains a `--refresh-snapshot` flag (or post-run hook) that invokes the refresh script once enrichment succeeds, so operators don’t have to remember a manual step.

This choice mirrors the original static JSON workflow but preserves the dynamic metric API for ad-hoc seed changes.

## Consequences

**Positive**

- Explorer startup becomes I/O bound on serving a JSON file (<200 ms) instead of recomputing 226k edges.
- The API remains available for seeds/weights changes, but avoids redundant cache reads unless the snapshot is stale or the operator forces a rebuild.
- Background snapshot generation can run on a schedule (post-enrichment hook, nightly cron) without impacting interactive users.
- Simplifies the “empty canvas” UX: we can bootstrap suggestions from the snapshot metadata without touching SQLite on every search.

**Negative / Considerations**

- Snapshot freshness still depends on discipline, but the manifest + mtime comparison and enrichment hook reduce risk. If the cache DB changes after the snapshot, startup will warn and rebuild live.
- Additional disk artifacts (JSON + Parquet + manifest) must be managed. Need to ensure `.gitignore`/CI handle large files and sensitive paths.
- Reconstructing NetworkX graphs from Parquet adds a small CPU hit, but it remains far cheaper than querying SQLite + merging shadow tables per request.

## Alternatives Considered

1. **Status quo (live rebuild on every request)**  
   - Pros: Always reflects latest cache metadata.  
   - Cons: 10–12 s latency, repeated disk churn, makes incremental UI impossible.

2. **In-process caching only**  
   - Load graph once per Flask worker and refresh on a timer.  
   - Less operational overhead but harder to coordinate across multiple processes and still leaves the frontend waiting for the first build after every deploy.

3. **Full task queue / streaming backend**  
   - Adds Redis/celery to precompute and stream deltas.  
   - Overkill for current scale and violates Prime Directive #4 (needs human validation before big architectural changes).

## Implementation Notes

- New script: `scripts/refresh_graph_snapshot.py` (wrapper that calls `scripts.analyze_graph.py --include-shadow --output graph-explorer/public/analysis_output.json --nodes data/graph_snapshot.nodes.parquet --edges data/graph_snapshot.edges.parquet --manifest data/graph_snapshot.meta.json` and logs coverage).
- Backend loader: `src/api/server.py` gains a snapshot loader that prefers the Parquet + manifest artifacts; falls back to live rebuild only if snapshot is missing or manifest indicates staleness.
- Verification: `scripts/verify_graph_snapshot.py` prints ✓/✗ for snapshot timestamp, node/edge counts, and a diff vs `SELECT COUNT(*)` from `shadow_edge`. Output follows the project’s verification format (Directive 11).
- Documentation: README + WORKLOG describe how/when to regenerate; ADR stays immutable after acceptance per guidelines.

## Testing & Verification

- Extend `tests/test_api.py` with a fixture that loads a synthetic snapshot and asserts `/api/graph-data` never touches `CachedDataFetcher`.
- Unit test the snapshot loader to ensure it rejects stale files and falls back correctly.
- Run the new verification script as part of `scripts/verify_setup.py` or a dedicated CI job.

## Status & Next Steps

Status is **Proposed** until we align on the operational cadence. After acceptance:

1. Implement the snapshot refresh + manifest + loader + verification script, and add the enrichment hook (`--refresh-snapshot`) so snapshots can be regenerated automatically after successful scrapes.
2. Update documentation (README, ROADMAP, WORKLOG) with the new workflow.
3. Plan follow-up ADR or WORKLOG entry for the incremental explorer UX that will rely on this precomputed data.
