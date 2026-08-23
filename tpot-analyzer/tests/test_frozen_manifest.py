from __future__ import annotations

import json

import pytest

from src.artifacts.digests import file_sha256
from src.artifacts.frozen_manifest import (
    FrozenManifestError,
    REQUIRED_FROZEN_FILES,
    verify_frozen_manifest,
)


def _write_manifest(data_dir):
    records = {}
    for filename in REQUIRED_FROZEN_FILES:
        path = data_dir / filename
        path.write_bytes(filename.encode())
        records[filename] = {
            "size_bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
    manifest_path = data_dir / "manifests" / "frozen_control_compatibility.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "bundle_id": "test-control",
                "selected_propagation": "community_propagation_train.npz",
                "files": records,
            }
        )
    )


def test_verifies_every_persisted_frozen_file_hash(tmp_path, capsys):
    _write_manifest(tmp_path)

    manifest = verify_frozen_manifest(tmp_path)

    assert len(manifest["files"]) == len(REQUIRED_FROZEN_FILES)
    assert "pins scientific file contents" in capsys.readouterr().out


def test_rejects_tampered_frozen_file(tmp_path):
    _write_manifest(tmp_path)
    (tmp_path / "graph_snapshot.spectral.npz").write_bytes(b"tampered")

    with pytest.raises(FrozenManifestError, match="mismatch.*spectral"):
        verify_frozen_manifest(tmp_path)
