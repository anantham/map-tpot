# Test Suite Audit Report

**Date**: 2024-12-17  
**Auditor**: Claude (with Aditya)  
**Scope**: `tpot-analyzer/tests/` (7,315 lines across 27 files)

---

## Executive Summary

The test suite has **strong algorithmic coverage** but suffers from:
1. **Test theater** — 6 placeholder tests that just `pytest.skip()`
2. **Misleading names** — "integration" tests that mock everything
3. **Weak assertions** — tests that only check `status == 200`
4. **Production data dependencies** — 7 files skip when `cache.db` missing
5. **Missing E2E coverage** — no tests for cluster routes (831 lines) or frontend

**Recommendation**: Delete placeholders, rename misleading files, add contract tests, create E2E fixtures.

---

## Part 1: Tests to DELETE

### `test_list_scraping.py` lines 57-158

Six placeholder tests that provide zero value:

```python
# These are marked @pytest.mark.skip and just call pytest.skip() again
class TestFetchListMembersIntegration:
    def test_fetch_real_list_members(self):
        pytest.skip("Integration test not implemented yet")
    
    def test_fetch_list_with_lazy_loading(self):
        pytest.skip("Integration test not implemented yet")
    
    def test_fetch_private_list_requires_auth(self):
        pytest.skip("Integration test not implemented yet")
    
    def test_list_scraping_end_to_end_workflow(self):
        pytest.skip("Integration test not implemented yet")

class TestListIDDetectionEndToEnd:
    def test_numeric_center_triggers_list_mode(self):
        pytest.skip("Integration test not implemented yet")
    
    def test_alphanumeric_center_triggers_username_mode(self):
        pytest.skip("Integration test not implemented yet")
```

**Why delete**: These are test plans masquerading as tests. They inflate test count, provide false sense of coverage, and the "Test Plan" comments should be in documentation.

**Action**: 
```bash
# Delete lines 57-158 from test_list_scraping.py
# OR move the test plans to docs/test-plans/list-scraping-tests.md
```

---

## Part 2: Tests to RENAME

### `test_shadow_enrichment_integration.py` → `test_enricher_orchestration.py`

**Problem**: File name says "integration" but contains **201 mock references**:

```bash
$ grep -c "mock\|Mock\|patch\|MagicMock" tests/test_shadow_enrichment_integration.py
201
```

**Evidence of mocking everything**:
```python
# From the file - this is not integration testing
@pytest.fixture
def enricher(mock_shadow_store, mock_enrichment_policy, mock_enrichment_config, mock_selenium_worker):
    """Create enricher with all dependencies mocked."""
    enricher = ShadowEnricher(...)
    enricher._selenium = mock_selenium_worker  # Mock
    enricher._store = mock_shadow_store  # Mock
    return enricher
```

**What it actually tests**: Orchestration logic - that the enricher calls the right methods in the right order with the right arguments. This is valuable but calling it "integration" is misleading.

**Action**:
```bash
git mv tests/test_shadow_enrichment_integration.py tests/test_enricher_orchestration.py
# Update any imports
```

---

## Part 3: Tests to STRENGTHEN

### `test_api.py` - Weak Assertions

**Current state** (problematic patterns found on these lines):
```python
# Line 41, 57, 80, 118, 194 - Only checks status code
assert response.status_code == 200

# Line 66-67, 136-137, 140, 199 - Only checks non-empty
assert len(data["nodes"]) > 0
assert len(data["edges"]) > 0
```

**Problem**: These tests pass if the API returns `{"nodes": ["garbage"], "edges": [1]}`. They don't validate:
- Schema correctness
- Required fields
- Data types
- Value ranges

**Recommended fix** - Add JSON schema validation:

```python
# tests/schemas/api_schemas.py (new file)
CLUSTERS_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["clusters", "edges", "positions", "meta"],
    "properties": {
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "size", "label"],
                "properties": {
                    "id": {"type": "string", "pattern": "^d_\\d+$"},
                    "size": {"type": "integer", "minimum": 1},
                    "label": {"type": "string"},
                    "parentId": {"type": ["string", "null"]},
                    "childrenIds": {"type": ["array", "null"]},
                }
            }
        },
        "positions": {
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2
            }
        },
        "meta": {
            "type": "object",
            "required": ["budget", "budget_remaining"],
            "properties": {
                "budget": {"type": "integer", "minimum": 1},
                "budget_remaining": {"type": "integer", "minimum": 0}
            }
        }
    }
}

# In test_api.py
from jsonschema import validate
from tests.schemas.api_schemas import CLUSTERS_RESPONSE_SCHEMA

def test_clusters_response_shape(test_client):
    response = test_client.get('/api/clusters?n=10')
    assert response.status_code == 200
    data = json.loads(response.data)
    validate(data, CLUSTERS_RESPONSE_SCHEMA)  # Fails on schema violations
```

---

## Part 4: Tests to ISOLATE (Production Data Dependencies)

These 7 files skip tests when production `data/cache.db` is missing:

| File | Lines | Skips When |
|------|-------|------------|
| `test_api.py` | 316 | `cache.db` missing |
| `test_connection.py` | 67 | Supabase credentials missing |
| `test_shadow_archive_consistency.py` | 165 | `cache.db` or Supabase missing |
| `test_shadow_coverage.py` | 127 | `cache.db` missing |
| `test_shadow_enricher_utils.py` | 234 | `cache.db` missing |
| `test_shadow_enrichment_integration.py` | 486 | Production fixtures missing |
| `conftest.py` | 213 | Defines skip markers |

**Problem**: Tests should use fixtures, not production data. This creates:
- Non-deterministic test results across machines
- CI failures when secrets aren't configured
- False confidence from green tests on dev machines

**Recommended fix**: Create deterministic test fixtures:

```python
# tests/fixtures/create_test_db.py
import sqlite3
from pathlib import Path

def create_test_cache_db(path: Path) -> None:
    """Create a minimal but realistic test database."""
    conn = sqlite3.connect(path)
    
    # Create tables matching production schema
    conn.executescript("""
        CREATE TABLE shadow_account (
            account_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            display_name TEXT,
            bio TEXT,
            followers_total INTEGER DEFAULT 0,
            following_total INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE shadow_edge (
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            edge_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (source_id, target_id, edge_type)
        );
        
        CREATE INDEX idx_edge_source ON shadow_edge(source_id);
        CREATE INDEX idx_edge_target ON shadow_edge(target_id);
    """)
    
    # Insert deterministic test data (50 accounts, predictable relationships)
    accounts = [(f"id_{i}", f"user_{i}", f"User {i}", f"Bio {i}", i * 100, i * 50) 
                for i in range(50)]
    conn.executemany(
        "INSERT INTO shadow_account VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
        accounts
    )
    
    # Create a small-world network
    edges = []
    for i in range(50):
        # Each account follows next 3 accounts (wrapping)
        for j in range(1, 4):
            target = (i + j) % 50
            edges.append((f"id_{i}", f"id_{target}", "following"))
    
    conn.executemany(
        "INSERT INTO shadow_edge VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
        edges
    )
    
    conn.commit()
    conn.close()
```

---

## Part 5: Tests That Are Actually Good ✓

These test files demonstrate proper testing practices:

### `test_selenium_worker_unit.py` (566 lines) ✓
- Tests HTML parsing with real HTML fixtures
- No mocks on the code under test
- Edge cases covered (malformed HTML, missing fields)

### `test_selenium_extraction.py` (554 lines) ✓
- Tests DOM extraction with realistic payloads
- Covers UserCell, ProfileOverview, pagination
- Uses fixture files, not production data

### `test_scoring.py` (528 lines) ✓
- Tests PageRank, composite scoring, HITS
- Uses fixture NetworkX graphs
- Validates mathematical properties

### `test_x_api_client.py` (458 lines) ✓
- Tests rate limiting with time mocking
- Tests retry logic with mock responses
- Good isolation of API client behavior

### `test_graph_metrics.py` (187 lines) ✓
- Tests centrality algorithms on small graphs
- Mathematical assertions (betweenness sums to N-1 choose 2)

### `test_clusters.py` (145 lines) ✓
- Tests cluster assignment, soft membership
- Uses fixture linkage matrices
- Validates properties (rows sum to 1)

### `test_spectral.py` (72 lines) ✓
- Tests Laplacian construction
- Tests eigenvalue properties
- Save/load round-trip

---

## Part 6: Missing Test Coverage

### Critical Gaps

| Component | Lines | Tests | Priority |
|-----------|-------|-------|----------|
| `src/api/cluster_routes.py` | 831 | 0 | 🔴 HIGH |
| `src/api/discovery.py` | 553 | 0 | 🔴 HIGH |
| `src/graph/hierarchy/builder.py` | 500+ | 4 | 🟡 MEDIUM |
| `graph-explorer/src/ClusterView.jsx` | 800+ | 0 E2E | 🔴 HIGH |
| `graph-explorer/src/Discovery.jsx` | 400+ | 0 E2E | 🟡 MEDIUM |

### Existing E2E Tests

| File | Status | Notes |
|------|--------|-------|
| `e2e/cluster_mock.spec.ts` | ✅ 8/8 passing | Uses mocked API |
| `e2e/cluster_real.spec.ts` | ⚠️ Requires real backend | Runs against `scripts.start_api_server` |
| `e2e/teleport_tagging_mock.spec.ts` | ✅ Works | Mocked API |

---

## Part 7: Circular Mock Assertions (Anti-Pattern)

Found in `test_shadow_enricher_utils.py` and `test_shadow_enrichment_integration.py`:

```python
# This pattern tests that code calls a mock, not that it works correctly
mock_store.get_shadow_list.return_value = fresh_list
# ... code runs ...
mock_store.get_shadow_list.assert_called_once_with("list123")
```

**Why this is weak**: If the implementation changes to use a different method that achieves the same result, the test fails even though behavior is correct.

**Better approach**: Test outcomes, not implementation:

```python
# Instead of asserting mock calls, assert the result
result = enricher.process_list("list123")
assert result.members == expected_members
assert result.processed_at is not None
```

---

## Part 8: Recommended Test Metrics

### Current State

| Metric | Value |
|--------|-------|
| Total test files | 27 |
| Total lines | 7,315 |
| Placeholder tests | 6 |
| Files requiring prod data | 7 |
| Mock references in "integration" test | 201 |
| API routes with 0 tests | 2 (1,384 lines) |

### Target State

| Metric | Target |
|--------|--------|
| Placeholder tests | 0 |
| Files requiring prod data | 0 |
| "Integration" tests that mock everything | 0 (renamed) |
| Contract tests for API routes | 1 per route |
| E2E coverage | All major views |

---

## Appendix A: File-by-File Summary

| File | Lines | Verdict |
|------|-------|---------|
| `test_account_status_tracking.py` | 89 | ✓ Good |
| `test_account_tags_store.py` | 156 | ✓ Good |
| `test_accounts_search_teleport_tags.py` | 234 | ⚠️ Some prod deps |
| `test_api.py` | 316 | ⚠️ Weak assertions |
| `test_api_autocomplete.py` | 98 | ✓ Good |
| `test_api_json_serialization.py` | 67 | ✓ Good |
| `test_cluster_tag_summary.py` | 145 | ✓ Good |
| `test_clusters.py` | 145 | ✓ Good |
| `test_connection.py` | 67 | ⚠️ Requires Supabase |
| `test_graph_builder.py` | 234 | ✓ Good |
| `test_graph_metrics.py` | 187 | ✓ Good |
| `test_hierarchy_focus_leaf.py` | 89 | ✓ Good |
| `test_hierarchy_math.py` | 180 | ✓ Good (new) |
| `test_hierarchy_members.py` | 45 | ✓ Good |
| `test_list_scraping.py` | 158 | ❌ 6 placeholders |
| `test_parse_compact_count.py` | 56 | ✓ Good |
| `test_scoring.py` | 528 | ✓ Good |
| `test_seeds.py` | 123 | ✓ Good |
| `test_selenium_extraction.py` | 554 | ✓ Good |
| `test_selenium_worker_unit.py` | 566 | ✓ Good |
| `test_shadow_archive_consistency.py` | 165 | ⚠️ Requires prod |
| `test_shadow_coverage.py` | 127 | ⚠️ Requires prod |
| `test_shadow_enricher_utils.py` | 234 | ⚠️ Mock overuse |
| `test_shadow_enrichment_integration.py` | 486 | ❌ Rename needed |
| `test_shadow_store_retry.py` | 58 | ✓ Good |
| `test_shadow_store_unit.py` | 884 | ✓ Good |
| `test_spectral.py` | 72 | ✓ Good |
| `test_x_api_client.py` | 458 | ✓ Good |

---

## Appendix B: Commands to Run Audit

```bash
# Count lines per file
wc -l tests/*.py | sort -n

# Find mock usage
grep -c "mock\|Mock\|patch" tests/*.py | sort -t: -k2 -n

# Find skip markers
grep -r "pytest.skip\|@pytest.mark.skip" tests/

# Find prod data dependencies
grep -l "cache.db\|SUPABASE" tests/*.py

# Find weak assertions
grep -n "assert.*status_code.*200" tests/test_api.py
grep -n "assert.*len.*>" tests/test_api.py
```
