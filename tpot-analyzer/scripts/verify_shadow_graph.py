"""Verification script for shadow enrichment pipeline."""
from __future__ import annotations

import json
from pathlib import Path

from src.config import get_cache_settings
from src.data.fetcher import CachedDataFetcher
from src.data.shadow_store import get_shadow_store

CHECK = "✓"
CROSS = "✗"


def count_shadow_entities(cache_path: Path) -> tuple[int, int]:
    with CachedDataFetcher(cache_db=cache_path) as fetcher:
        store = get_shadow_store(fetcher.engine)
        accounts = store.fetch_accounts()
        edges = store.fetch_edges()
    return len(accounts), len(edges)


def inspect_analysis_output(analysis_path: Path) -> tuple[int, int]:
    if not analysis_path.exists():
        return (0, 0)
    payload = json.loads(analysis_path.read_text())
    nodes = payload.get("graph", {}).get("nodes", {})
    edges = payload.get("graph", {}).get("edges", [])
    shadow_nodes = sum(1 for meta in nodes.values() if meta.get("shadow"))
    shadow_edges = sum(1 for edge in edges if edge.get("shadow"))
    return shadow_nodes, shadow_edges


def main() -> None:
    cache_settings = get_cache_settings()
    cache_path = cache_settings.path
    analysis_path = Path("analysis_output.json")

    shadow_accounts, shadow_edges = count_shadow_entities(cache_path)
    analysis_shadow_nodes, analysis_shadow_edges = inspect_analysis_output(analysis_path)

    print("Shadow enrichment verification\n------------------------------")
    print(f"Cache path: {cache_path}")
    print(f"Analysis output: {analysis_path if analysis_path.exists() else 'missing'}\n")

    print(f"{CHECK if shadow_accounts else CROSS} shadow accounts cached: {shadow_accounts}")
    print(f"{CHECK if shadow_edges else CROSS} shadow edges cached: {shadow_edges}")
    print(
        f"{CHECK if analysis_shadow_nodes else CROSS} analysis shadow nodes: {analysis_shadow_nodes} (edges: {analysis_shadow_edges})"
    )

    next_steps: list[str] = []
    if shadow_accounts == 0:
        next_steps.append("Run python -m scripts.enrich_shadow_graph --cookies <path> [--include-followers]")
    if analysis_shadow_nodes == 0 and shadow_accounts:
        next_steps.append("Re-run python -m scripts.analyze_graph --include-shadow")

    if next_steps:
        print("\nNext steps:")
        for step in next_steps:
            print(f"- {step}")


if __name__ == "__main__":
    main()
