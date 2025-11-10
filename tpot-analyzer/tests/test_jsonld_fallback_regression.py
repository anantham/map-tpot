"""Regression tests for JSON-LD profile schema fallback parsing.

Tests ensure that profile metadata (followers, following, bio, location, website)
can be reliably extracted from Twitter's JSON-LD schema when visible DOM parsing fails.

These tests use realistic fixtures based on actual Twitter profile structures
to prevent regressions in the fallback parsing logic.
"""
from __future__ import annotations

import pytest

from src.shadow.selenium_worker import SeleniumWorker


# ==============================================================================
# Real-World Profile Fixtures
# ==============================================================================

@pytest.fixture
def profile_with_all_fields():
    """Complete profile with all optional fields populated."""
    return {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
        "dateCreated": "2009-11-11T19:54:16.000Z",
        "mainEntity": {
            "@type": "Person",
            "name": "Full Name",
            "additionalName": "fullname_user",
            "description": "This is a complete bio with all fields populated",
            "homeLocation": {"@type": "Place", "name": "San Francisco, CA"},
            "identifier": "123456789",
            "image": {
                "@type": "ImageObject",
                "contentUrl": "https://pbs.twimg.com/profile_images/123/photo.jpg",
            },
            "interactionStatistic": [
                {
                    "@type": "InteractionCounter",
                    "name": "Follows",
                    "userInteractionCount": 5432,
                },
                {
                    "@type": "InteractionCounter",
                    "name": "Friends",
                    "userInteractionCount": 1234,
                },
            ],
            "url": "https://x.com/fullname_user",
        },
        "relatedLink": ["https://example.com"],
    }


@pytest.fixture
def profile_minimal():
    """Minimal profile with only required fields."""
    return {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
        "mainEntity": {
            "@type": "Person",
            "additionalName": "minimal_user",
            "identifier": "987654321",
            "interactionStatistic": [
                {
                    "@type": "InteractionCounter",
                    "name": "Follows",
                    "userInteractionCount": 100,
                },
                {
                    "@type": "InteractionCounter",
                    "name": "Friends",
                    "userInteractionCount": 50,
                },
            ],
            "url": "https://x.com/minimal_user",
        },
    }


@pytest.fixture
def profile_with_missing_location():
    """Profile without location field."""
    return {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
        "mainEntity": {
            "@type": "Person",
            "additionalName": "no_location",
            "description": "Bio without location",
            "interactionStatistic": [
                {"@type": "InteractionCounter", "name": "Follows", "userInteractionCount": 200},
                {"@type": "InteractionCounter", "name": "Friends", "userInteractionCount": 100},
            ],
            "url": "https://x.com/no_location",
        },
    }


@pytest.fixture
def profile_with_high_counts():
    """Profile with very high follower/following counts (>1M)."""
    return {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
        "mainEntity": {
            "@type": "Person",
            "additionalName": "popular_user",
            "interactionStatistic": [
                {"@type": "InteractionCounter", "name": "Follows", "userInteractionCount": 2500000},
                {"@type": "InteractionCounter", "name": "Friends", "userInteractionCount": 5000},
            ],
            "url": "https://x.com/popular_user",
        },
    }


@pytest.fixture
def profile_with_multiple_websites():
    """Profile with multiple related links."""
    return {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
        "mainEntity": {
            "@type": "Person",
            "additionalName": "multilink_user",
            "interactionStatistic": [
                {"@type": "InteractionCounter", "name": "Follows", "userInteractionCount": 100},
                {"@type": "InteractionCounter", "name": "Friends", "userInteractionCount": 50},
            ],
            "url": "https://x.com/multilink_user",
        },
        "relatedLink": [
            "https://example.com",
            "https://another.com",
            "https://third-site.com",
        ],
    }


# ==============================================================================
# Test: Complete Profile Parsing
# ==============================================================================

@pytest.mark.unit
def test_parse_complete_profile(profile_with_all_fields):
    """Should parse all fields from a complete profile."""
    parsed = SeleniumWorker._parse_profile_schema_payload(
        profile_with_all_fields,
        target_username="fullname_user",
    )

    assert parsed is not None
    assert parsed["followers_total"] == 5432
    assert parsed["following_total"] == 1234
    assert parsed["bio"] == "This is a complete bio with all fields populated"
    assert parsed["location"] == "San Francisco, CA"
    assert parsed["website"] == "https://example.com"
    assert "profile_images/123/photo.jpg" in parsed["profile_image_url"]


@pytest.mark.unit
def test_parse_minimal_profile(profile_minimal):
    """Should parse minimal profile with only required fields."""
    parsed = SeleniumWorker._parse_profile_schema_payload(
        profile_minimal,
        target_username="minimal_user",
    )

    assert parsed is not None
    assert parsed["followers_total"] == 100
    assert parsed["following_total"] == 50
    # Optional fields should be None
    assert parsed.get("bio") is None
    assert parsed.get("location") is None
    assert parsed.get("website") is None


# ==============================================================================
# Test: Missing Optional Fields
# ==============================================================================

@pytest.mark.unit
def test_parse_profile_missing_location(profile_with_missing_location):
    """Should handle missing location gracefully."""
    parsed = SeleniumWorker._parse_profile_schema_payload(
        profile_with_missing_location,
        target_username="no_location",
    )

    assert parsed is not None
    assert parsed["followers_total"] == 200
    assert parsed["bio"] == "Bio without location"
    assert parsed.get("location") is None


@pytest.mark.unit
def test_parse_profile_missing_bio():
    """Should handle missing bio field."""
    payload = {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
        "mainEntity": {
            "@type": "Person",
            "additionalName": "no_bio",
            "interactionStatistic": [
                {"@type": "InteractionCounter", "name": "Follows", "userInteractionCount": 50},
                {"@type": "InteractionCounter", "name": "Friends", "userInteractionCount": 25},
            ],
            "url": "https://x.com/no_bio",
        },
    }

    parsed = SeleniumWorker._parse_profile_schema_payload(payload, target_username="no_bio")

    assert parsed is not None
    assert parsed.get("bio") is None


@pytest.mark.unit
def test_parse_profile_missing_image():
    """Should handle missing profile image."""
    payload = {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
        "mainEntity": {
            "@type": "Person",
            "additionalName": "no_image",
            "interactionStatistic": [
                {"@type": "InteractionCounter", "name": "Follows", "userInteractionCount": 10},
                {"@type": "InteractionCounter", "name": "Friends", "userInteractionCount": 5},
            ],
            "url": "https://x.com/no_image",
        },
    }

    parsed = SeleniumWorker._parse_profile_schema_payload(payload, target_username="no_image")

    assert parsed is not None
    assert parsed.get("profile_image_url") is None


# ==============================================================================
# Test: High Follower/Following Counts
# ==============================================================================

@pytest.mark.unit
def test_parse_profile_with_high_counts(profile_with_high_counts):
    """Should handle profiles with >1M followers."""
    parsed = SeleniumWorker._parse_profile_schema_payload(
        profile_with_high_counts,
        target_username="popular_user",
    )

    assert parsed is not None
    assert parsed["followers_total"] == 2500000  # 2.5M
    assert parsed["following_total"] == 5000


@pytest.mark.unit
def test_parse_profile_with_zero_counts():
    """Should handle profiles with zero followers/following."""
    payload = {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
        "mainEntity": {
            "@type": "Person",
            "additionalName": "new_user",
            "interactionStatistic": [
                {"@type": "InteractionCounter", "name": "Follows", "userInteractionCount": 0},
                {"@type": "InteractionCounter", "name": "Friends", "userInteractionCount": 0},
            ],
            "url": "https://x.com/new_user",
        },
    }

    parsed = SeleniumWorker._parse_profile_schema_payload(payload, target_username="new_user")

    assert parsed is not None
    assert parsed["followers_total"] == 0
    assert parsed["following_total"] == 0


# ==============================================================================
# Test: Multiple Websites
# ==============================================================================

@pytest.mark.unit
def test_parse_profile_with_multiple_websites(profile_with_multiple_websites):
    """Should take first website when multiple links present."""
    parsed = SeleniumWorker._parse_profile_schema_payload(
        profile_with_multiple_websites,
        target_username="multilink_user",
    )

    assert parsed is not None
    # Should take the first link
    assert parsed["website"] == "https://example.com"


@pytest.mark.unit
def test_parse_profile_with_empty_related_links():
    """Should handle empty relatedLink array."""
    payload = {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
        "mainEntity": {
            "@type": "Person",
            "additionalName": "no_links",
            "interactionStatistic": [
                {"@type": "InteractionCounter", "name": "Follows", "userInteractionCount": 10},
                {"@type": "InteractionCounter", "name": "Friends", "userInteractionCount": 5},
            ],
            "url": "https://x.com/no_links",
        },
        "relatedLink": [],
    }

    parsed = SeleniumWorker._parse_profile_schema_payload(payload, target_username="no_links")

    assert parsed is not None
    assert parsed.get("website") is None


# ==============================================================================
# Test: Username Mismatch
# ==============================================================================

@pytest.mark.unit
def test_parse_rejects_username_mismatch(profile_with_all_fields):
    """Should reject payload if username doesn't match target."""
    parsed = SeleniumWorker._parse_profile_schema_payload(
        profile_with_all_fields,
        target_username="different_user",
    )

    assert parsed is None


@pytest.mark.unit
def test_parse_username_case_insensitive(profile_with_all_fields):
    """Should match usernames case-insensitively."""
    parsed = SeleniumWorker._parse_profile_schema_payload(
        profile_with_all_fields,
        target_username="FULLNAME_USER",
    )

    assert parsed is not None
    assert parsed["followers_total"] == 5432


# ==============================================================================
# Test: Malformed Data
# ==============================================================================

@pytest.mark.unit
def test_parse_missing_main_entity():
    """Should return None if mainEntity is missing."""
    payload = {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
    }

    parsed = SeleniumWorker._parse_profile_schema_payload(payload, target_username="test")

    assert parsed is None


@pytest.mark.unit
def test_parse_missing_interaction_statistics():
    """Should return None if interactionStatistic is missing."""
    payload = {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
        "mainEntity": {
            "@type": "Person",
            "additionalName": "test_user",
            "url": "https://x.com/test_user",
        },
    }

    parsed = SeleniumWorker._parse_profile_schema_payload(payload, target_username="test_user")

    # Should return None because counts are required
    assert parsed is None


@pytest.mark.unit
def test_parse_incomplete_interaction_statistics():
    """Should return None if only one count type is present."""
    payload = {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
        "mainEntity": {
            "@type": "Person",
            "additionalName": "test_user",
            "interactionStatistic": [
                {"@type": "InteractionCounter", "name": "Follows", "userInteractionCount": 100},
                # Missing "Friends" counter
            ],
            "url": "https://x.com/test_user",
        },
    }

    parsed = SeleniumWorker._parse_profile_schema_payload(payload, target_username="test_user")

    # Should return None because both counts are required
    assert parsed is None


@pytest.mark.unit
def test_parse_invalid_count_format():
    """Should return None if interaction counts are non-numeric."""
    payload = {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
        "mainEntity": {
            "@type": "Person",
            "additionalName": "test_user",
            "interactionStatistic": [
                {"@type": "InteractionCounter", "name": "Follows", "userInteractionCount": "invalid"},
                {"@type": "InteractionCounter", "name": "Friends", "userInteractionCount": 100},
            ],
            "url": "https://x.com/test_user",
        },
    }

    parsed = SeleniumWorker._parse_profile_schema_payload(payload, target_username="test_user")

    # Should handle gracefully
    assert parsed is None or parsed["followers_total"] is None


# ==============================================================================
# Test: Special Characters in Fields
# ==============================================================================

@pytest.mark.unit
def test_parse_bio_with_special_characters():
    """Should handle bios with special characters, emoji, newlines."""
    payload = {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
        "mainEntity": {
            "@type": "Person",
            "additionalName": "emoji_user",
            "description": "I ❤️ coding! 🚀\nBuilding cool stuff 💻\n#developer #tech",
            "interactionStatistic": [
                {"@type": "InteractionCounter", "name": "Follows", "userInteractionCount": 100},
                {"@type": "InteractionCounter", "name": "Friends", "userInteractionCount": 50},
            ],
            "url": "https://x.com/emoji_user",
        },
    }

    parsed = SeleniumWorker._parse_profile_schema_payload(payload, target_username="emoji_user")

    assert parsed is not None
    assert "❤️" in parsed["bio"]
    assert "🚀" in parsed["bio"]
    assert "#developer" in parsed["bio"]


@pytest.mark.unit
def test_parse_location_with_unicode():
    """Should handle locations with unicode characters."""
    payload = {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
        "mainEntity": {
            "@type": "Person",
            "additionalName": "unicode_user",
            "homeLocation": {"@type": "Place", "name": "São Paulo, Brasil 🇧🇷"},
            "interactionStatistic": [
                {"@type": "InteractionCounter", "name": "Follows", "userInteractionCount": 100},
                {"@type": "InteractionCounter", "name": "Friends", "userInteractionCount": 50},
            ],
            "url": "https://x.com/unicode_user",
        },
    }

    parsed = SeleniumWorker._parse_profile_schema_payload(payload, target_username="unicode_user")

    assert parsed is not None
    assert parsed["location"] == "São Paulo, Brasil 🇧🇷"


# ==============================================================================
# Test: Edge Cases
# ==============================================================================

@pytest.mark.unit
def test_parse_empty_payload():
    """Should handle empty payload gracefully."""
    parsed = SeleniumWorker._parse_profile_schema_payload({}, target_username="test")

    assert parsed is None


@pytest.mark.unit
def test_parse_null_payload():
    """Should handle None payload gracefully."""
    parsed = SeleniumWorker._parse_profile_schema_payload(None, target_username="test")

    assert parsed is None


@pytest.mark.unit
def test_parse_very_long_bio():
    """Should handle very long bios (>1000 chars)."""
    long_bio = "A" * 2000
    payload = {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
        "mainEntity": {
            "@type": "Person",
            "additionalName": "long_bio",
            "description": long_bio,
            "interactionStatistic": [
                {"@type": "InteractionCounter", "name": "Follows", "userInteractionCount": 100},
                {"@type": "InteractionCounter", "name": "Friends", "userInteractionCount": 50},
            ],
            "url": "https://x.com/long_bio",
        },
    }

    parsed = SeleniumWorker._parse_profile_schema_payload(payload, target_username="long_bio")

    assert parsed is not None
    assert len(parsed["bio"]) == 2000
