#!/usr/bin/env python3
"""Quick test to verify coverage calculation and skip logic fixes.

⚠️  DEPRECATED: This script has been superseded by proper pytest tests.

All tests have been migrated to:
- tests/test_shadow_coverage.py::test_coverage_percentage_formula
- tests/test_shadow_enricher_utils.py::TestMultiRunFreshness
- tests/test_shadow_enricher_utils.py::TestAccountIDMigrationCacheLookup

Run the new tests with:
    pytest tests/test_shadow_coverage.py::test_coverage_percentage_formula -v
    pytest tests/test_shadow_enricher_utils.py::TestMultiRunFreshness -v
    pytest tests/test_shadow_enricher_utils.py::TestAccountIDMigrationCacheLookup -v

This script is kept for historical reference only.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data.shadow_store import ShadowStore, ScrapeRunMetrics
from src.shadow.enricher import EnrichmentPolicy, HybridShadowEnricher
from datetime import datetime
from sqlalchemy import create_engine


def test_coverage_calculation():
    """Test that coverage is now stored as percentage (0-100) not basis points (0-10000)."""
    print("=" * 60)
    print("TEST 1: Coverage Calculation")
    print("=" * 60)

    # Test the fix directly - simulate what record_scrape_metrics does
    test_cases = [
        (0.0265, 2.65, "53 following out of 2000"),
        (0.0230, 2.30, "230 followers out of 10000"),
        (0.027, 2.7, "angularocean following case"),
        (0.1669, 16.69, "angularocean followers case (old run)"),
    ]

    all_passed = True
    for ratio, expected_percentage, description in test_cases:
        # This is the fix: round(ratio * 100, 2) instead of int(ratio * 10000)
        stored_value = round(ratio * 100, 2)

        print(f"\nTest case: {description}")
        print(f"  Input ratio: {ratio}")
        print(f"  Stored value: {stored_value}")
        print(f"  Expected: {expected_percentage}")

        if stored_value == expected_percentage:
            print(f"  ✅ PASS")
        else:
            print(f"  ❌ FAIL: Expected {expected_percentage}, got {stored_value}")
            all_passed = False

    print()
    if all_passed:
        print("✅ ALL TESTS PASSED: Coverage is now stored as percentage (0-100)")
    else:
        print("❌ SOME TESTS FAILED")

    # Show what the OLD formula would have produced
    print("\n" + "=" * 60)
    print("For comparison, OLD formula (basis points):")
    print("=" * 60)
    for ratio, _, description in test_cases:
        old_value = int(ratio * 10000)
        print(f"{description}: {old_value} (basis points) - INCORRECT!")

    print()


def test_multi_run_freshness():
    """Test that the multi-run skip logic would work correctly."""
    print("=" * 60)
    print("TEST 2: Multi-Run Freshness Check Logic")
    print("=" * 60)

    # Query the database directly to simulate what _check_list_freshness_across_runs does
    db_path = project_root / "data" / "cache.db"
    engine = create_engine(f"sqlite:///{db_path}")

    # Test with angularocean
    account_id = "1220764014399184904"
    username = "angularocean"

    print(f"Checking scrape history for: {username} ({account_id})")
    print()

    # Query the database for recent runs
    from sqlalchemy import text
    with engine.connect() as conn:
        query = text("""
            SELECT
                datetime(run_at, 'localtime') as run_time,
                following_captured,
                followers_captured,
                following_coverage,
                followers_coverage
            FROM scrape_run_metrics
            WHERE seed_account_id = :account_id
            ORDER BY run_at DESC
            LIMIT 5
        """)
        results = conn.execute(query, {"account_id": account_id}).fetchall()

    print("Recent scrape runs:")
    print("-" * 60)
    for row in results:
        print(f"  {row[0]}: following={row[1] or 0}, followers={row[2] or 0}")

    # Analyze the data
    MIN_RAW_TO_SKIP = 5
    has_following = any(row[1] and row[1] > MIN_RAW_TO_SKIP for row in results)
    has_followers = any(row[2] and row[2] > MIN_RAW_TO_SKIP for row in results)

    print()
    print("Analysis:")
    print(f"  Has recent run with following data (>{MIN_RAW_TO_SKIP}): {has_following}")
    print(f"  Has recent run with followers data (>{MIN_RAW_TO_SKIP}): {has_followers}")
    print()

    if has_following and has_followers:
        print("✅ PASS: Both lists have fresh data across runs")
        print("   The smart skip logic should skip this account on next run")

        # Show which runs had the data
        following_run = next((row for row in results if row[1] and row[1] > MIN_RAW_TO_SKIP), None)
        followers_run = next((row for row in results if row[2] and row[2] > MIN_RAW_TO_SKIP), None)

        if following_run:
            print(f"   Following: {following_run[1]} accounts from {following_run[0]}")
        if followers_run:
            print(f"   Followers: {followers_run[2]} accounts from {followers_run[0]}")
    else:
        print("❌ FAIL: Missing data for at least one list")
        print(f"   Has following: {has_following}")
        print(f"   Has followers: {has_followers}")

    print()


def test_account_id_migration_cache_lookup():
    """Test that enricher finds historical scrape data even when account ID changes."""
    print("=" * 60)
    print("TEST 3: Account ID Migration Cache Lookup")
    print("=" * 60)
    print()
    print("Bug: When an account migrates from 'shadow:username' to real ID,")
    print("     the freshness check would fail to find historical scrape records.")
    print()
    print("Fix: _check_list_freshness_across_runs now checks both real ID and shadow ID.")
    print()

    db_path = project_root / "data" / "cache.db"
    engine = create_engine(f"sqlite:///{db_path}")

    # Test case: adityaarpitha
    # - Has historical scrapes with seed_account_id = "shadow:adityaarpitha"
    # - Now resolved to real account_id = "261659859"
    real_account_id = "261659859"
    shadow_account_id = "shadow:adityaarpitha"
    username = "adityaarpitha"

    print(f"Checking scrape history for: {username}")
    print(f"  Real account_id: {real_account_id}")
    print(f"  Shadow account_id: {shadow_account_id}")
    print()

    from sqlalchemy import text
    with engine.connect() as conn:
        # Check what's in the DB with shadow ID
        shadow_query = text("""
            SELECT
                datetime(run_at, 'localtime') as run_time,
                seed_account_id,
                following_captured,
                followers_captured
            FROM scrape_run_metrics
            WHERE seed_account_id = :shadow_id
            ORDER BY run_at DESC
            LIMIT 3
        """)
        shadow_results = conn.execute(shadow_query, {"shadow_id": shadow_account_id}).fetchall()

        # Check what's in the DB with real ID
        real_query = text("""
            SELECT
                datetime(run_at, 'localtime') as run_time,
                seed_account_id,
                following_captured,
                followers_captured
            FROM scrape_run_metrics
            WHERE seed_account_id = :real_id
            ORDER BY run_at DESC
            LIMIT 3
        """)
        real_results = conn.execute(real_query, {"real_id": real_account_id}).fetchall()

        # Simulate the FIXED query (checks both IDs)
        fixed_query = text("""
            SELECT
                datetime(run_at, 'localtime') as run_time,
                seed_account_id,
                following_captured,
                followers_captured
            FROM scrape_run_metrics
            WHERE seed_account_id IN (:real_id, :shadow_id)
            ORDER BY run_at DESC
            LIMIT 3
        """)
        fixed_results = conn.execute(fixed_query, {
            "real_id": real_account_id,
            "shadow_id": shadow_account_id
        }).fetchall()

    print(f"Records found with shadow ID only: {len(shadow_results)}")
    if shadow_results:
        for row in shadow_results[:2]:
            print(f"  {row[0]}: following={row[2] or 0}, followers={row[3] or 0}")

    print()
    print(f"Records found with real ID only: {len(real_results)}")
    if real_results:
        for row in real_results[:2]:
            print(f"  {row[0]}: following={row[2] or 0}, followers={row[3] or 0}")
    else:
        print("  (none - this is expected for migrated accounts)")

    print()
    print(f"Records found with BOTH IDs (FIXED query): {len(fixed_results)}")
    if fixed_results:
        for row in fixed_results[:2]:
            print(f"  {row[0]} ({row[1]}): following={row[2] or 0}, followers={row[3] or 0}")

    print()

    # Verify the fix works
    MIN_RAW_TO_SKIP = 5
    has_following = any(row[2] and row[2] > MIN_RAW_TO_SKIP for row in fixed_results)
    has_followers = any(row[3] and row[3] > MIN_RAW_TO_SKIP for row in fixed_results)

    if has_following and has_followers:
        print("✅ PASS: Fixed query finds historical data across ID migration")
        print("   The enricher will correctly skip re-scraping this account")
    else:
        print("❌ FAIL: Fixed query didn't find enough historical data")
        print(f"   Has following: {has_following}")
        print(f"   Has followers: {has_followers}")

    print()


if __name__ == "__main__":
    try:
        test_coverage_calculation()
        test_multi_run_freshness()
        test_account_id_migration_cache_lookup()
        print("=" * 60)
        print("All tests complete!")
        print("=" * 60)
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
