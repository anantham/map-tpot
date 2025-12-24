"""Tests for _parse_compact_count parsing of follower/following counts."""
import pytest
from src.shadow.selenium_worker import SeleniumWorker


class TestParseCompactCount:
    """Test suite for _parse_compact_count method."""

    def test_parse_compact_count_with_k_suffix(self):
        """Should parse counts with K suffix correctly."""
        assert SeleniumWorker._parse_compact_count("90.5K") == 90500
        assert SeleniumWorker._parse_compact_count("100K") == 100000
        assert SeleniumWorker._parse_compact_count("5.5K") == 5500

    def test_parse_compact_count_with_m_suffix(self):
        """Should parse counts with M suffix correctly."""
        assert SeleniumWorker._parse_compact_count("1.2M") == 1200000
        assert SeleniumWorker._parse_compact_count("5M") == 5000000

    def test_parse_compact_count_with_commas(self):
        """Should parse counts with commas correctly."""
        assert SeleniumWorker._parse_compact_count("1,064") == 1064
        assert SeleniumWorker._parse_compact_count("123,456") == 123456

    def test_parse_compact_count_with_label_text(self):
        """Should parse counts with trailing label text (e.g., 'Followers', 'Following')."""
        # Regression test: Ensures label text after numbers is stripped correctly
        assert SeleniumWorker._parse_compact_count("90.5K Followers") == 90500
        assert SeleniumWorker._parse_compact_count("1,064 Following") == 1064
        assert SeleniumWorker._parse_compact_count("123,456 Following") == 123456
        assert SeleniumWorker._parse_compact_count("5.5K Followers") == 5500

    def test_parse_compact_count_plain_numbers(self):
        """Should parse plain numbers correctly."""
        assert SeleniumWorker._parse_compact_count("90") == 90
        assert SeleniumWorker._parse_compact_count("1064") == 1064
        assert SeleniumWorker._parse_compact_count("0") == 0

    def test_parse_compact_count_invalid_input(self):
        """Should return None for invalid input."""
        assert SeleniumWorker._parse_compact_count("Followers") is None
        assert SeleniumWorker._parse_compact_count("") is None
        assert SeleniumWorker._parse_compact_count(None) is None
        assert SeleniumWorker._parse_compact_count("No numbers here") is None
