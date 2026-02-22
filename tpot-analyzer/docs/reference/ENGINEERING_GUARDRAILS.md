# Engineering Guardrails (Empirical)

Purpose: capture recurring failure patterns observed in this repository and
translate them into enforceable engineering guardrails.

Format per item:
- `Symptom` (what user/operator observes)
- `Generator` (deeper failure pattern)
- `Invariant` (always-true rule)
- `Guardrail` (test/check/runtime enforcement)
- `Migration policy` (how to change safely)

---

## 1) Discovery BFS Frontier Collapse (2026-02-18)

### Symptom
- Discovery UI could show empty/under-filled recommendations even with valid
  seeds, surfacing as:
  `No recommendations found. Try adjusting your filters.`
  (`graph-explorer/src/Discovery.jsx:948`)

### Data flow trace
1. Frontend dispatches recommendation request from:
   `graph-explorer/src/hooks/useRecommendations.js:280`
2. API route validates/resolves seeds and calls discovery engine:
   `src/api/routes/discovery.py:92`, `src/api/routes/discovery.py:138`
3. Engine expands k-hop neighborhood in:
   `src/api/discovery.py:211`

Historical bug shape (pre-fix):
```python
subgraph_nodes.update(next_layer)
current_layer = next_layer - subgraph_nodes
```
Because `subgraph_nodes` is updated first, `current_layer` becomes empty and
the BFS cannot progress to the next hop.

### Generator
- Mutation-order bug in iterative graph traversal (updating visited-state
  before deriving next frontier).

### Invariant
- BFS frontier must be computed against the previous visited set, then visited
  set can be mutated.

### Guardrail
- Unit regressions:
  `tests/test_discovery_logic.py:9`
  - depth=2 includes two-hop node
  - depth boundary excludes three-hop node
- Human-friendly verifier:
  `scripts/verify_discovery_depth.py:1`

### Migration policy
- Any traversal refactor must preserve depth semantics via fixture graph tests.
- Prefer pure helper extraction (`compute_next_frontier`) if traversal logic
  gets more complex.

---

## 2) Fetcher Resource Lifecycle Leak (2026-02-18)

### Symptom
- Intermittent SQLite handle contention and file I/O instability under repeated
  test runs.

### Data flow trace
1. Discovery/graph load fallback opens DB-backed fetcher:
   `src/api/routes/discovery.py:36`
2. Fetcher teardown previously did not dispose SQLAlchemy engine pools.
3. Handles accumulated over long runs.

### Generator
- Ownership mismatch: class owned multiple resources (HTTP + DB engine), but
  `close()` released only a subset.

### Invariant
- Any class that owns a SQLAlchemy engine must explicitly dispose it in teardown.

### Guardrail
- Fetcher cleanup behavior validated in:
  `scripts/verify_test_isolation.py:1`

### Migration policy
- When adding new owned resources to `CachedDataFetcher`, update `close()` in
  the same change and extend verifier coverage.

---

## 3) Real-DB Coupling in Default Tests (2026-02-18)

### Symptom
- Default test suite behavior depended on local `data/cache.db`, causing
  environment-coupled flakiness.

### Data flow trace
- Integration-style shadow coverage tests read shared DB paths by default:
  `tests/test_shadow_coverage.py:108`, `tests/test_shadow_enricher_utils.py:666`

### Generator
- Hidden external dependency in default test lane.

### Invariant
- Default local/CI suite must be deterministic and fixture-first.

### Guardrail
- Explicit opt-in gate:
  `TPOT_RUN_REAL_DB_TESTS`
- Skip markers enforce default deterministic behavior:
  `tests/test_shadow_coverage.py:13`,
  `tests/test_shadow_enricher_utils.py:26`

### Migration policy
- Keep real-DB checks in a dedicated opt-in lane; replace broad production-data
  tests with deterministic fixtures over time.

---

## 4) Optional Dependency Drift in Expansion Strategy (2026-02-18)

### Symptom
- Full suite fails with:
  `ModuleNotFoundError: No module named 'community'`
  during expansion strategy tests.

### Data flow trace
- Strategy evaluation imports Louvain backend dynamically:
  `src/graph/hierarchy/expansion_strategy.py:617`
- Test coverage reaches this code path:
  `tests/test_expansion_strategy.py`

### Generator
- Optional dependency treated as required in tests/runtime without explicit
  environment contract.

### Invariant
- Optional features must either:
  1) have explicit install contract in test/dev env, or
  2) fail fast with actionable skip/error diagnostics.

### Guardrail
- Dependency pin in:
  `requirements.txt` (`python-louvain==0.16`)
- Verification script:
  `scripts/verify_louvain_dependency_contract.py:1`

### Migration policy
- Add one of:
  - pinned dependency in standard env setup, or
  - explicit test skip markers + runtime guard path with install hint.

---

## General Checklist For New Bugs

When a new bug is fixed, add an entry here with:
1. Concrete UX/runtime symptom.
2. Code-path trace with exact file references.
3. Root generator pattern.
4. Invariant to enforce.
5. Guardrail artifact (test/verifier/lint/runtime check).
6. Migration policy (including deprecation windows when needed).
