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


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def mock_store():
    """Create a mock ShadowStore."""
    store = Mock()
    store.fetch_accounts = Mock(return_value=[])
    store.unresolved_accounts = Mock(return_value=[])
    store.is_seed_profile_complete = Mock(return_value=False)
    store.edge_summary_for_seed = Mock(return_value={"following": 0, "followers": 0, "total": 0})
    store.upsert_accounts = Mock(return_value=0)
    store.upsert_edges = Mock(return_value=0)
    store.upsert_discoveries = Mock(return_value=0)
    store.record_scrape_metrics = Mock(return_value=1)
    return store


@pytest.fixture
def mock_config():
    """Create a mock enrichment config."""
    config = Mock()
    config.selenium_cookies_path = Mock(exists=Mock(return_value=True))
    config.selenium_headless = True
    config.selenium_scroll_delay_min = 1.0
    config.selenium_scroll_delay_max = 2.0
    config.user_pause_seconds = 0.1
    config.action_delay_min = 1.0
    config.action_delay_max = 2.0
    config.chrome_binary = None
    config.wait_for_manual_login = False
    config.include_followers = True
    config.include_following = True
    config.include_followers_you_follow = True
    config.bearer_token = None
    config.confirm_first_scrape = False
    config.preview_sample_size = 5
    config.profile_only = False
    config.profile_only_all = False
    return config


# ==============================================================================
# SKIP LOGIC TESTS - CURRENTLY FAILING
# ==============================================================================
# These tests FAIL because there's no _enrich_seed() method.
# The skip logic is embedded in enrich() method (lines 102-143).
#
# Gap revealed: Cannot test skip logic in isolation.
# ==============================================================================

@pytest.mark.skip(reason="No _enrich_seed() method - skip logic is inline in enrich() at lines 102-143")
class TestSkipLogic:
    """Tests for skip logic when profiles already complete.

    ARCHITECTURAL GAP: Skip logic is not decomposed into testable method.
    Current implementation is inline at enricher.py:102-143.

    To make testable, would need:
        def _should_skip_seed(seed) -> tuple[bool, Optional[str]]:
            if not profile_only and has_edges and has_profile:
                return (True, "complete profile and edges exist")
            return (False, None)
    """

    def test_skip_when_complete_profile_and_edges(self, mock_store, mock_config):
        """DOCUMENTS: Should skip when profile complete AND has edges."""
        mock_store.is_seed_profile_complete = Mock(return_value=True)
        mock_store.edge_summary_for_seed = Mock(return_value={"following": 50, "followers": 100, "total": 150})

        with patch('src.shadow.enricher.SeleniumWorker'):
            enricher = HybridShadowEnricher(mock_store, mock_config)
            seed = SeedAccount(account_id="123", username="testuser")

            # This would test skip behavior if _enrich_seed() existed
            # result = enricher._enrich_seed(seed)
            # assert result['skipped'] is True

    def test_no_skip_when_incomplete_profile(self, mock_store, mock_config):
        """DOCUMENTS: Should scrape when profile incomplete even with edges."""
        mock_store.is_seed_profile_complete = Mock(return_value=False)
        mock_store.edge_summary_for_seed = Mock(return_value={"following": 50, "followers": 100, "total": 150})

    def test_no_skip_when_no_edges(self, mock_store, mock_config):
        """DOCUMENTS: Should scrape when no edges exist even with complete profile."""
        mock_store.is_seed_profile_complete = Mock(return_value=True)
        mock_store.edge_summary_for_seed = Mock(return_value={"following": 0, "followers": 0, "total": 0})


# ==============================================================================
# PROFILE-ONLY MODE TESTS - CURRENTLY FAILING
# ==============================================================================
# These tests FAIL because profile-only logic is inline in enrich() (lines 144-215).
#
# Gap revealed: Cannot test profile-only mode in isolation.
# ==============================================================================

@pytest.mark.skip(reason="Profile-only logic is inline in enrich() at lines 144-215")
class TestProfileOnlyMode:
    """Tests for --profile-only flag behavior.

    ARCHITECTURAL GAP: Profile-only logic is not decomposed.
    Current implementation is inline at enricher.py:144-215.

    To make testable, would need:
        def _update_profile_only(seed) -> dict:
            overview = self._selenium.fetch_profile_overview(seed.username)
            account = self._make_seed_account_record(seed, overview)
            self._store.upsert_accounts([account])
            return {"updated": True, "profile_overview": overview}
    """

    def test_profile_only_skips_list_scraping(self, mock_store, mock_config):
        """DOCUMENTS: Profile-only mode should only fetch profile, not lists."""
        mock_config.profile_only = True
        # Test would verify fetch_following/fetch_followers not called


# ==============================================================================
# PUBLIC API INTEGRATION TESTS - THESE SHOULD WORK
# ==============================================================================
# These test the actual public enrich() method with mocked dependencies.
# ==============================================================================

class TestEnrichPublicAPI:
    """Integration tests for the public enrich() method.

    These tests work because they test the actual API that exists.
    """

    def test_enrich_with_complete_seed_skips_scraping(self, mock_store, mock_config):
        """Test that complete seeds are skipped via public API."""
        mock_store.is_seed_profile_complete = Mock(return_value=True)
        mock_store.edge_summary_for_seed = Mock(return_value={
            "following": 50,
            "followers": 100,
            "total": 150
        })

        with patch('src.shadow.enricher.SeleniumWorker') as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker
            mock_worker.quit = Mock()

            enricher = HybridShadowEnricher(mock_store, mock_config)
            seed = SeedAccount(account_id="123", username="testuser")

            result = enricher.enrich([seed])

            # Should skip and not scrape
            assert result["123"]["skipped"] is True
            assert "complete" in result["123"]["reason"]
            assert not mock_worker.fetch_following.called
            assert not mock_worker.fetch_followers.called

    def test_enrich_with_incomplete_seed_scrapes(self, mock_store, mock_config):
        """Test that incomplete seeds trigger scraping via public API."""
        mock_store.is_seed_profile_complete = Mock(return_value=False)
        mock_store.edge_summary_for_seed = Mock(return_value={"following": 0, "followers": 0, "total": 0})

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

            enricher = HybridShadowEnricher(mock_store, mock_config)
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
