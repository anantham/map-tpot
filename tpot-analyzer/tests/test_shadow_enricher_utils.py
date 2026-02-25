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

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from src.data.shadow_store import ScrapeRunMetrics, ShadowList, ShadowListMember
from src.shadow import SeedAccount
from src.shadow.enricher import HybridShadowEnricher
from src.shadow.selenium_worker import CapturedUser, UserListCapture, ProfileOverview, ListOverview


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def mock_store():
    """Create a minimal mock ShadowStore."""
    store = Mock()
    store.get_account_id_by_username = Mock(return_value=None)
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
# _should_refresh_list Profile Total Tests
# ==============================================================================

@pytest.mark.unit
class TestShouldRefreshListProfileTotals:
    """Ensure small-account profile totals gate skip decisions."""

    @staticmethod
    def _make_metrics(
        *,
        following_captured: int,
        followers_captured: int,
    ) -> ScrapeRunMetrics:
        return ScrapeRunMetrics(
            seed_account_id="seed123",
            seed_username="seeduser",
            run_at=datetime.utcnow(),
            duration_seconds=1.0,
            following_captured=following_captured,
            followers_captured=followers_captured,
            followers_you_follow_captured=0,
            list_members_captured=0,
            following_claimed_total=None,
            followers_claimed_total=None,
            followers_you_follow_claimed_total=None,
            following_coverage=None,
            followers_coverage=None,
            followers_you_follow_coverage=None,
            accounts_upserted=0,
            edges_upserted=0,
            discoveries_upserted=0,
            skipped=False,
            skip_reason=None,
            error_type=None,
            error_details=None,
        )

    def test_small_account_counts_considered_complete(self, mock_store, mock_config):
        """Should skip when captured edges match the observed small profile total."""
        enricher = HybridShadowEnricher(mock_store, mock_config)
        seed = SeedAccount(account_id="seed123", username="seeduser")
        mock_store.get_last_scrape_metrics.return_value = self._make_metrics(
            following_captured=8,
            followers_captured=0,
        )
        mock_store.edge_summary_for_seed.return_value = {
            "following": 8,
            "followers": 0,
            "followers_you_follow": 0,
        }

        should_refresh, reason = enricher._should_refresh_list(seed, "following", current_total=8)

        assert should_refresh is False
        assert reason == "following_fresh_sufficient_capture"

    def test_small_account_needing_additional_edges(self, mock_store, mock_config):
        """Should refresh when captured edges fall short of the observed profile total."""
        enricher = HybridShadowEnricher(mock_store, mock_config)
        seed = SeedAccount(account_id="seed123", username="seeduser")
        mock_store.get_last_scrape_metrics.return_value = self._make_metrics(
            following_captured=7,
            followers_captured=0,
        )
        mock_store.edge_summary_for_seed.return_value = {
            "following": 7,
            "followers": 0,
            "followers_you_follow": 0,
        }

        should_refresh, reason = enricher._should_refresh_list(seed, "following", current_total=8)

        assert should_refresh is True
        assert reason == "profile_total_not_met"

    def test_small_account_db_mismatch_triggers_rescrape(self, mock_store, mock_config):
        """Should refresh when DB edges drop below the observed total despite metrics."""
        enricher = HybridShadowEnricher(mock_store, mock_config)
        seed = SeedAccount(account_id="seed123", username="seeduser")
        mock_store.get_last_scrape_metrics.return_value = self._make_metrics(
            following_captured=8,
            followers_captured=0,
        )
        mock_store.edge_summary_for_seed.return_value = {
            "following": 5,
            "followers": 0,
            "followers_you_follow": 0,
        }

        should_refresh, reason = enricher._should_refresh_list(seed, "following", current_total=8)

        assert should_refresh is True
        assert reason == "metrics_db_mismatch_corruption_detected"

    def test_missing_profile_total_falls_back_to_min_raw_threshold(self, mock_store, mock_config):
        """Fallback to legacy threshold when profile total is unavailable."""
        enricher = HybridShadowEnricher(mock_store, mock_config)
        seed = SeedAccount(account_id="seed123", username="seeduser")
        mock_store.get_last_scrape_metrics.return_value = self._make_metrics(
            following_captured=8,
            followers_captured=0,
        )
        mock_store.edge_summary_for_seed.return_value = {
            "following": 8,
            "followers": 0,
            "followers_you_follow": 0,
        }

        should_refresh, reason = enricher._should_refresh_list(seed, "following", current_total=None)

        assert should_refresh is True
        assert reason == "low_captured_count_in_metrics"


# ==============================================================================
# List caching Tests
# ==============================================================================


@pytest.mark.unit
class TestListCaching:
    def test_fetch_list_members_uses_cache_when_fresh(self, mock_config):
        from tests.helpers.recording_shadow_store import RecordingShadowStore

        store = RecordingShadowStore()
        fetched_at = datetime.utcnow() - timedelta(days=1)
        fresh_list = ShadowList(
            list_id="list123",
            name="Test List",
            description="Curated",
            owner_account_id="shadow:owner",
            owner_username="owner",
            owner_display_name="Owner",
            member_count=2,
            claimed_member_total=2,
            followers_count=5,
            fetched_at=fetched_at,
            source_channel="selenium_list_members",
            metadata={"owner_profile_url": "https://x.com/owner"},
        )
        cached_members = [
            ShadowListMember(
                list_id="list123",
                member_account_id="shadow:user1",
                member_username="user1",
                member_display_name="User 1",
                bio=None,
                website=None,
                profile_image_url=None,
                fetched_at=fetched_at,
                source_channel="hybrid_selenium",
                metadata={"list_types": ["list_members"]},
            ),
            ShadowListMember(
                list_id="list123",
                member_account_id="shadow:user2",
                member_username="user2",
                member_display_name="User 2",
                bio=None,
                website=None,
                profile_image_url=None,
                fetched_at=fetched_at,
                source_channel="hybrid_selenium",
                metadata={"list_types": ["list_members"]},
            ),
        ]

        store.upsert_lists([fresh_list])
        store.replace_list_members("list123", cached_members)

        class _FakeSelenium:
            def set_pause_callback(self, _callback):
                return None

            def set_shutdown_callback(self, _callback):
                return None

            def fetch_list_members(self, list_id):
                raise AssertionError("Selenium should not be used when cache is fresh")

        with patch("src.shadow.enricher.SeleniumWorker", return_value=_FakeSelenium()):
            enricher = HybridShadowEnricher(store, mock_config)
            capture = enricher.fetch_list_members_with_cache("list123")

        assert len(capture.entries) == 2
        assert capture.claimed_total == fresh_list.claimed_member_total
        assert capture.list_overview is not None
        assert capture.list_overview.owner_username == "owner"
        assert store.metrics == []

    def test_fetch_list_members_refreshes_when_stale(self, mock_config):
        from tests.helpers.recording_shadow_store import RecordingShadowStore

        store = RecordingShadowStore()
        stale_list = ShadowList(
            list_id="list123",
            name="Old List",
            description=None,
            owner_account_id=None,
            owner_username=None,
            owner_display_name=None,
            member_count=2,
            claimed_member_total=2,
            followers_count=None,
            fetched_at=datetime.utcnow() - timedelta(days=365),
            source_channel="selenium_list_members",
            metadata=None,
        )
        store.upsert_lists([stale_list])
        store.replace_list_members("list123", [])

        list_overview = ListOverview(
            list_id="list123",
            name="Refreshed",
            description=None,
            owner_username="owner",
            owner_display_name="Owner",
            owner_profile_url="https://x.com/owner",
            members_total=1,
            followers_total=7,
        )
        captured_entries = UserListCapture(
            list_type="list_members",
            entries=[
                CapturedUser(
                    username="user1",
                    display_name="User 1",
                    bio=None,
                    profile_url="https://x.com/user1",
                    website=None,
                    profile_image_url=None,
                    list_types={"list_members"},
                )
            ],
            claimed_total=1,
            page_url="https://twitter.com/i/lists/list123/members",
            profile_overview=None,
            list_overview=list_overview,
        )

        class _FakeSelenium:
            def __init__(self):
                self.fetch_calls = []

            def set_pause_callback(self, _callback):
                return None

            def set_shutdown_callback(self, _callback):
                return None

            def fetch_list_members(self, list_id):
                self.fetch_calls.append(list_id)
                return captured_entries

        fake_selenium = _FakeSelenium()

        with patch("src.shadow.enricher.SeleniumWorker", return_value=fake_selenium):
            enricher = HybridShadowEnricher(store, mock_config)
            enricher._resolve_username = lambda captured: {
                "account_id": f"shadow:{captured.username}",
                "username": captured.username,
                "display_name": captured.display_name,
                "source_channel": "hybrid_selenium",
            }

            capture = enricher.fetch_list_members_with_cache("list123")

        assert fake_selenium.fetch_calls == ["list123"]
        assert len(store.list_members["list123"]) == 1
        assert store.list_members["list123"][0].member_username == "user1"
        assert len(store.metrics) == 1
        assert capture.entries[0].username == "user1"
        assert capture.list_overview == list_overview
# _check_list_freshness_across_runs Tests (Account ID Migration)
# ==============================================================================

@pytest.mark.unit
class TestAccountIDMigrationCacheLookup:
    """Test that enricher finds historical scrape data when account ID changes."""

    def test_check_list_freshness_finds_shadow_id_records(self, mock_config):
        """Freshness check should find records using shadow ID when seed has real ID."""
        from datetime import datetime, timedelta
        from src.shadow import EnrichmentPolicy
        from tests.helpers.recording_shadow_store import RecordingShadowStore

        store = RecordingShadowStore()
        metrics = ScrapeRunMetrics(
            seed_account_id="shadow:adityaarpitha",
            seed_username="adityaarpitha",
            run_at=datetime.utcnow() - timedelta(days=10),
            duration_seconds=10.0,
            following_captured=120,
            followers_captured=0,
            followers_you_follow_captured=0,
            list_members_captured=0,
            following_claimed_total=120,
            followers_claimed_total=0,
            followers_you_follow_claimed_total=0,
            following_coverage=1.0,
            followers_coverage=0.0,
            followers_you_follow_coverage=0.0,
            accounts_upserted=0,
            edges_upserted=0,
            discoveries_upserted=0,
        )
        store.record_scrape_metrics(metrics)

        policy = EnrichmentPolicy.default()

        with patch("src.shadow.enricher.SeleniumWorker"):
            enricher = HybridShadowEnricher(store, mock_config, policy)

        following_skip, following_days, following_count = enricher._check_list_freshness_across_runs(
            "261659859",
            "following",
            "adityaarpitha",
        )

        assert following_skip is True
        assert following_count > 13
        assert following_days >= 0

    def test_check_list_freshness_without_username_still_checks_real_id(self, mock_config):
        """When username is None, still checks the provided account_id."""
        from datetime import datetime, timedelta
        from src.shadow import EnrichmentPolicy
        from tests.helpers.recording_shadow_store import RecordingShadowStore

        store = RecordingShadowStore()
        metrics = ScrapeRunMetrics(
            seed_account_id="shadow:adityaarpitha",
            seed_username="adityaarpitha",
            run_at=datetime.utcnow() - timedelta(days=5),
            duration_seconds=8.0,
            following_captured=50,
            followers_captured=0,
            followers_you_follow_captured=0,
            list_members_captured=0,
            following_claimed_total=50,
            followers_claimed_total=0,
            followers_you_follow_claimed_total=0,
            following_coverage=1.0,
            followers_coverage=0.0,
            followers_you_follow_coverage=0.0,
            accounts_upserted=0,
            edges_upserted=0,
            discoveries_upserted=0,
        )
        store.record_scrape_metrics(metrics)

        policy = EnrichmentPolicy.default()

        with patch("src.shadow.enricher.SeleniumWorker"):
            enricher = HybridShadowEnricher(store, mock_config, policy)

        following_skip, following_days, following_count = enricher._check_list_freshness_across_runs(
            "shadow:adityaarpitha",
            "following",
            username=None,
        )

        assert following_skip is True
        assert following_count > 13
        assert following_days >= 0


@pytest.mark.unit
class TestZeroCoverageEdgeCase:
    """Test that accounts with 0 following/followers are handled correctly.

    Bug: When an account has 0 following and we captured 0, that should be
    treated as 100% coverage (captured all 0 items), not 0% coverage.

    Fix: Coverage calculation now returns 100.0 for 0/0 case.
    """

    def test_zero_following_zero_captured_returns_full_coverage(self):
        """0 following, 0 captured should return 100% coverage."""
        following_coverage = HybridShadowEnricher._compute_skip_coverage_percent(0, 0)
        assert following_coverage == 100.0

    def test_small_count_still_uses_percentage(self):
        """Test that accounts with small non-zero counts use percentage calculation."""
        following_coverage = HybridShadowEnricher._compute_skip_coverage_percent(5, 5)
        assert following_coverage == 100.0

    def test_zero_following_nonzero_captured_is_corruption(self):
        """Test that 0 following but >0 captured is detected as data corruption."""
        following_coverage = HybridShadowEnricher._compute_skip_coverage_percent(0, 5)

        assert following_coverage == 0, (
            "Capturing 5 when profile says 0 should be treated as invalid data"
        )


@pytest.mark.unit
class TestMultiRunFreshness:
    """Test that enricher finds fresh data across multiple scrape runs."""

    def test_check_list_freshness_across_multiple_runs(self, mock_config):
        """Freshness check should combine data across different runs."""
        from datetime import datetime, timedelta
        from src.shadow import EnrichmentPolicy
        from tests.helpers.recording_shadow_store import RecordingShadowStore

        store = RecordingShadowStore()
        store.record_scrape_metrics(ScrapeRunMetrics(
            seed_account_id="seed123",
            seed_username="seeduser",
            run_at=datetime.utcnow() - timedelta(days=12),
            duration_seconds=12.0,
            following_captured=40,
            followers_captured=0,
            followers_you_follow_captured=0,
            list_members_captured=0,
            following_claimed_total=40,
            followers_claimed_total=0,
            followers_you_follow_claimed_total=0,
            following_coverage=1.0,
            followers_coverage=0.0,
            followers_you_follow_coverage=0.0,
            accounts_upserted=0,
            edges_upserted=0,
            discoveries_upserted=0,
        ))
        store.record_scrape_metrics(ScrapeRunMetrics(
            seed_account_id="seed123",
            seed_username="seeduser",
            run_at=datetime.utcnow() - timedelta(days=8),
            duration_seconds=9.0,
            following_captured=0,
            followers_captured=35,
            followers_you_follow_captured=0,
            list_members_captured=0,
            following_claimed_total=0,
            followers_claimed_total=35,
            followers_you_follow_claimed_total=0,
            following_coverage=0.0,
            followers_coverage=1.0,
            followers_you_follow_coverage=0.0,
            accounts_upserted=0,
            edges_upserted=0,
            discoveries_upserted=0,
        ))

        policy = EnrichmentPolicy.default()

        with patch("src.shadow.enricher.SeleniumWorker"):
            enricher = HybridShadowEnricher(store, mock_config, policy)

        following_skip, following_days, following_count = enricher._check_list_freshness_across_runs(
            "seed123",
            "following",
            "seeduser",
        )
        followers_skip, followers_days, followers_count = enricher._check_list_freshness_across_runs(
            "seed123",
            "followers",
            "seeduser",
        )

        assert following_skip is True
        assert following_count > 13
        assert 0 <= following_days <= 180

        assert followers_skip is True
        assert followers_count > 13
        assert 0 <= followers_days <= 180
