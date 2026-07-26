"""Manifest and inspection helpers for Community Archive Parquet snapshots."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from src.archive.snapshot import (
    DownloadRecord,
    RemoteObjectMetadata,
    utc_iso,
)
from src.archive.snapshot_contract import (
    DATA_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_SCHEMA_VERSION,
    REQUIRED_COLUMNS,
    SNAPSHOT_KIND,
    SnapshotCheck,
)
from src.archive.snapshot_validation import verify_snapshot_directory


def inspect_enriched_tweets_parquet(path: Path) -> dict[str, Any]:
    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    columns = schema.names
    missing = sorted(REQUIRED_COLUMNS - set(columns))
    if missing:
        raise ValueError(
            "Community Archive Parquet is missing required columns: "
            + ", ".join(missing)
        )
    invalid_id_types = [
        f"{name}={schema.field(name).type}"
        for name in ("tweet_id", "account_id")
        if not (
            pa.types.is_string(schema.field(name).type)
            or pa.types.is_large_string(schema.field(name).type)
        )
    ]
    if invalid_id_types:
        raise ValueError(
            "Community Archive Parquet must preserve snowflake values as string IDs; "
            + ", ".join(invalid_id_types)
        )
    created_type = schema.field("created_at").type
    if not pa.types.is_timestamp(created_type) or created_type.tz is None:
        raise ValueError(
            "Community Archive created_at must be a timezone-aware timestamp; "
            f"got {created_type}"
        )

    account_ids: set[str] = set()
    created_min: datetime | None = None
    created_max: datetime | None = None
    linked_rows = 0
    missing_upload_id_rows = 0
    scanned_rows = 0
    sample_rows: list[dict[str, Any]] = []

    for batch in parquet.iter_batches(
        batch_size=262_144,
        columns=["tweet_id", "account_id", "created_at", "archive_upload_id"],
    ):
        scanned_rows += batch.num_rows
        account_ids.update(
            str(value)
            for value in batch.column("account_id").to_pylist()
            if value is not None
        )
        created = pc.min_max(batch.column("created_at")).as_py()
        batch_min = created.get("min")
        batch_max = created.get("max")
        if batch_min is not None:
            if isinstance(batch_min, str):
                batch_min = datetime.fromisoformat(batch_min.replace("Z", "+00:00"))
            created_min = batch_min if created_min is None else min(created_min, batch_min)
        if batch_max is not None:
            if isinstance(batch_max, str):
                batch_max = datetime.fromisoformat(batch_max.replace("Z", "+00:00"))
            created_max = batch_max if created_max is None else max(created_max, batch_max)
        upload_ids = batch.column("archive_upload_id")
        missing_upload_id_rows += upload_ids.null_count
        linked_rows += batch.num_rows - upload_ids.null_count
        remaining_samples = 5 - len(sample_rows)
        if remaining_samples > 0:
            tweet_values = batch.column("tweet_id").slice(0, remaining_samples)
            account_values = batch.column("account_id").slice(0, remaining_samples)
            created_values = batch.column("created_at").slice(0, remaining_samples)
            upload_values = upload_ids.slice(0, remaining_samples)
            for tweet_id, account_id, created_at, upload_id in zip(
                tweet_values.to_pylist(),
                account_values.to_pylist(),
                created_values.to_pylist(),
                upload_values.to_pylist(),
            ):
                sample_rows.append(
                    {
                        "tweet_id": tweet_id,
                        "account_id": account_id,
                        "created_at": utc_iso(created_at),
                        "archive_upload_id": upload_id,
                    }
                )

    row_count = parquet.metadata.num_rows
    if scanned_rows != row_count:
        raise ValueError(
            f"Parquet row scan mismatch: metadata={row_count}, scanned={scanned_rows}"
        )
    return {
        "row_count": row_count,
        "account_count": len(account_ids),
        "columns": columns,
        "created_at_min": utc_iso(created_min) if created_min else None,
        "created_at_max": utc_iso(created_max) if created_max else None,
        "archive_upload_linked_rows": linked_rows,
        "archive_upload_id_missing_rows": missing_upload_id_rows,
        "sample_rows": sample_rows,
    }


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
