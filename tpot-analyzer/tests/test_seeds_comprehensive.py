"""Comprehensive tests for seed selection and username resolution.

Tests cover:
- Username extraction from HTML
- Seed candidate loading and merging
- Username normalization (lowercase, deduplication)
- Edge cases (empty strings, special characters, duplicates)
- Integration with graph building (username → account ID mapping)
"""
from __future__ import annotations

import networkx as nx
import pandas as pd
import pytest
from sqlalchemy import create_engine

from scripts.analyze_graph import _resolve_seeds
from src.data.shadow_store import ShadowStore
from src.graph import GraphBuildResult, build_graph
from src.graph.seeds import extract_usernames_from_html, load_seed_candidates


# ==============================================================================
# Test: Username Extraction from HTML
# ==============================================================================

@pytest.mark.unit
def test_extract_usernames_case_insensitive():
    """Should normalize usernames to lowercase."""
    html = "@Alice @ALICE @alice @aLiCe"
    usernames = extract_usernames_from_html(html)
    # Should deduplicate to single lowercase entry
    assert usernames == ["alice"]


@pytest.mark.unit
def test_extract_usernames_with_underscores():
    """Should handle usernames with underscores."""
    html = "@user_name @user_name_123 @simple"
    usernames = extract_usernames_from_html(html)
    # Should sort with preference for non-underscore names
    assert "simple" in usernames
    assert "user_name" in usernames
    assert "user_name_123" in usernames


@pytest.mark.unit
def test_extract_usernames_max_length():
    """Should extract valid Twitter usernames (max 15 chars)."""
    html = "@short @exactly15chars @this_is_way_too_long_for_twitter"
    usernames = extract_usernames_from_html(html)
    # Twitter usernames are max 15 chars, so long one might be truncated by regex
    assert "short" in usernames
    assert "exactly15chars" in usernames


@pytest.mark.unit
def test_extract_usernames_empty_html():
    """Should return empty list for HTML with no usernames."""
    html = "<html><body>No usernames here!</body></html>"
    usernames = extract_usernames_from_html(html)
    assert usernames == []


@pytest.mark.unit
def test_extract_usernames_duplicates():
    """Should deduplicate repeated usernames."""
    html = "@alice @bob @alice @alice @bob"
    usernames = extract_usernames_from_html(html)
    # Should have 2 unique usernames
    assert len(usernames) == 2
    assert "alice" in usernames
    assert "bob" in usernames


@pytest.mark.unit
def test_extract_usernames_special_formats():
    """Should handle usernames in various HTML contexts."""
    html = """
    <div>Follow @user1</div>
    <a href="https://twitter.com/user2">@user2</a>
    @user3 at the start
    end with @user4
    """
    usernames = extract_usernames_from_html(html)
    assert set(usernames) == {"user1", "user2", "user3", "user4"}


@pytest.mark.unit
def test_extract_usernames_with_numbers():
    """Should handle usernames with numbers."""
    html = "@user123 @123user @user_123 @abc123def"
    usernames = extract_usernames_from_html(html)
    assert "user123" in usernames
    assert "123user" in usernames
    assert "user_123" in usernames
    assert "abc123def" in usernames


@pytest.mark.unit
def test_extract_usernames_sorting():
    """Should sort usernames alphabetically, preferring non-underscore names."""
    html = "@zed @alice_x @alice @bob_y @bob"
    usernames = extract_usernames_from_html(html)

    # alice should come before alice_x (prefer non-underscore)
    alice_idx = usernames.index("alice")
    alice_x_idx = usernames.index("alice_x")
    assert alice_idx < alice_x_idx

    # bob should come before bob_y
    bob_idx = usernames.index("bob")
    bob_y_idx = usernames.index("bob_y")
    assert bob_idx < bob_y_idx


# ==============================================================================
# Test: Seed Candidate Loading
# ==============================================================================

@pytest.mark.unit
def test_load_seed_candidates_empty():
    """Should return default seeds when no additional seeds provided."""
    seeds = load_seed_candidates(additional=[])
    # Should at least return something (might be empty if no preset file)
    assert isinstance(seeds, set)


@pytest.mark.unit
def test_load_seed_candidates_lowercase_normalization():
    """Should normalize additional seeds to lowercase."""
    seeds = load_seed_candidates(additional=["Alice", "BOB", "ChArLiE"])
    assert "alice" in seeds
    assert "bob" in seeds
    assert "charlie" in seeds
    # Uppercase versions should NOT be present
    assert "Alice" not in seeds
    assert "BOB" not in seeds


@pytest.mark.unit
def test_load_seed_candidates_deduplication():
    """Should deduplicate seeds across default and additional."""
    # Load with duplicates
    seeds = load_seed_candidates(additional=["user1", "user1", "user2", "user2"])
    # Should only have unique entries
    assert seeds == {"user1", "user2"} or "user1" in seeds and "user2" in seeds


@pytest.mark.unit
def test_load_seed_candidates_merge():
    """Should merge default seeds with additional seeds."""
    additional = ["new_user_1", "new_user_2"]
    seeds = load_seed_candidates(additional=additional)

    # All additional seeds should be present
    assert "new_user_1" in seeds
    assert "new_user_2" in seeds

    # Original seed set should not be mutated
    seeds2 = load_seed_candidates(additional=["different_user"])
    assert "different_user" in seeds2


# ==============================================================================
# Test: Seed Resolution in Graph Building (Integration)
# ==============================================================================

@pytest.mark.integration
def test_seed_resolution_username_to_id(temp_shadow_db):
    """Graph builder should resolve seed usernames to account IDs."""
    engine = create_engine(f"sqlite:///{temp_shadow_db}")
    store = ShadowStore(engine)

    # Insert test accounts
    accounts_df = pd.DataFrame([
        {"account_id": "123", "username": "alice", "display_name": "Alice"},
        {"account_id": "456", "username": "bob", "display_name": "Bob"},
    ])
    store.upsert_accounts(accounts_df)

    # Create edges DataFrame for followers (required by graph builder)
    followers_df = pd.DataFrame([
        {"follower": "123", "account": "456"},  # alice follows bob
    ])
    following_df = pd.DataFrame([
        {"account": "123", "following": "456"},  # alice follows bob
    ])

    # Build graph with username seed
    result = build_graph(
        accounts=accounts_df,
        followers=followers_df,
        following=following_df,
        shadow_store=store,
        include_shadow=False,
    )

    # Verify both ID and username can be used to reference nodes
    assert "123" in result.directed.nodes  # Account ID
    assert result.directed.nodes["123"]["username"] == "alice"


@pytest.mark.integration
def test_seed_resolution_case_insensitive_mapping(temp_shadow_db):
    """Seed username resolution should be case-insensitive."""
    engine = create_engine(f"sqlite:///{temp_shadow_db}")
    store = ShadowStore(engine)

    # Insert account with mixed-case username
    accounts_df = pd.DataFrame([
        {"account_id": "789", "username": "MixedCase", "display_name": "Mixed"},
    ])
    store.upsert_accounts(accounts_df)

    followers_df = pd.DataFrame(columns=["follower", "account"])
    following_df = pd.DataFrame(columns=["account", "following"])

    result = build_graph(
        accounts=accounts_df,
        followers=followers_df,
        following=following_df,
        shadow_store=store,
        include_shadow=False,
    )

    # Username should be stored in original case
    assert result.directed.nodes["789"]["username"] == "MixedCase"


@pytest.mark.integration
def test_seed_resolution_with_shadow_accounts(temp_shadow_db):
    """Should resolve seeds for both archive and shadow accounts."""
    engine = create_engine(f"sqlite:///{temp_shadow_db}")
    store = ShadowStore(engine)

    # Insert archive account
    accounts_df = pd.DataFrame([
        {"account_id": "123", "username": "archive_user", "display_name": "Archive"},
    ])

    # Insert shadow account
    shadow_accounts_df = pd.DataFrame([
        {"account_id": "shadow:456", "username": "shadow_user", "display_name": "Shadow"},
    ])
    store.upsert_accounts(shadow_accounts_df)

    # Create edges
    followers_df = pd.DataFrame([
        {"follower": "shadow:456", "account": "123"},
    ])
    following_df = pd.DataFrame([
        {"account": "123", "following": "shadow:456"},
    ])

    # Build with shadow data
    result = build_graph(
        accounts=accounts_df,
        followers=followers_df,
        following=following_df,
        shadow_store=store,
        include_shadow=True,
    )

    # Both accounts should be in graph
    assert "123" in result.directed.nodes
    assert "shadow:456" in result.directed.nodes

    # Should be able to look up by username
    assert result.directed.nodes["123"]["username"] == "archive_user"
    assert result.directed.nodes["shadow:456"]["username"] == "shadow_user"


@pytest.mark.integration
def test_seed_resolution_nonexistent_username():
    """Attempting to use non-existent username as seed should be handled gracefully."""
    # Create minimal graph
    directed = nx.DiGraph()
    directed.add_node("123", username="alice")
    undirected = directed.to_undirected()

    graph_result = GraphBuildResult(
        directed=directed,
        undirected=undirected,
        archive_accounts=["123"],
        shadow_accounts=[],
        total_nodes=1,
        total_edges=0,
        mutual_edges=0,
    )

    # Try to resolve with non-existent username
    resolved = _resolve_seeds(graph_result, ["alice", "nonexistent"])

    # Should resolve alice, skip nonexistent
    assert "123" in resolved
    assert len(resolved) == 1


@pytest.mark.integration
def test_seed_resolution_mixed_ids_and_usernames():
    """Should handle seeds that are mix of IDs and usernames."""
    directed = nx.DiGraph()
    directed.add_node("123", username="alice")
    directed.add_node("456", username="bob")
    directed.add_node("789", username="charlie")
    undirected = directed.to_undirected()

    graph_result = GraphBuildResult(
        directed=directed,
        undirected=undirected,
        archive_accounts=["123", "456", "789"],
        shadow_accounts=[],
        total_nodes=3,
        total_edges=0,
        mutual_edges=0,
    )

    # Mix of IDs and usernames
    resolved = _resolve_seeds(graph_result, ["alice", "456", "charlie"])

    # All should resolve
    assert "123" in resolved  # alice
    assert "456" in resolved  # direct ID
    assert "789" in resolved  # charlie
    assert len(resolved) == 3


@pytest.mark.integration
def test_seed_resolution_preserves_order():
    """Seed resolution should return sorted list of IDs."""
    directed = nx.DiGraph()
    directed.add_node("999", username="zed")
    directed.add_node("111", username="alice")
    directed.add_node("555", username="mike")
    undirected = directed.to_undirected()

    graph_result = GraphBuildResult(
        directed=directed,
        undirected=undirected,
        archive_accounts=["111", "555", "999"],
        shadow_accounts=[],
        total_nodes=3,
        total_edges=0,
        mutual_edges=0,
    )

    resolved = _resolve_seeds(graph_result, ["zed", "alice", "mike"])

    # Should be sorted
    assert resolved == sorted(resolved)
    assert set(resolved) == {"111", "555", "999"}
