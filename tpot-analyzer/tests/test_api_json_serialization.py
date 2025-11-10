"""Tests for JSON serialization with NaN/Infinity handling."""
from __future__ import annotations

import json
import math
import pytest
from unittest.mock import patch, MagicMock

from src.api.server import SafeJSONEncoder, safe_jsonify


class TestSafeJSONEncoder:
    """Test SafeJSONEncoder handles NaN/Infinity correctly."""

    def test_encode_nan_value(self):
        """Test that NaN values are converted to null."""
        encoder = SafeJSONEncoder()
        data = {"value": float('nan')}
        result = json.loads(encoder.encode(data))
        assert result["value"] is None

    def test_encode_infinity_value(self):
        """Test that Infinity values are converted to null."""
        encoder = SafeJSONEncoder()
        data = {"value": float('inf')}
        result = json.loads(encoder.encode(data))
        assert result["value"] is None

    def test_encode_negative_infinity_value(self):
        """Test that negative Infinity values are converted to null."""
        encoder = SafeJSONEncoder()
        data = {"value": float('-inf')}
        result = json.loads(encoder.encode(data))
        assert result["value"] is None

    def test_encode_nested_nan_in_dict(self):
        """Test that NaN values in nested dicts are handled."""
        encoder = SafeJSONEncoder()
        data = {
            "outer": {
                "inner": {
                    "value": float('nan'),
                    "normal": 42
                }
            }
        }
        result = json.loads(encoder.encode(data))
        assert result["outer"]["inner"]["value"] is None
        assert result["outer"]["inner"]["normal"] == 42

    def test_encode_nan_in_list(self):
        """Test that NaN values in lists are handled."""
        encoder = SafeJSONEncoder()
        data = {
            "values": [1.0, float('nan'), 3.0, float('inf'), float('-inf')]
        }
        result = json.loads(encoder.encode(data))
        assert result["values"] == [1.0, None, 3.0, None, None]

    def test_encode_complex_nested_structure(self):
        """Test complex nested structure with multiple NaN/Inf values."""
        encoder = SafeJSONEncoder()
        data = {
            "users": [
                {
                    "username": "user1",
                    "followers": 1000,
                    "ratio": 1.5
                },
                {
                    "username": "user2",
                    "followers": float('nan'),
                    "ratio": float('inf')
                },
                {
                    "username": "user3",
                    "followers": 500,
                    "ratio": float('-inf')
                }
            ],
            "metadata": {
                "total": float('nan'),
                "average": 100.5
            }
        }
        result = json.loads(encoder.encode(data))

        assert result["users"][0]["ratio"] == 1.5
        assert result["users"][1]["followers"] is None
        assert result["users"][1]["ratio"] is None
        assert result["users"][2]["ratio"] is None
        assert result["metadata"]["total"] is None
        assert result["metadata"]["average"] == 100.5

    def test_encode_preserves_normal_values(self):
        """Test that normal values are preserved."""
        encoder = SafeJSONEncoder()
        data = {
            "string": "hello",
            "integer": 42,
            "float": 3.14,
            "boolean": True,
            "null": None,
            "list": [1, 2, 3],
            "dict": {"nested": "value"}
        }
        result = json.loads(encoder.encode(data))
        assert result == data

    def test_safe_jsonify_with_nan(self):
        """Test safe_jsonify function handles NaN."""
        data = {"ratio": float('nan'), "count": 100}
        response = safe_jsonify(data)
        result = json.loads(response.data)
        assert result["ratio"] is None
        assert result["count"] == 100
        assert response.mimetype == 'application/json'


class TestAutocompleteRegression:
    """Tests to prevent regression of autocomplete NaN bug."""

    def test_autocomplete_handles_nan_followers(self):
        """Test that autocomplete endpoint handles NaN in num_followers."""
        # Simulate the data structure that caused the original bug
        mock_graph = MagicMock()
        mock_graph.directed.nodes.return_value = [
            ("user1", {
                "username": "user1",
                "display_name": "User One",
                "num_followers": 1000.0,
                "bio": "Test bio",
                "shadow": False
            }),
            ("user2", {
                "username": "user2",
                "display_name": "User Two",
                "num_followers": float('nan'),  # This was causing the bug
                "bio": "Another bio",
                "shadow": True
            }),
            ("user3", {
                "username": "user3",
                "display_name": "User Three",
                "num_followers": float('inf'),  # Also problematic
                "bio": "Third bio",
                "shadow": False
            })
        ]

        encoder = SafeJSONEncoder()
        matches = [
            {
                "username": "user1",
                "display_name": "User One",
                "num_followers": 1000.0,
                "is_shadow": False,
                "bio": "Test bio"
            },
            {
                "username": "user2",
                "display_name": "User Two",
                "num_followers": float('nan'),
                "is_shadow": True,
                "bio": "Another bio"
            },
            {
                "username": "user3",
                "display_name": "User Three",
                "num_followers": float('inf'),
                "is_shadow": False,
                "bio": "Third bio"
            }
        ]

        # This should not raise an exception
        result = json.loads(encoder.encode(matches))

        # Verify NaN/Inf converted to null
        assert result[0]["num_followers"] == 1000.0
        assert result[1]["num_followers"] is None
        assert result[2]["num_followers"] is None


class TestDiscoveryEndpointRegression:
    """Tests to prevent regression of discovery endpoint NaN bug."""

    def test_discovery_handles_nan_ratio(self):
        """Test that discovery endpoint handles NaN in follower_following_ratio."""
        # Simulate the division by zero case that caused the bug
        recommendation = {
            "handle": "testuser",
            "display_name": "Test User",
            "metadata": {
                "num_followers": 100,
                "num_following": 0,  # Division by zero case
                "follower_following_ratio": float('nan'),  # Result of division
                "is_shadow": False,
                "bio": "Test bio"
            },
            "scores": {
                "neighbor_overlap": 0.5,
                "pagerank": float('nan'),  # Could also be NaN
                "community": 0.3,
                "path_distance": 0.2
            }
        }

        encoder = SafeJSONEncoder()
        result = json.loads(encoder.encode(recommendation))

        # Verify NaN values converted to null
        assert result["metadata"]["follower_following_ratio"] is None
        assert result["scores"]["pagerank"] is None
        assert result["scores"]["neighbor_overlap"] == 0.5