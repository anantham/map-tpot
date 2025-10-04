# ADR 001: Data Pipeline Architecture

- Status: Accepted
- Date: 2025-09-05
- Authors: Computational Peer + Human Collaborator
- Phase: 1.1 – Data Pipeline Setup

## Context

The TPOT Community Graph Analyzer needs reliable access to Community Archive data
(6.9M tweets, 12.3M likes, detailed profiles and interaction metadata). The
Archive is hosted in a public Supabase PostgreSQL instance. We must minimize
network chatter, support offline analysis, and ensure reproducible input data
before constructing higher-level graph analytics.

Key constraints:
- Read-only Supabase access shared across multiple agents.
- Human collaborators expect quick iteration without rate-limit surprises.
- Future phases will run exploratory queries repeatedly and in parallel.
- Local development environments may be offline or bandwidth-constrained.

## Decision

Adopt an API-first data access layer backed by a local SQLite cache. All data
fetches route through a `CachedDataFetcher` that queries Supabase first when the
cache is stale or forced to refresh, then persists normalized tables to SQLite
for reuse. Fetchers return pandas DataFrames to integrate smoothly with the
analysis stack.

## Rationale

- **Network efficiency:** Supabase calls occur only when cache entries expire or
  a refresh is explicitly requested.
- **Offline support:** Analysts can work with cached snapshots even without
  network access, satisfying Phase 1.1 goals.
- **Traceability:** SQLite cache tables include metadata columns (fetched_at,
  row counts) so humans can inspect the provenance of local data quickly.
- **Incremental evolution:** The cache layer can be extended with table-specific
  invalidation and future sync strategies without rewriting client code.

## Alternatives Considered

1. **Direct Supabase queries on every run**
   - *Pros:* Simpler implementation, no local state.
   - *Cons:* High latency, brittle under network issues, risks API rate limits.

2. **Full local PostgreSQL mirror**
   - *Pros:* Complete control over SQL, powerful joins.
   - *Cons:* Large storage footprint, heavy initial sync, operational burden.

## Consequences

- Development requires SQLite tooling alongside Supabase credentials.
- Cache invalidation policy (default 7 days) must be documented for humans and
  tests; future phases may tune per-table freshness requirements.
- Verification scripts must expose cache health to keep human gatekeepers in the
  loop (Directive 11).

## Follow-Up Actions

- Implement `CachedDataFetcher` with methods for profiles, tweets, and likes.
- Emit logs when cache entries exceed freshness thresholds.
- Document manual refresh workflows in the project README and WORKLOG.

## Related Decisions

- TBD: Phase 1.2 ADR covering engagement graph materialization.

## References

- Community Archive Supabase schema documentation.
- Operating Manual for Computational Peers (Prime Directives 1–11).
