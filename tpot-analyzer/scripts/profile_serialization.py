#!/usr/bin/env python3
"""Profile graph serialization to confirm it's the bottleneck.

Measures time to serialize the full graph (71K nodes, 230K edges) to JSON.
"""
import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.snapshot_loader import SnapshotLoader

def _serialize_datetime(dt):
    """Helper to serialize datetime."""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()

def profile_serialization():
    """Profile the serialization bottleneck."""

    print("=" * 80)
    print("GRAPH SERIALIZATION PROFILING")
    print("=" * 80)

    # Load graph from snapshot
    loader = SnapshotLoader(snapshot_dir=Path("data"))

    print("\n[1] Loading graph from snapshot...")
    t0 = time.time()
    graph = loader.load_graph()
    t1 = time.time()
    load_time = (t1 - t0) * 1000

    if not graph:
        print("❌ Failed to load snapshot")
        return

    directed = graph.directed
    print(f"    Load time: {load_time:.2f}ms")
    print(f"    Nodes: {directed.number_of_nodes():,}")
    print(f"    Edges: {directed.number_of_edges():,}")

    # Profile edge serialization (current approach)
    print("\n[2] Serializing edges (current approach - loop + dict build)...")
    t0 = time.time()
    edges = []
    for u, v in directed.edges():
        data = directed.get_edge_data(u, v, default={})
        edges.append({
            "source": u,
            "target": v,
            "mutual": directed.has_edge(v, u),
            "provenance": data.get("provenance", "archive"),
            "shadow": data.get("shadow", False),
            "metadata": data.get("metadata"),
            "direction_label": data.get("direction_label"),
            "fetched_at": _serialize_datetime(data.get("fetched_at")),
        })
    t1 = time.time()
    edge_serialize_time = (t1 - t0) * 1000
    print(f"    Time: {edge_serialize_time:.2f}ms ({directed.number_of_edges():,} edges)")
    print(f"    Per-edge: {edge_serialize_time/directed.number_of_edges():.4f}ms")

    # Profile node serialization (current approach)
    print("\n[3] Serializing nodes (current approach - loop + dict build)...")
    t0 = time.time()
    nodes = {}
    for node, data in directed.nodes(data=True):
        nodes[node] = {
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
            "shadow_scrape_stats": data.get("shadow_scrape_stats"),
            "fetched_at": _serialize_datetime(data.get("fetched_at")),
        }
    t1 = time.time()
    node_serialize_time = (t1 - t0) * 1000
    print(f"    Time: {node_serialize_time:.2f}ms ({directed.number_of_nodes():,} nodes)")
    print(f"    Per-node: {node_serialize_time/directed.number_of_nodes():.4f}ms")

    # Profile JSON encoding
    print("\n[4] JSON encoding (json.dumps)...")
    payload = {"nodes": nodes, "edges": edges}
    t0 = time.time()
    json_str = json.dumps(payload)
    t1 = time.time()
    json_encode_time = (t1 - t0) * 1000
    json_size_mb = len(json_str) / (1024 * 1024)
    print(f"    Time: {json_encode_time:.2f}ms")
    print(f"    Size: {json_size_mb:.2f} MB")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    total_time = edge_serialize_time + node_serialize_time + json_encode_time

    print(f"Edge serialization:  {edge_serialize_time:8.2f}ms ({edge_serialize_time/total_time*100:.1f}%)")
    print(f"Node serialization:  {node_serialize_time:8.2f}ms ({node_serialize_time/total_time*100:.1f}%)")
    print(f"JSON encoding:       {json_encode_time:8.2f}ms ({json_encode_time/total_time*100:.1f}%)")
    print(f"{'─'*40}")
    print(f"TOTAL:               {total_time:8.2f}ms ({total_time/1000:.1f}s)")

    print(f"\nPayload size: {json_size_mb:.2f} MB")
    print(f"Expected server time: ~{total_time/1000:.1f}s (measured: 16.8s avg)")

    if abs(total_time/1000 - 16.8) < 3:
        print("✅ CONFIRMED: Serialization is the bottleneck!")
    else:
        print("⚠️  Serialization time doesn't fully account for 16.8s - other factors involved")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    profile_serialization()
