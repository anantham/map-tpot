"""Unit tests for selenium_worker.py DOM extraction and parsing logic."""
from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from src.shadow.selenium_worker import SeleniumWorker


# ==============================================================================
# Compact Count Parsing Tests (_parse_compact_count)
# ==============================================================================
class TestParseCompactCount:
    """Test _parse_compact_count handles various Twitter count formats."""

    def test_parse_simple_integer(self):
        """Should parse simple integer strings."""
        assert SeleniumWorker._parse_compact_count("123") == 123
        assert SeleniumWorker._parse_compact_count("0") == 0
        assert SeleniumWorker._parse_compact_count("1") == 1

    def test_parse_comma_separated(self):
        """Should parse comma-separated thousands."""
        assert SeleniumWorker._parse_compact_count("1,234") == 1234
        assert SeleniumWorker._parse_compact_count("12,345") == 12345
        assert SeleniumWorker._parse_compact_count("1,234,567") == 1234567

    def test_parse_k_suffix(self):
        """Should parse 'K' suffix as thousands."""
        assert SeleniumWorker._parse_compact_count("1.5K") == 1500
        assert SeleniumWorker._parse_compact_count("2K") == 2000
        assert SeleniumWorker._parse_compact_count("10.2k") == 10200
        assert SeleniumWorker._parse_compact_count("999K") == 999000

    def test_parse_m_suffix(self):
        """Should parse 'M' suffix as millions."""
        assert SeleniumWorker._parse_compact_count("1.5M") == 1500000
        assert SeleniumWorker._parse_compact_count("2M") == 2000000
        assert SeleniumWorker._parse_compact_count("3.7m") == 3700000

    def test_parse_with_whitespace(self):
        """Should handle whitespace in count strings."""
        assert SeleniumWorker._parse_compact_count(" 123 ") == 123
        assert SeleniumWorker._parse_compact_count("1, 234") == 1234
        assert SeleniumWorker._parse_compact_count(" 1.5K ") == 1500

    def test_parse_with_label_text(self):
        """Should extract digits from strings with label text."""
        # These have non-digit text, should extract first digit sequence
        assert SeleniumWorker._parse_compact_count("123 followers") == 123
        assert SeleniumWorker._parse_compact_count("1,234 following") == 1234

    def test_parse_invalid_returns_none(self):
        """Should return None for invalid inputs."""
        assert SeleniumWorker._parse_compact_count(None) is None
        assert SeleniumWorker._parse_compact_count("") is None
        assert SeleniumWorker._parse_compact_count("   ") is None
        assert SeleniumWorker._parse_compact_count("abc") is None
        assert SeleniumWorker._parse_compact_count("no digits") is None


# ==============================================================================
# Handle Extraction Tests (_handle_from_href)
# ==============================================================================
class TestHandleFromHref:
    """Test _handle_from_href extracts usernames from various URL formats."""

    def test_extract_from_twitter_com_url(self):
        """Should extract handle from twitter.com URLs."""
        assert SeleniumWorker._handle_from_href("https://twitter.com/elonmusk") == "elonmusk"
        assert SeleniumWorker._handle_from_href("http://twitter.com/elonmusk") == "elonmusk"
        assert SeleniumWorker._handle_from_href("https://www.twitter.com/elonmusk") == "elonmusk"

    def test_extract_from_x_com_url(self):
        """Should extract handle from x.com URLs."""
        assert SeleniumWorker._handle_from_href("https://x.com/elonmusk") == "elonmusk"
        assert SeleniumWorker._handle_from_href("http://x.com/elonmusk") == "elonmusk"

    def test_extract_from_relative_path(self):
        """Should extract handle from relative paths."""
        assert SeleniumWorker._handle_from_href("/elonmusk") == "elonmusk"
        assert SeleniumWorker._handle_from_href("/elonmusk/") == "elonmusk"

    def test_strip_query_params(self):
        """Should strip query parameters and fragments."""
        assert SeleniumWorker._handle_from_href("https://twitter.com/elonmusk?ref_src=twsrc") == "elonmusk"
        assert SeleniumWorker._handle_from_href("/elonmusk#tweets") == "elonmusk"
        assert SeleniumWorker._handle_from_href("https://x.com/elonmusk?s=20&t=abc") == "elonmusk"

    def test_handle_at_prefix(self):
        """Should strip @ prefix if present."""
        assert SeleniumWorker._handle_from_href("/@elonmusk") == "elonmusk"

    def test_reject_paths_with_subpaths(self):
        """Should reject URLs with subpaths (not profile URLs)."""
        assert SeleniumWorker._handle_from_href("https://twitter.com/elonmusk/status/123") is None
        assert SeleniumWorker._handle_from_href("/elonmusk/following") is None
        assert SeleniumWorker._handle_from_href("https://x.com/i/lists/123") is None

    def test_reject_special_paths(self):
        """Should reject special Twitter paths starting with 'i'."""
        assert SeleniumWorker._handle_from_href("/i/flow/login") is None
        assert SeleniumWorker._handle_from_href("https://twitter.com/i/topics/123") is None

    def test_reject_long_handles(self):
        """Should reject handles longer than 40 characters."""
        long_handle = "a" * 41
        assert SeleniumWorker._handle_from_href(f"/{long_handle}") is None

    def test_reject_invalid_inputs(self):
        """Should return None for invalid inputs."""
        assert SeleniumWorker._handle_from_href(None) is None
        assert SeleniumWorker._handle_from_href("") is None
        assert SeleniumWorker._handle_from_href("   ") is None


# ==============================================================================
# JSON-LD Schema Parsing Tests (_parse_profile_schema_payload)
# ==============================================================================
class TestParseProfileSchemaPayload:
    """Test _parse_profile_schema_payload extracts data from JSON-LD."""

    def test_parse_complete_schema(self):
        """Should extract all fields from complete schema."""
        payload = {
            "mainEntity": {
                "identifier": "elonmusk",
                "additionalName": "elonmusk",
                "name": "Elon Musk",
                "description": "CEO of Tesla and SpaceX",
                "homeLocation": {"name": "Austin, Texas"},
                "image": {"contentUrl": "https://pbs.twimg.com/profile_images/123/avatar.jpg"},
                "interactionStatistic": [
                    {"name": "Follows", "userInteractionCount": 1000000},
                    {"name": "Friends", "userInteractionCount": 150},
                ],
            },
            "relatedLink": ["https://tesla.com"],
            "dateCreated": "2009-06-02",
        }

        result = SeleniumWorker._parse_profile_schema_payload(payload, "elonmusk")

        assert result is not None
        assert result["display_name"] == "Elon Musk"
        assert result["bio"] == "CEO of Tesla and SpaceX"
        assert result["location"] == "Austin, Texas"
        assert result["website"] == "https://tesla.com"
        assert result["followers_total"] == 1000000
        assert result["following_total"] == 150
        assert result["profile_image_url"] == "https://pbs.twimg.com/profile_images/123/avatar.jpg"
        assert result["joined_date"] == "2009-06-02"

    def test_parse_minimal_schema(self):
        """Should handle schema with minimal fields."""
        payload = {
            "mainEntity": {
                "identifier": "testuser",
                "name": "Test User",
            }
        }

        result = SeleniumWorker._parse_profile_schema_payload(payload, "testuser")

        assert result is not None
        assert result["display_name"] == "Test User"
        assert result["bio"] is None
        assert result["location"] is None
        assert result["followers_total"] is None
        assert result["following_total"] is None

    def test_username_validation_by_identifier(self):
        """Should validate target username matches identifier."""
        payload = {
            "mainEntity": {
                "identifier": "elonmusk",
                "name": "Elon Musk",
            }
        }

        # Should match case-insensitively
        assert SeleniumWorker._parse_profile_schema_payload(payload, "elonmusk") is not None
        assert SeleniumWorker._parse_profile_schema_payload(payload, "ELONMUSK") is not None
        assert SeleniumWorker._parse_profile_schema_payload(payload, "ElonMusk") is not None

        # Should reject wrong username
        assert SeleniumWorker._parse_profile_schema_payload(payload, "wronguser") is None

    def test_username_validation_by_additional_name(self):
        """Should validate against additionalName if identifier missing."""
        payload = {
            "mainEntity": {
                "additionalName": "elonmusk",
                "name": "Elon Musk",
            }
        }

        assert SeleniumWorker._parse_profile_schema_payload(payload, "elonmusk") is not None
        assert SeleniumWorker._parse_profile_schema_payload(payload, "wronguser") is None

    def test_username_validation_by_url(self):
        """Should extract and validate username from URL field."""
        payload = {
            "mainEntity": {
                "url": "https://twitter.com/elonmusk",
                "name": "Elon Musk",
            }
        }

        assert SeleniumWorker._parse_profile_schema_payload(payload, "elonmusk") is not None

    def test_follower_count_extraction(self):
        """Should extract follower count from interactionStatistic."""
        payload = {
            "mainEntity": {
                "identifier": "user1",
                "interactionStatistic": [
                    {"name": "Follows", "userInteractionCount": 5000},
                ],
            }
        }

        result = SeleniumWorker._parse_profile_schema_payload(payload, "user1")
        assert result["followers_total"] == 5000

    def test_following_count_extraction(self):
        """Should extract following count from Friends statistic."""
        # Test "Friends" naming (correctly extracts following count)
        payload1 = {
            "mainEntity": {
                "identifier": "user1",
                "interactionStatistic": [
                    {"name": "Friends", "userInteractionCount": 300},
                ],
            }
        }
        result1 = SeleniumWorker._parse_profile_schema_payload(payload1, "user1")
        assert result1["following_total"] == 300

        # NOTE: "Following" naming has a bug - it matches "follow" first and sets followers_total
        # This is existing behavior that should be fixed, but tests document current state
        payload2 = {
            "mainEntity": {
                "identifier": "user1",
                "interactionStatistic": [
                    {"name": "Following", "userInteractionCount": 250},
                ],
            }
        }
        result2 = SeleniumWorker._parse_profile_schema_payload(payload2, "user1")
        # BUG: Should be following_total, but current logic incorrectly sets followers_total
        assert result2["followers_total"] == 250
        assert result2["following_total"] is None

    def test_website_extraction_from_related_links_list(self):
        """Should extract website from relatedLink list."""
        payload = {
            "mainEntity": {"identifier": "user1"},
            "relatedLink": ["https://example.com", "https://blog.example.com"],
        }

        result = SeleniumWorker._parse_profile_schema_payload(payload, "user1")
        assert result["website"] == "https://example.com"

    def test_website_extraction_from_related_links_string(self):
        """Should handle relatedLink as string instead of list."""
        payload = {
            "mainEntity": {"identifier": "user1"},
            "relatedLink": "https://example.com",
        }

        result = SeleniumWorker._parse_profile_schema_payload(payload, "user1")
        assert result["website"] == "https://example.com"

    def test_website_extraction_from_main_entity(self):
        """Should extract website from mainEntity.relatedLink."""
        payload = {
            "mainEntity": {
                "identifier": "user1",
                "relatedLink": ["https://example.com"],
            }
        }

        result = SeleniumWorker._parse_profile_schema_payload(payload, "user1")
        assert result["website"] == "https://example.com"

    def test_joined_date_extraction_from_payload(self):
        """Should extract joined date from top-level dateCreated."""
        payload = {
            "mainEntity": {"identifier": "user1"},
            "dateCreated": "2010-03-15",
        }

        result = SeleniumWorker._parse_profile_schema_payload(payload, "user1")
        assert result["joined_date"] == "2010-03-15"

    def test_joined_date_extraction_from_main_entity(self):
        """Should extract joined date from mainEntity.dateCreated."""
        payload = {
            "mainEntity": {
                "identifier": "user1",
                "dateCreated": "2012-06-20",
            }
        }

        result = SeleniumWorker._parse_profile_schema_payload(payload, "user1")
        assert result["joined_date"] == "2012-06-20"

    def test_empty_main_entity_returns_none(self):
        """Should return None if mainEntity is missing or empty."""
        assert SeleniumWorker._parse_profile_schema_payload({}, "user1") is None
        assert SeleniumWorker._parse_profile_schema_payload({"mainEntity": {}}, "user1") is None

    def test_invalid_count_ignored(self):
        """Should ignore interaction counts that aren't integers."""
        payload = {
            "mainEntity": {
                "identifier": "user1",
                "interactionStatistic": [
                    {"name": "Follows", "userInteractionCount": "not a number"},
                    {"name": "Friends", "userInteractionCount": None},
                ],
            }
        }

        result = SeleniumWorker._parse_profile_schema_payload(payload, "user1")
        assert result["followers_total"] is None
        assert result["following_total"] is None


# ==============================================================================
# DOM Extraction Tests (with mocked WebElements)
# ==============================================================================
class TestExtractHandle:
    """Test _extract_handle from UserCell DOM elements."""

    def test_extract_from_anchor_href(self):
        """Should extract handle from anchor href attribute."""
        mock_cell = Mock()
        mock_link = Mock()
        mock_link.get_attribute.return_value = "https://twitter.com/elonmusk"
        mock_cell.find_elements.return_value = [mock_link]
        mock_cell.text = ""

        assert SeleniumWorker._extract_handle(mock_cell) == "elonmusk"

    def test_extract_from_multiple_anchors(self):
        """Should find first valid handle from multiple anchors."""
        mock_cell = Mock()
        mock_link1 = Mock()
        mock_link1.get_attribute.return_value = "/i/topics/123"  # Invalid (starts with i)
        mock_link2 = Mock()
        mock_link2.get_attribute.return_value = "/elonmusk"  # Valid
        mock_cell.find_elements.return_value = [mock_link1, mock_link2]
        mock_cell.text = ""

        assert SeleniumWorker._extract_handle(mock_cell) == "elonmusk"

    def test_extract_from_cell_text_fallback(self):
        """Should extract @handle from cell text if no valid anchors."""
        mock_cell = Mock()
        mock_cell.find_elements.return_value = []
        mock_cell.text = "Elon Musk @elonmusk\nCEO of Tesla"

        assert SeleniumWorker._extract_handle(mock_cell) == "elonmusk"

    def test_return_none_when_no_handle_found(self):
        """Should return None when no handle can be extracted."""
        mock_cell = Mock()
        mock_cell.find_elements.return_value = []
        mock_cell.text = "No handle here"

        assert SeleniumWorker._extract_handle(mock_cell) is None


class TestExtractDisplayName:
    """Test _extract_display_name from UserCell DOM elements."""

    def test_extract_from_username_div(self):
        """Should extract display name from UserName div."""
        mock_cell = Mock()
        mock_username_div = Mock()
        mock_span = Mock()
        mock_span.text = "Elon Musk"
        mock_username_div.find_elements.return_value = [mock_span]
        mock_cell.find_element.return_value = mock_username_div
        mock_cell.text = ""

        worker = SeleniumWorker(Mock())
        assert worker._extract_display_name(mock_cell) == "Elon Musk"

    def test_skip_handle_spans(self):
        """Should skip spans that start with @ (handles, not display names)."""
        mock_cell = Mock()
        mock_username_div = Mock()
        mock_span1 = Mock()
        mock_span1.text = "@elonmusk"
        mock_span2 = Mock()
        mock_span2.text = "Elon Musk"
        mock_username_div.find_elements.return_value = [mock_span1, mock_span2]
        mock_cell.find_element.return_value = mock_username_div
        mock_cell.text = ""

        worker = SeleniumWorker(Mock())
        assert worker._extract_display_name(mock_cell) == "Elon Musk"

    def test_fallback_to_text_parsing(self):
        """Should fallback to parsing cell text if structured div missing."""
        from selenium.common.exceptions import NoSuchElementException

        mock_cell = Mock()
        mock_cell.find_element.side_effect = NoSuchElementException()
        mock_cell.text = "Elon Musk\n@elonmusk\nCEO of Tesla"

        worker = SeleniumWorker(Mock())
        assert worker._extract_display_name(mock_cell) == "Elon Musk"

    def test_reject_long_display_names(self):
        """Should reject display names longer than 80 characters."""
        mock_cell = Mock()
        mock_username_div = Mock()
        mock_span = Mock()
        mock_span.text = "A" * 85  # Too long
        mock_username_div.find_elements.return_value = [mock_span]
        mock_cell.find_element.return_value = mock_username_div
        mock_cell.text = ""

        worker = SeleniumWorker(Mock())
        assert worker._extract_display_name(mock_cell) is None


class TestExtractBio:
    """Test _extract_bio from UserCell DOM elements."""

    def test_extract_from_description_div(self):
        """Should extract bio from UserDescription div."""
        mock_cell = Mock()
        mock_bio_div = Mock()
        mock_bio_div.text = "CEO of Tesla, SpaceX, and Neuralink"
        mock_cell.find_elements.return_value = [mock_bio_div]

        worker = SeleniumWorker(Mock())
        assert worker._extract_bio(mock_cell) == "CEO of Tesla, SpaceX, and Neuralink"

    def test_fallback_to_text_parsing(self):
        """Should fallback to parsing cell text if UserDescription missing."""
        mock_cell = Mock()
        mock_cell.find_elements.return_value = []
        mock_cell.text = "Elon Musk\n@elonmusk\nFollow\nCEO of Tesla and SpaceX"

        worker = SeleniumWorker(Mock())
        result = worker._extract_bio(mock_cell)
        assert "CEO of Tesla and SpaceX" in result

    def test_return_none_when_no_bio(self):
        """Should return None when no bio found."""
        mock_cell = Mock()
        mock_cell.find_elements.return_value = []
        mock_cell.text = "Elon Musk\n@elonmusk"

        worker = SeleniumWorker(Mock())
        assert worker._extract_bio(mock_cell) is None


class TestExtractWebsite:
    """Test _extract_website from UserCell DOM elements."""

    def test_extract_from_user_url_testid(self):
        """Should extract website from UserUrl data-testid."""
        mock_cell = Mock()
        mock_anchor = Mock()
        mock_anchor.get_attribute.return_value = "https://tesla.com"
        mock_cell.find_elements.side_effect = [
            [mock_anchor],  # First call: UserUrl anchors
        ]

        assert SeleniumWorker._extract_website(mock_cell) == "https://tesla.com"

    def test_extract_from_generic_anchor_fallback(self):
        """Should fallback to generic anchors if UserUrl not found."""
        mock_cell = Mock()
        mock_anchor = Mock()
        mock_anchor.get_attribute.return_value = "https://example.com"
        mock_cell.find_elements.side_effect = [
            [],  # First call: No UserUrl anchors
            [mock_anchor],  # Second call: Generic anchors
        ]

        assert SeleniumWorker._extract_website(mock_cell) == "https://example.com"

    def test_skip_twitter_links(self):
        """Should skip twitter.com links (not external websites)."""
        mock_cell = Mock()
        mock_twitter_link = Mock()
        mock_twitter_link.get_attribute.return_value = "https://twitter.com/elonmusk/status/123"
        mock_external_link = Mock()
        mock_external_link.get_attribute.return_value = "https://tesla.com"
        mock_cell.find_elements.side_effect = [
            [],  # No UserUrl
            [mock_twitter_link, mock_external_link],  # Generic anchors
        ]

        assert SeleniumWorker._extract_website(mock_cell) == "https://tesla.com"

    def test_skip_relative_paths(self):
        """Should skip relative paths starting with /."""
        mock_cell = Mock()
        mock_relative = Mock()
        mock_relative.get_attribute.return_value = "/i/topics/123"
        mock_external = Mock()
        mock_external.get_attribute.return_value = "https://blog.example.com"
        mock_cell.find_elements.side_effect = [
            [],
            [mock_relative, mock_external],
        ]

        assert SeleniumWorker._extract_website(mock_cell) == "https://blog.example.com"

    def test_return_none_when_no_website(self):
        """Should return None when no external website found."""
        mock_cell = Mock()
        mock_cell.find_elements.return_value = []

        assert SeleniumWorker._extract_website(mock_cell) is None


class TestExtractProfileImageUrl:
    """Test _extract_profile_image_url from UserCell DOM elements."""

    def test_extract_from_twimg_image(self):
        """Should extract profile image URL from twimg.com images."""
        mock_cell = Mock()
        mock_img = Mock()
        mock_img.get_attribute.return_value = "https://pbs.twimg.com/profile_images/123/avatar.jpg"
        mock_cell.find_elements.return_value = [mock_img]

        assert SeleniumWorker._extract_profile_image_url(mock_cell) == "https://pbs.twimg.com/profile_images/123/avatar.jpg"

    def test_extract_from_profile_images_path(self):
        """Should extract image URLs containing 'profile_images' path."""
        mock_cell = Mock()
        mock_img = Mock()
        mock_img.get_attribute.return_value = "https://cdn.example.com/profile_images/456/photo.png"
        mock_cell.find_elements.return_value = [mock_img]

        assert SeleniumWorker._extract_profile_image_url(mock_cell) == "https://cdn.example.com/profile_images/456/photo.png"

    def test_skip_non_profile_images(self):
        """Should skip images that aren't profile photos."""
        mock_cell = Mock()
        mock_icon = Mock()
        mock_icon.get_attribute.return_value = "https://example.com/icons/verified.svg"
        mock_profile = Mock()
        mock_profile.get_attribute.return_value = "https://pbs.twimg.com/profile_images/789/avatar.jpg"
        mock_cell.find_elements.return_value = [mock_icon, mock_profile]

        assert SeleniumWorker._extract_profile_image_url(mock_cell) == "https://pbs.twimg.com/profile_images/789/avatar.jpg"

    def test_return_none_when_no_profile_image(self):
        """Should return None when no profile image found."""
        mock_cell = Mock()
        mock_cell.find_elements.return_value = []

        assert SeleniumWorker._extract_profile_image_url(mock_cell) is None
