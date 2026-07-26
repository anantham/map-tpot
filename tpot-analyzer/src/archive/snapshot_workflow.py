"""High-level acquisition workflow for immutable Community Archive snapshots."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from src.archive.snapshot import RemoteObjectMetadata, download_remote_object
from src.archive.snapshot_contract import (
    DATA_FILENAME,
    MANIFEST_FILENAME,
    SnapshotCheck,
)
from src.archive.snapshot_manifest import (
    create_snapshot_manifest,
    inspect_enriched_tweets_parquet,
    verify_local_snapshot,
    write_snapshot_manifest,
)


@dataclass(frozen=True)
class SnapshotAcquisitionResult:
    status: Literal["downloaded", "reused"]
    snapshot_dir: Path
    manifest_path: Path
    checks: list[SnapshotCheck]
    metrics: dict[str, object]


def _failed_checks(checks: list[SnapshotCheck]) -> str:
    return "; ".join(
        f"{check.name}: {check.detail}" for check in checks if not check.passed
    )


def _source_matches(
    manifest_path: Path,
    metadata: RemoteObjectMetadata,
) -> bool:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = manifest.get("source", {})
    return (
        manifest.get("snapshot_id") == metadata.snapshot_id
        and source.get("url") == metadata.url
        and source.get("etag") == metadata.etag
        and source.get("last_modified") == metadata.last_modified
        and source.get("content_length") == metadata.content_length
    )


def acquire_enriched_tweets_snapshot(
    client: httpx.Client,
    metadata: RemoteObjectMetadata,
    output_root: Path,
    *,
    max_bytes: int,
    git_sha: str,
    git_dirty: bool,
) -> SnapshotAcquisitionResult:
    if max_bytes <= 0:
        raise ValueError(f"Download byte limit must be positive; got {max_bytes}")
    if metadata.content_length > max_bytes:
        raise ValueError(
            "Remote object exceeds download byte limit: "
            f"remote={metadata.content_length}, limit={max_bytes}"
        )
    if (
        not metadata.snapshot_id
        or Path(metadata.snapshot_id).name != metadata.snapshot_id
        or metadata.snapshot_id in {".", ".."}
    ):
        raise ValueError(f"Unsafe snapshot ID: {metadata.snapshot_id!r}")

    snapshot_dir = output_root / metadata.snapshot_id
    manifest_path = snapshot_dir / MANIFEST_FILENAME
    if snapshot_dir.is_symlink():
        raise RuntimeError(f"Snapshot directory must not be a symlink: {snapshot_dir}")

    if manifest_path.exists():
        checks, metrics = verify_local_snapshot(snapshot_dir, deep=True)
        if not all(check.passed for check in checks):
            raise RuntimeError(
                "Existing snapshot failed verification; refusing reuse: "
                + _failed_checks(checks)
            )
        if not _source_matches(manifest_path, metadata):
            raise RuntimeError(
                "Existing snapshot manifest does not match the probed remote object"
            )
        return SnapshotAcquisitionResult(
            status="reused",
            snapshot_dir=snapshot_dir,
            manifest_path=manifest_path,
            checks=checks,
            metrics=metrics,
        )

    if snapshot_dir.exists() and any(snapshot_dir.iterdir()):
        raise RuntimeError(
            "Snapshot directory contains unmanifested files; refusing to overwrite: "
            f"{snapshot_dir}"
        )
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    data_path = snapshot_dir / DATA_FILENAME
    download = download_remote_object(
        client,
        metadata,
        data_path,
        max_bytes=max_bytes,
    )
    dataset = inspect_enriched_tweets_parquet(data_path)
    manifest = create_snapshot_manifest(
        metadata,
        download,
        dataset,
        git_sha=git_sha,
        git_dirty=git_dirty,
    )
    write_snapshot_manifest(manifest_path, manifest)
    checks, metrics = verify_local_snapshot(snapshot_dir, deep=True)
    if not all(check.passed for check in checks):
        raise RuntimeError(
            "New snapshot failed post-publication verification: "
            + _failed_checks(checks)
        )
    return SnapshotAcquisitionResult(
        status="downloaded",
        snapshot_dir=snapshot_dir,
        manifest_path=manifest_path,
        checks=checks,
        metrics=metrics,
    )
