#!/usr/bin/env python
"""CLI for running graph metrics on cached Community Archive data."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import networkx as nx

from src.config import get_cache_settings
from src.data.fetcher import CachedDataFetcher
from src.data.shadow_store import get_shadow_store
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
README_PATH = Path("README.md")
MARKER_START = "<!-- AUTO:GRAPH_SNAPSHOT -->"
MARKER_END = "<!-- /AUTO:GRAPH_SNAPSHOT -->"


def _serialize_datetime(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


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
    parser.add_argument(
        "--global-pagerank",
        action="store_true",
        help="Also compute global (non-personalized) PageRank for comparison.",
    )
    parser.add_argument(
        "--include-shadow",
        action="store_true",
        help="Include shadow accounts/edges from enrichment cache.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print JSON summary to stdout instead of writing to a file.",
    )
    parser.add_argument(
        "--update-readme",
        action="store_true",
        help="Update README data snapshot (will prompt if marker is missing).",
    )
    parser.add_argument(
        "--seed-list",
        type=str,
        default=None,
        help="Name of a saved seed list (defaults to the active list synced from the UI).",
    )
    return parser.parse_args()


def load_seeds(args: argparse.Namespace) -> List[str]:
    seeds = load_seed_candidates(additional=args.seeds, preset=args.seed_list)
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
    global_pagerank = None
    if args.global_pagerank:
        global_pagerank = compute_personalized_pagerank(directed, seeds=[], alpha=args.alpha)
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
        data = directed.get_edge_data(u, v, default={})
        edges.append(
            {
                "source": u,
                "target": v,
                "mutual": directed.has_edge(v, u),
                "provenance": data.get("provenance", "archive"),
                "shadow": data.get("shadow", False),
                "metadata": data.get("metadata"),
                "direction_label": data.get("direction_label"),
                "fetched_at": _serialize_datetime(data.get("fetched_at")),
            }
        )

    nodes_payload = {}
    for node, data in directed.nodes(data=True):
        nodes_payload[node] = {
            "username": data.get("username"),
            "display_name": data.get("account_display_name") or data.get("display_name"),
            "num_followers": data.get("num_followers"),
            "num_following": data.get("num_following"),
            "num_likes": data.get("num_likes"),
            "num_tweets": data.get("num_tweets"),
            "bio": data.get("bio"),
            "location": data.get("location"),
            "provenance": data.get("provenance", "archive"),
            "shadow": data.get("shadow", False),
            "shadow_scrape_stats": data.get("shadow_scrape_stats"),
            "fetched_at": _serialize_datetime(data.get("fetched_at")),
        }

    return {
        "seeds": seeds,
        "resolved_seeds": resolved_seeds,
        "metrics": {
            "pagerank": pagerank,
            **({"global_pagerank": global_pagerank} if global_pagerank is not None else {}),
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


def _compute_coverage_stats(shadow_store) -> Optional[Dict[str, float]]:
    """Estimate coverage percentages from recorded scrape runs.

    Returns average coverage (captured/claimed) for following/followers/
    followers_you_follow across all recorded runs. Values expressed as
    percentages (0-100). Returns None if enrichment data is unavailable.
    """

    if shadow_store is None:
        return None

    totals = {
        "following": {"captured": 0, "claimed": 0},
        "followers": {"captured": 0, "claimed": 0},
        "followers_you_follow": {"captured": 0, "claimed": 0},
    }

    for run in shadow_store.get_recent_scrape_runs(days=3650):
        mappings = (
            ("following", run.following_captured, run.following_claimed_total),
            ("followers", run.followers_captured, run.followers_claimed_total),
            (
                "followers_you_follow",
                run.followers_you_follow_captured,
                run.followers_you_follow_claimed_total,
            ),
        )
        for key, captured, claimed in mappings:
            if captured is None or claimed in (None, 0):
                continue
            totals[key]["captured"] += captured
            totals[key]["claimed"] += claimed

    coverage: Dict[str, float] = {}
    for key, values in totals.items():
        claimed_total = values["claimed"]
        if claimed_total > 0:
            coverage[key] = (values["captured"] / claimed_total) * 100

    return coverage or None


def _format_snapshot(summary: dict, include_shadow: bool, coverage: Optional[Dict[str, float]]) -> str:
    directed_nodes = summary["graph"]["directed_nodes"]
    directed_edges = summary["graph"]["directed_edges"]
    parts = [
        f"Directed graph: {directed_nodes:,} nodes / {directed_edges:,} edges",
        f"shadow included: {'yes' if include_shadow else 'no'}",
    ]

    if coverage:
        label_map = {
            "following": "following",
            "followers": "followers",
            "followers_you_follow": "mutual follows",
        }
        cov_parts = [
            f"{label_map[key]} {value:.1f}%"
            for key, value in coverage.items()
            if value is not None and key in label_map
        ]
        if cov_parts:
            parts.append("average coverage " + ", ".join(cov_parts))

    parts.append(f"generated {datetime.utcnow().strftime('%Y-%m-%d')}")
    return f"_{'; '.join(parts)}._"


def _insert_snapshot_section(readme_text: str, block: str) -> str:
    section = f"## Data Snapshot\n\n{block}\n"
    marker = "## Project Status"
    idx = readme_text.find(marker)
    if idx == -1:
        return readme_text.rstrip() + "\n\n" + section + "\n"

    next_idx = readme_text.find("\n## ", idx + len(marker))
    if next_idx == -1:
        return readme_text.rstrip() + "\n\n" + section + "\n"

    return readme_text[:next_idx] + "\n\n" + section + "\n" + readme_text[next_idx:]


def update_readme_snapshot(
    summary: dict,
    *,
    include_shadow: bool,
    coverage: Optional[Dict[str, float]],
    readme_path: Path = README_PATH,
) -> bool:
    if not readme_path.exists():
        print("README not found; skipping README update.")
        return False

    snapshot_line = _format_snapshot(summary, include_shadow, coverage)
    block = f"{MARKER_START}\n{snapshot_line}\n{MARKER_END}"

    text = readme_path.read_text()
    if MARKER_START in text and MARKER_END in text:
        pattern = re.compile(r"<!-- AUTO:GRAPH_SNAPSHOT -->.*?<!-- /AUTO:GRAPH_SNAPSHOT -->", re.DOTALL)
        updated = pattern.sub(block, text)
        readme_path.write_text(updated)
        return True

    try:
        response = input(
            "README snapshot marker not found. Insert Data Snapshot section now? [y/N]: "
        ).strip().lower()
    except EOFError:
        response = ""

    if response != "y":
        print("Skipped README update; marker block not present.")
        return False

    updated_text = _insert_snapshot_section(text, block)
    readme_path.write_text(updated_text)
    return True


def main() -> None:
    args = parse_args()
    seeds = load_seeds(args)

    cache_settings = get_cache_settings()
    with CachedDataFetcher(cache_db=cache_settings.path) as fetcher:
        shadow_store = get_shadow_store(fetcher.engine) if args.include_shadow else None
        graph = build_graph(
            fetcher=fetcher,
            mutual_only=args.mutual_only,
            min_followers=args.min_followers,
            include_shadow=args.include_shadow,
            shadow_store=shadow_store,
        )

    summary = run_metrics(graph, seeds, args)

    coverage = _compute_coverage_stats(shadow_store)

    if args.summary_only:
        print(json.dumps(summary, indent=2))
    else:
        args.output.write_text(json.dumps(summary, indent=2))
        print(f"Wrote summary to {args.output}")

    if args.update_readme:
        updated = update_readme_snapshot(
            summary,
            include_shadow=args.include_shadow,
            coverage=coverage,
        )
        if updated:
            nodes = summary["graph"]["directed_nodes"]
            edges = summary["graph"]["directed_edges"]
            print(f"Updated README snapshot ({nodes:,} nodes / {edges:,} edges).")


if __name__ == "__main__":
    main()
