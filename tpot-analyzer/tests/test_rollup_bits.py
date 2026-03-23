"""Tests for scripts/rollup_bits.py — bits tag parsing and aggregation."""

import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path so we can import scripts.rollup_bits
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from rollup_bits import aggregate_bits, parse_bits_tag


# ── parse_bits_tag ────────────────────────────────────────────────────────────


class TestParseBitsTag:
    def test_positive_tag(self):
        assert parse_bits_tag("bits:LLM-Whisperers:+3") == ("LLM-Whisperers", 3)

    def test_negative_tag(self):
        assert parse_bits_tag("bits:Qualia-Research:-2") == ("Qualia-Research", -2)

    def test_zero_bits(self):
        assert parse_bits_tag("bits:highbies:+0") == ("highbies", 0)

    def test_malformed_no_prefix(self):
        assert parse_bits_tag("LLM-Whisperers:+3") is None

    def test_malformed_missing_value(self):
        assert parse_bits_tag("bits:LLM-Whisperers") is None

    def test_malformed_non_numeric(self):
        assert parse_bits_tag("bits:LLM-Whisperers:abc") is None

    def test_extra_colons(self):
        assert parse_bits_tag("bits:AI-Safety:+1:extra") is None

    def test_empty_string(self):
        assert parse_bits_tag("") is None

    def test_wrong_prefix(self):
        assert parse_bits_tag("domain:AI-Safety:+1") is None

    def test_bare_number_without_sign(self):
        """Tags like bits:X:3 (no +/-) should still parse — int('3') works."""
        assert parse_bits_tag("bits:highbies:3") == ("highbies", 3)


# ── aggregate_bits ────────────────────────────────────────────────────────────


class TestAggregateBits:
    """Test the aggregation logic that converts (account, tweet, tag) triples
    into per-(account, community) rollup dicts."""

    SHORT_TO_ID = {
        "LLM-Whisperers": "comm-llm",
        "Qualia-Research": "comm-qualia",
        "AI-Safety": "comm-ai",
    }

    def test_basic_aggregation_same_community(self):
        """Two tags for same community on different tweets → sum bits, tweet_count=2."""
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
            ("acct1", "tweet2", "bits:LLM-Whisperers:+2"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        key = ("acct1", "comm-llm")
        assert key in result
        assert result[key]["total_bits"] == 5
        assert result[key]["tweet_count"] == 2
        assert result[key]["pct"] == 100.0  # only community for this account

    def test_negative_bits_subtract(self):
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
            ("acct1", "tweet2", "bits:LLM-Whisperers:-1"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        assert result[("acct1", "comm-llm")]["total_bits"] == 2

    def test_unknown_community_skipped(self):
        tags = [
            ("acct1", "tweet1", "bits:Unknown-Comm:+5"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        assert len(result) == 0

    def test_pct_calculation(self):
        """30/70 split: abs(3)/(abs(3)+abs(7)) = 30%, abs(7)/(abs(3)+abs(7)) = 70%."""
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
            ("acct1", "tweet2", "bits:Qualia-Research:+7"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        assert abs(result[("acct1", "comm-llm")]["pct"] - 30.0) < 0.01
        assert abs(result[("acct1", "comm-qualia")]["pct"] - 70.0) < 0.01

    def test_pct_with_negative_bits(self):
        """pct uses abs(total_bits) — negative communities still get proportional share."""
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+6"),
            ("acct1", "tweet2", "bits:Qualia-Research:-4"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        # abs(6) + abs(-4) = 10
        assert abs(result[("acct1", "comm-llm")]["pct"] - 60.0) < 0.01
        assert abs(result[("acct1", "comm-qualia")]["pct"] - 40.0) < 0.01

    def test_multiple_accounts_separate(self):
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
            ("acct2", "tweet2", "bits:LLM-Whisperers:+5"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        assert result[("acct1", "comm-llm")]["total_bits"] == 3
        assert result[("acct2", "comm-llm")]["total_bits"] == 5
        # Each is 100% for their single-community account
        assert result[("acct1", "comm-llm")]["pct"] == 100.0
        assert result[("acct2", "comm-llm")]["pct"] == 100.0

    def test_same_tweet_same_community_multiple_tags_tweet_count_1(self):
        """Multiple bits tags for same (tweet, community) → tweet_count still 1."""
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
            ("acct1", "tweet1", "bits:LLM-Whisperers:+2"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        key = ("acct1", "comm-llm")
        assert result[key]["total_bits"] == 5
        assert result[key]["tweet_count"] == 1  # same tweet, same community

    def test_same_tweet_different_communities(self):
        """One tweet with tags for two communities → each community gets tweet_count=1."""
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
            ("acct1", "tweet1", "bits:Qualia-Research:+2"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        assert result[("acct1", "comm-llm")]["tweet_count"] == 1
        assert result[("acct1", "comm-qualia")]["tweet_count"] == 1

    def test_malformed_tags_skipped(self):
        tags = [
            ("acct1", "tweet1", "bits:LLM-Whisperers:+3"),
            ("acct1", "tweet2", "not-a-bits-tag"),
            ("acct1", "tweet3", "bits:LLM-Whisperers:abc"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        # Only the first valid tag contributes
        assert result[("acct1", "comm-llm")]["total_bits"] == 3
        assert result[("acct1", "comm-llm")]["tweet_count"] == 1

    def test_empty_input(self):
        result = aggregate_bits([], self.SHORT_TO_ID)
        assert result == {}

    def test_case_insensitive_short_name_lookup(self):
        """Tags may be lowercased by the tag system; lookup should be case-insensitive."""
        tags = [
            ("acct1", "tweet1", "bits:llm-whisperers:+3"),
        ]
        result = aggregate_bits(tags, self.SHORT_TO_ID)
        assert ("acct1", "comm-llm") in result
        assert result[("acct1", "comm-llm")]["total_bits"] == 3
