"""Unit tests for shadow enrichment utility methods.

These tests cover utility methods that can be tested in isolation:
- _compute_coverage (Bug: d284ebb)
- _combine_captures
- _truncate_text
- _make_discovery_records

More complex integration tests would require extensive mocking and
are better covered by end-to-end tests.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

import pytest

from src.shadow.enricher import HybridShadowEnricher
from src.shadow.selenium_worker import CapturedUser, UserListCapture, ProfileOverview


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def mock_store():
    """Create a minimal mock ShadowStore."""
    store = Mock()
    return store


@pytest.fixture
def mock_config():
    """Create a minimal mock enrichment config."""
    config = Mock()
    config.bearer_token = None
    config.profile_only = False
    return config


# ==============================================================================
# _compute_coverage Tests (Bug: d284ebb)
# ==============================================================================

@pytest.mark.unit
class TestComputeCoverage:
    """Test coverage calculation logic.

    Bug fix: d284ebb - Followers you follow assumes captured=total when None.
    """

    def test_compute_coverage_normal(self):
        """Test normal coverage calculation."""
        # 50 captured out of 100 total = 50% coverage
        coverage = HybridShadowEnricher._compute_coverage(50, 100)
        assert coverage == 0.5

    def test_compute_coverage_full(self):
        """Test full coverage (100%)."""
        coverage = HybridShadowEnricher._compute_coverage(100, 100)
        assert coverage == 1.0

    def test_compute_coverage_over_100(self):
        """Test coverage can exceed 100% (captured > claimed)."""
        coverage = HybridShadowEnricher._compute_coverage(150, 100)
        assert coverage == 1.5

    def test_compute_coverage_none_claimed_total(self):
        """Test coverage returns None when claimed_total is None."""
        coverage = HybridShadowEnricher._compute_coverage(50, None)
        assert coverage is None

    def test_compute_coverage_zero_total(self):
        """Test coverage returns None when total is zero."""
        coverage = HybridShadowEnricher._compute_coverage(0, 0)
        assert coverage is None

    def test_compute_coverage_zero_captured(self):
        """Test coverage is 0.0 when nothing captured but total exists."""
        coverage = HybridShadowEnricher._compute_coverage(0, 100)
        assert coverage == 0.0


# ==============================================================================
# _combine_captures Tests
# ==============================================================================

@pytest.mark.unit
class TestCombineCaptures:
    """Test combining multiple UserListCapture results."""

    def test_combine_single_capture(self):
        """Test combining a single capture."""
        captures = [
            UserListCapture(
                list_type="following",
                entries=[
                    CapturedUser(username="user1", display_name="User 1"),
                    CapturedUser(username="user2", display_name="User 2"),
                ],
                claimed_total=2,
                page_url="https://x.com/test/following",
            )
        ]

        combined = HybridShadowEnricher._combine_captures(captures)
        assert len(combined) == 2
        assert {u.username for u in combined} == {"user1", "user2"}

    def test_combine_multiple_captures(self):
        """Test combining multiple captures."""
        captures = [
            UserListCapture(
                list_type="following",
                entries=[
                    CapturedUser(username="user1", display_name="User 1", list_types={"following"}),
                ],
                claimed_total=1,
                page_url="https://x.com/test/following",
            ),
            UserListCapture(
                list_type="followers",
                entries=[
                    CapturedUser(username="user2", display_name="User 2", list_types={"followers"}),
                ],
                claimed_total=1,
                page_url="https://x.com/test/followers",
            ),
        ]

        combined = HybridShadowEnricher._combine_captures(captures)
        assert len(combined) == 2
        assert {u.username for u in combined} == {"user1", "user2"}

    def test_combine_deduplicates_across_lists(self):
        """Test that same user in multiple lists is deduplicated."""
        captures = [
            UserListCapture(
                list_type="following",
                entries=[
                    CapturedUser(username="user1", display_name="User 1", list_types={"following"}),
                ],
                claimed_total=1,
                page_url="https://x.com/test/following",
            ),
            UserListCapture(
                list_type="followers",
                entries=[
                    CapturedUser(username="user1", display_name="User 1 Updated", bio="New bio", list_types={"followers"}),
                ],
                claimed_total=1,
                page_url="https://x.com/test/followers",
            ),
        ]

        combined = HybridShadowEnricher._combine_captures(captures)
        assert len(combined) == 1
        user = combined[0]
        assert user.username == "user1"
        # Should merge list_types
        assert user.list_types == {"following", "followers"}
        # Should preserve non-null bio from second capture
        assert user.bio == "New bio"

    def test_combine_empty_captures(self):
        """Test combining empty captures."""
        captures = [
            UserListCapture(
                list_type="following",
                entries=[],
                claimed_total=0,
                page_url="https://x.com/test/following",
            )
        ]

        combined = HybridShadowEnricher._combine_captures(captures)
        assert len(combined) == 0


# ==============================================================================
# _truncate_text Tests
# ==============================================================================

@pytest.mark.unit
class TestTruncateText:
    """Test text truncation utility."""

    def test_truncate_short_text(self):
        """Test text shorter than limit is not truncated."""
        text = "Short text"
        truncated = HybridShadowEnricher._truncate_text(text, limit=100)
        assert truncated == "Short text"

    def test_truncate_long_text(self):
        """Test text longer than limit is truncated."""
        text = "a" * 200
        truncated = HybridShadowEnricher._truncate_text(text, limit=100)
        assert len(truncated) == 100  # Truncates to limit with ellipsis character
        assert truncated.endswith("…")  # Single character ellipsis

    def test_truncate_exact_limit(self):
        """Test text exactly at limit is not truncated."""
        text = "a" * 100
        truncated = HybridShadowEnricher._truncate_text(text, limit=100)
        assert truncated == text

    def test_truncate_none(self):
        """Test truncating None returns empty string."""
        truncated = HybridShadowEnricher._truncate_text(None)
        assert truncated == ""

    def test_truncate_default_limit(self):
        """Test default limit is 160."""
        text = "a" * 200
        truncated = HybridShadowEnricher._truncate_text(text)
        assert len(truncated) == 160  # Truncates to limit with ellipsis character
        assert truncated.endswith("…")


# ==============================================================================
# _make_discovery_records Tests
# ==============================================================================

@pytest.mark.unit
class TestMakeDiscoveryRecords:
    """Test discovery record creation.

    Note: _resolve_username always returns a dict with account_id,
    using fallback 'shadow:username' if API unavailable.
    """

    def test_make_discovery_records_following(self, mock_store, mock_config):
        """Test discovery records created for following list."""
        enricher = HybridShadowEnricher(mock_store, mock_config)

        # Mock username resolution (default behavior: shadow:username)
        from src.shadow import SeedAccount
        seed = SeedAccount(account_id="seed123", username="seeduser")

        following = [
            CapturedUser(username="user1", list_types={"following"}),
            CapturedUser(username="user2", list_types={"following"}),
        ]

        discoveries = enricher._make_discovery_records(
            seed=seed,
            following=following,
            followers=[],
            followers_you_follow=[]
        )

        assert len(discoveries) == 2
        assert all(d.seed_account_id == "seed123" for d in discoveries)
        assert all(d.discovery_method == "following" for d in discoveries)
        # Default resolution creates shadow:username IDs
        assert {d.shadow_account_id for d in discoveries} == {"shadow:user1", "shadow:user2"}

    def test_make_discovery_records_all_lists(self, mock_store, mock_config):
        """Test discovery records created for all three lists."""
        enricher = HybridShadowEnricher(mock_store, mock_config)
        from src.shadow import SeedAccount
        seed = SeedAccount(account_id="seed123", username="seeduser")

        following = [CapturedUser(username="user1", list_types={"following"})]
        followers = [CapturedUser(username="user2", list_types={"followers"})]
        followers_you_follow = [CapturedUser(username="user3", list_types={"followers_you_follow"})]

        discoveries = enricher._make_discovery_records(
            seed=seed,
            following=following,
            followers=followers,
            followers_you_follow=followers_you_follow
        )

        assert len(discoveries) == 3
        methods = {d.discovery_method for d in discoveries}
        assert methods == {"following", "followers", "followers_you_follow"}

    def test_make_discovery_records_empty_lists(self, mock_store, mock_config):
        """Test no discoveries when all lists empty."""
        enricher = HybridShadowEnricher(mock_store, mock_config)
        from src.shadow import SeedAccount
        seed = SeedAccount(account_id="seed123", username="seeduser")

        discoveries = enricher._make_discovery_records(
            seed=seed,
            following=[],
            followers=[],
            followers_you_follow=[]
        )

        assert len(discoveries) == 0


# ==============================================================================
# _profile_overview_from_captures Tests
# ==============================================================================

@pytest.mark.unit
class TestProfileOverviewFromCaptures:
    """Test extracting profile overview from captures."""

    def test_profile_overview_from_following_capture(self, mock_store, mock_config):
        """Test extracting overview from following capture."""
        enricher = HybridShadowEnricher(mock_store, mock_config)

        overview = ProfileOverview(
            username="testuser",
            display_name="Test User",
            bio="Test bio",
            location="Test Location",
            website="https://example.com",
            followers_total=100,
            following_total=50,
        )

        following_capture = UserListCapture(
            list_type="following",
            entries=[],
            claimed_total=50,
            page_url="https://x.com/testuser/following",
            profile_overview=overview
        )

        result = enricher._profile_overview_from_captures(following_capture, None, None)
        assert result == overview

    def test_profile_overview_returns_none_when_no_overview(self, mock_store, mock_config):
        """Test returns None when no overview in any capture."""
        enricher = HybridShadowEnricher(mock_store, mock_config)

        capture = UserListCapture(
            list_type="following",
            entries=[],
            claimed_total=50,
            page_url="https://x.com/testuser/following",
            profile_overview=None
        )

        result = enricher._profile_overview_from_captures(capture, None, None)
        assert result is None

    def test_profile_overview_uses_first_non_none(self, mock_store, mock_config):
        """Test uses first non-None overview when multiple captures."""
        enricher = HybridShadowEnricher(mock_store, mock_config)

        overview1 = ProfileOverview(
            username="testuser",
            display_name="First",
            bio=None,
            location=None,
            website=None,
            followers_total=100,
            following_total=50,
        )

        overview2 = ProfileOverview(
            username="testuser",
            display_name="Second",
            bio="Bio",
            location="Location",
            website="https://example.com",
            followers_total=100,
            following_total=50,
        )

        following_capture = UserListCapture("following", [], 50, "url1", overview1)
        followers_capture = UserListCapture("followers", [], 100, "url2", overview2)

        # Should return first non-None overview (following_capture's)
        result = enricher._profile_overview_from_captures(following_capture, followers_capture, None)
        assert result == overview1

    def test_profile_overview_skips_none_captures(self, mock_store, mock_config):
        """Test that None overview in first capture is skipped."""
        enricher = HybridShadowEnricher(mock_store, mock_config)

        overview = ProfileOverview(
            username="testuser",
            display_name="From Followers",
            bio=None,
            location=None,
            website=None,
            followers_total=100,
            following_total=50,
        )

        following_capture = UserListCapture("following", [], 50, "url1", None)
        followers_capture = UserListCapture("followers", [], 100, "url2", overview)

        # Should skip following_capture (no overview) and return followers_capture's overview
        result = enricher._profile_overview_from_captures(following_capture, followers_capture, None)
        assert result == overview


# ==============================================================================
# _check_list_freshness_across_runs Tests (Account ID Migration)
# ==============================================================================

@pytest.mark.integration
class TestAccountIDMigrationCacheLookup:
    """Test that enricher finds historical scrape data when account ID changes.

    Bug: When an account migrates from "shadow:username" to real ID "12345",
    the freshness check would fail to find historical scrape records.

    Fix: _check_list_freshness_across_runs now checks both real ID and shadow ID.
    """

    def test_check_list_freshness_finds_shadow_id_records(self):
        """Test that freshness check finds records using shadow ID when seed has real ID."""
        from src.data.fetcher import CachedDataFetcher
        from src.config import get_cache_settings
        from src.data.shadow_store import get_shadow_store
        from src.shadow import SeedAccount, EnrichmentPolicy, ShadowEnrichmentConfig
        from pathlib import Path

        # Use real database to verify integration
        with CachedDataFetcher(get_cache_settings().path) as fetcher:
            store = get_shadow_store(fetcher.engine)

            # Create enricher with minimal config
            config = ShadowEnrichmentConfig(
                selenium_cookies_path=Path("secrets/twitter_cookies.pkl"),
                selenium_headless=True,
            )
            policy = EnrichmentPolicy.default()
            policy.skip_if_ever_scraped = True

            enricher = HybridShadowEnricher(store, config, policy)

            # Test case: adityaarpitha
            # - Has historical scrapes with seed_account_id = "shadow:adityaarpitha"
            # - Now resolved to real account_id = "261659859"
            seed = SeedAccount(
                account_id="261659859",  # Real ID
                username="adityaarpitha"
            )

            # Check freshness - should find shadow ID records
            following_skip, following_days, following_count = enricher._check_list_freshness_across_runs(
                seed.account_id, "following", seed.username
            )

            # Verify it found the historical data from shadow ID scrapes
            # (We know from manual testing there are 853 following captured on Oct 8)
            assert following_skip is True, (
                f"Should find following data from shadow ID scrape, got skip={following_skip}"
            )
            assert following_count > 5, (
                f"Should find >5 following accounts, found {following_count}"
            )
            assert following_days >= 0, (
                f"Days ago should be non-negative, got {following_days}"
            )

    def test_check_list_freshness_without_username_still_checks_real_id(self):
        """Test that when username is None, still checks the provided account_id."""
        from src.data.fetcher import CachedDataFetcher
        from src.config import get_cache_settings
        from src.data.shadow_store import get_shadow_store
        from src.shadow import EnrichmentPolicy, ShadowEnrichmentConfig
        from pathlib import Path

        with CachedDataFetcher(get_cache_settings().path) as fetcher:
            store = get_shadow_store(fetcher.engine)
            config = ShadowEnrichmentConfig(
                selenium_cookies_path=Path("secrets/twitter_cookies.pkl"),
                selenium_headless=True,
            )
            policy = EnrichmentPolicy.default()
            enricher = HybridShadowEnricher(store, config, policy)

            # Check with just account_id, no username
            # Should still work, just won't check shadow ID variant
            following_skip, following_days, following_count = enricher._check_list_freshness_across_runs(
                "shadow:adityaarpitha", "following", username=None
            )

            # Should find data (or not) based on the shadow ID alone
            assert isinstance(following_skip, bool)
            assert isinstance(following_days, int)
            assert isinstance(following_count, int)


@pytest.mark.integration
class TestMultiRunFreshness:
    """Test that enricher finds fresh data across multiple scrape runs.

    Context: The smart skip logic should check multiple recent runs, not just the last one.
    For example, if following was scraped in run #1 and followers in run #2, both should
    be considered fresh even though no single run has both.
    """

    def test_check_list_freshness_across_multiple_runs(self):
        """Test that freshness check finds data across different runs.

        This verifies the "smart skip" logic where different lists might have been
        scraped in different runs within the 180-day threshold.
        """
        from src.data.fetcher import CachedDataFetcher
        from src.config import get_cache_settings
        from src.data.shadow_store import get_shadow_store
        from src.shadow import EnrichmentPolicy, ShadowEnrichmentConfig
        from pathlib import Path
        from sqlalchemy import text

        with CachedDataFetcher(get_cache_settings().path) as fetcher:
            store = get_shadow_store(fetcher.engine)
            config = ShadowEnrichmentConfig(
                selenium_cookies_path=Path("secrets/twitter_cookies.pkl"),
                selenium_headless=True,
            )
            policy = EnrichmentPolicy.default()
            policy.skip_if_ever_scraped = True

            enricher = HybridShadowEnricher(store, config, policy)

            # Find an account with split scrape runs (following in one run, followers in another)
            # Query for such an account
            with fetcher.engine.begin() as conn:
                result = conn.execute(text("""
                    WITH run_data AS (
                        SELECT
                            seed_account_id,
                            seed_username,
                            MAX(CASE WHEN following_captured > 5 THEN 1 ELSE 0 END) as has_following,
                            MAX(CASE WHEN followers_captured > 5 THEN 1 ELSE 0 END) as has_followers,
                            COUNT(DISTINCT CASE WHEN following_captured > 5 THEN run_at END) as following_runs,
                            COUNT(DISTINCT CASE WHEN followers_captured > 5 THEN run_at END) as followers_runs
                        FROM scrape_run_metrics
                        WHERE seed_username IS NOT NULL
                          AND datetime(run_at) > datetime('now', '-180 days')
                        GROUP BY seed_account_id, seed_username
                        HAVING has_following = 1 AND has_followers = 1
                    )
                    SELECT seed_account_id, seed_username
                    FROM run_data
                    WHERE following_runs >= 1 AND followers_runs >= 1
                    LIMIT 1
                """)).fetchone()

            if not result:
                pytest.skip("No accounts found with split scrape runs (need real scrape data)")

            account_id, username = result

            # Check freshness for both lists - should find data across runs
            following_skip, following_days, following_count = enricher._check_list_freshness_across_runs(
                account_id, "following", username
            )
            followers_skip, followers_days, followers_count = enricher._check_list_freshness_across_runs(
                account_id, "followers", username
            )

            # Verify both lists found fresh data (even if from different runs)
            assert following_skip is True, (
                f"Should find following data for {username}, got skip={following_skip}"
            )
            assert following_count > 5, (
                f"Should find >5 following accounts for {username}, found {following_count}"
            )

            assert followers_skip is True, (
                f"Should find followers data for {username}, got skip={followers_skip}"
            )
            assert followers_count > 5, (
                f"Should find >5 followers accounts for {username}, found {followers_count}"
            )

            # Both should have reasonable age
            assert 0 <= following_days <= 180, (
                f"Following data age should be within 180 days, got {following_days}"
            )
            assert 0 <= followers_days <= 180, (
                f"Followers data age should be within 180 days, got {followers_days}"
            )
