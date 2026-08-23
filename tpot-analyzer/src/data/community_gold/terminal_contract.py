"""Canonical validation for one-use terminal receipts and release manifests."""
from __future__ import annotations

import json
from typing import Any, Dict, Mapping

from src.artifacts.digests import json_sha256

from .frame_validation import (
    json_value,
    require_sha256,
    require_text,
    require_utc_aware,
)

_RECEIPT_BOOLEAN_FIELDS = (
    "modelsFinal",
    "policyFinal",
    "stoppingFinal",
    "continuationFinal",
)
_RECEIPT_HASH_FIELDS = (
    "policyArtifactHash",
    "stoppingRuleHash",
    "continuationRuleHash",
    "runManifestHash",
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def normalize_terminal_receipt(value: Any) -> Dict[str, Any]:
    normalized = json_value(value, field="access_receipt")
    if not isinstance(normalized, dict):
        raise ValueError("access_receipt must be an object")
    missing_or_false = [
        field
        for field in _RECEIPT_BOOLEAN_FIELDS
        if normalized.get(field) is not True
    ]
    if missing_or_false:
        raise ValueError(
            "access_receipt must affirm all frozen decisions; "
            f"missing_or_false={missing_or_false}"
        )
    model_hashes = normalized.get("modelArtifactHashes")
    if not isinstance(model_hashes, list) or not model_hashes:
        raise ValueError(
            "access_receipt.modelArtifactHashes must be a non-empty list"
        )
    normalized["modelArtifactHashes"] = [
        require_sha256(
            item,
            field=f"access_receipt.modelArtifactHashes[{index}]",
        )
        for index, item in enumerate(model_hashes)
    ]
    if len(normalized["modelArtifactHashes"]) != len(
        set(normalized["modelArtifactHashes"])
    ):
        raise ValueError(
            "access_receipt.modelArtifactHashes contains duplicates"
        )
    for field in _RECEIPT_HASH_FIELDS:
        normalized[field] = require_sha256(
            normalized.get(field),
            field=f"access_receipt.{field}",
        )
    return normalized


def _normalize_label_head(value: Any, *, index: int) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"release_manifest.labelHeads[{index}] must be an object")
    label_set_id = value.get("labelSetId")
    if (
        isinstance(label_set_id, bool)
        or not isinstance(label_set_id, int)
        or label_set_id <= 0
    ):
        raise ValueError(
            f"release_manifest.labelHeads[{index}].labelSetId "
            "must be a positive integer"
        )
    judgment = require_text(
        value.get("judgment"),
        field=f"release_manifest.labelHeads[{index}].judgment",
    )
    if judgment not in {"in", "out", "abstain"}:
        raise ValueError(
            f"release_manifest.labelHeads[{index}].judgment is invalid"
        )
    lineage_length = value.get("lineageLength")
    if (
        isinstance(lineage_length, bool)
        or not isinstance(lineage_length, int)
        or lineage_length <= 0
    ):
        raise ValueError(
            f"release_manifest.labelHeads[{index}].lineageLength "
            "must be a positive integer"
        )
    return {
        "labelSetId": label_set_id,
        "accountId": require_text(
            value.get("accountId"),
            field=f"release_manifest.labelHeads[{index}].accountId",
        ),
        "communityId": require_text(
            value.get("communityId"),
            field=f"release_manifest.labelHeads[{index}].communityId",
        ),
        "reviewer": require_text(
            value.get("reviewer"),
            field=f"release_manifest.labelHeads[{index}].reviewer",
        ),
        "judgment": judgment,
        "evidenceSnapshotHash": require_sha256(
            value.get("evidenceSnapshotHash"),
            field=(
                f"release_manifest.labelHeads[{index}]"
                ".evidenceSnapshotHash"
            ),
        ),
        "contextHash": require_sha256(
            value.get("contextHash"),
            field=f"release_manifest.labelHeads[{index}].contextHash",
        ),
        "observedAt": require_utc_aware(
            value.get("observedAt"),
            field=f"release_manifest.labelHeads[{index}].observedAt",
        ),
        "createdAt": require_utc_aware(
            value.get("createdAt"),
            field=f"release_manifest.labelHeads[{index}].createdAt",
        ),
        "judgmentPayloadHash": require_sha256(
            value.get("judgmentPayloadHash"),
            field=(
                f"release_manifest.labelHeads[{index}]"
                ".judgmentPayloadHash"
            ),
        ),
        "lineageHash": require_sha256(
            value.get("lineageHash"),
            field=f"release_manifest.labelHeads[{index}].lineageHash",
        ),
        "lineageLength": lineage_length,
    }


def normalize_release_manifest(
    value: Any,
    *,
    frame: Mapping[str, Any],
) -> Dict[str, Any]:
    normalized = json_value(value, field="release_manifest")
    if not isinstance(normalized, dict):
        raise ValueError("release_manifest must be an object")
    if normalized.get("schemaVersion") != 1:
        raise ValueError("release_manifest.schemaVersion must equal 1")
    expected_identity = {
        "frameId": frame["frameId"],
        "frameManifestDigest": frame["manifestDigest"],
        "purpose": "terminal_evaluation",
    }
    mismatches = {
        field: {"expected": expected, "observed": normalized.get(field)}
        for field, expected in expected_identity.items()
        if normalized.get(field) != expected
    }
    if mismatches:
        raise ValueError(
            f"terminal release manifest identity mismatch: {mismatches}"
        )
    reviewer = require_text(
        normalized.get("reviewer"),
        field="release_manifest.reviewer",
    )
    raw_heads = normalized.get("labelHeads")
    if not isinstance(raw_heads, list) or not raw_heads:
        raise ValueError(
            "terminal release manifest must contain non-empty labelHeads"
        )
    heads = [
        _normalize_label_head(item, index=index)
        for index, item in enumerate(raw_heads)
    ]
    if len({item["labelSetId"] for item in heads}) != len(heads):
        raise ValueError("release_manifest.labelHeads contains duplicate IDs")
    if {item["reviewer"] for item in heads} != {reviewer}:
        raise ValueError(
            "release_manifest label reviewers differ from its reviewer"
        )
    coverage = normalized.get("coverage")
    if not isinstance(coverage, dict):
        raise ValueError("release_manifest.coverage must be an object")
    expected_count = coverage.get("expectedLabelHeadCount")
    reviewed_count = coverage.get("reviewedLabelHeadCount")
    if (
        expected_count != len(heads)
        or reviewed_count != len(heads)
        or coverage.get("missingLabelHeadCount") != 0
        or coverage.get("complete") is not True
    ):
        raise ValueError(
            "terminal release coverage must be complete and match labelHeads"
        )
    counts = coverage.get("judgmentCounts")
    observed_counts = {
        judgment: sum(item["judgment"] == judgment for item in heads)
        for judgment in ("in", "out", "abstain")
    }
    if counts != observed_counts:
        raise ValueError(
            "terminal release judgment counts do not match labelHeads"
        )
    return {
        **normalized,
        "reviewer": reviewer,
        "labelHeads": heads,
        "coverage": {
            **coverage,
            "expectedLabelHeadCount": len(heads),
            "reviewedLabelHeadCount": len(heads),
            "missingLabelHeadCount": 0,
            "judgmentCounts": observed_counts,
            "complete": True,
        },
    }


def checked_payload(
    *,
    stored_json: Any,
    stored_hash: Any,
    normalized: Mapping[str, Any],
    record_name: str,
) -> None:
    canonical = canonical_json(normalized)
    observed_hash = json_sha256(normalized)
    if canonical != str(stored_json) or observed_hash != str(stored_hash):
        raise ValueError(
            f"terminal {record_name} hash/canonical JSON mismatch: "
            f"expected={stored_hash}, observed={observed_hash}"
        )
