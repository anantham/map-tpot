# ADR 002: Graph Analysis & Interactive Exploration Foundation

- Status: Accepted
- Date: 2025-10-04 (accepted 2025-10-10)
- Authors: Computational Peer + Human Collaborator
- Phase: 1.2 — Follow Graph Construction, Metrics, and Interactive Exploration

## Context

With the REST-based data pipeline in place (ADR 001), the next milestone is to
materialize the TPOT follow graph, derive interpretable status metrics, and make
those metrics explorable through an interactive, force-directed visualization.

The community archive currently exposes ~280 fully uploaded accounts, along with
`followers`/`following` adjacency tables and engagement metrics (likes, tweets).
We also maintain curated Twitter lists (e.g., Adi's TPOT list) that reflect a
human sense of "core" membership.

## Decision

Build a graph analysis and exploration layer inside `tpot-analyzer` that:

1. Loads cached Supabase tables (`account`, `profile`, `followers`, `following`)
   and constructs a directed graph (account IDs as nodes, follow edges as arcs)
   with node attributes (username, display name, follower counts, upload info,
   aggregate engagement).
2. Supports seed selection from pasted Twitter list HTML, uploaded CSV, or
   manual username input, defaulting to Adi's curated TPOT list.
3. Computes three baseline metrics client-side:
   - Personalized PageRank (restart probability 0.15) seeded on selected
     accounts.
   - Louvain community detection on the undirected (mutual-only) projection.
   - Betweenness centrality on the undirected projection.
4. Exposes an interactive React + d3-force artifact that:
   - Fetches minimal data (~5MB: accounts, mutual follow edges, aggregated
     engagement counts).
   - Allows toggling mutual-only view (default: on), setting minimum follower
     threshold, and adjusting status metric weights (α×PageRank + β×betweenness
     + γ×engagement).
   - Provides force-simulation controls (link distance, charge strength,
     gravity) and Louvain resolution slider.
   - Recomputes metrics and updates the visualization within 200 ms of any
     parameter change.
   - Supports focus views (ego network, path highlighting) in later iterations.
5. Outputs CSV summaries and human-readable rankings for reproducibility and CLI
   usage.

## Interactive Parameters (initial set)

**Graph filters**
- Mutual-only toggle (default ON) — show only bidirectional follows.
- Minimum follower threshold (default 0).

**Status metrics**
- PageRank weight α (0–1, default 0.4).
- Betweenness weight β (0–1, default 0.3).
- Engagement rate weight γ (0–1, default 0.3).

**Force simulation**
- Link distance (50–500px, default 100).
- Charge strength (−500 to −50, default −200).
- Gravity (0–1, default 0.1).

**Community detection**
- Louvain resolution (0.5–2.0, default 1.0).

All adjustments trigger immediate recalculation and animated transitions.

## Rationale

- **Responsiveness over scale:** With ~280 nodes, client-side computation (d3,
  NetworkX-like algorithms via JavaScript or WebAssembly) delivers <200 ms
  feedback, essential for exploratory analysis.
- **Transparency:** Making parameters visible as sliders/toggles prevents
  undocumented assumptions and encourages experimentation.
- **Seed flexibility:** Allowing users to import their own seed lists keeps the
  tool adaptable to different mental models of "core" TPOT.
- **Mutual-only focus:** Highlighting reciprocal relationships filters noise and
  surfaces status gradients more clearly.
- **UI first-steps:** Starting with force-directed graph ensures quick wins;
  additional views (timeline, diffusion) can layer on later.

## Alternatives Considered

1. CLI-only outputs (no interactive layer).
   - Pros: Simpler, faster to implement.
   - Cons: Hides design decisions, diminishes exploratory value.
2. Server-side metric computation.
   - Pros: Centralized logic.
   - Cons: Adds latency, complicates offline use, not needed at current scale.
3. Graph database (Neo4j).
   - Pros: Cypher query language, built-in visualization.
   - Cons: Overkill for current dataset, additional operational burden.

## Consequences

- Frontend stack includes React + d3-force (or vis-network) with state
  management for parameters.
- Need deterministic data loading and tests to keep behavior predictable as the
  archive grows.
- CSV/JSON outputs remain important for reproducibility and integration with
  notebooks or future services.
- Later phases can introduce advanced metrics (heat diffusion, temporal slices,
  GNN embeddings) without rearchitecting the pipeline.

## Work Items (Phase 1.2)

1. `docs/WORKLOG.md` — update phase entries, findings.
2. `src/graph/builder.py` — load cached data, clean it, construct directed and
   undirected graphs with attributes, mutual-only view support.
3. `src/graph/metrics.py` — implement personalized PageRank, Louvain, and
   betweenness with configurable weights and seeds.
4. `src/ui/seeds.py` — parse Twitter list HTML/CSV into seed sets, maintain
   default presets.
5. `artifacts/graph-explorer.jsx` (or similar) — React component for data fetch,
   parameter controls, d3-force visualization.
6. `scripts/analyze_graph.py` — CLI entrypoint to compute metrics and export
   CSV/JSON for non-interactive workflows.
7. Tests: `tests/test_graph_builder.py`, `tests/test_metrics.py`, and
   `tests/test_seed_parser.py` using small fixtures to verify behavior.

## References

- ADR 001: Data Pipeline Architecture
- NetworkX documentation on PageRank, community detection, betweenness
- Supabase schema (followers/following interaction tables)
- Adi’s TPOT Twitter list (seed example)
