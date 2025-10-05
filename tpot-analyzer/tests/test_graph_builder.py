from __future__ import annotations

import networkx as nx
import pandas as pd
import pytest

from src.graph.builder import build_graph_from_frames


def make_frames():
    accounts = pd.DataFrame([
        {
            "account_id": "a",
            "username": "user_a",
            "account_display_name": "A",
            "created_at": "2020-01-01",
            "created_via": "web",
            "num_followers": 2,
            "num_following": 1,
            "num_tweets": 3,
            "num_likes": 5,
        },
        {
            "account_id": "b",
            "username": "user_b",
            "account_display_name": "B",
            "created_at": "2020-01-02",
            "created_via": "web",
            "num_followers": 1,
            "num_following": 2,
            "num_tweets": 4,
            "num_likes": 6,
        },
        {
            "account_id": "c",
            "username": "user_c",
            "account_display_name": "C",
            "created_at": "2020-01-03",
            "created_via": "web",
            "num_followers": 0,
            "num_following": 0,
            "num_tweets": 1,
            "num_likes": 1,
        },
    ])

    profiles = pd.DataFrame([
        {"account_id": "a", "bio": "Bio A", "website": None, "location": None, "avatar_media_url": None, "header_media_url": None},
        {"account_id": "b", "bio": "Bio B", "website": None, "location": None, "avatar_media_url": None, "header_media_url": None},
    ])

    followers = pd.DataFrame([
        {"follower_account_id": "b", "account_id": "a"},
        {"follower_account_id": "a", "account_id": "b"},
        {"follower_account_id": "c", "account_id": "a"},
    ])

    following = pd.DataFrame([
        {"account_id": "a", "following_account_id": "b"},
        {"account_id": "b", "following_account_id": "a"},
    ])

    return accounts, profiles, followers, following


@pytest.mark.unit
def test_build_graph_mutual_only():
    accounts, profiles, followers, following = make_frames()
    result = build_graph_from_frames(
        accounts=accounts,
        profiles=profiles,
        followers=followers,
        following=following,
        mutual_only=True,
    )
    assert isinstance(result.directed, nx.DiGraph)
    assert result.directed.has_edge("a", "b")
    assert result.directed.has_edge("b", "a")
    # Edge from c->a should be excluded in mutual-only mode
    assert not result.directed.has_edge("c", "a")
    assert result.undirected.has_edge("a", "b")
    assert "bio" in result.directed.nodes["a"]


@pytest.mark.unit
def test_build_graph_all_edges():
    accounts, profiles, followers, following = make_frames()
    result = build_graph_from_frames(
        accounts=accounts,
        profiles=profiles,
        followers=followers,
        following=following,
        mutual_only=False,
    )
    assert result.directed.has_edge("c", "a")
    assert result.directed.has_edge("a", "b")
    assert result.undirected.has_edge("a", "b")


@pytest.mark.unit
def test_filter_min_followers():
    accounts, profiles, followers, following = make_frames()
    result = build_graph_from_frames(
        accounts=accounts,
        profiles=profiles,
        followers=followers,
        following=following,
        mutual_only=False,
        min_followers=1,
    )
    assert "c" not in result.directed
