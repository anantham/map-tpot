"""Unit tests for src/data/golden/schema.py math functions.

Tests the pure mathematical helpers used across the golden dataset pipeline:
split assignment, entropy, distance, and distribution validation.
"""
from __future__ import annotations

import math

import pytest

from src.data.golden.schema import (
    normalized_entropy,
    split_for_tweet,
    total_variation_distance,
    validate_distribution,
)


# ---------------------------------------------------------------------------
# normalized_entropy
# ---------------------------------------------------------------------------


class TestNormalizedEntropy:
    """Entropy of a label distribution, normalized to [0, 1]."""

    def test_uniform_distribution_is_one(self):
        """Maximum entropy: all labels equally likely."""
        dist = {"l1": 0.25, "l2": 0.25, "l3": 0.25, "l4": 0.25}
        assert normalized_entropy(dist) == pytest.approx(1.0, abs=0.001)

    def test_certain_distribution_is_zero(self):
        """Minimum entropy: one label has all probability."""
        dist = {"l1": 1.0, "l2": 0.0, "l3": 0.0, "l4": 0.0}
        assert normalized_entropy(dist) == pytest.approx(0.0, abs=0.001)

    def test_binary_split(self):
        """Two labels at 0.5 each, others zero. Entropy = log(2)/log(4) = 0.5."""
        dist = {"l1": 0.5, "l2": 0.5, "l3": 0.0, "l4": 0.0}
        expected = math.log(2) / math.log(4)  # 0.5
        assert normalized_entropy(dist) == pytest.approx(expected, abs=0.001)

    def test_skewed_distribution(self):
        """Dominated by one label — entropy should be low but nonzero."""
        dist = {"l1": 0.9, "l2": 0.05, "l3": 0.03, "l4": 0.02}
        result = normalized_entropy(dist)
        assert 0.0 < result < 0.5

    def test_result_clamped_to_zero_one(self):
        """Output is always in [0, 1]."""
        for _ in range(100):
            import random
            vals = [random.random() for _ in range(4)]
            total = sum(vals)
            dist = {f"l{i+1}": v / total for i, v in enumerate(vals)}
            result = normalized_entropy(dist)
            assert 0.0 <= result <= 1.0

    def test_all_zero_except_one(self):
        """Each single-label certain distribution should give zero entropy."""
        for label in ["l1", "l2", "l3", "l4"]:
            dist = {k: (1.0 if k == label else 0.0) for k in ["l1", "l2", "l3", "l4"]}
            assert normalized_entropy(dist) == pytest.approx(0.0, abs=0.001)


# ---------------------------------------------------------------------------
# total_variation_distance
# ---------------------------------------------------------------------------


class TestTotalVariationDistance:
    """Half L1 distance between two distributions."""

    def test_identical_distributions_is_zero(self):
        a = {"l1": 0.7, "l2": 0.2, "l3": 0.1, "l4": 0.0}
        assert total_variation_distance(a, a) == pytest.approx(0.0)

    def test_disjoint_distributions_is_one(self):
        """Maximum distance: all mass in different labels."""
        a = {"l1": 1.0, "l2": 0.0, "l3": 0.0, "l4": 0.0}
        b = {"l1": 0.0, "l2": 0.0, "l3": 0.0, "l4": 1.0}
        assert total_variation_distance(a, b) == pytest.approx(1.0)

    def test_symmetric(self):
        a = {"l1": 0.6, "l2": 0.2, "l3": 0.15, "l4": 0.05}
        b = {"l1": 0.3, "l2": 0.4, "l3": 0.2, "l4": 0.1}
        assert total_variation_distance(a, b) == pytest.approx(
            total_variation_distance(b, a)
        )

    def test_known_value(self):
        """Hand-computed: 0.5 * (|0.7-0.3| + |0.1-0.4| + |0.1-0.2| + |0.1-0.1|) = 0.5 * 0.8 = 0.4."""
        a = {"l1": 0.7, "l2": 0.1, "l3": 0.1, "l4": 0.1}
        b = {"l1": 0.3, "l2": 0.4, "l3": 0.2, "l4": 0.1}
        assert total_variation_distance(a, b) == pytest.approx(0.4)

    def test_result_bounded_zero_one(self):
        """TV distance between valid distributions is always in [0, 1]."""
        import random
        for _ in range(100):
            vals_a = [random.random() for _ in range(4)]
            vals_b = [random.random() for _ in range(4)]
            ta, tb = sum(vals_a), sum(vals_b)
            a = {f"l{i+1}": v / ta for i, v in enumerate(vals_a)}
            b = {f"l{i+1}": v / tb for i, v in enumerate(vals_b)}
            result = total_variation_distance(a, b)
            assert 0.0 <= result <= 1.0 + 1e-9


# ---------------------------------------------------------------------------
# validate_distribution
# ---------------------------------------------------------------------------


class TestValidateDistribution:
    """Input validation for label probability distributions."""

    def test_valid_distribution(self):
        dist = {"l1": 0.7, "l2": 0.2, "l3": 0.1, "l4": 0.0}
        result = validate_distribution(dist)
        assert result == {"l1": 0.7, "l2": 0.2, "l3": 0.1, "l4": 0.0}

    def test_coerces_string_numbers(self):
        dist = {"l1": "0.5", "l2": "0.3", "l3": "0.15", "l4": "0.05"}
        result = validate_distribution(dist)
        assert result["l1"] == 0.5

    def test_rejects_missing_label(self):
        with pytest.raises(ValueError, match="missing labels"):
            validate_distribution({"l1": 0.5, "l2": 0.5})

    def test_rejects_extra_label(self):
        with pytest.raises(ValueError, match="unknown labels"):
            validate_distribution({"l1": 0.5, "l2": 0.3, "l3": 0.1, "l4": 0.1, "l5": 0.0})

    def test_rejects_non_dict(self):
        with pytest.raises(ValueError, match="must be an object"):
            validate_distribution([0.25, 0.25, 0.25, 0.25])

    def test_rejects_negative(self):
        with pytest.raises(ValueError, match="must be in"):
            validate_distribution({"l1": -0.1, "l2": 0.5, "l3": 0.3, "l4": 0.3})

    def test_rejects_above_one(self):
        with pytest.raises(ValueError, match="must be in"):
            validate_distribution({"l1": 1.5, "l2": 0.0, "l3": 0.0, "l4": 0.0})

    def test_rejects_bad_sum(self):
        with pytest.raises(ValueError, match="must sum to 1.0"):
            validate_distribution({"l1": 0.5, "l2": 0.5, "l3": 0.5, "l4": 0.5})

    def test_allows_floating_point_tolerance(self):
        """Sum within ±0.001 is accepted."""
        dist = {"l1": 0.7, "l2": 0.2, "l3": 0.0999, "l4": 0.0}
        result = validate_distribution(dist)
        assert abs(sum(result.values()) - 0.9999) < 0.01

    def test_rejects_non_numeric(self):
        with pytest.raises(ValueError, match="must be numeric"):
            validate_distribution({"l1": "hello", "l2": 0.3, "l3": 0.3, "l4": 0.4})


# ---------------------------------------------------------------------------
# split_for_tweet (canonical tests — also exercised in test_classify_tweets.py)
# ---------------------------------------------------------------------------


class TestSplitForTweet:
    """Deterministic split assignment via SHA256 hash."""

    def test_pure_function(self):
        """Same input always produces same output."""
        for tid in ["abc", "12345", "tweet_999"]:
            assert split_for_tweet(tid) == split_for_tweet(tid)

    def test_distribution_70_15_15(self):
        """10K samples approximate expected distribution."""
        from collections import Counter
        c = Counter(split_for_tweet(str(i)) for i in range(10000))
        assert 6700 < c["train"] < 7300
        assert 1200 < c["dev"] < 1800
        assert 1200 < c["test"] < 1800

    def test_different_ids_can_differ(self):
        """Not all IDs map to the same split (sanity check)."""
        splits = {split_for_tweet(str(i)) for i in range(100)}
        assert len(splits) > 1
