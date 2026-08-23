"""Persisted hash contract for the certified frozen research control."""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.artifacts.digests import file_sha256

MANIFEST_RELATIVE_PATH = Path("manifests/frozen_control_compatibility.json")
REQUIRED_FROZEN_FILES = {
    "graph_snapshot.nodes.parquet",
    "graph_snapshot.edges.parquet",
    "adjacency_matrix_cache.pkl",
    "graph_snapshot.spectral.npz",
    "graph_snapshot.spectral_meta.json",
    "community_propagation_train.npz",
    "tpot_calibration.json",
    "tpot_holdout_seeds.json",
    "tpot_relevance_scores.npy",
    "graph_snapshot_tpot.mapping.json",
    "graph_snapshot_tpot.nodes.parquet",
    "graph_snapshot_tpot.edges.parquet",
    "graph_snapshot_tpot.spectral.npz",
    "graph_snapshot_tpot.spectral_meta.json",
    "adjacency_matrix_cache.tpot.pkl",
}
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class FrozenManifestError(ValueError):
    """Raised when a frozen-control file differs from its persisted identity."""


def load_frozen_manifest(data_dir: Path) -> dict:
    """Load and structurally validate the frozen-control manifest."""
    data_dir = Path(data_dir)
    path = data_dir / MANIFEST_RELATIVE_PATH
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise FrozenManifestError(f"cannot read frozen manifest {path}: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise FrozenManifestError("frozen manifest must declare schema_version=1")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise FrozenManifestError("frozen manifest files must be an object")
    selected_propagation = manifest.get("selected_propagation")
    if (
        not isinstance(selected_propagation, str)
        or Path(selected_propagation).name != selected_propagation
        or selected_propagation not in files
    ):
        raise FrozenManifestError(
            "frozen manifest selected_propagation must be a safe top-level "
            "filename present in files"
        )
    missing = sorted(REQUIRED_FROZEN_FILES - set(files))
    if missing:
        raise FrozenManifestError(
            f"frozen manifest is missing required files: {missing}"
        )
    for filename, record in files.items():
        if Path(filename).name != filename:
            raise FrozenManifestError(
                f"frozen manifest filename must be top-level: {filename!r}"
            )
        if not isinstance(record, dict):
            raise FrozenManifestError(
                f"frozen manifest record must be an object: {filename}"
            )
        size = record.get("size_bytes")
        digest = record.get("sha256")
        if isinstance(size, bool) or not isinstance(size, int) or size < 1:
            raise FrozenManifestError(
                f"frozen manifest size_bytes is invalid for {filename}: {size!r}"
            )
        if not isinstance(digest, str) or not _SHA256_PATTERN.fullmatch(digest):
            raise FrozenManifestError(
                f"frozen manifest sha256 is invalid for {filename}: {digest!r}"
            )
    return manifest


def expected_frozen_file_sha256(data_dir: Path, filename: str) -> str:
    """Return the persisted expected hash for one frozen-control file."""
    return load_frozen_manifest(data_dir)["files"][filename]["sha256"]


def verify_frozen_manifest(data_dir: Path) -> dict:
    """Hash every pinned file and fail on size or content drift."""
    data_dir = Path(data_dir)
    manifest = load_frozen_manifest(data_dir)
    total_bytes = 0
    for filename, record in sorted(manifest["files"].items()):
        path = data_dir / filename
        if not path.is_file():
            raise FrozenManifestError(f"frozen control file is absent: {path}")
        observed_size = path.stat().st_size
        if observed_size != record["size_bytes"]:
            raise FrozenManifestError(
                f"frozen manifest size mismatch for {filename}: "
                f"expected={record['size_bytes']}, observed={observed_size}"
            )
        observed_hash = file_sha256(path)
        if observed_hash != record["sha256"]:
            raise FrozenManifestError(
                f"frozen manifest hash mismatch for {filename}: "
                f"expected={record['sha256']}, observed={observed_hash}"
            )
        total_bytes += observed_size
    print(
        "✓ Persisted frozen manifest pins scientific file contents: "
        f"files={len(manifest['files'])}, bytes={total_bytes:,}, "
        f"bundle_id={manifest.get('bundle_id')}, "
        f"selected_propagation={manifest['selected_propagation']}"
    )
    return manifest
