from __future__ import annotations

import json

import numpy as np
import pytest

from src.artifacts.spectral_binding import (
    SpectralBindingError,
    validate_spectral_binding,
)


def _write_spectral(
    tmp_path,
    node_ids,
    *,
    embedding=None,
    approximate=False,
    micro_labels=None,
):
    node_ids = np.asarray(node_ids)
    embedding = (
        np.asarray(embedding)
        if embedding is not None
        else np.ones((len(node_ids), 2))
    )
    arrays = {
        "node_ids": node_ids,
        "embedding": embedding,
        "eigenvalues": np.ones(embedding.shape[1]),
        "linkage": np.ones((max(0, len(node_ids) - 1), 4)),
    }
    if approximate:
        labels = (
            np.asarray(micro_labels)
            if micro_labels is not None
            else np.array([0, 0, 1, 1])
        )
        arrays.update(
            {
                "micro_labels": labels,
                "micro_centroids": np.ones((2, embedding.shape[1])),
                "linkage": np.ones((1, 4)),
            }
        )
    npz_path = tmp_path / "snapshot.spectral.npz"
    metadata_path = tmp_path / "snapshot.spectral_meta.json"
    np.savez(npz_path, **arrays)
    metadata_path.write_text(
        json.dumps(
            {
                "n_nodes": len(node_ids),
                "n_dims": embedding.shape[1],
                "approximate_clustering": approximate,
            }
        )
    )
    return npz_path, metadata_path


def test_validates_direct_spectral_result(tmp_path):
    paths = _write_spectral(tmp_path, ["a", "b", "c"])

    result = validate_spectral_binding(*paths, np.array(["a", "b", "c"]))

    assert result.node_count == 3
    assert result.embedding_dims == 2
    assert result.linkage_rows == 2
    assert result.approximate is False
    assert len(result.ordered_node_sha256) == 64


def test_validates_approximate_spectral_result(tmp_path):
    paths = _write_spectral(
        tmp_path,
        ["a", "b", "c", "d"],
        approximate=True,
    )

    result = validate_spectral_binding(
        *paths,
        np.array(["a", "b", "c", "d"]),
    )

    assert result.approximate is True
    assert result.micro_cluster_count == 2
    assert result.linkage_rows == 1


def test_rejects_reordered_spectral_node_ids(tmp_path):
    paths = _write_spectral(tmp_path, ["b", "a", "c"])

    with pytest.raises(SpectralBindingError, match="node order mismatch"):
        validate_spectral_binding(*paths, np.array(["a", "b", "c"]))


def test_rejects_spectral_node_count_mismatch_descriptively(tmp_path):
    paths = _write_spectral(tmp_path, ["a", "b"])

    with pytest.raises(
        SpectralBindingError,
        match=r"node order mismatch.*expected=3, actual=2",
    ):
        validate_spectral_binding(*paths, np.array(["a", "b", "c"]))


def test_rejects_embedding_row_or_metadata_mismatch(tmp_path):
    paths = _write_spectral(
        tmp_path,
        ["a", "b", "c"],
        embedding=np.ones((2, 2)),
    )

    with pytest.raises(SpectralBindingError, match="embedding shape"):
        validate_spectral_binding(*paths, np.array(["a", "b", "c"]))

    paths = _write_spectral(tmp_path, ["a", "b", "c"])
    paths[1].write_text(
        json.dumps(
            {
                "n_nodes": 99,
                "n_dims": 2,
                "approximate_clustering": False,
            }
        )
    )
    with pytest.raises(SpectralBindingError, match="metadata n_nodes=99"):
        validate_spectral_binding(*paths, np.array(["a", "b", "c"]))


def test_rejects_nonfinite_spectral_arrays_and_invalid_micro_labels(tmp_path):
    paths = _write_spectral(
        tmp_path,
        ["a", "b", "c"],
        embedding=np.array([[1.0, 0.0], [np.nan, 1.0], [0.0, 1.0]]),
    )
    with pytest.raises(SpectralBindingError, match="embedding.*finite"):
        validate_spectral_binding(*paths, np.array(["a", "b", "c"]))

    paths = _write_spectral(
        tmp_path,
        ["a", "b", "c", "d"],
        approximate=True,
        micro_labels=np.array([0.0, 0.0, np.nan, 1.0]),
    )
    with pytest.raises(SpectralBindingError, match="micro_labels.*integers"):
        validate_spectral_binding(
            *paths,
            np.array(["a", "b", "c", "d"]),
        )
