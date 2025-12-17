# Test Coverage Baseline

**Measured:** 2025-10-05 (updated 2025-10-06)
**Total Coverage:** ~68% (estimated with x_api_client + shadow_store + selenium_worker improvements)
**Test Count:** 191 tests (23 x_api + 27 shadow_store + 50 selenium_worker + 14 shadow enrichment + 77 other)

## Coverage by Module

### Excellent Coverage (>85%) ✅
- `src/config.py`: **92%** (45/49 statements) — Well covered
- `src/data/shadow_store.py`: **88%** (212/240 statements) — **IMPROVED** from 39% (+49pp)
- `src/graph/metrics.py`: **96%** (47/49 statements) — Excellent
- `src/graph/seeds.py`: **100%** (17/17 statements) — Complete
- `src/shadow/x_api_client.py`: **97%** (113/117 statements) — **IMPROVED** from 28% (+69pp)

### Good Coverage (70-85%)
- `src/data/fetcher.py`: **83%** (99/119 statements) — Missing HTTP error handling
- `src/graph/builder.py`: **72%** (65/90 statements) — Missing filter edge cases

### Medium Coverage (50-70%)
- `src/shadow/enricher.py`: **62%** (260/422 statements)
  - Missing: Error handling, X API integration workflows

### Low Coverage (<50%) 🔴
- `src/shadow/selenium_worker.py`: **44%** (235/540 statements) — **IMPROVED** from 42% (+2pp)
  - Missing: Browser lifecycle (init, login), page navigation, scrolling workflows
  - Tested: DOM extraction, JSON-LD parsing, count parsing, URL extraction (50 unit tests)

## High-Priority Gaps (Completed ✅)

### 1. **x_api_client.py (97% coverage, 23 tests)** ✅ COMPLETED (2025-10-06)
**Status:** Comprehensive test suite added
**Coverage Improvement:** 28% → 97% (+69 percentage points)
**Tests Added:**
- RateLimit class: sliding window, wait time calculation, request recording (7 tests)
- State persistence: file loading, corruption handling, directory creation (6 tests)
- HTTP requests: 200 OK, 429 rate limits, error codes, network exceptions (5 tests)
- Public API: user lookups, list members, error handling (5 tests)

### 2. **shadow_store.py (88% coverage, 27 tests)** ✅ COMPLETED (2025-10-06)
**Status:** Direct unit tests added
**Coverage Improvement:** 39% → 88% (+49 percentage points)
**Tests Added:**
- COALESCE upsert behavior: None preservation, value replacement (3 tests)
- Edge summary aggregation: following/followers counting, list_type logic (4 tests)
- Coverage percentage conversion: 0.0, 0.5, 1.0, None handling (4 tests)
- Retry logic: disk I/O errors, database locked, exponential backoff (4 tests)
- Profile completeness: location AND (website OR joined) AND avatar AND counts (7 tests)
- Edge/discovery operations: composite keys, filtering (5 tests)

### 3. **selenium_worker.py (44% coverage, 50 tests)** ✅ PARTIALLY COMPLETED (2025-10-06)
**Status:** DOM extraction and parsing logic tested
**Coverage Improvement:** 42% → 44% (+2 percentage points)
**Tests Added:**
- Compact count parsing: "1.5K", "2M", comma-separated, edge cases (7 tests)
- URL handle extraction: twitter.com, x.com, relative paths, validation (10 tests)
- JSON-LD schema parsing: complete/minimal payloads, username validation, count extraction (15 tests)
- DOM extraction: handle, display name, bio, website, profile image with mocked WebElements (18 tests)

**Remaining Gaps:**
- Browser lifecycle methods (init_driver, login_with_cookies) - require Selenium integration
- Page navigation and scrolling (_collect_user_list) - require browser automation
- Profile overview extraction - requires live DOM interaction

**Note:** Uncovered methods require actual Selenium WebDriver (integration tests). Current unit tests cover all pure parsing logic and protect against Twitter HTML changes for static extraction methods.

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

- **Short-term:** ✅ 65%+ achieved (x_api_client + shadow_store)
- **Medium-term:** Reach 75% (selenium workflow tests)
- **Long-term:** Maintain 80%+ with regression tests

## Notes

- Coverage measured with `pytest -m unit` (fast tests only)
- Integration tests excluded from baseline (require database/network)
- Selenium tests marked separately (require browser automation)
