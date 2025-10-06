# Test Coverage Baseline

**Measured:** 2025-10-05 (updated 2025-10-06)
**Total Coverage:** ~60% (estimated with x_api_client improvements)
**Test Count:** 114 tests (23 x_api_client + 14 shadow enrichment + 77 other)

## Coverage by Module

| Module | Statements | Covered | Coverage | Priority Gaps |
|--------|-----------|---------|----------|---------------|
| `src/config.py` | 49 | 45 | **92%** | ✅ Well covered |
| `src/data/fetcher.py` | 119 | 99 | **83%** | Missing: HTTP error handling (lines 215-244) |
| `src/data/shadow_store.py` | 204 | 77 | **38%** 🔴 | **HIGH**: No direct unit tests, only integration coverage |
| `src/graph/builder.py` | 90 | 65 | **72%** | Missing: Filter edge cases (lines 132-168) |
| `src/graph/metrics.py` | 49 | 47 | **96%** | ✅ Excellent coverage |
| `src/graph/seeds.py` | 17 | 17 | **100%** | ✅ Complete |
| `src/shadow/enricher.py` | 422 | 260 | **62%** | Missing: Error handling, X API integration (lines 678-1043) |
| `src/shadow/selenium_worker.py` | 540 | 228 | **42%** 🔴 | **HIGH**: DOM extraction workflows untested (lines 409-745) |
| `src/shadow/x_api_client.py` | 117 | 113 | **97%** ✅ | **IMPROVED**: 23 tests added (rate limiting, HTTP errors, state persistence) |

## High-Priority Gaps

### 1. **x_api_client.py (97% coverage, 23 tests)** ✅ COMPLETED (2025-10-06)
**Status:** Comprehensive test suite added
**Coverage Improvement:** 28% → 97% (+69 percentage points)
**Tests Added:**
- RateLimit class: sliding window, wait time calculation, request recording (7 tests)
- State persistence: file loading, corruption handling, directory creation (6 tests)
- HTTP requests: 200 OK, 429 rate limits, error codes, network exceptions (5 tests)
- Public API: user lookups, list members, error handling (5 tests)

### 2. **shadow_store.py (38% coverage, 0 direct tests)** 🔴
**Impact:** Core data layer has no unit tests
**Risk:** COALESCE upsert bugs, edge summary aggregation errors
**Next Steps:**
- Add direct unit tests with temp SQLite fixture
- Test edge summary aggregation (following/followers counts)
- Test COALESCE upsert behavior (update vs insert)

### 3. **selenium_worker.py (42% coverage)** 🔴
**Impact:** DOM extraction workflows untested
**Risk:** Breaks silently when Twitter changes HTML
**Next Steps:**
- Add JSON-LD fallback tests with saved fixtures
- Test DOM extraction with realistic HTML samples
- Test scroll/pagination logic with mocked driver

## Test Infrastructure (Completed ✅)

- [x] `tests/conftest.py` with shared fixtures
- [x] Pytest markers (`unit`, `integration`, `selenium`)
- [x] pytest-cov integration
- [x] Coverage baseline documented

## Running Coverage

```bash
# Full coverage report
pytest --cov=src --cov-report=term-missing

# HTML report
pytest --cov=src --cov-report=html
open htmlcov/index.html

# Focus on uncovered lines
pytest --cov=src --cov-report=term-missing | grep -A 10 "TOTAL"
```

## Coverage Goals

- **Short-term:** Increase to 65% (add x_api_client, shadow_store tests)
- **Medium-term:** Reach 75% (selenium workflow tests)
- **Long-term:** Maintain 80%+ with regression tests

## Notes

- Coverage measured with `pytest -m unit` (fast tests only)
- Integration tests excluded from baseline (require database/network)
- Selenium tests marked separately (require browser automation)
