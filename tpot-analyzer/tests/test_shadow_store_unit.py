"""Direct unit tests for shadow_store.py data layer (COALESCE upserts, edge aggregation, metrics conversion)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from src.data.shadow_store import (
    ScrapeRunMetrics,
    ShadowAccount,
    ShadowDiscovery,
    ShadowEdge,
    ShadowStore,
)


@pytest.fixture
def shadow_store(tmp_path: Path) -> ShadowStore:
    """In-memory SQLite shadow store for isolated testing."""
    db_path = tmp_path / "test_shadow.db"
    engine = create_engine(f"sqlite:///{db_path}")
    return ShadowStore(engine)


# ==============================================================================
# COALESCE Upsert Behavior Tests
# ==============================================================================
class TestCoalesceUpsertBehavior:
    """Test COALESCE upsert logic preserves existing non-null values."""

    def test_initial_insert_with_all_fields(self, shadow_store: ShadowStore):
        """Should insert new account with all fields populated."""
        account = ShadowAccount(
            account_id="shadow:12345",
            username="testuser",
            display_name="Test User",
            bio="Test bio",
            location="Test Location",
            website="https://test.com",
            profile_image_url="https://test.com/avatar.jpg",
            followers_count=100,
            following_count=200,
            source_channel="selenium",
            fetched_at=datetime(2025, 1, 1, 12, 0, 0),
        )

        count = shadow_store.upsert_accounts([account])
        assert count == 1

        # Verify all fields persisted
        accounts = shadow_store.fetch_accounts(["shadow:12345"])
        assert len(accounts) == 1
        assert accounts[0]["username"] == "testuser"
        assert accounts[0]["bio"] == "Test bio"
        assert accounts[0]["location"] == "Test Location"
        assert accounts[0]["website"] == "https://test.com"
        assert accounts[0]["followers_count"] == 100

    def test_upsert_with_none_preserves_existing(self, shadow_store: ShadowStore):
        """Should preserve existing non-null values when upserting with None."""
        # Initial insert with full data
        account1 = ShadowAccount(
            account_id="shadow:12345",
            username="testuser",
            display_name="Test User",
            bio="Original bio",
            location="Original Location",
            website="https://original.com",
            profile_image_url="https://original.com/avatar.jpg",
            followers_count=100,
            following_count=200,
            source_channel="selenium",
            fetched_at=datetime(2025, 1, 1, 12, 0, 0),
        )
        shadow_store.upsert_accounts([account1])

        # Upsert with some None values (simulating partial enrichment)
        account2 = ShadowAccount(
            account_id="shadow:12345",
            username="testuser",
            display_name="Test User",
            bio=None,  # Should preserve "Original bio"
            location=None,  # Should preserve "Original Location"
            website=None,  # Should preserve "https://original.com"
            profile_image_url="https://new.com/avatar.jpg",  # Should update
            followers_count=150,  # Should update
            following_count=250,  # Should update
            source_channel="selenium",
            fetched_at=datetime(2025, 1, 2, 12, 0, 0),
        )
        shadow_store.upsert_accounts([account2])

        # Verify COALESCE behavior: None values didn't overwrite existing
        accounts = shadow_store.fetch_accounts(["shadow:12345"])
        assert len(accounts) == 1
        assert accounts[0]["bio"] == "Original bio"  # Preserved
        assert accounts[0]["location"] == "Original Location"  # Preserved
        assert accounts[0]["website"] == "https://original.com"  # Preserved
        assert accounts[0]["profile_image_url"] == "https://new.com/avatar.jpg"  # Updated
        assert accounts[0]["followers_count"] == 150  # Updated
        assert accounts[0]["following_count"] == 250  # Updated

    def test_upsert_with_new_values_replaces_existing(self, shadow_store: ShadowStore):
        """Should replace existing values when upserting with new non-null values."""
        # Initial insert
        account1 = ShadowAccount(
            account_id="shadow:12345",
            username="olduser",
            display_name="Old Name",
            bio="Old bio",
            location="Old Location",
            website=None,
            profile_image_url=None,
            followers_count=100,
            following_count=200,
            source_channel="selenium",
            fetched_at=datetime(2025, 1, 1, 12, 0, 0),
        )
        shadow_store.upsert_accounts([account1])

        # Upsert with new non-null values
        account2 = ShadowAccount(
            account_id="shadow:12345",
            username="newuser",
            display_name="New Name",
            bio="New bio",
            location="New Location",
            website="https://new.com",
            profile_image_url="https://new.com/avatar.jpg",
            followers_count=300,
            following_count=400,
            source_channel="x_api",
            fetched_at=datetime(2025, 1, 2, 12, 0, 0),
        )
        shadow_store.upsert_accounts([account2])

        # Verify all new values replaced old
        accounts = shadow_store.fetch_accounts(["shadow:12345"])
        assert len(accounts) == 1
        assert accounts[0]["username"] == "newuser"
        assert accounts[0]["display_name"] == "New Name"
        assert accounts[0]["bio"] == "New bio"
        assert accounts[0]["location"] == "New Location"
        assert accounts[0]["website"] == "https://new.com"
        assert accounts[0]["profile_image_url"] == "https://new.com/avatar.jpg"
        assert accounts[0]["followers_count"] == 300


# ==============================================================================
# Edge Summary Aggregation Tests
# ==============================================================================
class TestEdgeSummaryAggregation:
    """Test edge_summary_for_seed correctly counts following/followers."""

    def test_following_edges_counted_correctly(self, shadow_store: ShadowStore):
        """Should count following edges where source=seed and list_type=following."""
        seed_id = "shadow:seed1"

        # Insert following edges (seed follows others)
        following_edges = [
            ShadowEdge(
                source_id=seed_id,
                target_id=f"shadow:user{i}",
                direction="following",
                source_channel="selenium",
                fetched_at=datetime(2025, 1, 1, 12, 0, 0),
                metadata={"list_type": "following"},
            )
            for i in range(5)
        ]
        shadow_store.upsert_edges(following_edges)

        summary = shadow_store.edge_summary_for_seed(seed_id)
        assert summary["following"] == 5
        assert summary["followers"] == 0
        assert summary["total"] == 5

    def test_follower_edges_counted_correctly(self, shadow_store: ShadowStore):
        """Should count follower edges where target=seed and list_type=followers."""
        seed_id = "shadow:seed1"

        # Insert follower edges (others follow seed)
        follower_edges = [
            ShadowEdge(
                source_id=f"shadow:user{i}",
                target_id=seed_id,
                direction="followers",
                source_channel="selenium",
                fetched_at=datetime(2025, 1, 1, 12, 0, 0),
                metadata={"list_type": "followers"},
            )
            for i in range(3)
        ]
        shadow_store.upsert_edges(follower_edges)

        summary = shadow_store.edge_summary_for_seed(seed_id)
        assert summary["following"] == 0
        assert summary["followers"] == 3
        assert summary["total"] == 3

    def test_mixed_edges_aggregated_correctly(self, shadow_store: ShadowStore):
        """Should correctly aggregate both following and follower edges."""
        seed_id = "shadow:seed1"

        # Insert following edges
        following_edges = [
            ShadowEdge(
                source_id=seed_id,
                target_id=f"shadow:following{i}",
                direction="following",
                source_channel="selenium",
                fetched_at=datetime(2025, 1, 1, 12, 0, 0),
                metadata={"list_type": "following"},
            )
            for i in range(10)
        ]

        # Insert follower edges
        follower_edges = [
            ShadowEdge(
                source_id=f"shadow:follower{i}",
                target_id=seed_id,
                direction="followers",
                source_channel="selenium",
                fetched_at=datetime(2025, 1, 1, 12, 0, 0),
                metadata={"list_type": "followers"},
            )
            for i in range(7)
        ]

        shadow_store.upsert_edges(following_edges + follower_edges)

        summary = shadow_store.edge_summary_for_seed(seed_id)
        assert summary["following"] == 10
        assert summary["followers"] == 7
        assert summary["total"] == 17

    def test_edges_without_list_type_ignored(self, shadow_store: ShadowStore):
        """Should not count edges without list_type metadata."""
        seed_id = "shadow:seed1"

        # Insert edges without list_type
        edges = [
            ShadowEdge(
                source_id=seed_id,
                target_id=f"shadow:user{i}",
                direction="following",
                source_channel="selenium",
                fetched_at=datetime(2025, 1, 1, 12, 0, 0),
                metadata={},  # No list_type
            )
            for i in range(3)
        ]
        shadow_store.upsert_edges(edges)

        summary = shadow_store.edge_summary_for_seed(seed_id)
        assert summary["following"] == 0
        assert summary["followers"] == 0
        assert summary["total"] == 3  # Total still counts all edges


# ==============================================================================
# Coverage Percentage Conversion Tests
# ==============================================================================
class TestCoveragePercentageConversion:
    """Test metrics coverage percentage conversion (float ↔ int * 10000)."""

    def test_zero_coverage_persisted_correctly(self, shadow_store: ShadowStore):
        """Should correctly store and retrieve 0.0 coverage (not treated as None)."""
        metrics = ScrapeRunMetrics(
            seed_account_id="shadow:seed1",
            seed_username="testuser",
            run_at=datetime(2025, 1, 1, 12, 0, 0),
            duration_seconds=60.0,
            following_captured=0,
            followers_captured=0,
            followers_you_follow_captured=0,
            following_claimed_total=100,
            followers_claimed_total=100,
            followers_you_follow_claimed_total=100,
            following_coverage=0.0,  # Explicit zero
            followers_coverage=0.0,
            followers_you_follow_coverage=0.0,
            accounts_upserted=0,
            edges_upserted=0,
            discoveries_upserted=0,
        )

        shadow_store.record_scrape_metrics(metrics)
        retrieved = shadow_store.get_last_scrape_metrics("shadow:seed1")

        assert retrieved is not None
        assert retrieved.following_coverage == 0.0
        assert retrieved.followers_coverage == 0.0
        assert retrieved.followers_you_follow_coverage == 0.0

    def test_partial_coverage_conversion_accurate(self, shadow_store: ShadowStore):
        """Should accurately convert partial coverage percentages (0.5 = 50%)."""
        metrics = ScrapeRunMetrics(
            seed_account_id="shadow:seed1",
            seed_username="testuser",
            run_at=datetime(2025, 1, 1, 12, 0, 0),
            duration_seconds=60.0,
            following_captured=50,
            followers_captured=75,
            followers_you_follow_captured=25,
            following_claimed_total=100,
            followers_claimed_total=100,
            followers_you_follow_claimed_total=100,
            following_coverage=0.5,  # 50%
            followers_coverage=0.75,  # 75%
            followers_you_follow_coverage=0.25,  # 25%
            accounts_upserted=100,
            edges_upserted=125,
            discoveries_upserted=125,
        )

        shadow_store.record_scrape_metrics(metrics)
        retrieved = shadow_store.get_last_scrape_metrics("shadow:seed1")

        assert retrieved is not None
        assert retrieved.following_coverage == 0.5
        assert retrieved.followers_coverage == 0.75
        assert retrieved.followers_you_follow_coverage == 0.25

    def test_full_coverage_conversion(self, shadow_store: ShadowStore):
        """Should correctly store and retrieve 1.0 (100%) coverage."""
        metrics = ScrapeRunMetrics(
            seed_account_id="shadow:seed1",
            seed_username="testuser",
            run_at=datetime(2025, 1, 1, 12, 0, 0),
            duration_seconds=60.0,
            following_captured=100,
            followers_captured=100,
            followers_you_follow_captured=100,
            following_claimed_total=100,
            followers_claimed_total=100,
            followers_you_follow_claimed_total=100,
            following_coverage=1.0,
            followers_coverage=1.0,
            followers_you_follow_coverage=1.0,
            accounts_upserted=200,
            edges_upserted=200,
            discoveries_upserted=200,
        )

        shadow_store.record_scrape_metrics(metrics)
        retrieved = shadow_store.get_last_scrape_metrics("shadow:seed1")

        assert retrieved is not None
        assert retrieved.following_coverage == 1.0
        assert retrieved.followers_coverage == 1.0
        assert retrieved.followers_you_follow_coverage == 1.0

    def test_none_coverage_preserved(self, shadow_store: ShadowStore):
        """Should preserve None coverage when claimed_total is unavailable."""
        metrics = ScrapeRunMetrics(
            seed_account_id="shadow:seed1",
            seed_username="testuser",
            run_at=datetime(2025, 1, 1, 12, 0, 0),
            duration_seconds=60.0,
            following_captured=10,
            followers_captured=20,
            followers_you_follow_captured=5,
            following_claimed_total=None,
            followers_claimed_total=None,
            followers_you_follow_claimed_total=None,
            following_coverage=None,
            followers_coverage=None,
            followers_you_follow_coverage=None,
            accounts_upserted=30,
            edges_upserted=30,
            discoveries_upserted=30,
        )

        shadow_store.record_scrape_metrics(metrics)
        retrieved = shadow_store.get_last_scrape_metrics("shadow:seed1")

        assert retrieved is not None
        assert retrieved.following_coverage is None
        assert retrieved.followers_coverage is None
        assert retrieved.followers_you_follow_coverage is None


# ==============================================================================
# Retry Logic Tests
# ==============================================================================
class TestRetryLogic:
    """Test _execute_with_retry handles transient SQLite errors."""

    def test_retryable_disk_io_error_retries_and_succeeds(self, shadow_store: ShadowStore):
        """Should retry on 'disk i/o error' and succeed on subsequent attempt."""
        call_count = 0

        def failing_then_succeeding_op(engine):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Simulate transient disk I/O error
                exc = OperationalError("statement", {}, Exception("disk i/o error"))
                raise exc
            return "success"

        with patch('time.sleep'):  # Mock sleep to speed up test
            result = shadow_store._execute_with_retry("test_op", failing_then_succeeding_op)

        assert result == "success"
        assert call_count == 2  # Failed once, succeeded on retry

    def test_retryable_database_locked_error_retries(self, shadow_store: ShadowStore):
        """Should retry on 'database is locked' error."""
        call_count = 0

        def locked_then_succeeding_op(engine):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                exc = OperationalError("statement", {}, Exception("database is locked"))
                raise exc
            return "unlocked"

        with patch('time.sleep'):
            result = shadow_store._execute_with_retry("test_op", locked_then_succeeding_op)

        assert result == "unlocked"
        assert call_count == 3  # Failed twice, succeeded on third attempt

    def test_non_retryable_error_raises_immediately(self, shadow_store: ShadowStore):
        """Should not retry on non-retryable errors (e.g., syntax errors)."""
        call_count = 0

        def non_retryable_op(engine):
            nonlocal call_count
            call_count += 1
            exc = OperationalError("statement", {}, Exception("syntax error near SELECT"))
            raise exc

        with pytest.raises(OperationalError, match="syntax error"):
            shadow_store._execute_with_retry("test_op", non_retryable_op)

        assert call_count == 1  # No retries, raised immediately

    def test_exhausted_retries_raises_last_exception(self, shadow_store: ShadowStore):
        """Should raise last exception after exhausting max_attempts."""
        call_count = 0

        def always_failing_op(engine):
            nonlocal call_count
            call_count += 1
            exc = OperationalError("statement", {}, Exception("disk i/o error"))
            raise exc

        with patch('time.sleep'):
            with pytest.raises(OperationalError, match="disk i/o error"):
                shadow_store._execute_with_retry("test_op", always_failing_op, max_attempts=3)

        assert call_count == 3  # Tried 3 times, then raised


# ==============================================================================
# Profile Completeness Tests
# ==============================================================================
class TestProfileCompleteness:
    """Test is_seed_profile_complete logic for location AND (website OR joined) AND avatar AND counts."""

    def test_complete_profile_with_website(self, shadow_store: ShadowStore):
        """Should return True for profile with location + website + avatar + counts."""
        account = ShadowAccount(
            account_id="shadow:seed1",
            username="testuser",
            display_name="Test User",
            bio="Bio",
            location="San Francisco",
            website="https://test.com",
            profile_image_url="https://test.com/avatar.jpg",
            followers_count=100,
            following_count=200,
            source_channel="selenium",
            fetched_at=datetime(2025, 1, 1, 12, 0, 0),
        )
        shadow_store.upsert_accounts([account])

        assert shadow_store.is_seed_profile_complete("shadow:seed1") is True

    def test_complete_profile_with_joined_date(self, shadow_store: ShadowStore):
        """Should return True for profile with location + joined_date + avatar + counts."""
        account = ShadowAccount(
            account_id="shadow:seed1",
            username="testuser",
            display_name="Test User",
            bio="Bio",
            location="New York",
            website=None,  # No website
            profile_image_url="https://test.com/avatar.jpg",
            followers_count=100,
            following_count=200,
            source_channel="selenium",
            fetched_at=datetime(2025, 1, 1, 12, 0, 0),
            scrape_stats={"joined_date": "2020-01-01"},  # Has joined_date
        )
        shadow_store.upsert_accounts([account])

        assert shadow_store.is_seed_profile_complete("shadow:seed1") is True

    def test_incomplete_profile_missing_location(self, shadow_store: ShadowStore):
        """Should return False when location is missing."""
        account = ShadowAccount(
            account_id="shadow:seed1",
            username="testuser",
            display_name="Test User",
            bio="Bio",
            location=None,  # Missing location
            website="https://test.com",
            profile_image_url="https://test.com/avatar.jpg",
            followers_count=100,
            following_count=200,
            source_channel="selenium",
            fetched_at=datetime(2025, 1, 1, 12, 0, 0),
        )
        shadow_store.upsert_accounts([account])

        assert shadow_store.is_seed_profile_complete("shadow:seed1") is False

    def test_incomplete_profile_missing_website_and_joined(self, shadow_store: ShadowStore):
        """Should return False when both website AND joined_date are missing."""
        account = ShadowAccount(
            account_id="shadow:seed1",
            username="testuser",
            display_name="Test User",
            bio="Bio",
            location="Boston",
            website=None,  # No website
            profile_image_url="https://test.com/avatar.jpg",
            followers_count=100,
            following_count=200,
            source_channel="selenium",
            fetched_at=datetime(2025, 1, 1, 12, 0, 0),
            scrape_stats={},  # No joined_date
        )
        shadow_store.upsert_accounts([account])

        assert shadow_store.is_seed_profile_complete("shadow:seed1") is False

    def test_incomplete_profile_missing_avatar(self, shadow_store: ShadowStore):
        """Should return False when profile_image_url is missing."""
        account = ShadowAccount(
            account_id="shadow:seed1",
            username="testuser",
            display_name="Test User",
            bio="Bio",
            location="Seattle",
            website="https://test.com",
            profile_image_url=None,  # Missing avatar
            followers_count=100,
            following_count=200,
            source_channel="selenium",
            fetched_at=datetime(2025, 1, 1, 12, 0, 0),
        )
        shadow_store.upsert_accounts([account])

        assert shadow_store.is_seed_profile_complete("shadow:seed1") is False

    def test_incomplete_profile_zero_counts(self, shadow_store: ShadowStore):
        """Should return False when followers_count or following_count is zero."""
        account = ShadowAccount(
            account_id="shadow:seed1",
            username="testuser",
            display_name="Test User",
            bio="Bio",
            location="Austin",
            website="https://test.com",
            profile_image_url="https://test.com/avatar.jpg",
            followers_count=0,  # Zero counts
            following_count=0,
            source_channel="selenium",
            fetched_at=datetime(2025, 1, 1, 12, 0, 0),
        )
        shadow_store.upsert_accounts([account])

        assert shadow_store.is_seed_profile_complete("shadow:seed1") is False

    def test_nonexistent_account_returns_false(self, shadow_store: ShadowStore):
        """Should return False for accounts that don't exist."""
        assert shadow_store.is_seed_profile_complete("shadow:nonexistent") is False


# ==============================================================================
# Edge Operations Tests
# ==============================================================================
class TestEdgeOperations:
    """Test edge upsert and fetch operations."""

    def test_upsert_edges_with_composite_key(self, shadow_store: ShadowStore):
        """Should handle edges with composite primary key (source, target, direction)."""
        edge1 = ShadowEdge(
            source_id="shadow:user1",
            target_id="shadow:user2",
            direction="following",
            source_channel="selenium",
            fetched_at=datetime(2025, 1, 1, 12, 0, 0),
            metadata={"list_type": "following"},
        )
        shadow_store.upsert_edges([edge1])

        # Upsert same edge with updated metadata
        edge2 = ShadowEdge(
            source_id="shadow:user1",
            target_id="shadow:user2",
            direction="following",
            source_channel="x_api",
            fetched_at=datetime(2025, 1, 2, 12, 0, 0),
            metadata={"list_type": "following", "weight": 5},
        )
        shadow_store.upsert_edges([edge2])

        edges = shadow_store.fetch_edges()
        assert len(edges) == 1  # Only one edge (upserted)
        assert edges[0]["source_channel"] == "x_api"  # Updated
        assert edges[0]["metadata"]["weight"] == 5

    def test_fetch_edges_filtered_by_direction(self, shadow_store: ShadowStore):
        """Should filter edges by direction."""
        following_edge = ShadowEdge(
            source_id="shadow:user1",
            target_id="shadow:user2",
            direction="following",
            source_channel="selenium",
            fetched_at=datetime(2025, 1, 1, 12, 0, 0),
        )
        follower_edge = ShadowEdge(
            source_id="shadow:user3",
            target_id="shadow:user1",
            direction="followers",
            source_channel="selenium",
            fetched_at=datetime(2025, 1, 1, 12, 0, 0),
        )
        shadow_store.upsert_edges([following_edge, follower_edge])

        following_edges = shadow_store.fetch_edges(direction="following")
        assert len(following_edges) == 1
        assert following_edges[0]["direction"] == "following"

        follower_edges = shadow_store.fetch_edges(direction="followers")
        assert len(follower_edges) == 1
        assert follower_edges[0]["direction"] == "followers"

    def test_upsert_edges_returns_accurate_new_count(self, shadow_store: ShadowStore):
        """Should return count of only NEW edges inserted, not duplicates."""
        # First insert: 10 new edges
        edges_batch1 = [
            ShadowEdge(
                source_id="shadow:seed1",
                target_id=f"shadow:user{i}",
                direction="following",
                source_channel="selenium",
                fetched_at=datetime(2025, 1, 1, 12, 0, 0),
                metadata={"list_type": "following"},
            )
            for i in range(10)
        ]
        new_count = shadow_store.upsert_edges(edges_batch1)
        assert new_count == 10, "First insert should report 10 new edges"

        # Second insert: same 10 edges (all duplicates)
        new_count = shadow_store.upsert_edges(edges_batch1)
        assert new_count == 0, "Re-inserting same edges should report 0 new edges"

        # Third insert: 5 existing + 5 new (mixed)
        edges_batch2 = [
            ShadowEdge(
                source_id="shadow:seed1",
                target_id=f"shadow:user{i}",
                direction="following",
                source_channel="selenium",
                fetched_at=datetime(2025, 1, 2, 12, 0, 0),
                metadata={"list_type": "following"},
            )
            for i in range(5, 15)  # user5-user9 exist, user10-user14 are new
        ]
        new_count = shadow_store.upsert_edges(edges_batch2)
        assert new_count == 5, "Mixed batch should report only 5 new edges"

        # Verify total edges in DB is correct
        all_edges = shadow_store.fetch_edges()
        assert len(all_edges) == 15, "Should have 15 total unique edges"

    def test_upsert_edges_new_count_with_different_directions(self, shadow_store: ShadowStore):
        """Should treat same source/target with different direction as separate edges."""
        # Insert following edge
        following_edge = ShadowEdge(
            source_id="shadow:user1",
            target_id="shadow:user2",
            direction="following",
            source_channel="selenium",
            fetched_at=datetime(2025, 1, 1, 12, 0, 0),
        )
        new_count = shadow_store.upsert_edges([following_edge])
        assert new_count == 1

        # Insert reverse followers edge (different direction, should be NEW)
        followers_edge = ShadowEdge(
            source_id="shadow:user1",
            target_id="shadow:user2",
            direction="followers",
            source_channel="selenium",
            fetched_at=datetime(2025, 1, 1, 12, 0, 0),
        )
        new_count = shadow_store.upsert_edges([followers_edge])
        assert new_count == 1, "Different direction should count as new edge"

        # Re-insert following edge (should be duplicate)
        new_count = shadow_store.upsert_edges([following_edge])
        assert new_count == 0, "Re-inserting same edge should count as duplicate"

        # Verify we have 2 distinct edges
        all_edges = shadow_store.fetch_edges()
        assert len(all_edges) == 2


# ==============================================================================
# Discovery Operations Tests
# ==============================================================================
class TestDiscoveryOperations:
    """Test discovery upsert and fetch operations."""

    def test_upsert_discoveries_with_composite_key(self, shadow_store: ShadowStore):
        """Should handle discoveries with composite primary key."""
        discovery1 = ShadowDiscovery(
            shadow_account_id="shadow:discovered1",
            seed_account_id="shadow:seed1",
            discovered_at=datetime(2025, 1, 1, 12, 0, 0),
            discovery_method="following",
        )
        shadow_store.upsert_discoveries([discovery1])

        # Upsert same discovery with updated method
        discovery2 = ShadowDiscovery(
            shadow_account_id="shadow:discovered1",
            seed_account_id="shadow:seed1",
            discovered_at=datetime(2025, 1, 2, 12, 0, 0),
            discovery_method="followers",
        )
        shadow_store.upsert_discoveries([discovery2])

        discoveries = shadow_store.fetch_discoveries()
        assert len(discoveries) == 1
        assert discoveries[0]["discovery_method"] == "followers"  # Updated

    def test_fetch_discoveries_by_shadow_account(self, shadow_store: ShadowStore):
        """Should filter discoveries by shadow_account_id."""
        discovery1 = ShadowDiscovery(
            shadow_account_id="shadow:discovered1",
            seed_account_id="shadow:seed1",
            discovered_at=datetime(2025, 1, 1, 12, 0, 0),
            discovery_method="following",
        )
        discovery2 = ShadowDiscovery(
            shadow_account_id="shadow:discovered2",
            seed_account_id="shadow:seed1",
            discovered_at=datetime(2025, 1, 1, 12, 0, 0),
            discovery_method="followers",
        )
        shadow_store.upsert_discoveries([discovery1, discovery2])

        discoveries = shadow_store.fetch_discoveries(shadow_account_id="shadow:discovered1")
        assert len(discoveries) == 1
        assert discoveries[0]["shadow_account_id"] == "shadow:discovered1"

    def test_fetch_discoveries_by_seed_account(self, shadow_store: ShadowStore):
        """Should filter discoveries by seed_account_id."""
        discovery1 = ShadowDiscovery(
            shadow_account_id="shadow:discovered1",
            seed_account_id="shadow:seed1",
            discovered_at=datetime(2025, 1, 1, 12, 0, 0),
            discovery_method="following",
        )
        discovery2 = ShadowDiscovery(
            shadow_account_id="shadow:discovered1",
            seed_account_id="shadow:seed2",
            discovered_at=datetime(2025, 1, 1, 12, 0, 0),
            discovery_method="followers",
        )
        shadow_store.upsert_discoveries([discovery1, discovery2])

        discoveries = shadow_store.fetch_discoveries(seed_account_id="shadow:seed1")
        assert len(discoveries) == 1
        assert discoveries[0]["seed_account_id"] == "shadow:seed1"
