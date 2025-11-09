"""Utilities to build graphs from Community Archive data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

import networkx as nx
import pandas as pd

from src.data.shadow_store import ShadowStore
from src.performance_profiler import profile_phase, profile_operation


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
    include_shadow: bool = False,
    shadow_store: Optional[ShadowStore] = None,
) -> GraphBuildResult:
    """Construct graphs from pre-loaded DataFrames."""

    with profile_operation("build_graph_from_frames", {
        "accounts": len(accounts),
        "profiles": len(profiles),
        "followers": len(followers),
        "following": len(following),
        "include_shadow": include_shadow
    }, verbose=False) as report:

        with profile_phase("prepare_dataframes", "build_graph_from_frames"):
            account_cols = [col for col in _DEFAULT_ACCOUNT_COLUMNS if col in accounts.columns]
            profile_cols = [col for col in _DEFAULT_PROFILE_COLUMNS if col in profiles.columns]

            accounts_clean = accounts[account_cols].drop_duplicates("account_id")
            profiles_clean = profiles[profile_cols].drop_duplicates("account_id")

            account_lookup = accounts_clean.set_index("account_id").to_dict("index")
            profile_lookup = profiles_clean.set_index("account_id").to_dict("index")

        with profile_phase("create_nodes", "build_graph_from_frames", {"node_count": len(account_lookup)}):
            directed = nx.DiGraph()
            for account_id, attrs in account_lookup.items():
                profile_attrs = profile_lookup.get(account_id, {})
                directed.add_node(account_id, **attrs, **profile_attrs)

        with profile_phase("add_edges", "build_graph_from_frames", {"mutual_only": mutual_only}):
            directed = _add_edges(
                directed,
                followers=followers,
                following=following,
                mutual_only=mutual_only,
            )

        if min_followers > 0:
            with profile_phase("filter_min_followers", "build_graph_from_frames", {"threshold": min_followers}):
                directed = _filter_min_followers(directed, threshold=min_followers)

        if include_shadow and shadow_store:
            with profile_phase("inject_shadow_data", "build_graph_from_frames"):
                _inject_shadow_data(directed, shadow_store)

        with profile_phase("build_undirected_view", "build_graph_from_frames"):
            undirected = _build_undirected_view(directed, mutual_only=mutual_only)

        return GraphBuildResult(directed=directed, undirected=undirected)


def build_graph(
    *,
    fetcher,
    use_cache: bool = True,
    force_refresh: bool = False,
    mutual_only: bool = True,
    min_followers: int = 0,
    include_shadow: bool = False,
    include_archive: bool = True,
    shadow_store: Optional[ShadowStore] = None,
) -> GraphBuildResult:
    """Fetch necessary tables via the fetcher and build graphs."""

    with profile_operation("build_graph", {"include_shadow": include_shadow, "include_archive": include_archive}, verbose=False):
        with profile_phase("fetch_data", "build_graph"):
            accounts = fetcher.fetch_accounts(use_cache=use_cache, force_refresh=force_refresh)
            profiles = fetcher.fetch_profiles(use_cache=use_cache, force_refresh=force_refresh)
            followers = fetcher.fetch_followers(use_cache=use_cache, force_refresh=force_refresh)
            following = fetcher.fetch_following(use_cache=use_cache, force_refresh=force_refresh)

            # Fetch archive data if enabled
            if include_archive:
                archive_followers = fetcher.fetch_archive_followers()
                archive_following = fetcher.fetch_archive_following()

                # Merge archive data with REST data
                # NetworkX will handle duplicate edges naturally (last write wins for attributes)
                if not archive_followers.empty:
                    followers = pd.concat([followers, archive_followers], ignore_index=True)
                if not archive_following.empty:
                    following = pd.concat([following, archive_following], ignore_index=True)

        return build_graph_from_frames(
            accounts=accounts,
            profiles=profiles,
            followers=followers,
            following=following,
            mutual_only=mutual_only,
            min_followers=min_followers,
            include_shadow=include_shadow,
            shadow_store=shadow_store,
        )


def _build_undirected_view(directed: nx.DiGraph, *, mutual_only: bool) -> nx.Graph:
    undirected = nx.Graph()
    undirected.add_nodes_from(directed.nodes(data=True))
    for u, v, data in directed.edges(data=True):
        if mutual_only and not directed.has_edge(v, u):
            continue
        weight = data.copy()
        undirected.add_edge(*sorted((u, v)), **weight)
    return undirected


def _inject_shadow_data(graph: nx.DiGraph, store: ShadowStore) -> None:
    """Augment directed graph with shadow accounts and edges."""

    now = datetime.utcnow()
    accounts = store.fetch_accounts()
    for record in accounts:
        node_id = str(record["account_id"])
        if graph.has_node(node_id):
            graph.nodes[node_id].setdefault("provenance", "archive")
            continue
        graph.add_node(
            node_id,
            username=record.get("username"),
            account_display_name=record.get("display_name"),
            bio=record.get("bio"),
            location=record.get("location"),
            num_followers=record.get("followers_count"),
            num_following=record.get("following_count"),
            provenance=record.get("source_channel", "shadow"),
            shadow=True,
            shadow_scrape_stats=record.get("scrape_stats"),
            fetched_at=record.get("fetched_at", now),
        )

    edges = store.fetch_edges()
    for record in edges:
        source = str(record["source_id"])
        target = str(record["target_id"])
        if not graph.has_node(source):
            graph.add_node(source, provenance="shadow", shadow=True)
        if not graph.has_node(target):
            graph.add_node(target, provenance="shadow", shadow=True)
        attributes = {
            "provenance": record.get("source_channel", "shadow"),
            "direction_label": record.get("direction"),
            "shadow": True,
            "metadata": record.get("metadata"),
            "fetched_at": record.get("fetched_at") or now,
        }
        graph.add_edge(source, target, **attributes)


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
