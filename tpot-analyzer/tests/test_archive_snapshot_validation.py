from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.archive.snapshot import (
    DownloadRecord,
    RemoteObjectMetadata,
    build_snapshot_id,
)
from src.archive.snapshot_manifest import (
    create_snapshot_manifest,
    inspect_enriched_tweets_parquet,
    verify_local_snapshot,
    write_snapshot_manifest,
)


def _metadata(size: int) -> RemoteObjectMetadata:
    url = "https://example.test/enriched_tweets.parquet"
    observed_at = "2026-07-26T00:00:00+00:00"
    etag = '"v1"'
    last_modified = "2026-07-25T04:51:22+00:00"
    return RemoteObjectMetadata(
        url=url,
        observed_at=observed_at,
        etag=etag,
        last_modified=last_modified,
        content_length=size,
        content_type="application/octet-stream",
        snapshot_id=build_snapshot_id(
            url,
            etag,
            last_modified,
            size,
            observed_at,
        ),
    )


def _valid_manifest(snapshot_dir):
    data_path = snapshot_dir / "enriched_tweets.parquet"
    data_path.write_bytes(b"snapshot")
    download = DownloadRecord(
        path=data_path,
        size_bytes=8,
        sha256=hashlib.sha256(b"snapshot").hexdigest(),
    )
    dataset = {
        "row_count": 3,
        "account_count": 2,
        "columns": [
            "tweet_id",
            "account_id",
            "username",
            "created_at",
            "full_text",
            "archive_upload_id",
        ],
        "created_at_min": "2025-01-01T00:00:00+00:00",
        "created_at_max": "2026-07-25T00:00:00+00:00",
        "archive_upload_linked_rows": 2,
        "archive_upload_id_missing_rows": 1,
        "sample_rows": [
            {
                "tweet_id": "1",
                "account_id": "a",
                "created_at": "2025-01-01T00:00:00+00:00",
                "archive_upload_id": 10,
            }
        ],
    }
    return create_snapshot_manifest(
        _metadata(8),
        download,
        dataset,
        git_sha="abc123",
        git_dirty=False,
    )


def test_inspection_rejects_numeric_snowflake_ids(tmp_path):
    path = tmp_path / "enriched_tweets.parquet"
    table = pa.table(
        {
            "tweet_id": [1],
            "account_id": [2],
            "username": ["one"],
            "created_at": pa.array(
                [datetime(2026, 7, 25, tzinfo=timezone.utc)],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "full_text": ["x"],
            "archive_upload_id": [10],
        }
    )
    pq.write_table(table, path)

    with pytest.raises(ValueError, match="string IDs"):
        inspect_enriched_tweets_parquet(path)


def test_verifier_returns_failed_check_for_non_object_manifest(tmp_path):
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    (snapshot_dir / "manifest.json").write_text("[]", encoding="utf-8")

    checks, metrics = verify_local_snapshot(snapshot_dir, deep=True)

    assert [(check.name, check.passed) for check in checks] == [
        ("manifest object", False)
    ]
    assert metrics == {}


def test_verifier_detects_cross_field_manifest_contradictions(tmp_path):
    snapshot_dir = tmp_path / _metadata(8).snapshot_id
    snapshot_dir.mkdir()
    manifest = _valid_manifest(snapshot_dir)
    manifest["source"]["content_length"] = 999
    manifest["dataset"]["archive_upload_linked_rows"] = 3
    manifest["dataset"]["archive_upload_id_missing_rows"] = 2
    (snapshot_dir / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    checks, _ = verify_local_snapshot(snapshot_dir, deep=True)
    outcomes = {check.name: check.passed for check in checks}

    assert outcomes["source/local byte size"] is False
    assert outcomes["dataset row partition"] is False
    assert outcomes["snapshot directory identity"] is True


def test_manifest_round_trip_verifies_size_and_hash(tmp_path):
    metadata = _metadata(8)
    snapshot_dir = tmp_path / metadata.snapshot_id
    snapshot_dir.mkdir()
    manifest = _valid_manifest(snapshot_dir)

    write_snapshot_manifest(snapshot_dir / "manifest.json", manifest)
    checks, metrics = verify_local_snapshot(snapshot_dir, deep=True)

    assert all(check.passed for check in checks)
    assert metrics["snapshot_id"] == metadata.snapshot_id
    assert json.loads((snapshot_dir / "manifest.json").read_text()) == manifest


def test_manifest_publication_never_overwrites_existing_manifest(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text('{"original": true}\n', encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        write_snapshot_manifest(path, {"replacement": True})

    assert json.loads(path.read_text(encoding="utf-8")) == {"original": True}
    assert not list(tmp_path.glob("*.tmp"))
