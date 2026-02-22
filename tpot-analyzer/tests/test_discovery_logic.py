"""Unit tests for discovery subgraph extraction."""
from __future__ import annotations

import networkx as nx

from src.api.discovery import extract_subgraph


def test_extract_subgraph_reaches_two_hops_when_depth_is_two():
    graph = nx.DiGraph()
    graph.add_edge("seed", "hop_1")
    graph.add_edge("hop_1", "hop_2")

    subgraph, candidates = extract_subgraph(graph, ["seed"], depth=2)

    assert set(subgraph.nodes()) == {"seed", "hop_1", "hop_2"}
    assert set(candidates) == {"hop_1", "hop_2"}


def test_extract_subgraph_respects_depth_boundary():
    graph = nx.DiGraph()
    graph.add_edge("seed", "hop_1")
    graph.add_edge("hop_1", "hop_2")
    graph.add_edge("hop_2", "hop_3")

    subgraph, candidates = extract_subgraph(graph, ["seed"], depth=2)

    assert set(subgraph.nodes()) == {"seed", "hop_1", "hop_2"}
    assert "hop_3" not in candidates
