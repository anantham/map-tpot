#!/usr/bin/env python3
"""Profile snapshot loading to identify performance bottlenecks.

This script measures:
1. Parquet file I/O time
2. DataFrame iteration time (iterrows)
3. NetworkX graph construction time
4. Total load time

Run with: python -m scripts.profile_snapshot_load
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import networkx as nx
from src.api.snapshot_loader import SnapshotLoader

def profile_snapshot_load():
    """Profile each phase of snapshot loading."""

    print("=" * 80)
    print("SNAPSHOT LOAD PROFILING")
    print("=" * 80)

    loader = SnapshotLoader(snapshot_dir=Path("data"))

    # Phase 1: Check if snapshot exists
    t0 = time.time()
    exists = loader.snapshot_exists()
    t1 = time.time()
    print(f"\n[1] Snapshot existence check: {(t1-t0)*1000:.2f}ms")
    print(f"    Snapshot exists: {exists}")

    if not exists:
        print("\n❌ No snapshot found. Run: python -m scripts.refresh_graph_snapshot")
        return

    # Phase 2: Load manifest
    t0 = time.time()
    manifest = loader.load_manifest()
    t1 = time.time()
    print(f"\n[2] Manifest load: {(t1-t0)*1000:.2f}ms")
    if manifest:
        print(f"    Nodes: {manifest.node_count:,}")
        print(f"    Edges: {manifest.edge_count:,}")
        print(f"    Generated: {manifest.generated_at}")

    # Phase 3: Load Parquet files (I/O)
    t0 = time.time()
    nodes_df = pd.read_parquet(loader.nodes_path)
    t1 = time.time()
    parquet_nodes_time = (t1 - t0) * 1000

    edges_df = pd.read_parquet(loader.edges_path)
    t2 = time.time()
    parquet_edges_time = (t2 - t1) * 1000

    print(f"\n[3] Parquet I/O:")
    print(f"    Nodes: {parquet_nodes_time:.2f}ms ({len(nodes_df):,} rows)")
    print(f"    Edges: {parquet_edges_time:.2f}ms ({len(edges_df):,} rows)")
    print(f"    Total I/O: {parquet_nodes_time + parquet_edges_time:.2f}ms")

    # Phase 4: DataFrame iteration with .iterrows() (SLOW)
    directed = nx.DiGraph()

    t0 = time.time()
    for i, row in enumerate(nodes_df.iterrows()):
        if i == 0:
            first_row_time = time.time() - t0
        _, row = row
        node_id = row["node_id"]
        node_attrs = {
            "username": row.get("username"),
            "display_name": row.get("display_name"),
            "num_followers": row.get("num_followers"),
            "num_following": row.get("num_following"),
        }
        node_attrs = {k: v for k, v in node_attrs.items() if v is not None}
        directed.add_node(node_id, **node_attrs)
    t1 = time.time()
    iterrows_nodes_time = (t1 - t0) * 1000

    print(f"\n[4] DataFrame iteration (.iterrows()) - NODES:")
    print(f"    First row: {first_row_time*1000:.2f}ms")
    print(f"    Total: {iterrows_nodes_time:.2f}ms ({len(nodes_df):,} rows)")
    print(f"    Per-row avg: {iterrows_nodes_time/len(nodes_df):.3f}ms")

    # Edges iteration
    t0 = time.time()
    for _, row in edges_df.iterrows():
        directed.add_edge(row["source"], row["target"])
    t1 = time.time()
    iterrows_edges_time = (t1 - t0) * 1000

    print(f"\n[5] DataFrame iteration (.iterrows()) - EDGES:")
    print(f"    Total: {iterrows_edges_time:.2f}ms ({len(edges_df):,} rows)")
    print(f"    Per-row avg: {iterrows_edges_time/len(edges_df):.3f}ms")

    # Phase 5: Test vectorized alternative (FAST)
    directed_fast = nx.DiGraph()

    t0 = time.time()
    # Vectorized node addition using dict comprehension + bulk add
    node_data = [
        (
            row["node_id"],
            {
                k: v for k, v in {
                    "username": row.get("username"),
                    "display_name": row.get("display_name"),
                    "num_followers": row.get("num_followers"),
                    "num_following": row.get("num_following"),
                }.items() if v is not None
            }
        )
        for _, row in nodes_df.iterrows()
    ]
    directed_fast.add_nodes_from(node_data)
    t1 = time.time()
    vectorized_nodes_time = (t1 - t0) * 1000

    t0 = time.time()
    edge_data = [(row["source"], row["target"]) for _, row in edges_df.iterrows()]
    directed_fast.add_edges_from(edge_data)
    t1 = time.time()
    vectorized_edges_time = (t1 - t0) * 1000

    print(f"\n[6] ALTERNATIVE: Bulk graph construction:")
    print(f"    Nodes: {vectorized_nodes_time:.2f}ms")
    print(f"    Edges: {vectorized_edges_time:.2f}ms")
    print(f"    Total: {vectorized_nodes_time + vectorized_edges_time:.2f}ms")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    total_current = parquet_nodes_time + parquet_edges_time + iterrows_nodes_time + iterrows_edges_time
    total_optimized = parquet_nodes_time + parquet_edges_time + vectorized_nodes_time + vectorized_edges_time

    print(f"Current implementation:")
    print(f"  Parquet I/O:  {parquet_nodes_time + parquet_edges_time:8.2f}ms ({(parquet_nodes_time + parquet_edges_time)/total_current*100:.1f}%)")
    print(f"  .iterrows():  {iterrows_nodes_time + iterrows_edges_time:8.2f}ms ({(iterrows_nodes_time + iterrows_edges_time)/total_current*100:.1f}%)")
    print(f"  TOTAL:        {total_current:8.2f}ms ({total_current/1000:.1f}s)")

    print(f"\nOptimized (bulk construction):")
    print(f"  Parquet I/O:  {parquet_nodes_time + parquet_edges_time:8.2f}ms ({(parquet_nodes_time + parquet_edges_time)/total_optimized*100:.1f}%)")
    print(f"  Bulk ops:     {vectorized_nodes_time + vectorized_edges_time:8.2f}ms ({(vectorized_nodes_time + vectorized_edges_time)/total_optimized*100:.1f}%)")
    print(f"  TOTAL:        {total_optimized:8.2f}ms ({total_optimized/1000:.1f}s)")

    speedup = total_current / total_optimized
    print(f"\n⚡ Potential speedup: {speedup:.1f}x ({total_current - total_optimized:.0f}ms savings)")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    profile_snapshot_load()
