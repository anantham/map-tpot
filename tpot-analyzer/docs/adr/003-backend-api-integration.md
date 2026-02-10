# ADR 003: Backend API Integration for Graph Explorer

- Status: Accepted
- Date: 2025-10-10
- Authors: Computational Peer + Human Collaborator
- Phase: 1.3 — Interactive Visualization Evolution

## Context

The initial graph-explorer (Phase 1.3 kickoff) rendered metrics from a static
`analysis_output.json` artifact. Seed sliders and weight controls were wired to
client-side state only, meaning new seeds could not influence PageRank output,
metrics fell out of sync with enrichment updates, and the UI encouraged stale
interpretations of the TPOT graph.

Iterative enrichment work (Phase 1.4) increased the velocity of new shadow nodes
and demanded a live connection between the React UI and the cached SQLite data.
We evaluated options ranging from fully static regeneration to a heavy-weight
backend with caching and queueing.

## Decision

Adopt a lightweight Flask backend ("Option B — Simple Backend") that exposes the
minimum API surface needed for interactive exploration:

- `GET /health`: service availability check.
- `GET /api/graph-data`: returns node/edge structure with optional mutual and
  shadow filtering.
- `POST /api/metrics/compute`: recomputes personalized PageRank, betweenness,
  engagement, and composite scores using server-side NetworkX.
- `GET /api/metrics/presets`: surfaces curated seed lists.

The backend reuses the existing cached data pipeline (`CachedDataFetcher`,
`ShadowStore`) and runs in-process with simple configuration flags. The React
frontend now calls these endpoints via the `graph-explorer/src/data.js` client.

## Consequences

- Seed changes and weight sliders now trigger real recomputation; the UI reflects
  fresh enrichment data without manual JSON exports.
- PageRank, betweenness, and engagement weightings are evaluated server-side,
  ensuring consistent behavior between CLI and UI.
- Response times (300–1500 ms) remain acceptable for exploratory use; future
  caching can be layered without re-architecting.
- Additional verification is required (`tests/test_api.py`) to cover HTTP
  endpoints, but coverage remains within the existing pytest workflow.

## Alternatives Considered

1. **Static JSON regeneration** after every enrichment run.
   - Pros: zero backend maintenance.
   - Cons: breaks interactive seed/slider expectations; easy to ship stale data.

2. **Full-featured backend with task queue/caching layer.**
   - Pros: future-proof for heavier workloads.
   - Cons: unnecessary complexity for current dataset scale (~8k nodes post
     enrichment) and limited team bandwidth.

## References

- `docs/reference/BACKEND_IMPLEMENTATION.md` — implementation log and acceptance criteria.
- `graph-explorer/README.md` — architecture and setup instructions.
- `tests/test_api.py` — regression coverage for the new API surface.
