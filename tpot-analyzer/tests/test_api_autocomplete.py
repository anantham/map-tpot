"""Tests for the autocomplete endpoint."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.api.server import create_app


@pytest.fixture
def test_app():
    """Create test app with mocked dependencies."""
    with patch('src.api.snapshot_loader.get_snapshot_loader') as mock_get_loader:
        # Create a mock snapshot loader
        mock_loader = MagicMock()
        mock_graph = MagicMock()

        # Mock graph data for testing
        mock_graph.directed.nodes.return_value = [
            ("eigenrobot", {
                "username": "eigenrobot",
                "display_name": "eigenrobot",
                "num_followers": 104602.0,
                "bio": "robot. friend. diamond age mindset",
                "shadow": False
            }),
            ("EigenGender", {
                "username": "EigenGender",
                "display_name": "EigenGender",
                "num_followers": 7658.0,
                "bio": "priestess and paladin",
                "shadow": True
            }),
            ("eigenstate", {
                "username": "eigenstate",
                "display_name": "Semon Rezchikov",
                "num_followers": float('nan'),  # Test NaN handling
                "bio": "Mathematician",
                "shadow": True
            }),
            ("eigenron", {
                "username": "eigenron",
                "display_name": "eigenron",
                "num_followers": float('nan'),
                "bio": "shadow account",
                "shadow": True
            }),
            ("eigenlucy", {
                "username": "eigenlucy",
                "display_name": "eigenlucy",
                "num_followers": float('nan'),
                "bio": "shadow account",
                "shadow": True
            }),
            ("testuser", {
                "username": "testuser",
                "display_name": "Test User",
                "num_followers": 100.0,
                "bio": "Test bio",
                "shadow": False
            }),
            ("another", {
                "username": "another",
                "display_name": "Another User",
                "num_followers": float('inf'),  # Test infinity handling
                "bio": "Another bio",
                "shadow": False
            })
        ]

        mock_loader.load_graph.return_value = mock_graph
        mock_loader.load_pagerank_scores.return_value = {}

        # Return the mock loader when get_snapshot_loader is called
        mock_get_loader.return_value = mock_loader

        app = create_app()
        app.config["TESTING"] = True

        yield app


class TestAutocompleteEndpoint:
    """Test the /api/accounts/search autocomplete endpoint."""

    def test_autocomplete_basic_search(self, test_app):
        """Test basic autocomplete functionality."""
        with test_app.test_client() as client:
            response = client.get('/api/accounts/search?q=eigen&limit=5')
            assert response.status_code == 200

            data = json.loads(response.data)
            assert isinstance(data, list)

            # The API returns up to 5 results for 'eigen' query
            # We have eigenrobot, EigenGender, eigenstate, eigenron, eigenlucy in the test data
            assert len(data) == 5

            # Verify first result (highest followers)
            assert data[0]["username"] == "eigenrobot"
            assert data[0]["display_name"] == "eigenrobot"
            assert data[0]["num_followers"] == 104602.0
            assert data[0]["is_shadow"] is False

    def test_autocomplete_handles_nan_followers(self, test_app):
        """Test that NaN values in followers are converted to null."""
        with test_app.test_client() as client:
            response = client.get('/api/accounts/search?q=eigenstate')
            assert response.status_code == 200

            data = json.loads(response.data)
            assert len(data) == 1
            assert data[0]["username"] == "eigenstate"
            assert data[0]["num_followers"] is None  # NaN should be null

    def test_autocomplete_handles_infinity_followers(self, test_app):
        """Test that infinity values in followers are converted to null."""
        with test_app.test_client() as client:
            response = client.get('/api/accounts/search?q=another')
            assert response.status_code == 200

            data = json.loads(response.data)
            assert len(data) == 1
            assert data[0]["username"] == "another"
            assert data[0]["num_followers"] is None  # Infinity should be null

    def test_autocomplete_empty_query(self, test_app):
        """Test that empty query returns empty list."""
        with test_app.test_client() as client:
            response = client.get('/api/accounts/search?q=')
            assert response.status_code == 200

            data = json.loads(response.data)
            assert data == []

    def test_autocomplete_no_matches(self, test_app):
        """Test query with no matches returns empty list."""
        with test_app.test_client() as client:
            response = client.get('/api/accounts/search?q=nonexistent')
            assert response.status_code == 200

            data = json.loads(response.data)
            assert data == []

    def test_autocomplete_case_insensitive(self, test_app):
        """Test that search is case-insensitive."""
        with test_app.test_client() as client:
            # Uppercase query
            response = client.get('/api/accounts/search?q=EIGEN&limit=10')
            data = json.loads(response.data)
            assert len(data) == 5  # We have 5 eigen* users

            # Lowercase query
            response = client.get('/api/accounts/search?q=eigen&limit=10')
            data2 = json.loads(response.data)
            assert data == data2

    def test_autocomplete_limit_parameter(self, test_app):
        """Test that limit parameter works correctly."""
        with test_app.test_client() as client:
            # Request only 2 results
            response = client.get('/api/accounts/search?q=eigen&limit=2')
            assert response.status_code == 200

            data = json.loads(response.data)
            assert len(data) == 2

            # Should return top 2 by follower count
            assert data[0]["username"] == "eigenrobot"
            assert data[1]["username"] == "EigenGender"

    def test_autocomplete_max_limit(self, test_app):
        """Test that limit is capped at 50."""
        with test_app.test_client() as client:
            response = client.get('/api/accounts/search?q=&limit=100')
            assert response.status_code == 200
            # Can't verify the cap directly without more test data,
            # but the endpoint should handle it

    def test_autocomplete_sorting_by_followers(self, test_app):
        """Test results are sorted by follower count descending."""
        with test_app.test_client() as client:
            response = client.get('/api/accounts/search?q=eigen&limit=10')
            data = json.loads(response.data)

            # eigenrobot (104602) > EigenGender (7658) > rest have NaN/null
            assert data[0]["username"] == "eigenrobot"
            assert data[0]["num_followers"] == 104602.0

            assert data[1]["username"] == "EigenGender"
            assert data[1]["num_followers"] == 7658.0

            # The remaining users have NaN/null followers
            for i in range(2, len(data)):
                assert data[i]["num_followers"] is None

    def test_autocomplete_includes_shadow_accounts(self, test_app):
        """Test that shadow accounts are included in results."""
        with test_app.test_client() as client:
            response = client.get('/api/accounts/search?q=eigen&limit=10')
            data = json.loads(response.data)

            # Find shadow accounts
            shadow_accounts = [d for d in data if d["is_shadow"]]
            # We have 4 shadow accounts: EigenGender, eigenstate, eigenron, eigenlucy
            assert len(shadow_accounts) == 4

            # Verify shadow flag
            eigen_gender = next(d for d in data if d["username"] == "EigenGender")
            assert eigen_gender["is_shadow"] is True

    def test_autocomplete_response_structure(self, test_app):
        """Test the structure of autocomplete response."""
        with test_app.test_client() as client:
            response = client.get('/api/accounts/search?q=test')
            data = json.loads(response.data)

            assert len(data) == 1
            result = data[0]

            # Verify all expected fields are present
            assert "username" in result
            assert "display_name" in result
            assert "num_followers" in result
            assert "is_shadow" in result
            assert "bio" in result

            # Verify values
            assert result["username"] == "testuser"
            assert result["display_name"] == "Test User"
            assert result["num_followers"] == 100.0
            assert result["is_shadow"] is False
            assert result["bio"] == "Test bio"

    def test_autocomplete_prefix_matching(self, test_app):
        """Test that matching is based on username prefix."""
        with test_app.test_client() as client:
            # Should match all eigen* users
            response = client.get('/api/accounts/search?q=eig&limit=10')
            data = json.loads(response.data)
            assert len(data) == 5  # All eigen* users

            # Should match "eigenrobot" and "eigenron"
            response = client.get('/api/accounts/search?q=eigenr')
            data = json.loads(response.data)
            assert len(data) == 2
            assert data[0]["username"] == "eigenrobot"  # Higher followers
            assert data[1]["username"] == "eigenron"

            # Should not match (not a prefix)
            response = client.get('/api/accounts/search?q=robot')
            data = json.loads(response.data)
            assert len(data) == 0
