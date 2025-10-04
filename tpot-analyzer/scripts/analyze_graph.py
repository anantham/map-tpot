#!/usr/bin/env python
"""CLI for running graph metrics on cached Community Archive data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

import networkx as nx

from src.config import get_cache_settings
from src.data.fetcher import CachedDataFetcher
from src.graph import (
    GraphBuildResult,
    compute_betweenness,
    compute_composite_score,
    compute_engagement_scores,
    compute_louvain_communities,
    compute_personalized_pagerank,
    extract_usernames_from_html,
    load_seed_candidates,
    build_graph,
)

DEFAULT_OUTPUT = Path("analysis_output.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze TPOT follow graph")
    parser.add_argument(
        "--seeds",
        nargs="*",
        default=[],
        help="Seed usernames (without @). Defaults to preset seeds if omitted.",
    )
    parser.add_argument(
        "--seed-html",
        type=Path,
        help="Path to HTML file containing Twitter list members.",
    )
    parser.add_argument(
        "--mutual-only",
        action="store_true",
        help="Use only mutual follow edges.",
    )
    parser.add_argument(
        "--min-followers",
        type=int,
        default=0,
        help="Minimum in-degree required to keep a node.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Where to write JSON summary.",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.85,
        help="PageRank damping factor (alpha).",
    )
    parser.add_argument(
        "--weights",
        type=float,
        nargs=3,
        default=(0.4, 0.3, 0.3),
        metavar=("ALPHA", "BETA", "GAMMA"),
        help="Weights for pagerank, betweenness, engagement.",
    )
    parser.add_argument(
        "--resolution",
        type=float,
        default=1.0,
        help="Louvain resolution parameter.",
    )
    return parser.parse_args()


def load_seeds(args: argparse.Namespace) -> List[str]:
    seeds = load_seed_candidates(additional=args.seeds)
    if args.seed_html and args.seed_html.exists():
        seeds.update(extract_usernames_from_html(args.seed_html.read_text()))
    return sorted(seeds)


def _resolve_seeds(graph: GraphBuildResult, seeds: List[str]) -> List[str]:
    directed = graph.directed
    id_seeds = {seed for seed in seeds if seed in directed}
    username_to_id = {
        data.get("username", "").lower(): node
        for node, data in directed.nodes(data=True)
        if data.get("username")
    }
    for seed in seeds:
        lower = seed.lower()
        if lower in username_to_id:
            id_seeds.add(username_to_id[lower])
    return sorted(id_seeds)


def run_metrics(graph: GraphBuildResult, seeds: List[str], args: argparse.Namespace) -> dict:
    directed = graph.directed
    undirected = graph.undirected

    resolved_seeds = _resolve_seeds(graph, seeds)

    pagerank = compute_personalized_pagerank(directed, seeds=resolved_seeds, alpha=args.alpha)
    betweenness = compute_betweenness(undirected)
    engagement = compute_engagement_scores(undirected)
    composite = compute_composite_score(
        pagerank=pagerank,
        betweenness=betweenness,
        engagement=engagement,
        weights=tuple(args.weights),
    )
    communities = compute_louvain_communities(undirected, resolution=args.resolution)

    edges = []
    for u, v in directed.edges():
        edges.append(
            {
                "source": u,
                "target": v,
                "mutual": directed.has_edge(v, u),
            }
        )

    nodes_payload = {
        node: {
            "username": data.get("username"),
            "display_name": data.get("account_display_name"),
            "num_followers": data.get("num_followers"),
            "num_following": data.get("num_following"),
            "num_likes": data.get("num_likes"),
            "num_tweets": data.get("num_tweets"),
            "bio": data.get("bio"),
            "location": data.get("location"),
        }
        for node, data in directed.nodes(data=True)
    }

    return {
        "seeds": seeds,
        "resolved_seeds": resolved_seeds,
        "metrics": {
            "pagerank": pagerank,
            "betweenness": betweenness,
            "engagement": engagement,
            "composite": composite,
            "communities": communities,
        },
        "top": {
            "pagerank": sorted(pagerank.items(), key=lambda x: x[1], reverse=True)[:20],
            "betweenness": sorted(betweenness.items(), key=lambda x: x[1], reverse=True)[:20],
            "composite": sorted(composite.items(), key=lambda x: x[1], reverse=True)[:20],
        },
        "graph": {
            "nodes": nodes_payload,
            "edges": edges,
            "directed_nodes": directed.number_of_nodes(),
            "directed_edges": directed.number_of_edges(),
            "undirected_edges": undirected.number_of_edges(),
        },
    }


def main() -> None:
    args = parse_args()
    seeds = load_seeds(args)

    cache_settings = get_cache_settings()
    with CachedDataFetcher(cache_db=cache_settings.path) as fetcher:
        graph = build_graph(
            fetcher=fetcher,
            mutual_only=args.mutual_only,
            min_followers=args.min_followers,
        )

    summary = run_metrics(graph, seeds, args)

    args.output.write_text(json.dumps(summary, indent=2))
    print(f"Wrote summary to {args.output}")


if __name__ == "__main__":
    main()
