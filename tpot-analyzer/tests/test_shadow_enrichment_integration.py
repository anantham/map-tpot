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
# SKIP LOGIC TESTS - NOW WORKING ✅
# ==============================================================================
# These tests now work because _should_skip_seed() helper was extracted!
# ==============================================================================

@pytest.mark.unit
class TestSkipLogic:
    """Tests for _should_skip_seed() helper method.

    ✅ REFACTORED: Skip logic extracted from enrich() into testable helper.
    Tests verify skip decisions based on edge/profile completeness.
    """

    def test_skip_when_complete_profile_and_edges(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should skip when profile complete AND has edges in normal mode."""
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=True)
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 50, "followers": 100, "total": 150})

        with patch('src.shadow.enricher.SeleniumWorker'):
            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            should_skip, skip_reason, edge_summary = enricher._should_skip_seed(seed)

            assert should_skip is True
            assert skip_reason == "complete profile and edges exist"
            assert edge_summary["following"] == 50
            assert edge_summary["followers"] == 100

    def test_no_skip_when_incomplete_profile(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should NOT skip when profile incomplete even with edges."""
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=False)
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 50, "followers": 100, "total": 150})

        with patch('src.shadow.enricher.SeleniumWorker'):
            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            should_skip, skip_reason, edge_summary = enricher._should_skip_seed(seed)

            assert should_skip is False
            assert skip_reason is None

    def test_no_skip_when_no_edges(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should NOT skip when no edges exist even with complete profile."""
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=True)
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 0, "followers": 0, "total": 0})

        with patch('src.shadow.enricher.SeleniumWorker'):
            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            should_skip, skip_reason, edge_summary = enricher._should_skip_seed(seed)

            assert should_skip is False
            assert skip_reason is None

    def test_no_skip_in_profile_only_mode(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should NOT skip in profile-only mode (handled separately)."""
        mock_shadow_store.is_seed_profile_complete = Mock(return_value=True)
        mock_shadow_store.edge_summary_for_seed = Mock(return_value={"following": 50, "followers": 100, "total": 150})
        mock_enrichment_config.profile_only = True  # Enable profile-only mode

        with patch('src.shadow.enricher.SeleniumWorker'):
            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            should_skip, skip_reason, edge_summary = enricher._should_skip_seed(seed)

            # In profile-only mode, this helper never skips
            assert should_skip is False
            assert skip_reason is None


# ==============================================================================
# PROFILE-ONLY MODE TESTS - NOW WORKING ✅
# ==============================================================================
# These tests now work because _refresh_profile() helper was extracted!
# ==============================================================================

@pytest.mark.unit
class TestProfileOnlyMode:
    """Tests for _refresh_profile() helper method.

    ✅ REFACTORED: Profile-only logic extracted from enrich() into testable helper.
    Tests verify profile updates without list scraping.
    """

    def test_refresh_profile_updates_when_has_edges(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should update profile when has edges (normal profile-only mode)."""
        from src.shadow.selenium_worker import ProfileOverview

        mock_enrichment_config.profile_only = True
        mock_enrichment_config.profile_only_all = False
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

            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher._refresh_profile(seed, has_edges=True, has_profile=False)

            assert result is not None
            assert result["profile_only"] is True
            assert result["updated"] is True
            assert result["profile_overview"]["username"] == "testuser"
            mock_worker.fetch_profile_overview.assert_called_once_with("testuser")

    def test_refresh_profile_skips_when_no_edges(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should skip when no edges exist (default profile-only mode)."""
        mock_enrichment_config.profile_only = True
        mock_enrichment_config.profile_only_all = False

        with patch('src.shadow.enricher.SeleniumWorker'):
            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher._refresh_profile(seed, has_edges=False, has_profile=False)

            assert result is not None
            assert result["skipped"] is True
            assert result["reason"] == "no_edge_data"

    def test_refresh_profile_all_mode_ignores_edges(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should update profile even without edges in --profile-only-all mode."""
        from src.shadow.selenium_worker import ProfileOverview

        mock_enrichment_config.profile_only = True
        mock_enrichment_config.profile_only_all = True  # Force refresh all
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

            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher._refresh_profile(seed, has_edges=False, has_profile=False)

            assert result is not None
            assert result["updated"] is True
            mock_worker.fetch_profile_overview.assert_called_once()


# ==============================================================================
# POLICY-DRIVEN REFRESH TESTS - NOW WORKING ✅
# ==============================================================================
# These tests verify the new policy-driven list refresh logic.
# ==============================================================================

@pytest.mark.unit
class TestPolicyRefreshLogic:
    """Tests for policy-driven list refresh helpers.

    ✅ NEW: Tests verify age-based and delta-based refresh triggers.
    Tests verify user confirmation prompts and auto-confirm modes.
    """

    def test_should_refresh_when_no_previous_scrape(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should always refresh when no previous scrape exists."""
        mock_shadow_store.get_last_scrape_metrics = Mock(return_value=None)

        with patch('src.shadow.enricher.SeleniumWorker'):
            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            should_refresh, skip_reason = enricher._should_refresh_list(seed, "following", 100)

            assert should_refresh is True
            assert skip_reason is None

    def test_should_refresh_when_age_exceeds_threshold(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should refresh when age > list_refresh_days threshold."""
        from datetime import datetime, timedelta
        from src.data.shadow_store import ScrapeRunMetrics

        # Mock last scrape from 200 days ago (threshold is 180)
        old_scrape = ScrapeRunMetrics(
            seed_account_id="123",
            seed_username="testuser",
            run_at=datetime.utcnow() - timedelta(days=200),
            duration_seconds=10.0,
            following_captured=50,
            followers_captured=100,
            followers_you_follow_captured=0,
            following_claimed_total=50,
            followers_claimed_total=100,
            followers_you_follow_claimed_total=0,
            following_coverage=1.0,
            followers_coverage=1.0,
            followers_you_follow_coverage=0.0,
            accounts_upserted=150,
            edges_upserted=150,
            discoveries_upserted=150,
        )
        mock_shadow_store.get_last_scrape_metrics = Mock(return_value=old_scrape)

        with patch('src.shadow.enricher.SeleniumWorker'):
            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            should_refresh, skip_reason = enricher._should_refresh_list(seed, "following", 50)

            assert should_refresh is True
            assert skip_reason is None

    def test_should_refresh_when_delta_exceeds_threshold(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should refresh when pct_delta > pct_delta_threshold (50%)."""
        from datetime import datetime, timedelta
        from src.data.shadow_store import ScrapeRunMetrics

        # Mock recent scrape (1 day ago) with old count of 100
        recent_scrape = ScrapeRunMetrics(
            seed_account_id="123",
            seed_username="testuser",
            run_at=datetime.utcnow() - timedelta(days=1),
            duration_seconds=10.0,
            following_captured=100,
            followers_captured=100,
            followers_you_follow_captured=0,
            following_claimed_total=100,
            followers_claimed_total=100,
            followers_you_follow_claimed_total=0,
            following_coverage=1.0,
            followers_coverage=1.0,
            followers_you_follow_coverage=0.0,
            accounts_upserted=200,
            edges_upserted=200,
            discoveries_upserted=200,
        )
        mock_shadow_store.get_last_scrape_metrics = Mock(return_value=recent_scrape)

        with patch('src.shadow.enricher.SeleniumWorker'):
            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            # New count is 200 (100% increase, threshold is 50%)
            should_refresh, skip_reason = enricher._should_refresh_list(seed, "following", 200)

            assert should_refresh is True
            assert skip_reason is None

    def test_should_skip_when_fresh_data(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should skip when age < threshold AND delta < threshold."""
        from datetime import datetime, timedelta
        from src.data.shadow_store import ScrapeRunMetrics

        # Mock recent scrape (1 day ago) with small change
        recent_scrape = ScrapeRunMetrics(
            seed_account_id="123",
            seed_username="testuser",
            run_at=datetime.utcnow() - timedelta(days=1),
            duration_seconds=10.0,
            following_captured=100,
            followers_captured=100,
            followers_you_follow_captured=0,
            following_claimed_total=100,
            followers_claimed_total=100,
            followers_you_follow_claimed_total=0,
            following_coverage=1.0,
            followers_coverage=1.0,
            followers_you_follow_coverage=0.0,
            accounts_upserted=200,
            edges_upserted=200,
            discoveries_upserted=200,
        )
        mock_shadow_store.get_last_scrape_metrics = Mock(return_value=recent_scrape)

        with patch('src.shadow.enricher.SeleniumWorker'):
            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            # New count is 110 (10% increase, under 50% threshold)
            should_refresh, skip_reason = enricher._should_refresh_list(seed, "following", 110)

            assert should_refresh is False
            assert skip_reason == "following_fresh"

    def test_confirm_refresh_auto_confirms(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should auto-confirm when auto_confirm_rescrapes=True."""
        mock_enrichment_policy.auto_confirm_rescrapes = True
        mock_enrichment_policy.require_user_confirmation = True

        with patch('src.shadow.enricher.SeleniumWorker'):
            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            confirmed = enricher._confirm_refresh(seed, "following")

            assert confirmed is True

    def test_confirm_refresh_skips_prompt_when_not_required(self, mock_shadow_store, mock_enrichment_config, mock_enrichment_policy):
        """Should skip prompt when require_user_confirmation=False."""
        mock_enrichment_policy.auto_confirm_rescrapes = False
        mock_enrichment_policy.require_user_confirmation = False

        with patch('src.shadow.enricher.SeleniumWorker'):
            enricher = HybridShadowEnricher(mock_shadow_store, mock_enrichment_config, mock_enrichment_policy)
            seed = SeedAccount(account_id="123", username="testuser")

            confirmed = enricher._confirm_refresh(seed, "following")

            assert confirmed is True


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
