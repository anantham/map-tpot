"""Verification script for spectral clustering pipeline."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from src.graph.clusters import build_cluster_view, ClusterLabelStore
from src.graph.spectral import load_spectral_result


def status_line(ok: bool, msg: str) -> str:
    return f"{'✓' if ok else '✗'} {msg}"


def load_array(path: Path) -> np.ndarray:
    if path.suffix == ".npy":
        return np.load(path)
    raise ValueError(f"Unsupported array format: {path}")


def run_checks(base_path: Path, granularity: int = 25) -> list[str]:
    lines = []
    start = time.time()
    spec = load_spectral_result(base_path)
    load_time = time.time() - start
    lines.append(status_line(True, f"Loaded spectral result in {load_time:.3f}s"))

    # Basic shape checks
    lines.append(status_line(spec.embedding.shape[0] == len(spec.node_ids), f"Embedding rows match node_ids ({spec.embedding.shape[0]})"))
    lines.append(status_line(spec.embedding.shape[1] == len(spec.eigenvalues), f"Embedding dims match eigenvalues ({spec.embedding.shape[1]})"))

    # Minimal cluster build using synthetic adjacency (identity) to keep this lightweight
    n = spec.embedding.shape[0]
    adjacency = np.zeros((n, n))
    node_metadata = {nid: {"username": str(nid), "num_followers": 0} for nid in spec.node_ids}
    label_store = ClusterLabelStore(base_path.parent / "clusters.db")

    start = time.time()
    view = build_cluster_view(
        embedding=spec.embedding,
        linkage_matrix=spec.linkage_matrix,
        node_ids=spec.node_ids,
        adjacency=adjacency,
        node_metadata=node_metadata,
        granularity=granularity,
        label_store=label_store,
        signal_weights={"spectral": 1.0, "louvain": 0.0},
        # Pass micro-cluster artifacts when present (approximate mode)
        micro_labels=getattr(spec, "micro_labels", None),
        micro_centroids=getattr(spec, "micro_centroids", None),
    )
    build_time = time.time() - start
    lines.append(status_line(True, f"Cluster view built (granularity={granularity}) in {build_time:.3f}s"))
    lines.append(status_line(len(view.clusters) + len(view.individual_nodes) > 0, "Clusters or individuals present"))

    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify spectral cluster artifacts.")
    parser.add_argument("--base-path", type=Path, default=Path("data/graph_snapshot"), help="Base path for spectral artifacts (.spectral.npz/.json)")
    parser.add_argument("--granularity", type=int, default=25)
    args = parser.parse_args()

    lines = run_checks(args.base_path, granularity=args.granularity)
    print("\nVerification results:")
    for line in lines:
        print(line)

    failures = [ln for ln in lines if ln.startswith("✗")]
    if failures:
        print("\nNext steps:")
        print("- Inspect spectral artifacts and adjacency input")
        print("- Rerun scripts/build_spectral.py and retry verification")
    else:
        print("\nAll checks passed. Ready for API/visualization integration.")


if __name__ == "__main__":
    main()
