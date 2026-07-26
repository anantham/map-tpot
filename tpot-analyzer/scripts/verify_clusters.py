"""Verification script for the spectral clustering pipeline.

Test intent: this diagnostic script is itself the human-facing verification
surface, so it has no duplicate unit test. CI executes both supported fixture
granularities and treats any exception or failed check as a non-zero result.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from scipy import sparse

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

    # Empty sparse adjacency keeps this verifier safe for production-scale n.
    n = spec.embedding.shape[0]
    adjacency = sparse.csr_matrix((n, n), dtype=float)
    node_metadata = {nid: {"username": str(nid), "num_followers": 0} for nid in spec.node_ids}
    start = time.time()
    with TemporaryDirectory(prefix="tpot-cluster-verifier-") as temp_dir:
        label_store = ClusterLabelStore(Path(temp_dir) / "clusters.db")
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify spectral cluster artifacts.")
    parser.add_argument("--base-path", type=Path, default=Path("data/graph_snapshot"), help="Base path for spectral artifacts (.spectral.npz/.json)")
    parser.add_argument("--granularity", type=int, default=25)
    args = parser.parse_args()

    try:
        lines = run_checks(args.base_path, granularity=args.granularity)
    except Exception as exc:
        print("\nVerification results:")
        print(status_line(False, f"{type(exc).__name__}: {exc}"))
        print("\nMetrics:")
        print("- checks_passed: 0")
        print("\nNext steps:")
        print("- Confirm the base path has matching .spectral.npz and metadata artifacts")
        print("- Rebuild a deterministic fixture or spectral snapshot, then retry")
        return 1

    print("\nVerification results:")
    for line in lines:
        print(line)

    failures = [ln for ln in lines if ln.startswith("✗")]
    if failures:
        print("\nNext steps:")
        print("- Inspect spectral artifacts and adjacency input")
        print("- Rerun scripts/build_spectral.py and retry verification")
        return 1
    else:
        print("\nAll checks passed. Ready for API/visualization integration.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
