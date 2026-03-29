"""I/O utilities for propagation — save results and build adjacency from archive."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy.sparse as sp

from src.propagation.types import PropagationResult


def save_results(result: PropagationResult, output_dir: Path) -> Path:
    """Save propagation results as compressed numpy archive.

    Creates two files:
    - Timestamped archive in data/community_propagation_runs/
    - Active pointer at data/community_propagation.npz
    """
    archive_dir = output_dir / "community_propagation_runs"
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = archive_dir / f"{timestamp}.npz"

    active_path = output_dir / "community_propagation.npz"

    save_arrays = dict(
        memberships=result.memberships.astype(np.float32),
        uncertainty=result.uncertainty.astype(np.float32),
        abstain_mask=result.abstain_mask,
        labeled_mask=result.labeled_mask,
        node_ids=result.node_ids,
        community_ids=np.array(result.community_ids),
        community_names=np.array(result.community_names),
        community_colors=np.array(result.community_colors),
        converged=np.array(result.converged, dtype=bool),
        cg_iterations=np.array(result.cg_iterations, dtype=np.int32),
        mode=np.array(result.config.mode),
    )
    if result.seed_neighbor_counts is not None:
        save_arrays["seed_neighbor_counts"] = result.seed_neighbor_counts.astype(np.int16)

    np.savez_compressed(str(archive_path), **save_arrays)
    np.savez_compressed(str(active_path), **save_arrays)

    print(f"\nResults saved:")
    print(f"  Archive: {archive_path}")
    print(f"  Active:  {active_path}")
    print(f"  Size: {active_path.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"  Arrays: {list(save_arrays.keys())}")
    return active_path


def build_adjacency_from_archive(
    db_path: Path,
    weighted: bool = True,
    edge_weights: dict[str, float] | None = None,
) -> tuple[sp.csr_matrix, list[str]]:
    """Build adjacency matrix from archive_tweets.db using TypedGraph.

    Returns (adjacency: csr_matrix, node_ids: list[str])

    Loads all available edge types into a TypedGraph, then combines them
    with configurable per-type weights. See typed_graph.py for edge type
    semantics.

    Args:
        db_path: Path to archive_tweets.db.
        weighted: If True, load all edge types. If False, follow-only.
        edge_weights: Per-type weights for combination. Defaults to
            DEFAULT_EDGE_WEIGHTS from typed_graph.py.
    """
    from src.propagation.typed_graph import TypedGraph

    load_types = None if weighted else {"follow"}
    print(f"\nBuilding adjacency from {db_path.name}...")
    graph = TypedGraph.from_archive(db_path, load_types=load_types)

    adj = graph.combine(weights=edge_weights)
    print(f"\n  Combined graph: {graph.n:,} nodes, {adj.nnz:,} edges")

    return adj, graph.node_ids
