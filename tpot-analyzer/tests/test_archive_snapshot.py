from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.archive.snapshot import (
    RemoteObjectMetadata,
    SnapshotChangedError,
    build_snapshot_id,
    download_remote_object,
    probe_remote_object,
)
from src.archive.snapshot_manifest import (
    inspect_enriched_tweets_parquet,
)


URL = "https://example.test/enriched_tweets.parquet"
LAST_MODIFIED = "Sat, 25 Jul 2026 04:51:22 GMT"


def _metadata(*, etag: str = '"v1"', size: int = 12) -> RemoteObjectMetadata:
    observed_at = "2026-07-26T00:00:00+00:00"
    last_modified = "2026-07-25T04:51:22+00:00"
    return RemoteObjectMetadata(
        url=URL,
        observed_at=observed_at,
        etag=etag,
        last_modified=last_modified,
        content_length=size,
        content_type="application/octet-stream",
        snapshot_id=build_snapshot_id(
            URL,
            etag,
            last_modified,
            size,
            observed_at,
        ),
    )


def test_probe_captures_versionable_metadata():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "HEAD"
        return httpx.Response(
            200,
            headers={
                "ETag": '"v1"',
                "Last-Modified": LAST_MODIFIED,
                "Content-Length": "12",
                "Content-Type": "application/octet-stream",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        metadata = probe_remote_object(
            client,
            URL,
            observed_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )

    assert metadata.etag == '"v1"'
    assert metadata.last_modified == "2026-07-25T04:51:22+00:00"
    assert metadata.content_length == 12
    assert metadata.snapshot_id.startswith("20260725T045122Z-")


def test_download_is_atomic_and_hash_bound(tmp_path):
    payload = b"parquet-body"

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

    destination = tmp_path / "enriched_tweets.parquet"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        record = download_remote_object(
            client,
            _metadata(size=len(payload)),
            destination,
        )

    assert destination.read_bytes() == payload
    assert not destination.with_suffix(".parquet.part").exists()
    assert record.sha256 == hashlib.sha256(payload).hexdigest()
    assert record.size_bytes == len(payload)


def test_download_rejects_changed_validator_without_publishing(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"new payload",
            headers={"ETag": '"v2"', "Content-Length": "11"},
        )

    destination = tmp_path / "enriched_tweets.parquet"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SnapshotChangedError, match="ETag"):
            download_remote_object(client, _metadata(), destination)

    assert not destination.exists()
    assert not destination.with_suffix(".parquet.part").exists()


def test_download_rejects_missing_validator_without_publishing(tmp_path):
    payload = b"parquet-body"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={"Content-Length": str(len(payload))},
        )

    destination = tmp_path / "enriched_tweets.parquet"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SnapshotChangedError, match="ETag"):
            download_remote_object(
                client,
                _metadata(size=len(payload)),
                destination,
            )

    assert not destination.exists()
    assert not destination.with_suffix(".parquet.part").exists()


def test_download_rejects_changed_last_modified_without_publishing(tmp_path):
    payload = b"parquet-body"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={
                "ETag": '"v1"',
                "Last-Modified": "Sun, 26 Jul 2026 04:51:22 GMT",
                "Content-Length": str(len(payload)),
            },
        )

    destination = tmp_path / "enriched_tweets.parquet"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SnapshotChangedError, match="Last-Modified"):
            download_remote_object(
                client,
                _metadata(size=len(payload)),
                destination,
            )

    assert not destination.exists()


def test_download_enforces_streaming_byte_limit(tmp_path):
    payload = b"parquet-body"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={"ETag": '"v1"', "Content-Length": str(len(payload))},
        )

    destination = tmp_path / "enriched_tweets.parquet"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="byte limit"):
            download_remote_object(
                client,
                _metadata(size=len(payload)),
                destination,
                max_bytes=len(payload) - 1,
            )

    assert not destination.exists()
    assert not destination.with_suffix(".parquet.part").exists()


def test_download_enforces_byte_limit_when_get_omits_length(tmp_path):
    class ChunkedBody(httpx.SyncByteStream):
        def __iter__(self):
            yield b"1234"
            yield b"56"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=ChunkedBody(),
            headers={
                "ETag": '"v1"',
                "Last-Modified": LAST_MODIFIED,
            },
        )

    destination = tmp_path / "enriched_tweets.parquet"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="byte limit"):
            download_remote_object(
                client,
                _metadata(size=5),
                destination,
                max_bytes=5,
            )

    assert not destination.exists()


def test_download_never_overwrites_published_snapshot(tmp_path):
    payload = b"parquet-body"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={"ETag": '"v1"', "Content-Length": str(len(payload))},
        )

    destination = tmp_path / "enriched_tweets.parquet"
    destination.write_bytes(b"existing")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(FileExistsError, match="already exists"):
            download_remote_object(
                client,
                _metadata(size=len(payload)),
                destination,
            )

    assert destination.read_bytes() == b"existing"
    assert not destination.with_suffix(".parquet.part").exists()


def test_inspect_enriched_tweets_parquet_reports_cutoffs(tmp_path):
    path = tmp_path / "enriched_tweets.parquet"
    table = pa.table(
        {
            "tweet_id": ["1", "2", "3"],
            "account_id": ["a", "a", "b"],
            "username": ["one", "one", "two"],
            "created_at": pa.array(
                [
                    datetime(2025, 1, 1, tzinfo=timezone.utc),
                    datetime(2026, 7, 25, tzinfo=timezone.utc),
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                ],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "full_text": ["x", "y", "z"],
            "archive_upload_id": [10, None, 11],
        }
    )
    pq.write_table(table, path)

    result = inspect_enriched_tweets_parquet(path)

    assert result["row_count"] == 3
    assert result["account_count"] == 2
    assert result["created_at_min"] == "2025-01-01T00:00:00+00:00"
    assert result["created_at_max"] == "2026-07-25T00:00:00+00:00"
    assert result["archive_upload_linked_rows"] == 2
    assert result["archive_upload_id_missing_rows"] == 1
    assert result["sample_rows"] == [
        {
            "tweet_id": "1",
            "account_id": "a",
            "created_at": "2025-01-01T00:00:00+00:00",
            "archive_upload_id": 10,
        },
        {
            "tweet_id": "2",
            "account_id": "a",
            "created_at": "2026-07-25T00:00:00+00:00",
            "archive_upload_id": None,
        },
        {
            "tweet_id": "3",
            "account_id": "b",
            "created_at": "2026-01-01T00:00:00+00:00",
            "archive_upload_id": 11,
        },
    ]
