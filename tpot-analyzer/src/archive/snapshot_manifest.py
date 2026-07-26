"""Manifest and inspection helpers for Community Archive Parquet snapshots."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from src.archive.snapshot import (
    DownloadRecord,
    RemoteObjectMetadata,
)
from src.archive.snapshot_contract import (
    DATA_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_SCHEMA_VERSION,
    SNAPSHOT_KIND,
    SnapshotCheck,
)
from src.archive.snapshot_inspection import inspect_enriched_tweets_parquet
from src.archive.snapshot_validation import verify_snapshot_directory


def create_snapshot_manifest(
    metadata: RemoteObjectMetadata,
    download: DownloadRecord,
    dataset: dict[str, Any],
    *,
    git_sha: str,
    git_dirty: bool,
) -> dict[str, Any]:
    if download.size_bytes != metadata.content_length:
        raise ValueError(
            "Downloaded size does not match remote metadata: "
            f"{download.size_bytes} != {metadata.content_length}"
        )
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": SNAPSHOT_KIND,
        "snapshot_id": metadata.snapshot_id,
        "created_at": metadata.observed_at,
        "source": {
            "url": metadata.url,
            "etag": metadata.etag,
            "last_modified": metadata.last_modified,
            "content_length": metadata.content_length,
            "content_type": metadata.content_type,
            "observed_at": metadata.observed_at,
        },
        "local": {
            "filename": download.path.name,
            "size_bytes": download.size_bytes,
            "sha256": download.sha256,
        },
        "dataset": dataset,
        "acquisition_code": {
            "git_sha": git_sha,
            "git_dirty": git_dirty,
        },
    }


def write_snapshot_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(
            f"Refusing to overwrite snapshot manifest that already exists: {path}"
        )
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        temporary.unlink()
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def verify_local_snapshot(
    snapshot_dir: Path,
    *,
    deep: bool = False,
) -> tuple[list[SnapshotCheck], dict[str, Any]]:
    return verify_snapshot_directory(snapshot_dir, deep=deep)
