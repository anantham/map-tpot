"""Integration tests for shadow enrichment workflow.

These tests verify enricher behavior through the public enrich() API.
They use mocking to isolate the enricher from external dependencies
(Selenium, database) while testing observable outcomes.

NOTE: These are orchestration unit tests (heavily mocked), not true integration tests.
For actual integration tests against real browser/database, see integration markers
used in separate suites.
- Tests in test_shadow_archive_consistency.py for DB integration

CURRENT STATUS: 14/14 tests PASS (refactored 2024-12 to test through public API).
"""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from src.shadow.enricher import HybridShadowEnricher, SeedAccount
from src.shadow.selenium_worker import CapturedUser, UserListCapture, ProfileOverview
from tests.helpers.recording_shadow_store import RecordingShadowStore

# Fixtures mock_enrichment_config and mock_enrichment_policy are auto-loaded from conftest.py


@pytest.fixture
def recording_shadow_store():
    """Stateful store to capture enrichment side effects."""
    return RecordingShadowStore()


# ==============================================================================
# SKIP LOGIC TESTS - BEHAVIORAL (REFACTORED) ✅
# ==============================================================================
# Tests verify skip behavior through public enrich() API.
# Focus: Observable outcomes (summary, no scraping), not implementation details.
# ==============================================================================

@pytest.mark.unit
class TestSkipLogic:
    """Behavioral tests for seed skip logic.

    ✅ REFACTORED: Test through public enrich() API, verify observable outcomes.
    These tests survive refactoring (rename helpers, reorder code).
    """

    def test_enrich_skips_when_complete_profile_and_edges(self, recording_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """enrich() should skip seeds with complete profile, existing edges, and fresh data."""
        from datetime import datetime, timedelta
        from src.data.shadow_store import ScrapeRunMetrics

        # Setup: Seed has complete profile and edges
        recording_shadow_store.set_profile_complete("123", True)
        recording_shadow_store.set_edge_summary("123", 50, 100)

        # Mock recent scrape (fresh data, policy says skip)
        recent_scrape = ScrapeRunMetrics(
            seed_account_id="123", seed_username="testuser",
            run_at=datetime.utcnow() - timedelta(days=1),
            duration_seconds=10.0,
            following_captured=50, followers_captured=100, followers_you_follow_captured=0,
            list_members_captured=0,
            following_claimed_total=50, followers_claimed_total=100, followers_you_follow_claimed_total=0,
            following_coverage=1.0, followers_coverage=1.0, followers_you_follow_coverage=0.0,
            accounts_upserted=150, edges_upserted=150, discoveries_upserted=150,
        )
        recording_shadow_store.set_last_scrape_metrics("123", recent_scrape)

        overview = ProfileOverview(
            username="testuser", display_name="Test", bio="", location="",
            website="", followers_total=100, following_total=50
        )

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(recording_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Skipped in summary (policy confirms fresh)
            assert result["123"]["skipped"] is True
            assert "policy confirms fresh" in result["123"]["reason"]
            assert result["123"]["edge_summary"]["following"] == 50
            assert recording_shadow_store.metrics[-1].skipped is True
            assert "policy confirms fresh" in (recording_shadow_store.metrics[-1].skip_reason or "")
            assert len(recording_shadow_store.edges) == 0
            assert len(recording_shadow_store.discoveries) == 0

    def test_enrich_scrapes_when_incomplete_profile(self, recording_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """enrich() should scrape when profile is incomplete, even with edges."""
        # Setup: Has edges but incomplete profile
        recording_shadow_store.set_profile_complete("123", False)
        recording_shadow_store.set_edge_summary("123", 50, 100)

        overview = ProfileOverview(
            username="testuser",
            display_name="Test User",
            bio="Bio",
            location="Location",
            website="https://example.com",
            followers_total=100,
            following_total=50,
        )
        following_entries = [
            CapturedUser(username="user1", display_name="User One", bio="Bio one", list_types={"following"}),
        ]
        followers_entries = [
            CapturedUser(username="user2", display_name="User Two", bio="Bio two", list_types={"followers"}),
        ]

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.fetch_following = Mock(return_value=UserListCapture("following", following_entries, 50, "url", overview))
            mock_worker.fetch_followers = Mock(return_value=UserListCapture("followers", followers_entries, 100, "url", overview))
            mock_worker.fetch_followers_you_follow = Mock(return_value=UserListCapture("followers_you_follow", [], 0, "url", overview))
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(recording_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Not skipped
            seed_summary = result["123"]
            assert seed_summary.get("skipped") is not True
            assert seed_summary["following_captured"] == len(following_entries)
            assert seed_summary["followers_captured"] == len(followers_entries)
            assert seed_summary["edges_upserted"] == len(following_entries) + len(followers_entries)
            assert len(recording_shadow_store.edges) == len(following_entries) + len(followers_entries)

    def test_enrich_scrapes_when_no_edges(self, recording_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """enrich() should scrape when no edges exist, even with complete profile."""
        # Setup: Complete profile but no edges
        recording_shadow_store.set_profile_complete("123", True)

        overview = ProfileOverview(
            username="testuser",
            display_name="Test User",
            bio="Bio",
            location="Location",
            website="https://example.com",
            followers_total=100,
            following_total=50,
        )
        following_entries = [
            CapturedUser(username="user3", display_name="User Three", bio="Bio three", list_types={"following"}),
        ]
        followers_entries = [
            CapturedUser(username="user4", display_name="User Four", bio="Bio four", list_types={"followers"}),
        ]

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.fetch_following = Mock(return_value=UserListCapture("following", following_entries, 50, "url", overview))
            mock_worker.fetch_followers = Mock(return_value=UserListCapture("followers", followers_entries, 100, "url", overview))
            mock_worker.fetch_followers_you_follow = Mock(return_value=UserListCapture("followers_you_follow", [], 0, "url", overview))
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(recording_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Scraping happened (not skipped)
            seed_summary = result["123"]
            assert seed_summary.get("skipped") is not True
            assert seed_summary["following_captured"] == len(following_entries)
            assert seed_summary["followers_captured"] == len(followers_entries)
            assert seed_summary["edges_upserted"] == len(following_entries) + len(followers_entries)
            assert len(recording_shadow_store.edges) == len(following_entries) + len(followers_entries)


# ==============================================================================
# PROFILE-ONLY MODE TESTS - BEHAVIORAL (REFACTORED) ✅
# ==============================================================================
# Tests verify profile-only behavior through public enrich() API.
# Focus: Profile updates without list scraping, observable in summary.
# ==============================================================================

@pytest.mark.unit
class TestProfileOnlyMode:
    """Behavioral tests for profile-only enrichment mode.

    ✅ REFACTORED: Test through public enrich() API with profile_only=True.
    Verifies profile updates happen without list scraping, checks upsert calls.
    """

    def test_enrich_updates_profile_when_has_edges(self, recording_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """enrich() in profile-only mode updates profiles for seeds with edges."""
        # Setup: Profile-only mode, seed has edges
        mock_enrichment_config.profile_only = True
        mock_enrichment_config.profile_only_all = False
        recording_shadow_store.set_edge_summary("123", 50, 100)
        recording_shadow_store.set_profile_complete("123", False)

        overview = ProfileOverview(
            username="testuser",
            display_name="Test User",
            bio="Bio",
            location="Location",
            website="https://example.com",
            followers_total=100,
            following_total=50,
            profile_image_url="https://example.com/avatar.jpg",
            joined_date="2020-01-01",
        )

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(recording_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Profile updated in summary
            assert result["123"]["profile_only"] is True
            assert result["123"]["updated"] is True
            assert result["123"]["profile_overview"]["username"] == "testuser"
            assert "123" in recording_shadow_store.accounts
            assert len(recording_shadow_store.edges) == 0

    def test_enrich_skips_profile_when_no_edges(self, recording_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """enrich() in profile-only mode skips seeds without edges (default behavior)."""
        # Setup: Profile-only mode, seed has NO edges
        mock_enrichment_config.profile_only = True
        mock_enrichment_config.profile_only_all = False
        recording_shadow_store.set_profile_complete("123", False)

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(recording_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Skipped in summary
            assert result["123"]["skipped"] is True
            assert result["123"]["reason"] == "no_edge_data"
            assert recording_shadow_store.accounts == {}
            assert recording_shadow_store.metrics == []

    def test_enrich_updates_all_in_profile_only_all_mode(self, recording_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """enrich() with --profile-only-all updates even seeds without edges."""
        # Setup: profile-only-all mode (force refresh)
        mock_enrichment_config.profile_only = True
        mock_enrichment_config.profile_only_all = True
        recording_shadow_store.set_profile_complete("123", False)

        overview = ProfileOverview(
            username="testuser",
            display_name="Test User",
            bio="Bio",
            location="Location",
            website="https://example.com",
            followers_total=100,
            following_total=50,
            profile_image_url="https://example.com/avatar.jpg",
            joined_date="2020-01-01",
        )

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(recording_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Profile updated (NOT skipped despite no edges)
            assert result["123"]["updated"] is True
            assert "123" in recording_shadow_store.accounts


# ==============================================================================
# POLICY-DRIVEN REFRESH TESTS - NOW WORKING ✅
# ==============================================================================
# These tests verify policy-driven list refresh behavior through public API.
# ==============================================================================

@pytest.mark.unit
class TestPolicyRefreshLogic:
    """Tests for policy-driven list refresh behavior.

    ✅ REFACTORED: Tests verify age-based and delta-based refresh triggers
    through the public enrich() API, not private helpers.
    """

    def test_enrich_refreshes_when_no_previous_scrape(self, recording_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should scrape lists when no previous scrape exists."""
        # Setup: no previous scrape, incomplete profile
        recording_shadow_store.set_profile_complete("123", False)

        overview = ProfileOverview(
            username="testuser", display_name="Test", bio="", location="",
            website="", followers_total=100, following_total=50
        )
        following_entries = [
            CapturedUser(username="user1", display_name="User One", bio="Bio one", list_types={"following"}),
        ]
        followers_entries = [
            CapturedUser(username="user2", display_name="User Two", bio="Bio two", list_types={"followers"}),
        ]

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.fetch_following = Mock(return_value=UserListCapture("following", following_entries, 50, "url", overview))
            mock_worker.fetch_followers = Mock(return_value=UserListCapture("followers", followers_entries, 100, "url", overview))
            mock_worker.fetch_followers_you_follow = Mock(return_value=UserListCapture("followers_you_follow", [], 0, "url", overview))
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(recording_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Lists scraped (no skip due to missing baseline)
            seed_summary = result["123"]
            assert seed_summary["following_captured"] == len(following_entries)
            assert seed_summary["followers_captured"] == len(followers_entries)
            assert seed_summary["edges_upserted"] == len(following_entries) + len(followers_entries)
            assert len(recording_shadow_store.edges) == len(following_entries) + len(followers_entries)

    def test_enrich_refreshes_when_age_exceeds_threshold(self, recording_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should re-scrape COMPLETE seed when age > list_refresh_days (180 days)."""
        from datetime import datetime, timedelta
        from src.data.shadow_store import ScrapeRunMetrics

        # Setup: old scrape from 200 days ago, COMPLETE profile + edges (policy still triggers)
        old_scrape = ScrapeRunMetrics(
            seed_account_id="123", seed_username="testuser",
            run_at=datetime.utcnow() - timedelta(days=200),
            duration_seconds=10.0,
            following_captured=50, followers_captured=100, followers_you_follow_captured=0,
            list_members_captured=0,
            following_claimed_total=50, followers_claimed_total=100, followers_you_follow_claimed_total=0,
            following_coverage=1.0, followers_coverage=1.0, followers_you_follow_coverage=0.0,
            accounts_upserted=150, edges_upserted=150, discoveries_upserted=150,
        )
        recording_shadow_store.set_last_scrape_metrics("123", old_scrape)
        recording_shadow_store.set_profile_complete("123", True)
        recording_shadow_store.set_edge_summary("123", 50, 100)

        overview = ProfileOverview(
            username="testuser", display_name="Test", bio="", location="",
            website="", followers_total=100, following_total=50
        )
        following_entries = [
            CapturedUser(username="user1", display_name="User One", bio="Bio one", list_types={"following"}),
        ]
        followers_entries = [
            CapturedUser(username="user2", display_name="User Two", bio="Bio two", list_types={"followers"}),
        ]

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.fetch_following = Mock(return_value=UserListCapture("following", following_entries, 50, "url", overview))
            mock_worker.fetch_followers = Mock(return_value=UserListCapture("followers", followers_entries, 100, "url", overview))
            mock_worker.fetch_followers_you_follow = Mock(return_value=UserListCapture("followers_you_follow", [], 0, "url", overview))
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(recording_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Lists re-scraped despite complete data (age trigger)
            seed_summary = result["123"]
            assert seed_summary["following_captured"] == len(following_entries)
            assert seed_summary["followers_captured"] == len(followers_entries)
            assert seed_summary["edges_upserted"] == len(following_entries) + len(followers_entries)
            assert len(recording_shadow_store.edges) == len(following_entries) + len(followers_entries)

    def test_enrich_refreshes_when_delta_exceeds_threshold(self, recording_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should re-scrape COMPLETE seed when pct_delta > 50% threshold."""
        from datetime import datetime, timedelta
        from src.data.shadow_store import ScrapeRunMetrics

        # Setup: recent scrape (1 day ago) with 100 following, COMPLETE profile + edges
        recent_scrape = ScrapeRunMetrics(
            seed_account_id="123", seed_username="testuser",
            run_at=datetime.utcnow() - timedelta(days=1),
            duration_seconds=10.0,
            following_captured=100, followers_captured=100, followers_you_follow_captured=0,
            list_members_captured=0,
            following_claimed_total=100, followers_claimed_total=100, followers_you_follow_claimed_total=0,
            following_coverage=1.0, followers_coverage=1.0, followers_you_follow_coverage=0.0,
            accounts_upserted=200, edges_upserted=200, discoveries_upserted=200,
        )
        recording_shadow_store.set_last_scrape_metrics("123", recent_scrape)
        recording_shadow_store.set_profile_complete("123", True)
        recording_shadow_store.set_edge_summary("123", 100, 100)

        # Overview shows 200 following (100% increase from baseline 100)
        overview = ProfileOverview(
            username="testuser", display_name="Test", bio="", location="",
            website="", followers_total=100, following_total=200
        )
        following_entries = [
            CapturedUser(username="user3", display_name="User Three", bio="Bio three", list_types={"following"}),
        ]
        followers_entries = [
            CapturedUser(username="user4", display_name="User Four", bio="Bio four", list_types={"followers"}),
        ]

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.fetch_following = Mock(return_value=UserListCapture("following", following_entries, 200, "url", overview))
            mock_worker.fetch_followers = Mock(return_value=UserListCapture("followers", followers_entries, 100, "url", overview))
            mock_worker.fetch_followers_you_follow = Mock(return_value=UserListCapture("followers_you_follow", [], 0, "url", overview))
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(recording_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Following list refreshed; followers list remains fresh.
            seed_summary = result["123"]
            assert seed_summary["following_captured"] == len(following_entries)
            assert seed_summary["followers_captured"] == 0
            assert seed_summary["edges_upserted"] == len(following_entries)
            assert len(recording_shadow_store.edges) == len(following_entries)

    def test_enrich_skips_when_fresh_data(self, recording_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should skip COMPLETE seed when age < threshold AND delta < threshold."""
        from datetime import datetime, timedelta
        from src.data.shadow_store import ScrapeRunMetrics

        # Setup: recent scrape (1 day ago) with 100 following, COMPLETE profile + edges
        recent_scrape = ScrapeRunMetrics(
            seed_account_id="123", seed_username="testuser",
            run_at=datetime.utcnow() - timedelta(days=1),
            duration_seconds=10.0,
            following_captured=100, followers_captured=100, followers_you_follow_captured=0,
            list_members_captured=0,
            following_claimed_total=100, followers_claimed_total=100, followers_you_follow_claimed_total=0,
            following_coverage=1.0, followers_coverage=1.0, followers_you_follow_coverage=0.0,
            accounts_upserted=200, edges_upserted=200, discoveries_upserted=200,
        )
        recording_shadow_store.set_last_scrape_metrics("123", recent_scrape)
        recording_shadow_store.set_profile_complete("123", True)
        recording_shadow_store.set_edge_summary("123", 100, 100)

        # Overview shows 110 following (10% increase, below 50% threshold)
        overview = ProfileOverview(
            username="testuser", display_name="Test", bio="", location="",
            website="", followers_total=100, following_total=110
        )

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(recording_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Skipped (complete data + policy confirms fresh)
            assert result["123"]["skipped"] is True
            assert "policy confirms fresh" in result["123"]["reason"]
            assert len(recording_shadow_store.edges) == 0
            assert recording_shadow_store.metrics[-1].skipped is True

    def test_enrich_proceeds_when_auto_confirm_enabled(self, recording_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should auto-proceed when auto_confirm_rescrapes=True (no prompt)."""
        # Setup: policy requires confirmation but auto-confirms
        mock_enrichment_policy.auto_confirm_rescrapes = True
        mock_enrichment_policy.require_user_confirmation = True

        recording_shadow_store.set_profile_complete("123", False)

        overview = ProfileOverview(
            username="testuser", display_name="Test", bio="", location="",
            website="", followers_total=100, following_total=50
        )
        following_entries = [
            CapturedUser(username="user1", display_name="User One", bio="Bio one", list_types={"following"}),
        ]
        followers_entries = [
            CapturedUser(username="user2", display_name="User Two", bio="Bio two", list_types={"followers"}),
        ]

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.fetch_following = Mock(return_value=UserListCapture("following", following_entries, 50, "url", overview))
            mock_worker.fetch_followers = Mock(return_value=UserListCapture("followers", followers_entries, 100, "url", overview))
            mock_worker.fetch_followers_you_follow = Mock(return_value=UserListCapture("followers_you_follow", [], 0, "url", overview))
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(recording_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Enrichment proceeded (no blocking prompt)
            seed_summary = result["123"]
            assert seed_summary["following_captured"] == len(following_entries)
            assert seed_summary["followers_captured"] == len(followers_entries)
            assert len(recording_shadow_store.edges) == len(following_entries) + len(followers_entries)

    def test_enrich_proceeds_when_confirmation_not_required(self, recording_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should proceed when require_user_confirmation=False (default)."""
        # Setup: policy does not require confirmation
        mock_enrichment_policy.auto_confirm_rescrapes = False
        mock_enrichment_policy.require_user_confirmation = False

        recording_shadow_store.set_profile_complete("123", False)

        overview = ProfileOverview(
            username="testuser", display_name="Test", bio="", location="",
            website="", followers_total=100, following_total=50
        )
        following_entries = [
            CapturedUser(username="user3", display_name="User Three", bio="Bio three", list_types={"following"}),
        ]
        followers_entries = [
            CapturedUser(username="user4", display_name="User Four", bio="Bio four", list_types={"followers"}),
        ]

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.fetch_following = Mock(return_value=UserListCapture("following", following_entries, 50, "url", overview))
            mock_worker.fetch_followers = Mock(return_value=UserListCapture("followers", followers_entries, 100, "url", overview))
            mock_worker.fetch_followers_you_follow = Mock(return_value=UserListCapture("followers_you_follow", [], 0, "url", overview))
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(recording_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Enrichment proceeded (no prompt)
            seed_summary = result["123"]
            assert seed_summary["following_captured"] == len(following_entries)
            assert seed_summary["followers_captured"] == len(followers_entries)
            assert len(recording_shadow_store.edges) == len(following_entries) + len(followers_entries)


# ==============================================================================
# PUBLIC API INTEGRATION TESTS - THESE SHOULD WORK
# ==============================================================================
# These test the actual public enrich() method with mocked dependencies.
# ==============================================================================

class TestEnrichPublicAPI:
    """Integration tests for the public enrich() method.

    These tests work because they test the actual API that exists.
    """

    @pytest.mark.unit
    def test_enrich_with_complete_seed_skips_scraping(self, recording_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Test that complete seeds with fresh data are skipped via public API."""
        from datetime import datetime, timedelta
        from src.data.shadow_store import ScrapeRunMetrics

        # Mock recent scrape (fresh data)
        recent_scrape = ScrapeRunMetrics(
            seed_account_id="123", seed_username="testuser",
            run_at=datetime.utcnow() - timedelta(days=1),
            duration_seconds=10.0,
            following_captured=50, followers_captured=100, followers_you_follow_captured=0,
            list_members_captured=0,
            following_claimed_total=50, followers_claimed_total=100, followers_you_follow_claimed_total=0,
            following_coverage=1.0, followers_coverage=1.0, followers_you_follow_coverage=0.0,
            accounts_upserted=150, edges_upserted=150, discoveries_upserted=150,
        )
        recording_shadow_store.set_profile_complete("123", True)
        recording_shadow_store.set_edge_summary("123", 50, 100)
        recording_shadow_store.set_last_scrape_metrics("123", recent_scrape)

        overview = ProfileOverview(
            username="testuser", display_name="Test", bio="", location="",
            website="", followers_total=100, following_total=50
        )

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(recording_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Should skip and not scrape (policy confirms fresh)
            assert result["123"]["skipped"] is True
            assert "policy confirms fresh" in result["123"]["reason"]
            assert len(recording_shadow_store.edges) == 0
            assert recording_shadow_store.metrics[-1].skipped is True

    @pytest.mark.unit
    def test_enrich_with_incomplete_seed_scrapes(self, recording_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Test that incomplete seeds trigger scraping via public API."""
        recording_shadow_store.set_profile_complete("123", False)

        overview = ProfileOverview(
            username="testuser",
            display_name="Test User",
            bio="Bio",
            location="Location",
            website="https://example.com",
            followers_total=100,
            following_total=50,
        )
        following_entries = [
            CapturedUser(username="user5", display_name="User Five", bio="Bio five", list_types={"following"}),
        ]
        followers_entries = [
            CapturedUser(username="user6", display_name="User Six", bio="Bio six", list_types={"followers"}),
        ]

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.fetch_following = Mock(return_value=UserListCapture(
                "following", following_entries, 50, "url", overview
            ))
            mock_worker.fetch_followers = Mock(return_value=UserListCapture(
                "followers", followers_entries, 100, "url", overview
            ))
            mock_worker.fetch_followers_you_follow = Mock(return_value=UserListCapture(
                "followers_you_follow", [], 0, "url", overview
            ))
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(recording_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Should scrape
            seed_summary = result["123"]
            assert seed_summary["following_captured"] == len(following_entries)
            assert seed_summary["followers_captured"] == len(followers_entries)
            assert seed_summary["edges_upserted"] == len(following_entries) + len(followers_entries)
            assert len(recording_shadow_store.edges) == len(following_entries) + len(followers_entries)


# ==============================================================================
# ARCHITECTURAL NOTES (historical - tests now pass)
# ==============================================================================

"""
## Historical Notes (tests refactored 2024-12, all pass now)

The original tests revealed architectural issues that were addressed:

### 1. Monolithic Design
The `enrich()` method is ~300 lines doing:
- Skip logic (lines 102-143)
- Profile-only mode (lines 144-215)
- Full scraping workflow (lines 217-378)
- Metrics recording (lines 340-360)

### 2. Not Decomposed
No helper methods exist for:
- `_should_skip_seed(seed)` - Skip decision logic
- `_update_profile_only(seed)` - Profile-only workflow
- `_scrape_seed_lists(seed)` - List scraping workflow
- `_record_scrape_metrics(seed, results)` - Metrics recording

### 3. Testing Gaps
Cannot unit test:
- Skip conditions in isolation
- Profile-only vs full enrichment paths
- Error handling at each step
- Edge cases (no followers, timeout, etc.)

### 4. Future Refactoring Needed
To make testable, extract:
```python
def _should_skip_seed(self, seed) -> tuple[bool, Optional[str]]:
    edge_summary = self._store.edge_summary_for_seed(seed.account_id)
    has_edges = edge_summary["following"] > 0 and edge_summary["followers"] > 0
    has_profile = self._store.is_seed_profile_complete(seed.account_id)

    if not self._config.profile_only and has_edges and has_profile:
        return (True, "complete profile and edges exist")
    return (False, None)

def _scrape_seed_profile_only(self, seed) -> dict:
    overview = self._selenium.fetch_profile_overview(seed.username)
    if not overview:
        return {"error": "profile_overview_missing"}
    account = self._make_seed_account_record(seed, overview)
    inserted = self._store.upsert_accounts([account])
    return {"updated": inserted > 0, "overview": overview}

def _scrape_seed_full(self, seed) -> dict:
    # Current lines 217-378 extracted
    ...
```

### 5. Value of Failing Tests
Even though 8/14 tests fail, they provide:
- ✅ Documentation of expected behavior
- ✅ Specification for refactoring
- ✅ Regression tests once decomposed
- ✅ Design constraints (what SHOULD be testable)
- ✅ Evidence that current design is hard to test (code smell)

### 6. Immediate Next Steps
1. Keep these failing tests (don't delete!)
2. Mark as temporarily skipped with a clear reason
3. Create issue: "Refactor HybridShadowEnricher for testability"
4. Use failing tests as acceptance criteria for refactor
"""
