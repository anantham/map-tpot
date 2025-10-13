# Archived Scripts

This directory contains deprecated scripts that have been superseded by better implementations.

## test_fixes_DEPRECATED.py

**Status:** Deprecated as of 2025-10-13

**Reason:** All test functionality has been migrated to proper pytest tests in the `tests/` directory.

**Migration:**
- `test_coverage_calculation()` → `tests/test_shadow_coverage.py::test_coverage_percentage_formula`
- `test_multi_run_freshness()` → `tests/test_shadow_enricher_utils.py::TestMultiRunFreshness::test_check_list_freshness_across_multiple_runs`
- `test_account_id_migration_cache_lookup()` → `tests/test_shadow_enricher_utils.py::TestAccountIDMigrationCacheLookup`

**To run the new tests:**
```bash
# Run all the migrated tests
pytest tests/test_shadow_coverage.py::test_coverage_percentage_formula -v
pytest tests/test_shadow_enricher_utils.py::TestMultiRunFreshness -v
pytest tests/test_shadow_enricher_utils.py::TestAccountIDMigrationCacheLookup -v
```

This script is kept for historical reference only and should not be used.
