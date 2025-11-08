#!/usr/bin/env python3
"""Verify graph snapshot health and freshness.

Checks snapshot files, compares counts against SQLite cache, and reports
whether the snapshot is usable for API/Explorer startup.

Usage:
    python -m scripts.verify_graph_snapshot
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.snapshot_loader import SnapshotLoader
from src.config import get_cache_settings
from src.data.fetcher import CachedDataFetcher
from src.data.shadow_store import get_shadow_store


def format_status(passed: bool) -> str:
    """Format check status."""
    return "✓" if passed else "✗"


def main():
    print("=" * 60)
    print("GRAPH SNAPSHOT VERIFICATION")
    print("=" * 60)
    print()

    loader = SnapshotLoader()
    cache_settings = get_cache_settings()

    checks_passed = 0
    checks_failed = 0

    # Check 1: Snapshot files exist
    print("[1] Checking snapshot files...")
    if loader.snapshot_exists():
        print(f"  {format_status(True)} All snapshot files found:")
        print(f"     - {loader.nodes_path}")
        print(f"     - {loader.edges_path}")
        print(f"     - {loader.manifest_path}")
        checks_passed += 1
    else:
        print(f"  {format_status(False)} Snapshot files missing")
        print(f"     Nodes: {loader.nodes_path.exists()}")
        print(f"     Edges: {loader.edges_path.exists()}")
        print(f"     Manifest: {loader.manifest_path.exists()}")
        checks_failed += 1
        print()
        print("=" * 60)
        print(f"RESULT: {checks_passed}/{checks_passed + checks_failed} checks passed")
        print("Run: python -m scripts.refresh_graph_snapshot --include-shadow")
        print("=" * 60)
        sys.exit(1)

    print()

    # Check 2: Manifest is valid
    print("[2] Checking manifest...")
    manifest = loader.load_manifest()
    if manifest:
        print(f"  {format_status(True)} Manifest loaded successfully")
        print(f"     Generated: {manifest.generated_at}")
        print(f"     Cache modified: {manifest.cache_db_modified}")
        print(f"     Nodes: {manifest.node_count}")
        print(f"     Edges: {manifest.edge_count}")
        print(f"     Include shadow: {manifest.include_shadow}")
        print(f"     Metrics computed: {manifest.metrics_computed}")
        checks_passed += 1
    else:
        print(f"  {format_status(False)} Failed to load manifest")
        checks_failed += 1
        print()
        print("=" * 60)
        print(f"RESULT: {checks_passed}/{checks_passed + checks_failed} checks passed")
        print("Cannot continue without valid manifest.")
        print("Run: python -m scripts.refresh_graph_snapshot --include-shadow")
        print("=" * 60)
        sys.exit(1)

    print()

    # Check 3: Snapshot freshness
    print("[3] Checking snapshot freshness...")
    should_use, reason = loader.should_use_snapshot()

    if should_use:
        print(f"  {format_status(True)} {reason}")
        checks_passed += 1
    else:
        print(f"  {format_status(False)} {reason}")
        checks_failed += 1

    print()

    # Check 4: Compare counts with cache
    print("[4] Comparing counts with cache...")
    try:
        with CachedDataFetcher(cache_db=cache_settings.path) as fetcher:
            shadow_store = get_shadow_store(fetcher.engine) if manifest.include_shadow else None

            # Count archive accounts
            accounts = fetcher.fetch_accounts()
            archive_accounts = len(accounts)

            # Count shadow accounts
            shadow_accounts = 0
            if shadow_store:
                shadow_account_records = shadow_store.fetch_accounts()
                shadow_accounts = len(shadow_account_records)

            total_expected_nodes = archive_accounts + shadow_accounts

            # Count edges
            followers = fetcher.fetch_followers()
            following = fetcher.fetch_following()
            archive_edges = len(followers) + len(following)

            shadow_edges = 0
            if shadow_store:
                shadow_edge_records = shadow_store.fetch_edges()
                shadow_edges = len(shadow_edge_records)

            total_expected_edges = archive_edges + shadow_edges

            # Compare
            node_match = manifest.node_count >= archive_accounts
            edge_match = manifest.edge_count >= archive_edges

            print(f"  Archive accounts: {archive_accounts}")
            if shadow_accounts > 0:
                print(f"  Shadow accounts: {shadow_accounts}")
            print(f"  Expected total nodes: {total_expected_nodes}")
            print(f"  Snapshot nodes: {manifest.node_count}")

            print()
            print(f"  Archive edges: {archive_edges}")
            if shadow_edges > 0:
                print(f"  Shadow edges: {shadow_edges}")
            print(f"  Expected total edges: {total_expected_edges}")
            print(f"  Snapshot edges: {manifest.edge_count}")

            print()
            if node_match and edge_match:
                print(f"  {format_status(True)} Counts match (snapshot >= cache)")
                checks_passed += 1
            else:
                print(f"  {format_status(False)} Count mismatch detected")
                if not node_match:
                    print(f"     Node count too low: {manifest.node_count} < {archive_accounts}")
                if not edge_match:
                    print(f"     Edge count too low: {manifest.edge_count} < {archive_edges}")
                checks_failed += 1

    except Exception as e:
        print(f"  {format_status(False)} Error comparing with cache: {e}")
        checks_failed += 1

    print()

    # Check 5: Can load graph
    print("[5] Testing graph load...")
    try:
        graph = loader.load_graph(force_reload=True)
        if graph:
            print(f"  {format_status(True)} Graph loaded successfully")
            print(f"     Nodes in memory: {graph.directed.number_of_nodes()}")
            print(f"     Edges in memory: {graph.directed.number_of_edges()}")
            checks_passed += 1
        else:
            print(f"  {format_status(False)} Failed to load graph")
            checks_failed += 1
    except Exception as e:
        print(f"  {format_status(False)} Error loading graph: {e}")
        checks_failed += 1

    print()
    print("=" * 60)
    print(f"RESULT: {checks_passed}/{checks_passed + checks_failed} checks passed")

    if checks_failed == 0:
        print("✓ Snapshot is healthy and ready to use")
        print()
        print("API server will use this snapshot on startup.")
        print("=" * 60)
        sys.exit(0)
    else:
        print("✗ Snapshot has issues")
        print()
        print("Recommended action:")
        print("  python -m scripts.refresh_graph_snapshot --include-shadow")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
