"""Content-addressed provenance envelope for terminal-test access."""
from __future__ import annotations

from typing import Any, Dict

from src.artifacts.digests import json_sha256

from .frame_validation import (
    require_sha256,
    require_text,
    require_utc_aware,
)


def build_access_envelope(
    *,
    frame_id: Any,
    role_registry_id: Any,
    accessed_by: Any,
    accessed_at: Any,
    access_receipt_hash: Any,
    release_manifest_hash: Any,
    released_label_head_count: Any,
) -> Dict[str, Any]:
    """Normalize all outer fields whose mutation would change provenance."""

    if (
        isinstance(released_label_head_count, bool)
        or not isinstance(released_label_head_count, int)
        or released_label_head_count <= 0
    ):
        raise ValueError(
            "released_label_head_count must be a positive integer"
        )
    return {
        "schemaVersion": 1,
        "frameId": require_text(frame_id, field="terminal frame_id"),
        "roleRegistryId": require_text(
            role_registry_id,
            field="terminal role_registry_id",
        ),
        "accessedBy": require_text(
            accessed_by,
            field="terminal accessed_by",
        ),
        "accessedAt": require_utc_aware(
            accessed_at,
            field="terminal accessed_at",
        ),
        "accessReceiptHash": require_sha256(
            access_receipt_hash,
            field="terminal access_receipt_hash",
        ),
        "releaseManifestHash": require_sha256(
            release_manifest_hash,
            field="terminal release_manifest_hash",
        ),
        "releasedLabelHeadCount": released_label_head_count,
    }


def access_envelope_hash(**values: Any) -> str:
    return json_sha256(build_access_envelope(**values))


def verify_access_envelope(row: Any) -> Dict[str, Any]:
    envelope = build_access_envelope(
        frame_id=row["frame_id"],
        role_registry_id=row["role_registry_id"],
        accessed_by=row["accessed_by"],
        accessed_at=row["accessed_at"],
        access_receipt_hash=row["access_receipt_hash"],
        release_manifest_hash=row["release_manifest_hash"],
        released_label_head_count=row["released_label_head_count"],
    )
    expected = require_sha256(
        row["access_envelope_hash"],
        field="terminal access_envelope_hash",
    )
    observed = json_sha256(envelope)
    if observed != expected:
        raise ValueError(
            "terminal access provenance envelope hash mismatch: "
            f"expected={expected}, observed={observed}"
        )
    return envelope
