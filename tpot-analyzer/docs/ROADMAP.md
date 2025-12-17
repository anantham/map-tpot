# Roadmap

Living backlog of follow-on work items. Update this document as new ideas,
coverage gaps, or UX improvements surface.

## Testing Coverage

- Expand Selenium worker coverage to browser lifecycle + scrolling workflows once
  reliable integration harness is available.
- [x] Automate README graph snapshot insertion via `python -m scripts.analyze_graph --update-readme`
  (implemented 2025-10-11; maintains marker block in README).
- Add Playwright smoke tests for graph-explorer front end (load graph, adjust
  weights, inspect node detail panel).

## Features & Analysis

- Phase 1.4 completion: finalize policy-driven refresh loop and document human
  confirmation UX.
- Phase 2 planning: temporal analysis of follower deltas and community evolution
  (requires historical scrape storage upgrades).
- Investigate advanced metrics (heat diffusion, GNN embeddings) once baseline
  enrichment stabilizes.
- Surface cached list snapshot freshness in CLI summaries and reuse them when
  prioritising seeds (now that persistence exists).

## Infrastructure & Tooling

- Introduce caching layer for Flask metrics endpoint to reduce recomputation
  during rapid slider adjustments.
- Monitor SQLite growth and evaluate move to PostgreSQL if enrichment scale
  exceeds current performance envelope.
- Bundle verification scripts (`scripts/verify_*.py`) into a consolidated CLI
  entry point for Phase 2.
- Add housekeeping task to expire or refresh list snapshots that exceed
  `list_refresh_days` so cache stays accurate.
- Instrument Selenium/enricher phases with timing metrics so slow steps are
  visible in summaries and `ScrapeRunMetrics`.
- Add GPU-aware execution path: at startup detect CUDA-capable hardware
  (e.g., via `nvidia-smi` or PyTorch), route heavy graph metrics to cuGraph /
  RAPIDS when available, and fall back to CPU when no dGPU is present.

## Developer Experience

- Document end-to-end enrichment + explorer refresh workflow in a `docs/PLAYBOOK.md`.
- Add `make` targets (or equivalent task runner) to standardize setup, tests,
  and verification commands.
- Decompose `tpot-analyzer/graph-explorer/src/GraphExplorer.jsx` into smaller components/hooks (<300 LOC each) to keep debugging manageable.
