from __future__ import annotations

import pickle

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from src.artifacts.digests import file_sha256
from src.artifacts.propagation_alignment import ArtifactCompatibilityError
from src.artifacts.tpot_inputs import load_bound_tpot_inputs


def _write_propagation(path, node_ids):
    n_nodes = len(node_ids)
    np.savez(
        path,
        node_ids=np.asarray(node_ids),
        memberships=np.column_stack(
            (
                np.full(n_nodes, 0.8, dtype=np.float32),
                np.full(n_nodes, 0.2, dtype=np.float32),
            )
        ),
        uncertainty=np.zeros(n_nodes, dtype=np.float32),
        labeled_mask=np.zeros(n_nodes, dtype=bool),
        community_ids=np.array(["community-1"]),
        community_names=np.array(["one"]),
        community_colors=np.array(["#111111"]),
        converged=np.array([True, True]),
        mode=np.array("classic"),
    )


def test_loads_and_binds_graph_cache_and_first_compatible_propagation(tmp_path):
    nodes = pd.DataFrame({"node_id": ["a", "b", "c"]})
    edges = pd.DataFrame({"source": ["a"], "target": ["b"]})
    nodes.to_parquet(tmp_path / "graph_snapshot.nodes.parquet", index=False)
    edges.to_parquet(tmp_path / "graph_snapshot.edges.parquet", index=False)
    adjacency = sparse.csr_matrix(([1.0], ([0], [1])), shape=(3, 3))
    with (tmp_path / "adjacency_matrix_cache.pkl").open("wb") as handle:
        pickle.dump(adjacency, handle)
    _write_propagation(tmp_path / "incompatible.npz", ["a", "outside"])
    _write_propagation(tmp_path / "compatible.npz", ["c", "a", "b"])

    inputs = load_bound_tpot_inputs(
        tmp_path,
        ["incompatible.npz", "compatible.npz"],
    )

    assert inputs.binding.node_count == 3
    assert inputs.propagation.path.name == "compatible.npz"
    np.testing.assert_array_equal(
        inputs.propagation.graph_node_ids,
        np.array(["a", "b", "c"]),
    )
    assert (
        inputs.provenance["graph"]["ordered_node_sha256"]
        == inputs.propagation.graph_node_sha256
    )


def test_rejects_independent_lift_for_probability_relevance(tmp_path):
    nodes = pd.DataFrame({"node_id": ["a", "b"]})
    edges = pd.DataFrame({"source": ["a"], "target": ["b"]})
    nodes.to_parquet(tmp_path / "graph_snapshot.nodes.parquet", index=False)
    edges.to_parquet(tmp_path / "graph_snapshot.edges.parquet", index=False)
    adjacency = sparse.csr_matrix(([1.0], ([0], [1])), shape=(2, 2))
    with (tmp_path / "adjacency_matrix_cache.pkl").open("wb") as handle:
        pickle.dump(adjacency, handle)
    _write_propagation(tmp_path / "independent.npz", ["a", "b"])
    with np.load(tmp_path / "independent.npz") as payload:
        arrays = {key: payload[key] for key in payload.files}
    arrays["mode"] = np.array("independent")
    arrays["memberships"] = np.array(
        [[3.0, 0.2], [1.0, 4.0]],
        dtype=np.float32,
    )
    np.savez(tmp_path / "independent.npz", **arrays)

    with pytest.raises(
        ArtifactCompatibilityError,
        match="requires classic probability-simplex",
    ):
        load_bound_tpot_inputs(tmp_path, ["independent.npz"])


def test_undeclared_mode_requires_exact_certified_legacy_hash(tmp_path):
    nodes = pd.DataFrame({"node_id": ["a", "b"]})
    edges = pd.DataFrame({"source": ["a"], "target": ["b"]})
    nodes.to_parquet(tmp_path / "graph_snapshot.nodes.parquet", index=False)
    edges.to_parquet(tmp_path / "graph_snapshot.edges.parquet", index=False)
    adjacency = sparse.csr_matrix(([1.0], ([0], [1])), shape=(2, 2))
    with (tmp_path / "adjacency_matrix_cache.pkl").open("wb") as handle:
        pickle.dump(adjacency, handle)
    propagation_path = tmp_path / "legacy.npz"
    _write_propagation(propagation_path, ["a", "b"])
    with np.load(propagation_path) as payload:
        arrays = {
            key: payload[key]
            for key in payload.files
            if key != "mode"
        }
    np.savez(propagation_path, **arrays)

    with pytest.raises(
        ArtifactCompatibilityError,
        match="explicitly declared propagation mode",
    ):
        load_bound_tpot_inputs(tmp_path, ["legacy.npz"])

    inputs = load_bound_tpot_inputs(
        tmp_path,
        ["legacy.npz"],
        legacy_undeclared_mode_sha256=file_sha256(propagation_path),
    )
    assert inputs.provenance["propagation"]["mode_declared"] is False
