from __future__ import annotations

import json
import pickle

import numpy as np
import pandas as pd
from scipy import sparse

from scripts.verify_artifact_compatibility import verify
from src.artifacts.digests import file_sha256
from src.artifacts.frozen_manifest import REQUIRED_FROZEN_FILES
from src.graph.tpot_relevance import compute_relevance


def _write_spectral(data_dir, stem, node_ids):
    n_nodes = len(node_ids)
    np.savez(
        data_dir / f"{stem}.spectral.npz",
        embedding=np.ones((n_nodes, 1), dtype=np.float32),
        node_ids=np.asarray(node_ids),
        eigenvalues=np.array([0.1], dtype=np.float32),
        linkage=np.ones((n_nodes - 1, 4), dtype=np.float64),
    )
    (data_dir / f"{stem}.spectral_meta.json").write_text(
        json.dumps(
            {
                "n_nodes": n_nodes,
                "n_dims": 1,
                "approximate_clustering": False,
            }
        )
    )


def _write_propagation(path):
    np.savez(
        path,
        node_ids=np.array(["a", "b", "c"]),
        memberships=np.array(
            [[0.9, 0.1], [0.1, 0.9], [0.1, 0.9]],
            dtype=np.float32,
        ),
        uncertainty=np.zeros(3, dtype=np.float32),
        abstain_mask=np.zeros(3, dtype=bool),
        labeled_mask=np.array([True, False, False]),
        community_ids=np.array(["community-1"]),
        community_names=np.array(["one"]),
        community_colors=np.array(["#111111"]),
        converged=np.array([True, True]),
        cg_iterations=np.array([1, 1]),
    )


def _write_bundle(data_dir):
    nodes = pd.DataFrame(
        {
            "node_id": ["a", "b", "c"],
            "username": ["alpha", "beta", "gamma"],
        }
    )
    edges = pd.DataFrame(
        {
            "source": ["a"],
            "target": ["b"],
            "mutual": [False],
        }
    )
    nodes.to_parquet(data_dir / "graph_snapshot.nodes.parquet", index=False)
    edges.to_parquet(data_dir / "graph_snapshot.edges.parquet", index=False)
    adjacency = sparse.csr_matrix(([1.0], ([0], [1])), shape=(3, 3))
    with (data_dir / "adjacency_matrix_cache.pkl").open("wb") as handle:
        pickle.dump(adjacency, handle)
    _write_spectral(data_dir, "graph_snapshot", ["a", "b", "c"])
    _write_propagation(data_dir / "community_propagation_train.npz")
    relevance = compute_relevance(
        np.array(
            [[0.9, 0.1], [0.1, 0.9], [0.1, 0.9]],
            dtype=np.float32,
        ),
        np.zeros(3, dtype=np.float32),
        np.array([True, True]),
        np.array([1.0, 1.0, 0.0]),
        1.0,
    )
    np.save(data_dir / "tpot_relevance_scores.npy", relevance.astype(np.float32))

    (data_dir / "tpot_calibration.json").write_text(
        json.dumps(
            {
                "tau": 0.5,
                "calibrated": True,
                "n_nodes_total": 3,
                "n_core": 1,
                "n_halo": 1,
                "n_total": 2,
            }
        )
    )
    (data_dir / "tpot_holdout_seeds.json").write_text("{}")
    (data_dir / "graph_snapshot_tpot.mapping.json").write_text(
        json.dumps(
            {
                "tau": 0.5,
                "n_total_graph": 3,
                "n_tpot_subgraph": 2,
                "n_core": 1,
                "n_halo": 1,
                "tpot_node_ids": ["a", "b"],
            }
        )
    )
    nodes.iloc[:2].to_parquet(
        data_dir / "graph_snapshot_tpot.nodes.parquet",
        index=False,
    )
    edges.to_parquet(
        data_dir / "graph_snapshot_tpot.edges.parquet",
        index=False,
    )
    _write_spectral(data_dir, "graph_snapshot_tpot", ["a", "b"])
    with (data_dir / "adjacency_matrix_cache.tpot.pkl").open("wb") as handle:
        pickle.dump(
            sparse.csr_matrix(([1.0], ([0], [1])), shape=(2, 2)),
            handle,
        )
    records = {}
    for filename in REQUIRED_FROZEN_FILES:
        path = data_dir / filename
        records[filename] = {
            "size_bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
    manifest_path = (
        data_dir / "manifests" / "frozen_control_compatibility.json"
    )
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "bundle_id": "fixture",
                "selected_propagation": "community_propagation_train.npz",
                "files": records,
            }
        )
    )


def test_verifier_accepts_complete_compatible_fixture(tmp_path, capsys):
    _write_bundle(tmp_path)

    assert verify(tmp_path) == 0
    output = capsys.readouterr().out
    assert "✓ Persisted frozen manifest pins scientific file contents" in output
    assert "✓ Full spectral rows match authoritative graph order" in output
    assert "✓ Manifest-selected community_propagation_train.npz" in output
    assert "score_semantics=probability_simplex" in output
    assert "✓ TPOT runtime adjacency matches mutual-edge semantics" in output


def test_verifier_rejects_reordered_tpot_spectral_fixture(tmp_path, capsys):
    _write_bundle(tmp_path)
    _write_spectral(tmp_path, "graph_snapshot_tpot", ["b", "a"])

    assert verify(tmp_path) == 1
    output = capsys.readouterr().out
    assert "✗ Compatibility verification failed" in output
    assert "frozen manifest hash mismatch" in output


def test_verifier_rejects_changed_legacy_relevance_fixture(tmp_path, capsys):
    _write_bundle(tmp_path)
    np.save(
        tmp_path / "tpot_relevance_scores.npy",
        np.array([0.8, 0.1, 0.0], dtype=np.float32),
    )

    assert verify(tmp_path) == 1
    output = capsys.readouterr().out
    assert "✗ Compatibility verification failed" in output
    assert "frozen manifest hash mismatch" in output


def test_verifier_keeps_unpinned_compatible_active_candidate_diagnostic_only(
    tmp_path,
    capsys,
):
    _write_bundle(tmp_path)
    _write_propagation(tmp_path / "community_propagation.npz")

    assert verify(tmp_path) == 0
    output = capsys.readouterr().out
    assert "Propagation candidate community_propagation.npz: exact graph order" in output
    assert "✓ Manifest-selected community_propagation_train.npz" in output
