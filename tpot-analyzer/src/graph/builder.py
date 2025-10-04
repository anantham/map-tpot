"""Utilities to build graphs from Community Archive data."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import networkx as nx
import pandas as pd


@dataclass
class GraphBuildResult:
    """Container holding both directed and undirected graph views."""

    directed: nx.DiGraph
    undirected: nx.Graph


_DEFAULT_ACCOUNT_COLUMNS = [
    "account_id",
    "username",
    "account_display_name",
    "created_at",
    "created_via",
    "num_followers",
    "num_following",
    "num_tweets",
    "num_likes",
]

_DEFAULT_PROFILE_COLUMNS = [
    "account_id",
    "bio",
    "website",
    "location",
    "avatar_media_url",
    "header_media_url",
]


def build_graph_from_frames(
    *,
    accounts: pd.DataFrame,
    profiles: pd.DataFrame,
    followers: pd.DataFrame,
    following: pd.DataFrame,
    mutual_only: bool = True,
    min_followers: int = 0,
) -> GraphBuildResult:
    """Construct graphs from pre-loaded DataFrames."""

    account_cols = [col for col in _DEFAULT_ACCOUNT_COLUMNS if col in accounts.columns]
    profile_cols = [col for col in _DEFAULT_PROFILE_COLUMNS if col in profiles.columns]

    accounts_clean = accounts[account_cols].drop_duplicates("account_id")
    profiles_clean = profiles[profile_cols].drop_duplicates("account_id")

    account_lookup = accounts_clean.set_index("account_id").to_dict("index")
    profile_lookup = profiles_clean.set_index("account_id").to_dict("index")

    directed = nx.DiGraph()
    for account_id, attrs in account_lookup.items():
        profile_attrs = profile_lookup.get(account_id, {})
        directed.add_node(account_id, **attrs, **profile_attrs)

    directed = _add_edges(
        directed,
        followers=followers,
        following=following,
        mutual_only=mutual_only,
    )

    if min_followers > 0:
        directed = _filter_min_followers(directed, threshold=min_followers)

    undirected = nx.Graph()
    undirected.add_nodes_from(directed.nodes(data=True))
    undirected.add_edges_from(
        {
            tuple(sorted((u, v))): directed.get_edge_data(u, v)
            for u, v in directed.edges()
            if directed.has_edge(v, u) or not mutual_only
        }
    )

    return GraphBuildResult(directed=directed, undirected=undirected)


def build_graph(
    *,
    fetcher,
    use_cache: bool = True,
    force_refresh: bool = False,
    mutual_only: bool = True,
    min_followers: int = 0,
) -> GraphBuildResult:
    """Fetch necessary tables via the fetcher and build graphs."""

    accounts = fetcher.fetch_accounts(use_cache=use_cache, force_refresh=force_refresh)
    profiles = fetcher.fetch_profiles(use_cache=use_cache, force_refresh=force_refresh)
    followers = fetcher.fetch_followers(use_cache=use_cache, force_refresh=force_refresh)
    following = fetcher.fetch_following(use_cache=use_cache, force_refresh=force_refresh)

    return build_graph_from_frames(
        accounts=accounts,
        profiles=profiles,
        followers=followers,
        following=following,
        mutual_only=mutual_only,
        min_followers=min_followers,
    )


def _add_edges(
    graph: nx.DiGraph,
    *,
    followers: pd.DataFrame,
    following: pd.DataFrame,
    mutual_only: bool,
) -> nx.DiGraph:
    """Add edges from followers/following tables."""

    follower_cols = [col for col in ("follower_account_id", "account_id") if col in followers.columns]
    following_cols = [col for col in ("account_id", "following_account_id") if col in following.columns]

    follower_edges = (
        followers[follower_cols]
        .rename(columns={
            follower_cols[0]: "follower_account_id",
            follower_cols[1]: "account_id",
        })
        .dropna()
        if len(follower_cols) == 2
        else pd.DataFrame(columns=["follower_account_id", "account_id"])
    )
    following_edges = (
        following[following_cols]
        .rename(columns={
            following_cols[0]: "account_id",
            following_cols[1]: "following_account_id",
        })
        .dropna()
        if len(following_cols) == 2
        else pd.DataFrame(columns=["account_id", "following_account_id"])
    )

    if mutual_only:
        follower_set = set(map(tuple, follower_edges.itertuples(index=False, name=None)))
        following_set = set(map(tuple, following_edges.itertuples(index=False, name=None)))

        mutual_edges = follower_set & {(b, a) for a, b in following_set}
        for follower_id, account_id in mutual_edges:
            if graph.has_node(follower_id) and graph.has_node(account_id):
                graph.add_edge(follower_id, account_id)
                graph.add_edge(account_id, follower_id)
        return graph

    # Otherwise add all directed edges
    for follower_id, account_id in follower_edges.itertuples(index=False, name=None):
        if graph.has_node(follower_id) and graph.has_node(account_id):
            graph.add_edge(follower_id, account_id)
    for account_id, following_id in following_edges.itertuples(index=False, name=None):
        if graph.has_node(account_id) and graph.has_node(following_id):
            graph.add_edge(account_id, following_id)
    return graph


def _filter_min_followers(graph: nx.DiGraph, *, threshold: int) -> nx.DiGraph:
    """Prune nodes whose follower count (in-degree) is below threshold."""

    to_remove = [node for node, degree in graph.in_degree() if degree < threshold]
    graph.remove_nodes_from(to_remove)
    return graph
