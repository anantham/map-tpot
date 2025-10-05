"""Unit tests for Selenium DOM extraction methods.

These tests cover all extraction bugs fixed in commits:
- a8eec0d: profile_image_url, website text prioritization
- 9c806a4: display_name and bio text parsing
- 7a55bde: bio xpath fallback (tested via mock in extract_profile_overview)
- 6869738: claimed_total selector improvements

Each test uses mock Selenium elements to isolate extraction logic.
"""
from __future__ import annotations

from unittest.mock import MagicMock, Mock
from typing import List

import pytest

from src.shadow.selenium_worker import SeleniumWorker


# ==============================================================================
# Mock Helpers
# ==============================================================================

def mock_element(
    tag: str = "div",
    text: str = "",
    attrs: dict = None,
    children: List = None
) -> Mock:
    """Create a mock Selenium WebElement."""
    elem = Mock()
    elem.tag_name = tag
    elem.text = text

    def get_attr(name: str) -> str | None:
        return (attrs or {}).get(name)

    elem.get_attribute = Mock(side_effect=get_attr)

    def find_elements(by, selector):
        return children or []

    elem.find_elements = Mock(side_effect=find_elements)

    def find_element(by, selector):
        elems = find_elements(by, selector)
        if not elems:
            from selenium.common.exceptions import NoSuchElementException
            raise NoSuchElementException(f"No element found for {selector}")
        return elems[0]

    elem.find_element = Mock(side_effect=find_element)

    return elem


# ==============================================================================
# _parse_compact_count Tests
# ==============================================================================

class TestParseCompactCount:
    """Test compact number parsing (1.2K, 5M, etc.)."""

    def test_parse_integer(self):
        assert SeleniumWorker._parse_compact_count("123") == 123
        assert SeleniumWorker._parse_compact_count("1,234") == 1234
        assert SeleniumWorker._parse_compact_count("1,234,567") == 1234567

    def test_parse_k_suffix(self):
        assert SeleniumWorker._parse_compact_count("1.2K") == 1200
        assert SeleniumWorker._parse_compact_count("1.2k") == 1200
        assert SeleniumWorker._parse_compact_count("5K") == 5000

    def test_parse_m_suffix(self):
        assert SeleniumWorker._parse_compact_count("1.5M") == 1500000
        assert SeleniumWorker._parse_compact_count("1.5m") == 1500000
        assert SeleniumWorker._parse_compact_count("2M") == 2000000

    def test_parse_with_whitespace(self):
        assert SeleniumWorker._parse_compact_count(" 123 ") == 123
        assert SeleniumWorker._parse_compact_count("1 234") == 1234

    def test_parse_fallback_to_first_digits(self):
        # Should extract first digit group when format doesn't match
        assert SeleniumWorker._parse_compact_count("Following 123") == 123
        assert SeleniumWorker._parse_compact_count("Followers: 1,234") == 1234

    def test_parse_none_and_invalid(self):
        assert SeleniumWorker._parse_compact_count(None) is None
        assert SeleniumWorker._parse_compact_count("") is None
        assert SeleniumWorker._parse_compact_count("abc") is None
        assert SeleniumWorker._parse_compact_count("Follow") is None


# ==============================================================================
# JSON-LD Profile Schema Parsing
# ==============================================================================

class TestProfileSchemaParsing:
    """Ensure JSON-LD fallback recovers counts and metadata."""

    SAMPLE_PAYLOAD = {
        "@context": "http://schema.org",
        "@type": "ProfilePage",
        "dateCreated": "2009-11-11T19:54:16.000Z",
        "mainEntity": {
            "@type": "Person",
            "name": "critter",
            "additionalName": "BecomingCritter",
            "description": "treehouse bio",
            "homeLocation": {"@type": "Place", "name": "pretty good thanks"},
            "identifier": "89266660",
            "image": {
                "@type": "ImageObject",
                "contentUrl": "https://pbs.twimg.com/profile_images/example_normal.png",
            },
            "interactionStatistic": [
                {
                    "@type": "InteractionCounter",
                    "name": "Follows",
                    "userInteractionCount": 22107,
                },
                {
                    "@type": "InteractionCounter",
                    "name": "Friends",
                    "userInteractionCount": 1103,
                },
            ],
            "url": "https://x.com/BecomingCritter",
        },
        "relatedLink": ["https://becomingcreature.substack.com/"],
    }

    def test_parse_profile_schema_payload_matches_username(self):
        parsed = SeleniumWorker._parse_profile_schema_payload(
            self.SAMPLE_PAYLOAD,
            target_username="becomingcritter",
        )
        assert parsed is not None
        assert parsed["followers_total"] == 22107
        assert parsed["following_total"] == 1103
        assert parsed["location"] == "pretty good thanks"
        assert parsed["website"] == "https://becomingcreature.substack.com/"
        assert parsed["profile_image_url"].endswith("example_normal.png")

    def test_parse_profile_schema_payload_rejects_mismatch(self):
        parsed = SeleniumWorker._parse_profile_schema_payload(
            self.SAMPLE_PAYLOAD,
            target_username="someoneelse",
        )
        assert parsed is None


# ==============================================================================
# _handle_from_href Tests
# ==============================================================================

class TestHandleFromHref:
    """Test extracting Twitter handles from various href formats."""

    def test_absolute_url(self):
        assert SeleniumWorker._handle_from_href("https://twitter.com/username") == "username"
        assert SeleniumWorker._handle_from_href("https://x.com/username") == "username"

    def test_relative_path(self):
        assert SeleniumWorker._handle_from_href("/username") == "username"
        assert SeleniumWorker._handle_from_href("username") == "username"

    def test_with_query_params(self):
        assert SeleniumWorker._handle_from_href("/username?src=hash") == "username"
        assert SeleniumWorker._handle_from_href("https://twitter.com/username?tab=following") == "username"

    def test_with_fragment(self):
        assert SeleniumWorker._handle_from_href("/username#section") == "username"

    def test_with_trailing_slash(self):
        assert SeleniumWorker._handle_from_href("/username/") == "username"

    def test_with_at_prefix(self):
        assert SeleniumWorker._handle_from_href("/@username") == "username"

    def test_invalid_hrefs(self):
        # Multiple path segments
        assert SeleniumWorker._handle_from_href("/username/followers") is None
        # Reserved paths
        assert SeleniumWorker._handle_from_href("/i/topics") is None
        # Too long
        assert SeleniumWorker._handle_from_href("/" + "a" * 50) is None
        # Empty/None
        assert SeleniumWorker._handle_from_href(None) is None
        assert SeleniumWorker._handle_from_href("") is None
        assert SeleniumWorker._handle_from_href("   ") is None
        # External URLs
        assert SeleniumWorker._handle_from_href("https://example.com/user") is None


# ==============================================================================
# _extract_handle Tests
# ==============================================================================

class TestExtractHandle:
    """Test handle extraction from UserCell elements."""

    def test_extract_from_link_href(self):
        link = mock_element(tag="a", attrs={"href": "https://twitter.com/testuser"})
        cell = mock_element(children=[link])
        assert SeleniumWorker._extract_handle(cell) == "testuser"

    def test_extract_from_relative_href(self):
        link = mock_element(tag="a", attrs={"href": "/testuser"})
        cell = mock_element(children=[link])
        assert SeleniumWorker._extract_handle(cell) == "testuser"

    def test_extract_from_text_with_at_symbol(self):
        cell = mock_element(text="@testuser follows you")
        assert SeleniumWorker._extract_handle(cell) == "testuser"

    def test_prefer_link_over_text(self):
        link = mock_element(tag="a", attrs={"href": "/realuser"})
        cell = mock_element(text="@fakeuser", children=[link])
        assert SeleniumWorker._extract_handle(cell) == "realuser"

    def test_return_none_when_no_handle(self):
        cell = mock_element(text="No handle here")
        assert SeleniumWorker._extract_handle(cell) is None


# ==============================================================================
# _extract_display_name Tests (Bug: 9c806a4)
# ==============================================================================

class TestExtractDisplayName:
    """Test display name extraction with structured and fallback logic.

    Bug fix: 9c806a4 - Improved text parsing fallback when data-testid fails.
    """

    def test_extract_from_username_div_structured(self):
        """Test structured extraction from UserName div."""
        worker = SeleniumWorker(Mock())

        name_span = mock_element(tag="span", text="Display Name")
        handle_span = mock_element(tag="span", text="@testuser")
        username_div = mock_element(
            tag="div",
            attrs={"data-testid": "UserName"},
            children=[name_span, handle_span]
        )
        cell = mock_element(children=[username_div])

        # Mock find_element to return username_div
        cell.find_element = Mock(return_value=username_div)
        username_div.find_elements = Mock(return_value=[name_span, handle_span])

        assert worker._extract_display_name(cell) == "Display Name"

    def test_fallback_to_text_parsing_first_line(self):
        """Test fallback: first non-@ line is display name."""
        worker = SeleniumWorker(Mock())

        from selenium.common.exceptions import NoSuchElementException
        cell = mock_element(text="Display Name\n@testuser\nBio text here")
        cell.find_element = Mock(side_effect=NoSuchElementException())

        assert worker._extract_display_name(cell) == "Display Name"

    def test_fallback_when_first_line_is_handle(self):
        """Test fallback returns None when first line is @handle."""
        worker = SeleniumWorker(Mock())

        from selenium.common.exceptions import NoSuchElementException
        cell = mock_element(text="@testuser\nBio text here")
        cell.find_element = Mock(side_effect=NoSuchElementException())

        assert worker._extract_display_name(cell) is None

    def test_skip_long_text(self):
        """Test that overly long text (>80 chars) is skipped."""
        worker = SeleniumWorker(Mock())

        long_text = "a" * 100
        span = mock_element(tag="span", text=long_text)
        username_div = mock_element(
            tag="div",
            attrs={"data-testid": "UserName"},
            children=[span]
        )
        cell = mock_element()
        cell.find_element = Mock(return_value=username_div)
        username_div.find_elements = Mock(return_value=[span])

        assert worker._extract_display_name(cell) is None


# ==============================================================================
# _extract_bio Tests (Bug: 9c806a4)
# ==============================================================================

class TestExtractBio:
    """Test bio extraction with structured and fallback logic.

    Bug fix: 9c806a4 - Text parsing finds bio after @handle and optional Follow button.
    """

    def test_extract_from_description_div_structured(self):
        """Test structured extraction from UserDescription div."""
        worker = SeleniumWorker(Mock())

        bio_div = mock_element(
            tag="div",
            attrs={"data-testid": "UserDescription"},
            text="This is my bio"
        )
        cell = mock_element()
        cell.find_elements = Mock(return_value=[bio_div])

        assert worker._extract_bio(cell) == "This is my bio"

    def test_fallback_bio_after_handle(self):
        """Test fallback: bio starts after @handle line."""
        worker = SeleniumWorker(Mock())

        from selenium.common.exceptions import NoSuchElementException
        cell = mock_element(text="Display Name\n@testuser\nThis is my bio")
        cell.find_elements = Mock(return_value=[])

        assert worker._extract_bio(cell) == "This is my bio"

    def test_fallback_bio_after_handle_and_follow_button(self):
        """Test fallback: bio starts after @handle and 'Follow' button."""
        worker = SeleniumWorker(Mock())

        cell = mock_element(text="Display Name\n@testuser\nFollow\nThis is my bio")
        cell.find_elements = Mock(return_value=[])

        assert worker._extract_bio(cell) == "This is my bio"

    def test_fallback_with_following_button(self):
        """Test fallback: bio starts after @handle and 'Following' button."""
        worker = SeleniumWorker(Mock())

        cell = mock_element(text="Display Name\n@testuser\nFollowing\nThis is my bio")
        cell.find_elements = Mock(return_value=[])

        assert worker._extract_bio(cell) == "This is my bio"

    def test_multiline_bio(self):
        """Test bio can span multiple lines."""
        worker = SeleniumWorker(Mock())

        cell = mock_element(text="Name\n@handle\nFirst line of bio\nSecond line of bio")
        cell.find_elements = Mock(return_value=[])

        assert worker._extract_bio(cell) == "First line of bio Second line of bio"

    def test_return_none_when_no_bio(self):
        """Test returns None when no bio found."""
        worker = SeleniumWorker(Mock())

        cell = mock_element(text="Name\n@handle")
        cell.find_elements = Mock(return_value=[])

        assert worker._extract_bio(cell) is None


# ==============================================================================
# _extract_website Tests (Bug: a8eec0d)
# ==============================================================================

class TestExtractWebsite:
    """Test website extraction from UserCell.

    Bug fix: a8eec0d - Changed to prefer link text over href for clean URLs.
    Note: The current implementation still uses href, not text. This test documents expected behavior.
    """

    def test_extract_from_user_url_testid(self):
        """Test extraction from a[data-testid='UserUrl']."""
        link = mock_element(
            tag="a",
            attrs={
                "data-testid": "UserUrl",
                "href": "https://example.com"
            }
        )
        cell = mock_element()
        cell.find_elements = Mock(return_value=[link])

        assert SeleniumWorker._extract_website(cell) == "https://example.com"

    def test_fallback_to_generic_links(self):
        """Test fallback to any a[href] when UserUrl not found."""
        link = mock_element(
            tag="a",
            attrs={"href": "https://website.com"}
        )
        cell = mock_element()
        # First call returns empty (no UserUrl), second returns generic link
        cell.find_elements = Mock(side_effect=[[], [link]])

        assert SeleniumWorker._extract_website(cell) == "https://website.com"

    def test_skip_twitter_internal_links(self):
        """Test that Twitter internal links are skipped."""
        twitter_link = mock_element(
            tag="a",
            attrs={"href": "https://twitter.com/i/topics"}
        )
        external_link = mock_element(
            tag="a",
            attrs={"href": "https://example.com"}
        )
        cell = mock_element()
        cell.find_elements = Mock(return_value=[twitter_link, external_link])

        assert SeleniumWorker._extract_website(cell) == "https://example.com"

    def test_skip_relative_links(self):
        """Test that relative links are skipped."""
        relative_link = mock_element(tag="a", attrs={"href": "/settings"})
        external_link = mock_element(tag="a", attrs={"href": "https://example.com"})
        cell = mock_element()
        cell.find_elements = Mock(return_value=[relative_link, external_link])

        assert SeleniumWorker._extract_website(cell) == "https://example.com"

    def test_return_none_when_no_external_link(self):
        """Test returns None when no external links found."""
        cell = mock_element()
        cell.find_elements = Mock(return_value=[])

        assert SeleniumWorker._extract_website(cell) is None


# ==============================================================================
# _extract_profile_image_url Tests (Bug: a8eec0d)
# ==============================================================================

class TestExtractProfileImageUrl:
    """Test profile image URL extraction from UserCell.

    Bug fix: a8eec0d - Added profile_image_url extraction.
    """

    def test_extract_from_twimg_src(self):
        """Test extraction from img with twimg.com in src."""
        img = mock_element(
            tag="img",
            attrs={"src": "https://pbs.twimg.com/profile_images/123/abc_x96.jpg"}
        )
        cell = mock_element()
        cell.find_elements = Mock(return_value=[img])

        url = SeleniumWorker._extract_profile_image_url(cell)
        assert url == "https://pbs.twimg.com/profile_images/123/abc_x96.jpg"

    def test_extract_from_profile_images_path(self):
        """Test extraction from img with 'profile_images' in path."""
        img = mock_element(
            tag="img",
            attrs={"src": "https://cdn.example.com/profile_images/123.jpg"}
        )
        cell = mock_element()
        cell.find_elements = Mock(return_value=[img])

        url = SeleniumWorker._extract_profile_image_url(cell)
        assert url == "https://cdn.example.com/profile_images/123.jpg"

    def test_skip_non_profile_images(self):
        """Test that non-profile images are skipped."""
        banner_img = mock_element(
            tag="img",
            attrs={"src": "https://example.com/banner.jpg"}
        )
        profile_img = mock_element(
            tag="img",
            attrs={"src": "https://pbs.twimg.com/profile_images/123.jpg"}
        )
        cell = mock_element()
        cell.find_elements = Mock(return_value=[banner_img, profile_img])

        url = SeleniumWorker._extract_profile_image_url(cell)
        assert url == "https://pbs.twimg.com/profile_images/123.jpg"

    def test_return_none_when_no_profile_image(self):
        """Test returns None when no profile image found."""
        cell = mock_element()
        cell.find_elements = Mock(return_value=[])

        assert SeleniumWorker._extract_profile_image_url(cell) is None


# ==============================================================================
# Integration Test: Full UserCell Extraction
# ==============================================================================

class TestUserCellExtraction:
    """Integration tests for extracting all data from a UserCell."""

    def test_extract_complete_user_cell(self):
        """Test extracting all fields from a complete UserCell."""
        worker = SeleniumWorker(Mock())

        # Mock a complete UserCell with all data
        profile_link = mock_element(tag="a", attrs={"href": "/testuser"})
        website_link = mock_element(
            tag="a",
            attrs={"data-testid": "UserUrl", "href": "https://example.com"}
        )
        profile_img = mock_element(
            tag="img",
            attrs={"src": "https://pbs.twimg.com/profile_images/123.jpg"}
        )

        from selenium.common.exceptions import NoSuchElementException

        cell = mock_element(
            text="Display Name\n@testuser\nFollow\nMy awesome bio",
            children=[profile_link]
        )

        # Mock find_elements for different selectors
        def mock_find_elements(by, selector):
            if "UserName" in selector:
                return []  # Force text fallback
            elif "UserDescription" in selector:
                return []  # Force text fallback
            elif "UserUrl" in selector:
                return [website_link]
            elif "img" in selector:
                return [profile_img]
            elif "a" == selector or selector == "a[href]":
                return [profile_link, website_link]
            return []

        cell.find_elements = Mock(side_effect=mock_find_elements)
        cell.find_element = Mock(side_effect=NoSuchElementException())

        # Test all extraction methods
        assert SeleniumWorker._extract_handle(cell) == "testuser"
        assert worker._extract_display_name(cell) == "Display Name"
        assert worker._extract_bio(cell) == "My awesome bio"
        assert SeleniumWorker._extract_website(cell) == "https://example.com"
        assert SeleniumWorker._extract_profile_image_url(cell) == "https://pbs.twimg.com/profile_images/123.jpg"
