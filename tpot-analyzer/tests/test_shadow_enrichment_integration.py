"""Integration tests for shadow enrichment workflow.

NOTE: Many of these tests are currently FAILING or SKIPPED because the enricher
is not designed for unit testing. The failures reveal architectural issues:

1. No decomposed helper methods (_enrich_seed doesn't exist)
2. Skip logic is inline in enrich() method (lines 102-143)
3. Profile-only logic is inline (lines 144-215)
4. Cannot test individual workflow steps in isolation

These tests document EXPECTED behavior even when not currently testable.
They serve as:
- Design documentation for future refactoring
- Regression tests once enricher is decomposed
- Specification of correct behavior

CURRENT STATUS: 8/14 tests FAIL - this is VALUABLE DATA showing enricher needs refactoring.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from src.shadow.enricher import HybridShadowEnricher, SeedAccount
from src.shadow.selenium_worker import CapturedUser, UserListCapture, ProfileOverview

# Fixtures mock_shadow_store and mock_enrichment_config are auto-loaded from conftest.py


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

    def test_enrich_skips_when_complete_profile_and_edges(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """enrich() should skip seeds with complete profile and existing edges."""
        # Setup: Seed has complete profile and edges
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=True)
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 50, "followers": 100, "total": 150})

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Skipped in summary
            assert result["123"]["skipped"] is True
            assert "complete" in result["123"]["reason"]
            assert result["123"]["edge_summary"]["following"] == 50

            # Verify: No scraping happened
            assert not mock_worker.fetch_following.called
            assert not mock_worker.fetch_followers.called

    def test_enrich_scrapes_when_incomplete_profile(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """enrich() should scrape when profile is incomplete, even with edges."""
        # Setup: Has edges but incomplete profile
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=False)
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 50, "followers": 100, "total": 150})

        overview = ProfileOverview(
            username="testuser",
            display_name="Test User",
            bio="Bio",
            location="Location",
            website="https://example.com",
            followers_total=100,
            following_total=50,
        )

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.fetch_following = Mock(return_value=UserListCapture("following", [], 50, "url", overview))
            mock_worker.fetch_followers = Mock(return_value=UserListCapture("followers", [], 100, "url", overview))
            mock_worker.fetch_followers_you_follow = Mock(return_value=UserListCapture("followers_you_follow", [], 0, "url", overview))
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Not skipped
            assert "skipped" not in result["123"] or result["123"]["skipped"] is False

            # Verify: Scraping happened
            assert mock_worker.fetch_following.called
            assert mock_worker.fetch_followers.called

    def test_enrich_scrapes_when_no_edges(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """enrich() should scrape when no edges exist, even with complete profile."""
        # Setup: Complete profile but no edges
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=True)
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 0, "followers": 0, "total": 0})

        overview = ProfileOverview(
            username="testuser",
            display_name="Test User",
            bio="Bio",
            location="Location",
            website="https://example.com",
            followers_total=100,
            following_total=50,
        )

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.fetch_following = Mock(return_value=UserListCapture("following", [], 50, "url", overview))
            mock_worker.fetch_followers = Mock(return_value=UserListCapture("followers", [], 100, "url", overview))
            mock_worker.fetch_followers_you_follow = Mock(return_value=UserListCapture("followers_you_follow", [], 0, "url", overview))
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Scraping happened (not skipped)
            assert mock_worker.fetch_following.called
            assert mock_worker.fetch_followers.called


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

    def test_enrich_updates_profile_when_has_edges(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """enrich() in profile-only mode updates profiles for seeds with edges."""
        # Setup: Profile-only mode, seed has edges
        mock_enrichment_config.profile_only = True
        mock_enrichment_config.profile_only_all = False
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 50, "followers": 100, "total": 150})
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=False)
        mock_shadow_store.upsert_accounts = Mock(return_value=1)

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

            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Profile updated in summary
            assert result["123"]["profile_only"] is True
            assert result["123"]["updated"] is True
            assert result["123"]["profile_overview"]["username"] == "testuser"

            # Verify: Profile fetched, accounts upserted
            mock_worker.fetch_profile_overview.assert_called_once_with("testuser")
            mock_shadow_store.upsert_accounts.assert_called_once()

            # Verify: No list scraping
            assert not mock_worker.fetch_following.called
            assert not mock_worker.fetch_followers.called

    def test_enrich_skips_profile_when_no_edges(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """enrich() in profile-only mode skips seeds without edges (default behavior)."""
        # Setup: Profile-only mode, seed has NO edges
        mock_enrichment_config.profile_only = True
        mock_enrichment_config.profile_only_all = False
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 0, "followers": 0, "total": 0})
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=False)

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Skipped in summary
            assert result["123"]["skipped"] is True
            assert result["123"]["reason"] == "no_edge_data"

            # Verify: No profile fetch, no list scraping
            assert not mock_worker.fetch_profile_overview.called
            assert not mock_worker.fetch_following.called

    def test_enrich_updates_all_in_profile_only_all_mode(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """enrich() with --profile-only-all updates even seeds without edges."""
        # Setup: profile-only-all mode (force refresh)
        mock_enrichment_config.profile_only = True
        mock_enrichment_config.profile_only_all = True
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 0, "followers": 0, "total": 0})
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=False)
        mock_shadow_store.upsert_accounts = Mock(return_value=1)

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

            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Profile updated (NOT skipped despite no edges)
            assert result["123"]["updated"] is True
            mock_worker.fetch_profile_overview.assert_called_once()
            mock_shadow_store.upsert_accounts.assert_called_once()


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

    def test_enrich_refreshes_when_no_previous_scrape(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should scrape lists when no previous scrape exists."""
        from src.shadow.selenium_worker import ProfileOverview, UserListCapture

        # Setup: no previous scrape, incomplete profile
        mock_shadow_store.get_last_scrape_metrics = Mock(return_value=None)
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=False)
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 0, "followers": 0, "total": 0})

        overview = ProfileOverview(
            username="testuser", display_name="Test", bio="", location="",
            website="", followers_total=100, following_total=50
        )

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.fetch_following = Mock(return_value=UserListCapture("following", [], 50, "url", overview))
            mock_worker.fetch_followers = Mock(return_value=UserListCapture("followers", [], 100, "url", overview))
            mock_worker.fetch_followers_you_follow = Mock(return_value=UserListCapture("followers_you_follow", [], 0, "url", overview))
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Lists scraped (no skip due to missing baseline)
            assert mock_worker.fetch_following.called
            assert mock_worker.fetch_followers.called
            assert result["123"]["edges_upserted"] >= 0

    def test_enrich_refreshes_when_age_exceeds_threshold(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should re-scrape lists when age > list_refresh_days (180 days)."""
        from datetime import datetime, timedelta
        from src.data.shadow_store import ScrapeRunMetrics
        from src.shadow.selenium_worker import ProfileOverview, UserListCapture

        # Setup: old scrape from 200 days ago, but INCOMPLETE profile (so policy is consulted)
        old_scrape = ScrapeRunMetrics(
            seed_account_id="123", seed_username="testuser",
            run_at=datetime.utcnow() - timedelta(days=200),
            duration_seconds=10.0,
            following_captured=50, followers_captured=100, followers_you_follow_captured=0,
            following_claimed_total=50, followers_claimed_total=100, followers_you_follow_claimed_total=0,
            following_coverage=1.0, followers_coverage=1.0, followers_you_follow_coverage=0.0,
            accounts_upserted=150, edges_upserted=150, discoveries_upserted=150,
        )
        mock_shadow_store.get_last_scrape_metrics = Mock(return_value=old_scrape)
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=False)  # Incomplete so policy runs
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 0, "followers": 0, "total": 0})

        overview = ProfileOverview(
            username="testuser", display_name="Test", bio="", location="",
            website="", followers_total=100, following_total=50
        )

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.fetch_following = Mock(return_value=UserListCapture("following", [], 50, "url", overview))
            mock_worker.fetch_followers = Mock(return_value=UserListCapture("followers", [], 100, "url", overview))
            mock_worker.fetch_followers_you_follow = Mock(return_value=UserListCapture("followers_you_follow", [], 0, "url", overview))
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Lists scraped (age trigger for incomplete seed)
            assert mock_worker.fetch_following.called
            assert mock_worker.fetch_followers.called
            assert result["123"]["edges_upserted"] >= 0

    def test_enrich_refreshes_when_delta_exceeds_threshold(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should re-scrape when pct_delta > 50% threshold."""
        from datetime import datetime, timedelta
        from src.data.shadow_store import ScrapeRunMetrics
        from src.shadow.selenium_worker import ProfileOverview, UserListCapture

        # Setup: recent scrape (1 day ago) with 100 following, but INCOMPLETE profile (so policy runs)
        recent_scrape = ScrapeRunMetrics(
            seed_account_id="123", seed_username="testuser",
            run_at=datetime.utcnow() - timedelta(days=1),
            duration_seconds=10.0,
            following_captured=100, followers_captured=100, followers_you_follow_captured=0,
            following_claimed_total=100, followers_claimed_total=100, followers_you_follow_claimed_total=0,
            following_coverage=1.0, followers_coverage=1.0, followers_you_follow_coverage=0.0,
            accounts_upserted=200, edges_upserted=200, discoveries_upserted=200,
        )
        mock_shadow_store.get_last_scrape_metrics = Mock(return_value=recent_scrape)
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=False)  # Incomplete so policy runs
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 0, "followers": 0, "total": 0})

        # Overview shows 200 following (100% increase from baseline 100)
        overview = ProfileOverview(
            username="testuser", display_name="Test", bio="", location="",
            website="", followers_total=100, following_total=200
        )

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.fetch_following = Mock(return_value=UserListCapture("following", [], 200, "url", overview))
            mock_worker.fetch_followers = Mock(return_value=UserListCapture("followers", [], 100, "url", overview))
            mock_worker.fetch_followers_you_follow = Mock(return_value=UserListCapture("followers_you_follow", [], 0, "url", overview))
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Lists scraped (delta trigger for incomplete seed)
            assert mock_worker.fetch_following.called
            assert result["123"]["edges_upserted"] >= 0

    def test_enrich_skips_when_fresh_data(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should skip lists when age < threshold AND delta < threshold (for incomplete seeds)."""
        from datetime import datetime, timedelta
        from src.data.shadow_store import ScrapeRunMetrics
        from src.shadow.selenium_worker import ProfileOverview

        # Setup: recent scrape (1 day ago) with 100 following, INCOMPLETE profile (so policy runs)
        recent_scrape = ScrapeRunMetrics(
            seed_account_id="123", seed_username="testuser",
            run_at=datetime.utcnow() - timedelta(days=1),
            duration_seconds=10.0,
            following_captured=100, followers_captured=100, followers_you_follow_captured=0,
            following_claimed_total=100, followers_claimed_total=100, followers_you_follow_claimed_total=0,
            following_coverage=1.0, followers_coverage=1.0, followers_you_follow_coverage=0.0,
            accounts_upserted=200, edges_upserted=200, discoveries_upserted=200,
        )
        mock_shadow_store.get_last_scrape_metrics = Mock(return_value=recent_scrape)
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=False)  # Incomplete so policy runs
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 0, "followers": 0, "total": 0})

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

            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Lists NOT scraped (policy skipped, data fresh)
            assert not mock_worker.fetch_following.called
            assert not mock_worker.fetch_followers.called
            # Skip metrics recorded
            mock_shadow_store.record_scrape_metrics.assert_called()
            recorded_metrics = mock_shadow_store.record_scrape_metrics.call_args[0][0]
            assert recorded_metrics.skipped is True
            assert recorded_metrics.skip_reason == "policy_fresh_data"

    def test_enrich_proceeds_when_auto_confirm_enabled(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should auto-proceed when auto_confirm_rescrapes=True (no prompt)."""
        from src.shadow.selenium_worker import ProfileOverview, UserListCapture

        # Setup: policy requires confirmation but auto-confirms
        mock_enrichment_policy.auto_confirm_rescrapes = True
        mock_enrichment_policy.require_user_confirmation = True

        mock_shadow_store.get_last_scrape_metrics = Mock(return_value=None)
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=False)
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 0, "followers": 0, "total": 0})

        overview = ProfileOverview(
            username="testuser", display_name="Test", bio="", location="",
            website="", followers_total=100, following_total=50
        )

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.fetch_following = Mock(return_value=UserListCapture("following", [], 50, "url", overview))
            mock_worker.fetch_followers = Mock(return_value=UserListCapture("followers", [], 100, "url", overview))
            mock_worker.fetch_followers_you_follow = Mock(return_value=UserListCapture("followers_you_follow", [], 0, "url", overview))
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Enrichment proceeded (no blocking prompt)
            assert mock_worker.fetch_following.called
            assert result["123"]["edges_upserted"] >= 0

    def test_enrich_proceeds_when_confirmation_not_required(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should proceed when require_user_confirmation=False (default)."""
        from src.shadow.selenium_worker import ProfileOverview, UserListCapture

        # Setup: policy does not require confirmation
        mock_enrichment_policy.auto_confirm_rescrapes = False
        mock_enrichment_policy.require_user_confirmation = False

        mock_shadow_store.get_last_scrape_metrics = Mock(return_value=None)
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=False)
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 0, "followers": 0, "total": 0})

        overview = ProfileOverview(
            username="testuser", display_name="Test", bio="", location="",
            website="", followers_total=100, following_total=50
        )

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.fetch_following = Mock(return_value=UserListCapture("following", [], 50, "url", overview))
            mock_worker.fetch_followers = Mock(return_value=UserListCapture("followers", [], 100, "url", overview))
            mock_worker.fetch_followers_you_follow = Mock(return_value=UserListCapture("followers_you_follow", [], 0, "url", overview))
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Verify: Enrichment proceeded (no prompt)
            assert mock_worker.fetch_following.called
            assert result["123"]["edges_upserted"] >= 0


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
    def test_enrich_with_complete_seed_skips_scraping(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Test that complete seeds are skipped via public API."""
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=True)
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={
            "following": 50,
            "followers": 100,
            "total": 150
        })

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Should skip and not scrape
            assert result["123"]["skipped"] is True
            assert "complete" in result["123"]["reason"]
            assert not mock_worker.fetch_following.called
            assert not mock_worker.fetch_followers.called

    @pytest.mark.unit
    def test_enrich_with_incomplete_seed_scrapes(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Test that incomplete seeds trigger scraping via public API."""
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=False)
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 0, "followers": 0, "total": 0})

        overview = ProfileOverview(
            username="testuser",
            display_name="Test User",
            bio="Bio",
            location="Location",
            website="https://example.com",
            followers_total=100,
            following_total=50,
        )

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.fetch_profile_overview = Mock(return_value=overview)
            mock_worker.fetch_following = Mock(return_value=UserListCapture(
                "following", [], 50, "url", overview
            ))
            mock_worker.fetch_followers = Mock(return_value=UserListCapture(
                "followers", [], 100, "url", overview
            ))
            mock_worker.fetch_followers_you_follow = Mock(return_value=UserListCapture(
                "followers_you_follow", [], 0, "url", overview
            ))
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Should scrape
            assert mock_worker.fetch_following.called
            assert mock_worker.fetch_followers.called
            assert result["123"]["accounts_upserted"] >= 0


# ==============================================================================
# ARCHITECTURAL ANALYSIS
# ==============================================================================

"""
## What The Failing Tests Reveal:

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
2. Mark with @pytest.mark.skip + reason
3. Create issue: "Refactor HybridShadowEnricher for testability"
4. Use failing tests as acceptance criteria for refactor
"""
