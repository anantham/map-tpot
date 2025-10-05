# Test Coverage Baseline

**Date:** 2025-10-05  
**Total Coverage:** 53% (804/1516 lines)  
**Test Count:** 77 passing, 4 skipped

## Coverage by Module

### High Coverage (>80%)
- `src/config.py`: **92%** (4 missing lines)
- `src/data/fetcher.py`: **83%** (20 missing lines)
- `src/graph/metrics.py`: **96%** (2 missing lines)
- `src/graph/seeds.py`: **100%** (full coverage)
- `src/graph/__init__.py`: **100%**
- `src/__init__.py`: **100%**
- `src/data/__init__.py`: **100%**
- `src/shadow/__init__.py`: **100%**

### Medium Coverage (50-80%)
- `src/graph/builder.py`: **72%** (25 missing lines)
- `src/shadow/enricher.py`: **56%** (144 missing lines)
  - **Gap:** Monolithic `enrich()` method (300 lines, not decomposed)
  - **Gap:** Profile-only mode workflow
  - **Gap:** Skip logic embedded in main flow

### Low Coverage (<50%) — Priority Gaps
- `src/shadow/selenium_worker.py`: **42%** (312 missing lines)
  - **Gap:** Collection workflow (`_collect_user_list`, scrolling logic)
  - **Gap:** Browser lifecycle (`_init_driver`, `_login_with_cookies`)
  - **Gap:** Profile extraction (`_extract_profile_overview`, JSON-LD parsing)
  
- `src/data/shadow_store.py`: **39%** (121 missing lines)
  - **Gap:** No direct unit tests (only migration tests exist)
  - **Gap:** COALESCE upsert behavior not tested
  - **Gap:** Edge summary aggregation not tested

- `src/shadow/x_api_client.py`: **28%** (84 missing lines) ⚠️ **HIGHEST PRIORITY**
  - **Gap:** ZERO test coverage for production API client
  - **Gap:** Rate limiting logic untested
  - **Gap:** Persistent state loading/saving untested
  - **Gap:** HTTP error handling untested

## Key Insights

1. **Graph analysis code is well-tested** (72-100% coverage)
2. **Shadow enrichment system is undertested** (28-56% coverage)
3. **X API Client has no tests** despite being used in production
4. **Shadow store lacks direct unit tests** (only migration tests exist)

## Improvement Targets

Based on risk and current gaps:

1. **Week 1:** X API Client tests (~20 tests) → Target 80%+ coverage
2. **Week 2:** Shadow store unit tests (~25 tests) → Target 70%+ coverage
3. **Week 3:** Enricher refactor + workflow tests → Target 70%+ coverage
4. **Week 4:** Selenium worker collection tests → Target 60%+ coverage

**Expected Final Coverage:** ~65-70% (realistic given Selenium/browser complexity)

## Running Coverage Reports

```bash
# Full coverage report
pytest --cov=src --cov-report=term-missing tests/

# Coverage for specific module
pytest --cov=src/shadow/x_api_client --cov-report=term-missing tests/

# HTML report (browse in browser)
pytest --cov=src --cov-report=html tests/
open htmlcov/index.html
```
