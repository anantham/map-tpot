#!/usr/bin/env python3
"""Refresh precomputed graph snapshot for fast API/Explorer startup.

This script generates:
  - graph-explorer/public/analysis_output.json (for React frontend)
  - data/graph_snapshot.nodes.parquet (backend node table)
  - data/graph_snapshot.edges.parquet (backend edge table)
  - data/graph_snapshot.meta.json (manifest with freshness metadata)

Usage:
    python -m scripts.refresh_graph_snapshot [--include-shadow] [--output-dir PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh precomputed graph snapshot")
    parser.add_argument(
        "--include-shadow",
        action="store_true",
        help="Include shadow enrichment data in snapshot"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data"),
        help="Directory for snapshot files (default: data/)"
    )
    parser.add_argument(
        "--frontend-output",
        type=Path,
        default=Path("graph-explorer/public/analysis_output.json"),
        help="Path for frontend JSON (default: graph-explorer/public/analysis_output.json)"
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.85,
        help="PageRank damping factor"
    )
    parser.add_argument(
        "--resolution",
        type=float,
        default=1.0,
        help="Louvain resolution parameter"
    )
    parser.add_argument(
        "--weights",
        type=float,
        nargs=3,
        default=(0.4, 0.3, 0.3),
        metavar=("ALPHA", "BETA", "GAMMA"),
        help="Weights for pagerank, betweenness, engagement"
    )
    return parser.parse_args()


def _serialize_datetime(value) -> str | None:
    """Serialize datetime to ISO format."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _resolve_seeds(graph_result, seeds: list[str]) -> list[str]:
    """Resolve username/handle seeds to account IDs."""
    directed = graph_result.directed
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


def main():
    args = parse_args()

    print("=" * 60)
    print("REFRESHING GRAPH SNAPSHOT")
    print("=" * 60)
    print(f"Include shadow: {args.include_shadow}")
    print(f"Output directory: {args.output_dir}")
    print(f"Frontend output: {args.frontend_output}")
    print()

    # Ensure output directories exist
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.frontend_output.parent.mkdir(parents=True, exist_ok=True)

    # Get cache settings
    cache_settings = get_cache_settings()
    cache_path = cache_settings.path

    print(f"[1/6] Loading data from cache: {cache_path}")

    with CachedDataFetcher(cache_db=cache_path) as fetcher:
        shadow_store = get_shadow_store(fetcher.engine) if args.include_shadow else None

        # Record cache row counts for data-based freshness checking
        cache_row_counts = {}
        with fetcher.engine.connect() as conn:
            for table in ["account", "profile", "followers", "following"]:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                cache_row_counts[table] = result.fetchone()[0]

        print(f"[2/6] Building graph structure...")
        graph = build_graph(
            fetcher=fetcher,
            mutual_only=False,
            min_followers=0,
            include_shadow=args.include_shadow,
            shadow_store=shadow_store,
        )

        directed = graph.directed
        undirected = graph.undirected

        print(f"  → {directed.number_of_nodes()} nodes, {directed.number_of_edges()} directed edges")

        # Load seeds
        print(f"[3/6] Loading seed candidates...")
        seeds = sorted(load_seed_candidates())
        resolved_seeds = _resolve_seeds(graph, seeds)
        print(f"  → {len(seeds)} seeds ({len(resolved_seeds)} resolved)")

        # Compute metrics
        print(f"[4/6] Computing metrics...")
        print("  - PageRank...")
        pagerank = compute_personalized_pagerank(
            directed,
            seeds=resolved_seeds,
            alpha=args.alpha
        )

        print("  - Betweenness centrality...")
        betweenness = compute_betweenness(undirected)

        print("  - Engagement scores...")
        engagement = compute_engagement_scores(undirected)

        print("  - Composite scores...")
        composite = compute_composite_score(
            pagerank=pagerank,
            betweenness=betweenness,
            engagement=engagement,
            weights=tuple(args.weights),
        )

        print("  - Community detection...")
        communities = compute_louvain_communities(undirected, resolution=args.resolution)

        # Serialize nodes and edges
        print(f"[5/6] Serializing graph data...")

        # Node data
        nodes_records = []
        for node_id, data in directed.nodes(data=True):
            nodes_records.append({
                "node_id": node_id,
                "username": data.get("username"),
                "display_name": data.get("account_display_name") or data.get("display_name"),
                "num_followers": data.get("num_followers"),
                "num_following": data.get("num_following"),
                "num_likes": data.get("num_likes"),
                "num_tweets": data.get("num_tweets"),
                "bio": data.get("bio"),
                "location": data.get("location"),
                "website": data.get("website"),
                "profile_image_url": data.get("profile_image_url"),
                "provenance": data.get("provenance", "archive"),
                "shadow": data.get("shadow", False),
                "fetched_at": _serialize_datetime(data.get("fetched_at")),
            })

        nodes_df = pd.DataFrame(nodes_records)

        # Edge data
        edges_records = []
        for u, v in directed.edges():
            edge_data = directed.get_edge_data(u, v, default={})
            edges_records.append({
                "source": u,
                "target": v,
                "mutual": directed.has_edge(v, u),
                "provenance": edge_data.get("provenance", "archive"),
                "shadow": edge_data.get("shadow", False),
                "metadata": json.dumps(edge_data.get("metadata")) if edge_data.get("metadata") else None,
                "direction_label": edge_data.get("direction_label"),
                "fetched_at": _serialize_datetime(edge_data.get("fetched_at")),
            })

        edges_df = pd.DataFrame(edges_records)

        # Write Parquet files
        print(f"[6/6] Writing snapshot files...")

        nodes_path = args.output_dir / "graph_snapshot.nodes.parquet"
        edges_path = args.output_dir / "graph_snapshot.edges.parquet"
        manifest_path = args.output_dir / "graph_snapshot.meta.json"

        print(f"  → {nodes_path}")
        nodes_df.to_parquet(nodes_path, index=False, compression="snappy")

        print(f"  → {edges_path}")
        edges_df.to_parquet(edges_path, index=False, compression="snappy")

        # Generate manifest
        cache_mtime = os.path.getmtime(cache_path) if Path(cache_path).exists() else None
        manifest = {
            "generated_at": datetime.utcnow().isoformat(),
            "cache_db_path": str(cache_path),
            "cache_db_modified": datetime.fromtimestamp(cache_mtime).isoformat() if cache_mtime else None,
            "node_count": len(nodes_df),
            "edge_count": len(edges_df),
            "include_shadow": args.include_shadow,
            "seed_count": len(seeds),
            "resolved_seed_count": len(resolved_seeds),
            "metrics_computed": True,
            "cache_row_counts": cache_row_counts,  # For data-based freshness checking
            "parameters": {
                "alpha": args.alpha,
                "resolution": args.resolution,
                "weights": list(args.weights),
            }
        }

        print(f"  → {manifest_path}")
        manifest_path.write_text(json.dumps(manifest, indent=2))

        # Generate frontend JSON (full analysis output)
        frontend_data = {
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
                "nodes": {
                    node_id: {
                        "username": data.get("username"),
                        "display_name": data.get("account_display_name") or data.get("display_name"),
                        "num_followers": data.get("num_followers"),
                        "num_following": data.get("num_following"),
                        "num_likes": data.get("num_likes"),
                        "num_tweets": data.get("num_tweets"),
                        "bio": data.get("bio"),
                        "location": data.get("location"),
                        "website": data.get("website"),
                        "provenance": data.get("provenance", "archive"),
                        "shadow": data.get("shadow", False),
                        "fetched_at": _serialize_datetime(data.get("fetched_at")),
                    }
                    for node_id, data in directed.nodes(data=True)
                },
                "edges": [
                    {
                        "source": u,
                        "target": v,
                        "mutual": directed.has_edge(v, u),
                        "provenance": directed.get_edge_data(u, v, default={}).get("provenance", "archive"),
                        "shadow": directed.get_edge_data(u, v, default={}).get("shadow", False),
                    }
                    for u, v in directed.edges()
                ],
                "directed_nodes": directed.number_of_nodes(),
                "directed_edges": directed.number_of_edges(),
                "undirected_edges": undirected.number_of_edges(),
            },
        }

        print(f"  → {args.frontend_output}")
        args.frontend_output.write_text(json.dumps(frontend_data, indent=2))

    print()
    print("=" * 60)
    print("SNAPSHOT REFRESH COMPLETE")
    print("=" * 60)
    print(f"Nodes: {manifest['node_count']}")
    print(f"Edges: {manifest['edge_count']}")
    print(f"Generated: {manifest['generated_at']}")
    print(f"Cache modified: {manifest['cache_db_modified']}")
    print()
    print("Files created:")
    print(f"  - {nodes_path}")
    print(f"  - {edges_path}")
    print(f"  - {manifest_path}")
    print(f"  - {args.frontend_output}")
    print()
    print("Next steps:")
    print("  1. Restart the API server to load the snapshot")
    print("  2. Run: python -m scripts.verify_graph_snapshot")
    print("=" * 60)


if __name__ == "__main__":
    main()
