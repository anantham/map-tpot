#!/usr/bin/env python3
"""Verify discovery depth traversal behavior with explicit pass/fail output."""
from __future__ import annotations

import sys

import networkx as nx

from src.api.discovery import extract_subgraph


def _print_result(name: str, passed: bool, detail: str) -> bool:
    status = "✓" if passed else "✗"
    print(f"{status} {name}: {detail}")
    return passed


def main() -> int:
    print("Discovery Depth Verification")
    print("=" * 32)

    checks_passed = 0
    total_checks = 0

    graph = nx.DiGraph()
    graph.add_edge("seed", "hop_1")
    graph.add_edge("hop_1", "hop_2")
    graph.add_edge("hop_2", "hop_3")

    subgraph, candidates = extract_subgraph(graph, ["seed"], depth=2)
    nodes = set(subgraph.nodes())
    candidate_set = set(candidates)

    total_checks += 1
    if _print_result(
        "two-hop-inclusion",
        "hop_2" in nodes,
        f"nodes={sorted(nodes)}",
    ):
        checks_passed += 1

    total_checks += 1
    if _print_result(
        "depth-boundary",
        "hop_3" not in nodes,
        f"depth=2 nodes_count={len(nodes)}",
    ):
        checks_passed += 1

    total_checks += 1
    empty_graph, empty_candidates = extract_subgraph(graph, ["missing_seed"], depth=2)
    if _print_result(
        "invalid-seed-handling",
        len(empty_graph.nodes()) == 0 and len(empty_candidates) == 0,
        f"empty_nodes={len(empty_graph.nodes())} empty_candidates={len(empty_candidates)}",
    ):
        checks_passed += 1

    print("\nMetrics")
    print(f"- checks_passed: {checks_passed}/{total_checks}")
    print(f"- candidate_count: {len(candidate_set)}")
    print(f"- candidates: {sorted(candidate_set)}")

    if checks_passed == total_checks:
        print("\nNext steps: run `python3 -m pytest tests/test_discovery_logic.py -q` for regression coverage.")
        return 0

    print("\nNext steps: inspect `src/api/discovery.py` BFS frontier updates before shipping.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
