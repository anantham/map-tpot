"""Verify observation-aware adjacency construction on local graph snapshots."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.graph.observation_model import (
    ObservationWeightingConfig,
    build_binary_adjacency_from_edges,
    build_ipw_adjacency_from_edges,
    compute_observation_completeness,
    summarize_completeness,
)


def status_line(ok: bool, label: str) -> str:
    return f"{'✓' if ok else '✗'} {label}"


def _safe_expected_following(nodes_df: pd.DataFrame) -> dict[str, float]:
    if "node_id" not in nodes_df.columns or "num_following" not in nodes_df.columns:
        return {}
    subset = nodes_df[["node_id", "num_following"]].copy()
    subset["node_id"] = subset["node_id"].astype(str)
    return dict(zip(subset["node_id"].tolist(), subset["num_following"].tolist()))


def run(data_dir: Path, mode: str, p_min: float, completeness_floor: float) -> list[str]:
    lines: list[str] = []
    nodes_path = data_dir / "graph_snapshot.nodes.parquet"
    edges_path = data_dir / "graph_snapshot.edges.parquet"

    lines.append(status_line(nodes_path.exists(), f"Found nodes parquet: {nodes_path}"))
    lines.append(status_line(edges_path.exists(), f"Found edges parquet: {edges_path}"))
    if not nodes_path.exists() or not edges_path.exists():
        return lines

    nodes_df = pd.read_parquet(nodes_path)
    edges_df = pd.read_parquet(edges_path)

    node_ids = nodes_df["node_id"].astype(str).to_numpy()
    lines.append(status_line(len(node_ids) > 0, f"Loaded node_ids count={len(node_ids):,}"))
    lines.append(status_line(len(edges_df) > 0, f"Loaded edges count={len(edges_df):,}"))

    cfg = ObservationWeightingConfig(mode=mode, p_min=p_min, completeness_floor=completeness_floor)
    expected_following = _safe_expected_following(nodes_df)

    if cfg.mode == "ipw":
        completeness = compute_observation_completeness(
            edges_df,
            node_ids,
            expected_following=expected_following,
            completeness_floor=cfg.completeness_floor,
        )
        adjacency, stats = build_ipw_adjacency_from_edges(
            edges_df,
            node_ids,
            completeness,
            p_min=cfg.p_min,
        )
        cstats = summarize_completeness(completeness)

        lines.append(status_line(adjacency.count_nonzero() > 0, f"Built IPW adjacency nnz={adjacency.count_nonzero():,}"))
        lines.append(status_line(stats["mean_weight"] >= 1.0, f"Mean IPW edge weight={stats['mean_weight']:.4f}"))
        lines.append(status_line(cstats["mean"] > 0.0, f"Completeness mean={cstats['mean']:.4f}, p10={cstats['p10']:.4f}, p90={cstats['p90']:.4f}"))
        lines.append(status_line(stats["clipped_pairs"] >= 0, f"Clipped pairs={stats['clipped_pairs']:,} (p_min={cfg.p_min})"))
    else:
        adjacency = build_binary_adjacency_from_edges(edges_df, node_ids)
        lines.append(status_line(adjacency.count_nonzero() > 0, f"Built binary adjacency nnz={adjacency.count_nonzero():,}"))

    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify observation-aware adjacency construction")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--mode", choices=["off", "ipw"], default="off")
    parser.add_argument("--p-min", type=float, default=0.01)
    parser.add_argument("--completeness-floor", type=float, default=0.01)
    args = parser.parse_args()

    lines = run(args.data_dir, args.mode, args.p_min, args.completeness_floor)

    print("Observation Weighting Verification")
    print("=" * 33)
    for line in lines:
        print(line)

    failures = [line for line in lines if line.startswith("✗")]
    print("\nNext steps")
    if failures:
        print("- Resolve missing snapshot artifacts or invalid settings.")
        print("- Re-run with: python -m scripts.verify_observation_weighting --mode ipw")
        raise SystemExit(1)

    if args.mode == "off":
        print("- Baseline adjacency checks passed.")
        print("- Run IPW mode next: python -m scripts.verify_observation_weighting --mode ipw")
    else:
        print("- IPW adjacency checks passed.")
        print("- Compare cluster latency before enabling obs_weighting=ipw by default.")


if __name__ == "__main__":
    main()
