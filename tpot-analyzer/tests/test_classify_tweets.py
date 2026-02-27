"""Tests for scripts/classify_tweets.py."""
from __future__ import annotations

import json
import pytest

from scripts.classify_tweets import (
    build_prompt,
    load_taxonomy,
    parse_response,
)
from src.data.golden.schema import split_for_tweet


# ---------------------------------------------------------------------------
# _split_for_tweet
# ---------------------------------------------------------------------------

class TestSplitForTweet:
    """Deterministic hash-based split assignment (tests schema.py canonical implementation)."""

    def test_deterministic(self):
        """Same tweet_id always gets same split."""
        assert split_for_tweet("12345") == split_for_tweet("12345")

    def test_known_splits(self):
        """Verify distribution roughly matches 70/15/15."""
        splits = {"train": 0, "dev": 0, "test": 0}
        for i in range(10000):
            splits[split_for_tweet(str(i))] += 1
        # Allow ±3% tolerance
        assert 6700 < splits["train"] < 7300
        assert 1200 < splits["dev"] < 1800
        assert 1200 < splits["test"] < 1800

    def test_returns_valid_split_names(self):
        """Output is always one of the three valid splits."""
        for i in range(1000):
            assert split_for_tweet(str(i)) in {"train", "dev", "test"}


# ---------------------------------------------------------------------------
# parse_response
# ---------------------------------------------------------------------------

class TestParseResponse:
    """Parse and validate OpenRouter responses."""

    def test_valid_response(self):
        raw = {
            "choices": [{
                "message": {
                    "content": '{"distribution": {"l1": 0.7, "l2": 0.2, "l3": 0.1, "l4": 0.0}}'
                }
            }]
        }
        dist = parse_response(raw)
        assert dist is not None
        assert abs(sum(dist.values()) - 1.0) < 0.01
        assert dist["l1"] == 0.7

    def test_markdown_fenced_response(self):
        raw = {
            "choices": [{
                "message": {
                    "content": '```json\n{"distribution": {"l1": 0.5, "l2": 0.3, "l3": 0.15, "l4": 0.05}}\n```'
                }
            }]
        }
        dist = parse_response(raw)
        assert dist is not None
        assert dist["l1"] == 0.5

    def test_flat_dict_response(self):
        """Some models return the distribution directly without nesting."""
        raw = {
            "choices": [{
                "message": {
                    "content": '{"l1": 0.6, "l2": 0.2, "l3": 0.15, "l4": 0.05}'
                }
            }]
        }
        dist = parse_response(raw)
        assert dist is not None
        assert dist["l1"] == 0.6

    def test_normalizes_non_unit_sum(self):
        raw = {
            "choices": [{
                "message": {
                    "content": '{"distribution": {"l1": 0.8, "l2": 0.3, "l3": 0.1, "l4": 0.0}}'
                }
            }]
        }
        dist = parse_response(raw)
        assert dist is not None
        assert abs(sum(dist.values()) - 1.0) < 0.01

    def test_non_json_returns_none(self):
        raw = {
            "choices": [{
                "message": {"content": "I cannot classify this tweet."}
            }]
        }
        assert parse_response(raw) is None

    def test_empty_response_returns_none(self):
        raw = {"choices": [{}]}
        assert parse_response(raw) is None

    def test_zero_sum_returns_none(self):
        raw = {
            "choices": [{
                "message": {
                    "content": '{"distribution": {"l1": 0, "l2": 0, "l3": 0, "l4": 0}}'
                }
            }]
        }
        assert parse_response(raw) is None


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    """Prompt construction from taxonomy."""

    @pytest.fixture
    def taxonomy(self):
        return load_taxonomy()

    def test_contains_all_levels(self, taxonomy):
        prompt = build_prompt(taxonomy, "test tweet")
        assert "L1 (The Map)" in prompt
        assert "L2 (The Persuasion)" in prompt
        assert "L3 (The Signal)" in prompt
        assert "L4 (The Simulacrum)" in prompt

    def test_contains_golden_examples(self, taxonomy):
        prompt = build_prompt(taxonomy, "test tweet")
        assert "GOLDEN EXAMPLES:" in prompt
        assert "Classification:" in prompt

    def test_contains_tweet(self, taxonomy):
        prompt = build_prompt(taxonomy, "hello world this is a test")
        assert "hello world this is a test" in prompt

    def test_truncates_long_tweet(self, taxonomy):
        long_tweet = "x" * 1000
        prompt = build_prompt(taxonomy, long_tweet)
        # Should be truncated to 500 chars
        assert "x" * 500 in prompt
        assert "x" * 501 not in prompt

    def test_requests_json_output(self, taxonomy):
        prompt = build_prompt(taxonomy, "test")
        assert '"distribution"' in prompt
        assert "sum to 1.0" in prompt
