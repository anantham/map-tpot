import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from src.shadow.selenium_worker import SeleniumWorker, AccountStatusInfo, ProfileOverview, SeleniumConfig
from src.shadow.enricher import EnrichmentPolicy, HybridShadowEnricher, SeedAccount
from src.data.shadow_store import ScrapeRunMetrics, ShadowAccount

class TestAccountStatusTracking(unittest.TestCase):
    def setUp(self):
        config = SeleniumConfig(cookies_path=Mock())
        self.worker = SeleniumWorker(config)
        self.worker._driver = Mock()
        # Mock ensure_driver to return True
        self.worker._ensure_driver = Mock(return_value=True)

    def test_check_account_exists_protected(self):
        # Setup protected account page
        self.worker._driver.find_elements.side_effect = lambda by, val: [] # no empty state
        body_mock = Mock()
        body_mock.text = "Some text... These posts are protected ... some more text"
        self.worker._driver.find_element.return_value = body_mock
        
        # Run
        status = self.worker._check_account_exists("protected_user")
        
        # Verify
        self.assertEqual(status.status, "protected")
        self.assertEqual(status.message, "These posts are protected")

    def test_check_account_exists_active(self):
        self.worker._driver.find_elements.side_effect = lambda by, val: [] # no empty state
        body_mock = Mock()
        body_mock.text = "Just a normal profile"
        self.worker._driver.find_element.return_value = body_mock
        
        status = self.worker._check_account_exists("active_user")
        self.assertEqual(status.status, "active")

    def test_fetch_profile_overview_protected(self):
        # Mock _check_account_exists to return protected
        with patch.object(self.worker, '_check_account_exists') as mock_check:
            mock_check.return_value = AccountStatusInfo(
                status="protected",
                detected_at=datetime.utcnow(),
                message="Protected"
            )
            self.worker._save_page_snapshot = Mock()
            # Mock wait
            with patch('src.shadow.selenium_worker.WebDriverWait'):
                profile = self.worker.fetch_profile_overview("protected_user")
            
            self.assertEqual(profile.display_name, "[PROTECTED]")
            self.assertEqual(profile.bio, "[ACCOUNT PROTECTED]")

    def test_enricher_skips_protected_account(self):
        # Setup enricher with mocked store
        store = Mock()
        config = Mock()
        policy = EnrichmentPolicy(skip_if_ever_scraped=True)
        
        with patch('src.shadow.enricher.XAPIClient'):
            enricher = HybridShadowEnricher(store, config, policy)
        
        # Seed account
        seed = SeedAccount(account_id="123", username="protected_user")
        
        # Mock edge summary
        store.edge_summary_for_seed.return_value = {"following": 0, "followers": 0, "total": 0}
        
        # Last scrape was skipped
        last_scrape = ScrapeRunMetrics(
            seed_account_id="123", seed_username="protected_user",
            run_at=datetime.utcnow() - timedelta(days=1), # yesterday
            duration_seconds=0,
            following_captured=0, followers_captured=0, followers_you_follow_captured=0, list_members_captured=0,
            following_claimed_total=0, followers_claimed_total=0, followers_you_follow_claimed_total=0,
            following_coverage=None, followers_coverage=None, followers_you_follow_coverage=None,
            accounts_upserted=0, edges_upserted=0, discoveries_upserted=0,
            phase_timings={},
            skipped=True,
            skip_reason="account_status_protected_retry_pending"
        )
        store.get_last_scrape_metrics.return_value = last_scrape
        
        # Shadow account has protected status detected yesterday
        account = ShadowAccount(
            account_id="123", username="protected_user",
            display_name="Test", bio="Bio", location="Loc", website="Web",
            profile_image_url="Img", followers_count=0, following_count=0,
            source_channel="test", fetched_at=datetime.utcnow(),
            scrape_stats={
                "account_status": "protected",
                "status_detected_at": (datetime.utcnow() - timedelta(days=1)).isoformat()
            }
        )
        store.get_shadow_account.return_value = account
        
        # Run enrich
        result = enricher.enrich([seed])
        
        # Verify
        self.assertTrue(result["123"]["skipped"])
        self.assertIn("account_status_protected_within_retry_period", result["123"]["reason"])
        # Should not have called _check_list_freshness_across_runs (which isn't mocked here but if called would probably crash or do nothing depending on implementation)
        # Actually, since we didn't mock _check_list_freshness_across_runs, if it was called it would try to access store._execute_with_retry
        # store is a Mock, so it returns a Mock, which is not iterable.
        # So if this test PASSES, it confirms we skipped BEFORE hitting the troublesome code.

    def test_enricher_retries_expired_status(self):
        # Setup enricher
        store = Mock()
        config = Mock()
        policy = EnrichmentPolicy(skip_if_ever_scraped=True)
        
        with patch('src.shadow.enricher.XAPIClient'):
            enricher = HybridShadowEnricher(store, config, policy)
        
        # Mock helper methods to avoid needing full Selenium/Store setup
        enricher._should_skip_seed = Mock(return_value=(False, None, {"following": 0, "followers": 0}, None))
        enricher._refresh_profile = Mock(return_value=None)
        enricher._selenium = Mock()
        enricher._selenium.fetch_profile_overview.return_value = None # Simulate failure to keep it simple
        
        # Mock _check_list_freshness_across_runs to avoid the Mock iteration error
        # We expect this to be called because we are retrying
        enricher._check_list_freshness_across_runs = Mock(return_value=(False, 0, 0))

        seed = SeedAccount(account_id="123", username="protected_user")
        
        # Mock edge summary
        store.edge_summary_for_seed.return_value = {"following": 0, "followers": 0, "total": 0}
        
        # Status detected 100 days ago (expired for protected)
        last_scrape = ScrapeRunMetrics(
            seed_account_id="123", seed_username="protected_user",
            run_at=datetime.utcnow() - timedelta(days=100),
            duration_seconds=0,
            following_captured=0, followers_captured=0, followers_you_follow_captured=0, list_members_captured=0,
            following_claimed_total=0, followers_claimed_total=0, followers_you_follow_claimed_total=0,
            following_coverage=None, followers_coverage=None, followers_you_follow_coverage=None,
            accounts_upserted=0, edges_upserted=0, discoveries_upserted=0,
            phase_timings={},
            skipped=True,
            skip_reason="account_status_protected_retry_pending"
        )
        store.get_last_scrape_metrics.return_value = last_scrape
        
        account = ShadowAccount(
            account_id="123", username="protected_user",
            display_name="Test", bio="Bio", location="Loc", website="Web",
            profile_image_url="Img", followers_count=0, following_count=0,
            source_channel="test", fetched_at=datetime.utcnow(),
            scrape_stats={
                "account_status": "protected",
                "status_detected_at": (datetime.utcnow() - timedelta(days=100)).isoformat()
            }
        )
        store.get_shadow_account.return_value = account
        
        # Run enrich
        result = enricher.enrich([seed])
        
        # Verify we did NOT skip early due to status
        # result might contain error because we mocked fetch_profile_overview to return None
        # But key is checking that we proceeded past the status check
        self.assertFalse(result.get("123", {}).get("skipped", False))
