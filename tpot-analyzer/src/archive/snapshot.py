"""Versioned acquisition helpers for mutable Community Archive exports."""
from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx


class SnapshotChangedError(RuntimeError):
    """Raised when the remote object changes between probe and download."""


@dataclass(frozen=True)
class RemoteObjectMetadata:
    url: str
    observed_at: str
    etag: str | None
    last_modified: str | None
    content_length: int
    content_type: str | None
    snapshot_id: str


@dataclass(frozen=True)
class DownloadRecord:
    path: Path
    size_bytes: int
    sha256: str


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_last_modified(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    try:
        return utc_iso(parsedate_to_datetime(raw_value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid Last-Modified header: {raw_value!r}") from exc


def build_snapshot_id(
    url: str,
    etag: str | None,
    last_modified: str | None,
    content_length: int,
    observed_at: str,
) -> str:
    identity = "\0".join(
        (url, etag or "", last_modified or "", str(content_length))
    ).encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()[:12]
    timestamp_value = last_modified or observed_at
    timestamp = datetime.fromisoformat(timestamp_value).astimezone(timezone.utc)
    return f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{digest}"


def probe_remote_object(
    client: httpx.Client,
    url: str,
    *,
    observed_at: datetime | None = None,
) -> RemoteObjectMetadata:
    response = client.head(url, follow_redirects=True)
    response.raise_for_status()
    raw_length = response.headers.get("Content-Length")
    try:
        content_length = int(raw_length or "")
    except ValueError as exc:
        raise ValueError(
            f"Remote object has invalid Content-Length: {raw_length!r}"
        ) from exc
    if content_length <= 0:
        raise ValueError(
            f"Remote object must have a positive Content-Length; got {content_length}"
        )

    observed = utc_iso(observed_at or datetime.now(timezone.utc))
    etag = response.headers.get("ETag")
    last_modified = _parse_last_modified(response.headers.get("Last-Modified"))
    return RemoteObjectMetadata(
        url=str(response.url),
        observed_at=observed,
        etag=etag,
        last_modified=last_modified,
        content_length=content_length,
        content_type=response.headers.get("Content-Type"),
        snapshot_id=build_snapshot_id(
            str(response.url),
            etag,
            last_modified,
            content_length,
            observed,
        ),
    )


def download_remote_object(
    client: httpx.Client,
    metadata: RemoteObjectMetadata,
    destination: Path,
    *,
    max_bytes: int | None = None,
) -> DownloadRecord:
    if max_bytes is not None:
        if max_bytes <= 0:
            raise ValueError(f"Download byte limit must be positive; got {max_bytes}")
        if metadata.content_length > max_bytes:
            raise ValueError(
                "Remote object exceeds download byte limit: "
                f"remote={metadata.content_length}, limit={max_bytes}"
            )

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(
            f"Refusing to overwrite snapshot data that already exists: {destination}"
        )
    partial: Path | None = None
    digest = hashlib.sha256()
    size_bytes = 0

    try:
        with client.stream("GET", metadata.url, follow_redirects=True) as response:
            response.raise_for_status()
            response_etag = response.headers.get("ETag")
            if metadata.etag is not None and response_etag != metadata.etag:
                raise SnapshotChangedError(
                    "Remote ETag changed between probe and download: "
                    f"{metadata.etag!r} -> {response_etag!r}"
                )
            response_last_modified = _parse_last_modified(
                response.headers.get("Last-Modified")
            )
            if (
                metadata.last_modified is not None
                and response_last_modified != metadata.last_modified
            ):
                raise SnapshotChangedError(
                    "Remote Last-Modified changed between probe and download: "
                    f"{metadata.last_modified!r} -> {response_last_modified!r}"
                )
            raw_length = response.headers.get("Content-Length")
            if raw_length:
                response_length = int(raw_length)
                if response_length != metadata.content_length:
                    raise SnapshotChangedError(
                        "Remote Content-Length changed between probe and download: "
                        f"{metadata.content_length} -> {response_length}"
                    )

            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{destination.name}.",
                suffix=".part",
                dir=destination.parent,
                delete=False,
            ) as handle:
                partial = Path(handle.name)
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    if max_bytes is not None and size_bytes + len(chunk) > max_bytes:
                        raise ValueError(
                            "Download exceeded byte limit while streaming: "
                            f"received>{max_bytes}"
                        )
                    if size_bytes + len(chunk) > metadata.content_length:
                        raise SnapshotChangedError(
                            "Download exceeded probed Content-Length while streaming: "
                            f"received>{metadata.content_length}"
                        )
                    handle.write(chunk)
                    digest.update(chunk)
                    size_bytes += len(chunk)
                handle.flush()
                os.fsync(handle.fileno())

        if size_bytes != metadata.content_length:
            raise SnapshotChangedError(
                "Downloaded byte count does not match probed Content-Length: "
                f"expected {metadata.content_length}, got {size_bytes}"
            )
        if partial is None:
            raise RuntimeError("Download completed without creating a temporary file")
        os.link(partial, destination)
        partial.unlink()
    except BaseException:
        if partial is not None:
            partial.unlink(missing_ok=True)
        raise

    return DownloadRecord(
        path=destination,
        size_bytes=size_bytes,
        sha256=digest.hexdigest(),
    )
