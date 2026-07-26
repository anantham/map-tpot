"""Load and prove compatibility of inputs shared by TPOT artifact pipelines."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

from src.artifacts.adjacency_binding import AdjacencyBinding
from src.artifacts.adjacency_binding import validate_adjacency_binding
from src.artifacts.digests import file_sha256
from src.artifacts.propagation_alignment import AlignedPropagation
from src.artifacts.propagation_alignment import ArtifactCompatibilityError
from src.artifacts.propagation_alignment import select_aligned_propagation
from src.artifacts.propagation_schema import propagation_score_semantics
from src.artifacts.provenance import build_artifact_provenance
from src.data.adjacency import load_adjacency_cache


@dataclass(frozen=True)
class BoundTpotInputs:
    """Graph tables, adjacency, propagation, and their compatibility record."""

    nodes: pd.DataFrame
    edges: pd.DataFrame
    adjacency: sp.csr_matrix
    binding: AdjacencyBinding
    propagation: AlignedPropagation
    provenance: dict
    nodes_path: Path
    edges_path: Path
    adjacency_path: Path

    @property
    def graph_node_ids(self) -> np.ndarray:
        return self.propagation.graph_node_ids


def load_bound_tpot_inputs(
    data_dir: Path,
    propagation_candidates: list[str | Path],
    *,
    legacy_undeclared_mode_sha256: str | None = None,
) -> BoundTpotInputs:
    """Load graph inputs and fail unless every positional identity is proven."""
    data_dir = Path(data_dir)
    nodes_path = data_dir / "graph_snapshot.nodes.parquet"
    edges_path = data_dir / "graph_snapshot.edges.parquet"
    adjacency_path = data_dir / "adjacency_matrix_cache.pkl"
    nodes = pd.read_parquet(nodes_path)
    edges = pd.read_parquet(edges_path)
    if "node_id" not in nodes.columns:
        raise ValueError(f"graph node table is missing node_id: {nodes_path}")
    graph_node_ids = nodes["node_id"].astype(str).to_numpy()
    adjacency = load_adjacency_cache(adjacency_path)
    binding = validate_adjacency_binding(adjacency, graph_node_ids, edges)
    candidate_paths = [
        path if Path(path).is_absolute() else data_dir / path
        for path in map(Path, propagation_candidates)
    ]
    propagation = select_aligned_propagation(
        graph_node_ids,
        adjacency,
        candidate_paths,
    )
    mode, score_semantics, mode_declared = propagation_score_semantics(
        propagation.arrays
    )
    if not mode_declared:
        observed_hash = file_sha256(propagation.path)
        if legacy_undeclared_mode_sha256 is None:
            raise ArtifactCompatibilityError(
                "TPOT inputs require an explicitly declared propagation mode; "
                f"{propagation.path.name} is mode-less and has no certified "
                "legacy hash exception"
            )
        if observed_hash != legacy_undeclared_mode_sha256:
            raise ArtifactCompatibilityError(
                "mode-less propagation does not match the certified legacy "
                f"hash: expected={legacy_undeclared_mode_sha256}, "
                f"observed={observed_hash}"
            )
    if score_semantics != "probability_simplex":
        raise ArtifactCompatibilityError(
            "TPOT relevance requires classic probability-simplex memberships; "
            f"selected {propagation.path.name} has mode={mode!r}, "
            f"score_semantics={score_semantics!r}"
        )
    provenance = build_artifact_provenance(
        binding,
        propagation,
        source_files={
            "nodes": nodes_path,
            "edges": edges_path,
            "adjacency_cache": adjacency_path,
        },
    )
    return BoundTpotInputs(
        nodes=nodes,
        edges=edges,
        adjacency=adjacency,
        binding=binding,
        propagation=propagation,
        provenance=provenance,
        nodes_path=nodes_path,
        edges_path=edges_path,
        adjacency_path=adjacency_path,
    )
