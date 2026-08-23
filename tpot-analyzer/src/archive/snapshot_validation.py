"""Structural and content validation for local archive snapshot manifests."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from src.archive.snapshot import build_snapshot_id
from src.archive.snapshot_contract import (
    DATA_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_SCHEMA_VERSION,
    SNAPSHOT_KIND,
    SnapshotCheck,
)
from src.archive.snapshot_dataset_validation import validate_dataset


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integer(value: object, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _section(
    manifest: dict[str, Any],
    name: str,
    checks: list[SnapshotCheck],
) -> dict[str, Any]:
    value = manifest.get(name)
    passed = isinstance(value, dict)
    checks.append(
        SnapshotCheck(
            f"{name} object",
            passed,
            type(value).__name__ if value is not None else "missing",
        )
    )
    return value if passed else {}


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _source_identity(
    source: dict[str, Any],
    snapshot_id: object,
) -> tuple[bool, str]:
    url = source.get("url")
    length = source.get("content_length")
    observed_at = source.get("observed_at")
    etag = source.get("etag")
    last_modified = source.get("last_modified")
    if (
        not isinstance(url, str)
        or not url
        or not _integer(length, minimum=1)
        or _parse_timestamp(observed_at) is None
        or (etag is not None and not isinstance(etag, str))
        or (last_modified is not None and _parse_timestamp(last_modified) is None)
    ):
        return False, "source identity fields are missing or invalid"
    try:
        expected = build_snapshot_id(
            url,
            etag,
            last_modified,
            length,
            observed_at,
        )
    except (TypeError, ValueError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return expected == snapshot_id, f"expected={expected}, manifest={snapshot_id}"


def verify_snapshot_directory(
    snapshot_dir: Path,
    *,
    deep: bool = False,
) -> tuple[list[SnapshotCheck], dict[str, Any]]:
    manifest_path = snapshot_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return [SnapshotCheck("manifest exists", False, str(manifest_path))], {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [
            SnapshotCheck("manifest readable", False, f"{type(exc).__name__}: {exc}")
        ], {}
    if not isinstance(manifest, dict):
        return [
            SnapshotCheck("manifest object", False, type(manifest).__name__)
        ], {}

    checks = [
        SnapshotCheck(
            "manifest schema",
            manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION,
            str(manifest.get("schema_version")),
        ),
        SnapshotCheck(
            "manifest kind",
            manifest.get("kind") == SNAPSHOT_KIND,
            str(manifest.get("kind")),
        ),
    ]
    source = _section(manifest, "source", checks)
    local = _section(manifest, "local", checks)
    dataset = _section(manifest, "dataset", checks)
    acquisition = _section(manifest, "acquisition_code", checks)

    snapshot_id = manifest.get("snapshot_id")
    checks.append(
        SnapshotCheck(
            "snapshot directory identity",
            isinstance(snapshot_id, str) and snapshot_dir.name == snapshot_id,
            f"directory={snapshot_dir.name}, manifest={snapshot_id}",
        )
    )
    identity_ok, identity_detail = _source_identity(source, snapshot_id)
    checks.append(SnapshotCheck("source snapshot identity", identity_ok, identity_detail))
    has_validator = bool(source.get("etag") or source.get("last_modified"))
    checks.append(
        SnapshotCheck(
            "source validator",
            has_validator,
            f"etag={source.get('etag')}, last_modified={source.get('last_modified')}",
        )
    )

    filename = local.get("filename")
    safe_filename = filename == DATA_FILENAME
    checks.append(
        SnapshotCheck("snapshot filename", safe_filename, str(filename or "missing"))
    )
    data_path = snapshot_dir / DATA_FILENAME
    exists = data_path.is_file() and not data_path.is_symlink()
    checks.append(SnapshotCheck("snapshot data file", exists, str(data_path)))

    source_size = source.get("content_length")
    local_size = local.get("size_bytes")
    sizes_valid = _integer(source_size, minimum=1) and _integer(local_size, minimum=1)
    checks.append(
        SnapshotCheck(
            "source/local byte size",
            sizes_valid and source_size == local_size,
            f"source={source_size}, local={local_size}",
        )
    )
    if exists:
        actual_size = data_path.stat().st_size
        checks.append(
            SnapshotCheck(
                "snapshot byte size",
                _integer(local_size, minimum=1) and actual_size == local_size,
                f"expected={local_size}, actual={actual_size}",
            )
        )

    expected_hash = local.get("sha256")
    hash_shape = isinstance(expected_hash, str) and bool(
        SHA256_PATTERN.fullmatch(expected_hash)
    )
    checks.append(
        SnapshotCheck("sha256 shape", hash_shape, str(expected_hash or "missing"))
    )
    if deep and exists:
        try:
            actual_hash = sha256_file(data_path)
            checks.append(
                SnapshotCheck(
                    "snapshot sha256",
                    hash_shape and actual_hash == expected_hash,
                    actual_hash,
                )
            )
        except OSError as exc:
            checks.append(
                SnapshotCheck(
                    "snapshot sha256",
                    False,
                    f"{type(exc).__name__}: {exc}",
                )
            )

    dataset_checks, dataset_metrics = validate_dataset(dataset)
    checks.extend(dataset_checks)
    code_valid = (
        isinstance(acquisition.get("git_sha"), str)
        and bool(acquisition.get("git_sha"))
        and isinstance(acquisition.get("git_dirty"), bool)
    )
    checks.append(
        SnapshotCheck(
            "acquisition code identity",
            code_valid,
            f"sha={acquisition.get('git_sha')}, dirty={acquisition.get('git_dirty')}",
        )
    )

    metrics = {
        "snapshot_id": snapshot_id,
        **dataset_metrics,
        "size_bytes": local_size,
        "sha256": expected_hash,
    }
    return checks, metrics
