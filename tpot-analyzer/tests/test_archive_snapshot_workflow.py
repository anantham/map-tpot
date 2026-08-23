from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.archive.snapshot import RemoteObjectMetadata, build_snapshot_id
from src.archive.snapshot_workflow import acquire_enriched_tweets_snapshot


LAST_MODIFIED = "Sat, 25 Jul 2026 04:51:22 GMT"


def _parquet_payload(tmp_path) -> bytes:
    path = tmp_path / "source.parquet"
    table = pa.table(
        {
            "tweet_id": ["1", "2"],
            "account_id": ["a", "b"],
            "username": ["one", "two"],
            "created_at": pa.array(
                [
                    datetime(2026, 7, 24, tzinfo=timezone.utc),
                    datetime(2026, 7, 25, tzinfo=timezone.utc),
                ],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "full_text": ["x", "y"],
            "archive_upload_id": [10, None],
        }
    )
    pq.write_table(table, path)
    return path.read_bytes()


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


def test_acquisition_writes_verified_manifest_after_data(tmp_path):
    payload = _parquet_payload(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(
            200,
            content=payload,
            headers={
                "ETag": '"v1"',
                "Last-Modified": LAST_MODIFIED,
                "Content-Length": str(len(payload)),
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = acquire_enriched_tweets_snapshot(
            client,
            _metadata(len(payload)),
            tmp_path / "snapshots",
            max_bytes=len(payload),
            git_sha="abc123",
            git_dirty=False,
        )

    assert result.status == "downloaded"
    assert all(check.passed for check in result.checks)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["dataset"]["row_count"] == 2
    assert manifest["dataset"]["account_count"] == 2
    assert manifest["local"]["filename"] == "enriched_tweets.parquet"
    assert manifest["acquisition_code"] == {
        "git_dirty": False,
        "git_sha": "abc123",
    }


def test_acquisition_reuses_only_a_verified_matching_snapshot(tmp_path):
    payload = _parquet_payload(tmp_path)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            content=payload,
            headers={
                "ETag": '"v1"',
                "Last-Modified": LAST_MODIFIED,
                "Content-Length": str(len(payload)),
            },
        )

    output_root = tmp_path / "snapshots"
    metadata = _metadata(len(payload))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        acquire_enriched_tweets_snapshot(
            client,
            metadata,
            output_root,
            max_bytes=len(payload),
            git_sha="abc123",
            git_dirty=False,
        )
        reused = acquire_enriched_tweets_snapshot(
            client,
            metadata,
            output_root,
            max_bytes=len(payload),
            git_sha="different",
            git_dirty=True,
        )

    assert calls == 1
    assert reused.status == "reused"
    assert all(check.passed for check in reused.checks)


def test_acquisition_refuses_unmanifested_nonempty_snapshot_directory(tmp_path):
    output_root = tmp_path / "snapshots"
    metadata = _metadata(12)
    snapshot_dir = output_root / metadata.snapshot_id
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "unexpected.bin").write_bytes(b"x")

    with httpx.Client(transport=httpx.MockTransport(lambda request: None)) as client:
        with pytest.raises(RuntimeError, match="unmanifested files"):
            acquire_enriched_tweets_snapshot(
                client,
                metadata,
                output_root,
                max_bytes=12,
                git_sha="abc123",
                git_dirty=False,
            )
