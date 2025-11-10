#!/usr/bin/env python3
"""Benchmark graph metrics across different backends (GPU/NetworKit/NetworkX).

Usage:
    python -m scripts.benchmark_metrics [--include-shadow] [--sample-size N]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_cache_settings
from src.data.fetcher import CachedDataFetcher
from src.data.shadow_store import get_shadow_store
from src.graph import build_graph, load_seed_candidates
from src.graph.gpu_capability import get_gpu_capability


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark graph metrics")
    parser.add_argument(
        "--include-shadow",
        action="store_true",
        help="Include shadow enrichment data"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=500,
        help="Betweenness sampling size (default: 500)"
    )
    parser.add_argument(
        "--test-gpu",
        action="store_true",
        help="Test GPU metrics (requires cuGraph)"
    )
    return parser.parse_args()


def benchmark_backend(name: str, func: callable) -> tuple[float, any]:
    """Run a benchmark and return (duration_seconds, result)."""
    print(f"  [{name}] Starting...")
    start = time.time()
    try:
        result = func()
        duration = time.time() - start
        print(f"  [{name}] ✓ Completed in {duration:.2f}s")
        return duration, result
    except Exception as e:
        duration = time.time() - start
        print(f"  [{name}] ✗ Failed after {duration:.2f}s: {e}")
        return duration, None


def main():
    args = parse_args()

    print("=" * 60)
    print("GRAPH METRICS BENCHMARK")
    print("=" * 60)
    print(f"Include shadow: {args.include_shadow}")
    print(f"Betweenness sampling: k={args.sample_size}")
    print()

    # Check GPU capability
    gpu_cap = get_gpu_capability()
    print(f"GPU Status: {gpu_cap}")
    print()

    # Load graph
    print("[1/4] Loading graph...")
    cache_settings = get_cache_settings()

    with CachedDataFetcher(cache_db=cache_settings.path) as fetcher:
        shadow_store = get_shadow_store(fetcher.engine) if args.include_shadow else None
        graph = build_graph(
            fetcher=fetcher,
            mutual_only=False,
            min_followers=0,
            include_shadow=args.include_shadow,
            shadow_store=shadow_store,
        )

    directed = graph.directed
    undirected = graph.undirected
    num_nodes = directed.number_of_nodes()
    num_edges = directed.number_of_edges()

    print(f"  Nodes: {num_nodes:,}")
    print(f"  Edges: {num_edges:,}")
    print()

    # Load seeds
    print("[2/4] Loading seeds...")
    seeds = sorted(load_seed_candidates())
    print(f"  Seeds: {len(seeds)}")
    print()

    # Benchmark PageRank
    print("[3/4] Benchmarking PageRank...")
    results = {}

    # NetworkX baseline
    from src.graph.metrics import compute_personalized_pagerank
    duration, pr_nx = benchmark_backend(
        "NetworkX",
        lambda: compute_personalized_pagerank(directed, seeds=seeds, alpha=0.85)
    )
    results["pagerank_networkx"] = duration

    # NetworKit (if available)
    try:
        from src.graph.metrics_fast import compute_pagerank_fast
        duration, pr_nk = benchmark_backend(
            "NetworKit",
            lambda: compute_pagerank_fast(directed, seeds=seeds, alpha=0.85)
        )
        results["pagerank_networkit"] = duration

        # Compare results
        if pr_nx and pr_nk:
            common_nodes = set(pr_nx.keys()) & set(pr_nk.keys())
            if common_nodes:
                sample = list(common_nodes)[:10]
                diffs = [abs(pr_nx[n] - pr_nk[n]) for n in sample]
                print(f"  Comparison: avg diff = {sum(diffs)/len(diffs):.6f} (sample size: {len(sample)})")

    except ImportError:
        print("  [NetworKit] Not available")

    # GPU (if requested and available)
    if args.test_gpu and gpu_cap.can_use_gpu:
        try:
            from src.graph.gpu_metrics import compute_pagerank_gpu
            duration, pr_gpu = benchmark_backend(
                "cuGraph (GPU)",
                lambda: compute_pagerank_gpu(directed, seeds=seeds, alpha=0.85)
            )
            results["pagerank_gpu"] = duration

            # Compare results
            if pr_nx and pr_gpu:
                common_nodes = set(pr_nx.keys()) & set(pr_gpu.keys())
                if common_nodes:
                    sample = list(common_nodes)[:10]
                    diffs = [abs(pr_nx[n] - pr_gpu[n]) for n in sample]
                    print(f"  Comparison: avg diff = {sum(diffs)/len(diffs):.6f} (sample size: {len(sample)})")

        except Exception as e:
            print(f"  [cuGraph (GPU)] Failed: {e}")

    print()

    # Benchmark Betweenness
    print(f"[4/4] Benchmarking Betweenness (k={args.sample_size})...")

    # NetworkX sampled
    from src.graph.metrics import compute_betweenness
    duration, bt_nx = benchmark_backend(
        "NetworkX (sampled)",
        lambda: compute_betweenness(undirected, sample_size=args.sample_size)
    )
    results["betweenness_networkx_sampled"] = duration

    # NetworKit (if available)
    try:
        from src.graph.metrics_fast import compute_betweenness_fast
        duration, bt_nk = benchmark_backend(
            "NetworKit (sampled)",
            lambda: compute_betweenness_fast(undirected, sample_size=args.sample_size)
        )
        results["betweenness_networkit_sampled"] = duration

        # Compare results
        if bt_nx and bt_nk:
            common_nodes = set(bt_nx.keys()) & set(bt_nk.keys())
            if common_nodes:
                sample = list(common_nodes)[:10]
                diffs = [abs(bt_nx[n] - bt_nk[n]) / (bt_nx[n] + 1e-10) for n in sample]
                print(f"  Comparison: avg relative diff = {sum(diffs)/len(diffs):.2%} (sample size: {len(sample)})")

    except ImportError:
        print("  [NetworKit] Not available")

    # GPU (if requested and available)
    if args.test_gpu and gpu_cap.can_use_gpu:
        try:
            from src.graph.gpu_metrics import compute_betweenness_gpu
            duration, bt_gpu = benchmark_backend(
                "cuGraph (GPU)",
                lambda: compute_betweenness_gpu(undirected, k=args.sample_size)
            )
            results["betweenness_gpu_sampled"] = duration

            # Compare results
            if bt_nx and bt_gpu:
                common_nodes = set(bt_nx.keys()) & set(bt_gpu.keys())
                if common_nodes:
                    sample = list(common_nodes)[:10]
                    diffs = [abs(bt_nx[n] - bt_gpu[n]) / (bt_nx[n] + 1e-10) for n in sample]
                    print(f"  Comparison: avg relative diff = {sum(diffs)/len(diffs):.2%} (sample size: {len(sample)})")

        except Exception as e:
            print(f"  [cuGraph (GPU)] Failed: {e}")

    print()

    # Summary
    print("=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)

    for key, duration in sorted(results.items()):
        print(f"{key:35s}: {duration:8.2f}s")

    # Speedups
    if "pagerank_networkx" in results:
        baseline = results["pagerank_networkx"]
        if "pagerank_networkit" in results:
            speedup = baseline / results["pagerank_networkit"]
            print(f"\nPageRank NetworKit speedup: {speedup:.2f}x")
        if "pagerank_gpu" in results:
            speedup = baseline / results["pagerank_gpu"]
            print(f"PageRank GPU speedup: {speedup:.2f}x")

    if "betweenness_networkx_sampled" in results:
        baseline = results["betweenness_networkx_sampled"]
        if "betweenness_networkit_sampled" in results:
            speedup = baseline / results["betweenness_networkit_sampled"]
            print(f"Betweenness NetworKit speedup: {speedup:.2f}x")
        if "betweenness_gpu_sampled" in results:
            speedup = baseline / results["betweenness_gpu_sampled"]
            print(f"Betweenness GPU speedup: {speedup:.2f}x")

    print("=" * 60)


if __name__ == "__main__":
    main()
