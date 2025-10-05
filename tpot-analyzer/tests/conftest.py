"""Shared pytest configuration and fixtures for the test suite.

This module centralizes:
- Path setup (eliminates sys.path hacks in individual test files)
- Pytest markers for test categorization (unit, integration, selenium)
- Common fixtures for mocking shadow enrichment components
- Temporary database fixtures for integration tests
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest


# ==============================================================================
# Path Setup - Ensures src/ is importable
# ==============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ==============================================================================
# Pytest Configuration
# ==============================================================================

def pytest_configure(config):
    """Register custom markers for test categorization."""
    config.addinivalue_line(
        "markers",
        "unit: Fast tests with no I/O (mocked dependencies)",
    )
    config.addinivalue_line(
        "markers",
        "integration: Tests hitting SQLite, file system, or network",
    )
    config.addinivalue_line(
        "markers",
        "selenium: Browser-based tests requiring Selenium (slowest)",
    )
    config.addinivalue_line(
        "markers",
        "requires_supabase: Tests requiring SUPABASE_KEY environment variable",
    )


# ==============================================================================
# Conditional Skip Markers
# ==============================================================================

REQUIRES_SUPABASE = pytest.mark.skipif(
    not os.getenv("SUPABASE_KEY"),
    reason="SUPABASE_KEY environment variable not configured",
)


# ==============================================================================
# Shadow Enrichment Mock Fixtures
# ==============================================================================

@pytest.fixture
def mock_shadow_store():
    """Create a mock ShadowStore with default behavior.

    All methods return empty/zero values by default. Tests can override
    specific methods as needed.

    Example:
        def test_something(mock_shadow_store):
            mock_shadow_store.fetch_accounts.return_value = [...]
            # Test code
    """
    store = Mock()
    store.fetch_accounts = Mock(return_value=[])
    store.unresolved_accounts = Mock(return_value=[])
    store.is_seed_profile_complete = Mock(return_value=False)
    store.edge_summary_for_seed = Mock(return_value={
        "following": 0,
        "followers": 0,
        "total": 0,
    })
    store.upsert_accounts = Mock(return_value=0)
    store.upsert_edges = Mock(return_value=0)
    store.upsert_discoveries = Mock(return_value=0)
    store.record_scrape_metrics = Mock(return_value=1)
    store.get_last_scrape_metrics = Mock(return_value=None)  # No previous scrape by default
    return store


@pytest.fixture
def mock_enrichment_policy():
    """Create a mock enrichment policy with test-friendly defaults.

    Returns a policy that auto-confirms refreshes to avoid blocking on user input.
    Tests can override specific attributes as needed.

    Example:
        def test_policy_check(mock_enrichment_policy):
            mock_enrichment_policy.require_user_confirmation = True
            # Test code
    """
    policy = Mock()
    policy.list_refresh_days = 180
    policy.profile_refresh_days = 30
    policy.pct_delta_threshold = 0.5
    policy.require_user_confirmation = False  # Don't block on user input in tests
    policy.auto_confirm_rescrapes = True  # Always proceed in tests
    return policy


@pytest.fixture
def mock_enrichment_config():
    """Create a mock enrichment config with sensible defaults.

    Returns a config suitable for testing without actual Selenium/cookies.
    Tests can override specific attributes as needed.

    Example:
        def test_profile_only(mock_enrichment_config):
            mock_enrichment_config.profile_only = True
            # Test code
    """
    config = Mock()

    # Selenium settings
    config.selenium_cookies_path = Mock(exists=Mock(return_value=True))
    config.selenium_headless = True
    config.selenium_scroll_delay_min = 1.0
    config.selenium_scroll_delay_max = 2.0
    config.chrome_binary = None
    config.wait_for_manual_login = False

    # Enrichment mode flags
    config.include_followers = True
    config.include_following = True
    config.include_followers_you_follow = True
    config.profile_only = False
    config.profile_only_all = False

    # Confirmation and preview
    config.confirm_first_scrape = False
    config.preview_sample_size = 5

    # API settings
    config.bearer_token = None

    # Delay settings
    config.user_pause_seconds = 0.1
    config.action_delay_min = 1.0
    config.action_delay_max = 2.0

    return config


@pytest.fixture
def mock_selenium_worker():
    """Create a mock SeleniumWorker with stubs for common methods.

    Useful for testing enricher logic without actual browser automation.

    Example:
        def test_enrichment(mock_selenium_worker):
            from src.shadow.selenium_worker import UserListCapture
            mock_selenium_worker.fetch_following.return_value = UserListCapture(...)
            # Test code
    """
    worker = Mock()
    worker.fetch_following = Mock()
    worker.fetch_followers = Mock()
    worker.fetch_followers_you_follow = Mock()
    worker.fetch_profile_overview = Mock()
    worker.quit = Mock()
    return worker


# ==============================================================================
# Temporary Database Fixtures
# ==============================================================================

@pytest.fixture
def temp_cache_db():
    """Create a temporary SQLite database for cache testing.

    Returns a Path to a temporary .db file that will be cleaned up
    after the test completes.

    Example:
        def test_cache(temp_cache_db):
            from src.data.fetcher import CachedDataFetcher
            fetcher = CachedDataFetcher(cache_path=temp_cache_db)
            # Test code
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def temp_shadow_db():
    """Create a temporary SQLite database for shadow store testing.

    Returns a Path to a temporary .db file that will be cleaned up
    after the test completes.

    Example:
        def test_shadow_store(temp_shadow_db):
            from sqlalchemy import create_engine
            from src.data.shadow_store import ShadowStore
            engine = create_engine(f"sqlite:///{temp_shadow_db}")
            store = ShadowStore(engine)
            # Test code
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


# ==============================================================================
# Helper Fixtures for Common Test Data
# ==============================================================================

@pytest.fixture
def sample_seed_account():
    """Create a sample SeedAccount for testing.

    Example:
        def test_skip_logic(sample_seed_account):
            # sample_seed_account.account_id == "12345"
            # sample_seed_account.username == "testuser"
    """
    from src.shadow.enricher import SeedAccount
    return SeedAccount(account_id="12345", username="testuser")


@pytest.fixture
def sample_profile_overview():
    """Create a sample ProfileOverview for testing.

    Returns a ProfileOverview with realistic test data.
    """
    from src.shadow.selenium_worker import ProfileOverview
    return ProfileOverview(
        username="testuser",
        display_name="Test User",
        bio="Sample bio for testing",
        location="Test Location",
        website="https://example.com",
        followers_total=1000,
        following_total=500,
        profile_image_url="https://example.com/avatar.jpg",
        joined_date="2020-01-01",
    )


@pytest.fixture
def sample_captured_user():
    """Create a sample CapturedUser for testing.

    Returns a CapturedUser with realistic test data.
    """
    from src.shadow.selenium_worker import CapturedUser
    return CapturedUser(
        username="testuser",
        display_name="Test User",
        bio="Sample bio",
        website="https://example.com",
        profile_image_url="https://example.com/avatar.jpg",
        list_types=["followers"],
    )
