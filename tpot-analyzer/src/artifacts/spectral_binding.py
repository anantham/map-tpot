"""Validate persisted spectral arrays against an authoritative node order."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.artifacts.digests import ordered_node_digest


class SpectralBindingError(ValueError):
    """Raised when a spectral result does not belong to its graph."""


@dataclass(frozen=True)
class SpectralBinding:
    node_count: int
    embedding_dims: int
    linkage_rows: int
    approximate: bool
    micro_cluster_count: int | None
    ordered_node_sha256: str


def _normalized_ids(values, *, label: str) -> np.ndarray:
    raw = np.asarray(values)
    if raw.ndim != 1:
        raise SpectralBindingError(
            f"{label} node IDs must be one-dimensional; got {raw.shape}"
        )
    normalized = np.asarray([str(value) for value in raw])
    if len(np.unique(normalized)) != len(normalized):
        raise SpectralBindingError(f"{label} node IDs contain duplicates")
    return normalized


def _require_finite_numeric(array: np.ndarray, *, label: str) -> None:
    if not np.issubdtype(array.dtype, np.number):
        raise SpectralBindingError(f"{label} must be numeric; got {array.dtype}")
    if not np.all(np.isfinite(array)):
        raise SpectralBindingError(f"{label} values must all be finite")


def validate_spectral_binding(
    npz_path: Path,
    metadata_path: Path,
    expected_node_ids,
) -> SpectralBinding:
    """Validate spectral arrays and metadata."""
    npz_path = Path(npz_path)
    metadata_path = Path(metadata_path)
    try:
        with np.load(npz_path, allow_pickle=False) as payload:
            required = {"embedding", "node_ids", "eigenvalues", "linkage"}
            missing = sorted(required - set(payload.files))
            if missing:
                raise SpectralBindingError(
                    f"{npz_path} is missing spectral arrays: {missing}"
                )
            arrays = {key: np.asarray(payload[key]) for key in payload.files}
        metadata = json.loads(metadata_path.read_text())
    except SpectralBindingError:
        raise
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SpectralBindingError(
            f"cannot read spectral artifact {npz_path}: {exc}"
        ) from exc
    if not isinstance(metadata, dict):
        raise SpectralBindingError(
            f"spectral metadata root must be an object: {metadata_path}"
        )

    expected_ids = _normalized_ids(expected_node_ids, label="expected")
    actual_ids = _normalized_ids(arrays["node_ids"], label="spectral")
    if len(actual_ids) != len(expected_ids):
        raise SpectralBindingError(
            "spectral node order mismatch: "
            f"expected={len(expected_ids)}, actual={len(actual_ids)}, "
            "mismatch_positions=[]"
        )
    if not np.array_equal(actual_ids, expected_ids):
        mismatch = np.flatnonzero(actual_ids != expected_ids)
        raise SpectralBindingError(
            "spectral node order mismatch: "
            f"expected={len(expected_ids)}, actual={len(actual_ids)}, "
            f"mismatch_positions={mismatch[:5].tolist()}"
        )

    n_nodes = len(expected_ids)
    embedding = arrays["embedding"]
    if embedding.ndim != 2 or embedding.shape[0] != n_nodes:
        raise SpectralBindingError(
            f"embedding shape must be ({n_nodes}, dims); got {embedding.shape}"
        )
    _require_finite_numeric(embedding, label="embedding")
    n_dims = embedding.shape[1]
    if n_dims == 0:
        raise SpectralBindingError("embedding must have at least one dimension")
    if arrays["eigenvalues"].shape != (n_dims,):
        raise SpectralBindingError(
            "eigenvalue shape must match embedding dimensions: "
            f"eigenvalues={arrays['eigenvalues'].shape}, dims={n_dims}"
        )
    _require_finite_numeric(arrays["eigenvalues"], label="eigenvalues")
    if metadata.get("n_nodes") != n_nodes:
        raise SpectralBindingError(
            f"metadata n_nodes={metadata.get('n_nodes')!r}, expected {n_nodes}"
        )
    if metadata.get("n_dims") != n_dims:
        raise SpectralBindingError(
            f"metadata n_dims={metadata.get('n_dims')!r}, expected {n_dims}"
        )
    approximate = metadata.get("approximate_clustering")
    if not isinstance(approximate, bool):
        raise SpectralBindingError(
            "metadata approximate_clustering must be boolean"
        )

    linkage = arrays["linkage"]
    _require_finite_numeric(linkage, label="linkage")
    micro_count = None
    if approximate:
        missing_micro = {"micro_labels", "micro_centroids"} - set(arrays)
        if missing_micro:
            raise SpectralBindingError(
                f"approximate spectral result is missing {sorted(missing_micro)}"
            )
        labels = arrays["micro_labels"]
        centroids = arrays["micro_centroids"]
        if labels.shape != (n_nodes,):
            raise SpectralBindingError(
                f"micro_labels must have shape=({n_nodes},); got {labels.shape}"
            )
        if not np.issubdtype(labels.dtype, np.integer):
            raise SpectralBindingError(
                "micro_labels must contain finite integers"
            )
        if centroids.ndim != 2 or centroids.shape[1] != n_dims:
            raise SpectralBindingError(
                f"micro_centroids must have shape=(clusters, {n_dims}); "
                f"got {centroids.shape}"
            )
        _require_finite_numeric(centroids, label="micro_centroids")
        micro_count = centroids.shape[0]
        if micro_count == 0 or np.any(labels < 0) or np.any(labels >= micro_count):
            raise SpectralBindingError(
                f"micro_labels must index {micro_count} centroids"
            )
        expected_linkage = (max(0, micro_count - 1), 4)
    else:
        if {"micro_labels", "micro_centroids"} & set(arrays):
            raise SpectralBindingError(
                "direct spectral result must not contain micro-cluster arrays"
            )
        expected_linkage = (max(0, n_nodes - 1), 4)
    if linkage.shape != expected_linkage:
        raise SpectralBindingError(
            f"linkage must have shape={expected_linkage}; got {linkage.shape}"
        )

    return SpectralBinding(
        node_count=n_nodes,
        embedding_dims=n_dims,
        linkage_rows=linkage.shape[0],
        approximate=approximate,
        micro_cluster_count=micro_count,
        ordered_node_sha256=ordered_node_digest(expected_ids),
    )
