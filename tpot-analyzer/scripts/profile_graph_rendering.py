#!/usr/bin/env python3
"""Profile graph rendering performance to identify bottlenecks.

This script runs the complete graph analysis pipeline with detailed timing
instrumentation to identify which operations are slow.

Usage:
    python -m scripts.profile_graph_rendering [--include-shadow] [--verbose]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_cache_settings
from src.data.fetcher import CachedDataFetcher
from src.data.shadow_store import get_shadow_store
from src.graph import (
    build_graph,
    compute_betweenness,
    compute_composite_score,
    compute_engagement_scores,
    compute_louvain_communities,
    compute_personalized_pagerank,
    load_seed_candidates,
)
from src.performance_profiler import (
    PerformanceProfiler,
    profile_operation,
    profile_phase,
    print_summary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile graph rendering performance")
    parser.add_argument(
        "--include-shadow",
        action="store_true",
        help="Include shadow enrichment data"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed phase breakdowns"
    )
    parser.add_argument(
        "--disable-profiling",
        action="store_true",
        help="Disable profiling to measure overhead"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.disable_profiling:
        PerformanceProfiler.disable()
        print("Performance profiling disabled (measuring baseline)")
    else:
        PerformanceProfiler.enable()
        print("Performance profiling enabled")

    print(f"\nProfiling graph rendering pipeline...")
    print(f"Include shadow: {args.include_shadow}")
    print("=" * 60)

    with profile_operation("complete_graph_analysis", {
        "include_shadow": args.include_shadow
    }, verbose=False) as report:

        # Step 1: Load data from cache
        print("\n[1/6] Loading data from cache...")
        with profile_phase("load_cache", "complete_graph_analysis"):
            cache_settings = get_cache_settings()
            fetcher = CachedDataFetcher(cache_db=cache_settings.path)
            fetcher.__enter__()

            shadow_store = None
            if args.include_shadow:
                shadow_store = get_shadow_store(fetcher.engine)

        # Step 2: Build graph structure
        print("[2/6] Building graph structure...")
        with profile_phase("build_graph", "complete_graph_analysis"):
            graph = build_graph(
                fetcher=fetcher,
                mutual_only=False,
                min_followers=0,
                include_shadow=args.include_shadow,
                shadow_store=shadow_store,
            )

        print(f"  → {graph.directed.number_of_nodes()} nodes, {graph.directed.number_of_edges()} edges")

        # Step 3: Load seeds
        print("[3/6] Loading seed candidates...")
        with profile_phase("load_seeds", "complete_graph_analysis"):
            seeds = sorted(load_seed_candidates())
            print(f"  → {len(seeds)} seeds")

        # Step 4: Compute metrics
        print("[4/6] Computing graph metrics...")

        directed = graph.directed
        undirected = graph.undirected

        # Resolve seeds
        with profile_phase("resolve_seeds", "complete_graph_analysis"):
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
            resolved_seeds = sorted(id_seeds)
            print(f"  → {len(resolved_seeds)} resolved seeds")

        # Compute individual metrics
        print("  Computing PageRank...")
        pagerank = compute_personalized_pagerank(
            directed,
            seeds=resolved_seeds,
            alpha=0.85
        )

        print("  Computing betweenness...")
        betweenness = compute_betweenness(undirected)

        print("  Computing engagement...")
        with profile_phase("compute_engagement", "complete_graph_analysis"):
            engagement = compute_engagement_scores(undirected)

        print("  Computing communities...")
        communities = compute_louvain_communities(undirected, resolution=1.0)

        print("  Computing composite scores...")
        with profile_phase("compute_composite", "complete_graph_analysis"):
            composite = compute_composite_score(
                pagerank=pagerank,
                betweenness=betweenness,
                engagement=engagement,
                weights=(0.4, 0.3, 0.3),
            )

        # Step 5: Serialize graph data (simulate API response)
        print("[5/6] Serializing graph data...")
        with profile_phase("serialize_graph", "complete_graph_analysis"):
            # Simulate edge serialization
            edges_json = []
            for u, v in directed.edges():
                edge_data = directed.get_edge_data(u, v, default={})
                edges_json.append({
                    "source": u,
                    "target": v,
                    "mutual": directed.has_edge(v, u),
                    "provenance": edge_data.get("provenance", "archive"),
                    "shadow": edge_data.get("shadow", False),
                })

            # Simulate node serialization
            nodes_json = {}
            for node, node_data in directed.nodes(data=True):
                nodes_json[node] = {
                    "username": node_data.get("username"),
                    "display_name": node_data.get("account_display_name"),
                    "num_followers": node_data.get("num_followers"),
                    "num_following": node_data.get("num_following"),
                    "bio": node_data.get("bio"),
                    "provenance": node_data.get("provenance", "archive"),
                    "shadow": node_data.get("shadow", False),
                }

            print(f"  → Serialized {len(nodes_json)} nodes, {len(edges_json)} edges")

        # Step 6: Format metrics output
        print("[6/6] Formatting metrics output...")
        with profile_phase("format_metrics", "complete_graph_analysis"):
            metrics_output = {
                "pagerank": pagerank,
                "betweenness": betweenness,
                "engagement": engagement,
                "composite": composite,
                "communities": communities,
            }

            top_composite = sorted(composite.items(), key=lambda x: x[1], reverse=True)[:20]
            print(f"  → Top 5 composite scores:")
            for i, (node_id, score) in enumerate(top_composite[:5], 1):
                username = nodes_json.get(node_id, {}).get("username", "unknown")
                print(f"     {i}. @{username}: {score:.4f}")

        fetcher.__exit__(None, None, None)

    print("\n" + "=" * 60)
    print("PROFILING COMPLETE")
    print("=" * 60)

    # Print summary
    print_summary()

    # Print detailed breakdown if verbose
    if args.verbose and not args.disable_profiling:
        print("\n" + "=" * 60)
        print("DETAILED PHASE BREAKDOWN")
        print("=" * 60)

        from src.performance_profiler import get_profiler
        profiler = get_profiler()

        for report in profiler.get_all_reports():
            print(report.format_report(verbose=True))


if __name__ == "__main__":
    main()
