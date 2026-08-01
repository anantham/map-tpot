"""Private evidence artifact contract for bounded dossier acquisition."""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from .acquisition_manifest import canonical_json_hash
from .dossier_executor_types import AcquisitionExecutionError, TransportResponse
from .dossier_receipt_validation import (
    DossierReceiptValidationError,
    validate_completed_receipt_calls,
)
from .dossier_response_contract import response_receipt


class DossierEvidenceArtifactError(ValueError):
    """Raised when raw evidence cannot be bound to its plan and receipt."""


_ARTIFACT_FIELDS = {
    "schema_version",
    "kind",
    "visibility",
    "plan_sha256",
    "selection_manifest_sha256",
    "execution_receipt_sha256",
    "records",
    "artifact_sha256",
}
_RECORD_FIELDS = {
    "endpoint",
    "params",
    "status_code",
    "requested_at",
    "received_at",
    "body",
}
_FINGERPRINT_FIELDS = {
    "http_status",
    "response_sha256",
    "response_top_level_keys",
    "requested_at",
    "received_at",
}


def _strict(value: Any, fields: set[str], context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DossierEvidenceArtifactError(f"{context} must be an object")
    unexpected = set(value) - fields
    if unexpected:
        names = ", ".join(sorted(str(item) for item in unexpected))
        raise DossierEvidenceArtifactError(
            f"unexpected field(s) in {context}: {names}"
        )
    missing = fields - set(value)
    if missing:
        names = ", ".join(sorted(missing))
        raise DossierEvidenceArtifactError(f"missing field(s) in {context}: {names}")
    return value


def _hash(value: dict[str, Any], context: str) -> str:
    try:
        return canonical_json_hash(value)
    except ValueError as exc:
        raise DossierEvidenceArtifactError(
            f"{context} must contain canonical JSON"
        ) from exc


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DossierEvidenceArtifactError(
            "evidence artifact must contain canonical JSON"
        ) from exc


def _validate_record(
    raw_record: Any,
    *,
    index: int,
    endpoint: str,
    params: dict[str, str],
    observation: dict[str, Any],
) -> dict[str, Any]:
    record = _strict(raw_record, _RECORD_FIELDS, f"records[{index}]")
    if record["endpoint"] != endpoint:
        raise DossierEvidenceArtifactError(f"records[{index}] endpoint mismatch")
    if record["params"] != params:
        raise DossierEvidenceArtifactError(f"records[{index}] params mismatch")
    if type(record["status_code"]) is not int or record["status_code"] != 200:
        raise DossierEvidenceArtifactError(f"records[{index}] status must be HTTP 200")
    response = TransportResponse(
        status_code=record["status_code"],
        body=record["body"],
        requested_at=record["requested_at"],
        received_at=record["received_at"],
    )
    try:
        fingerprint = response_receipt(response)
    except AcquisitionExecutionError as exc:
        raise DossierEvidenceArtifactError(
            f"records[{index}] response is invalid: {exc}"
        ) from exc
    for field in _FINGERPRINT_FIELDS:
        if observation[field] != fingerprint[field]:
            raise DossierEvidenceArtifactError(
                f"records[{index}] {field} or response hash mismatch"
            )
    return deepcopy(record)


def _reconcile(
    plan: dict[str, Any], receipt: Any, records: Any
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        receipt_row, expected = validate_completed_receipt_calls(plan, receipt)
    except DossierReceiptValidationError as exc:
        raise DossierEvidenceArtifactError(str(exc)) from exc
    if not isinstance(records, list) or len(records) != len(expected):
        raise DossierEvidenceArtifactError(
            "records must match two telemetry calls plus every planned action"
        )
    validated = [
        _validate_record(
            record,
            index=index,
            endpoint=call[0],
            params=call[1],
            observation=call[2],
        )
        for index, (record, call) in enumerate(zip(records, expected))
    ]
    balances = receipt_row["balance"]
    for index, expected_credits in (
        (0, balances["before_credits"]),
        (len(validated) - 1, balances["after_credits"]),
    ):
        if validated[index]["body"].get("recharge_credits") != expected_credits:
            raise DossierEvidenceArtifactError(
                f"records[{index}] balance body does not reconcile"
            )
    return receipt_row, validated


def build_dossier_evidence_artifact(
    *, plan: dict[str, Any], receipt: dict[str, Any], records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Bind exact private response bodies to a completed plan receipt."""
    _, validated = _reconcile(plan, receipt, deepcopy(records))
    manifest = {
        "schema_version": 1,
        "kind": "twitterapiio-dossier-evidence-artifact",
        "visibility": "private",
        "plan_sha256": plan["plan_sha256"],
        "selection_manifest_sha256": plan["selection_manifest_sha256"],
        "execution_receipt_sha256": _hash(receipt, "execution receipt"),
        "records": validated,
    }
    return {**manifest, "artifact_sha256": _hash(manifest, "evidence artifact")}


def verify_dossier_evidence_artifact(
    artifact: Any, *, plan: dict[str, Any], receipt: dict[str, Any]
) -> dict[str, Any]:
    """Verify artifact self-hash, external bindings, and every captured call."""
    row = _strict(artifact, _ARTIFACT_FIELDS, "evidence artifact")
    declared = row["artifact_sha256"]
    manifest = {key: value for key, value in row.items() if key != "artifact_sha256"}
    if not isinstance(declared, str) or declared != _hash(manifest, "evidence artifact"):
        raise DossierEvidenceArtifactError("artifact_sha256 mismatch")
    receipt_hash = _hash(receipt, "execution receipt")
    if row["execution_receipt_sha256"] != receipt_hash:
        raise DossierEvidenceArtifactError("execution receipt hash mismatch")
    if (
        row["schema_version"] != 1
        or row["kind"] != "twitterapiio-dossier-evidence-artifact"
        or row["visibility"] != "private"
        or row["plan_sha256"] != plan.get("plan_sha256")
        or row["selection_manifest_sha256"]
        != plan.get("selection_manifest_sha256")
    ):
        raise DossierEvidenceArtifactError("evidence artifact identity mismatch")
    _, records = _reconcile(plan, receipt, row["records"])
    verified = {**manifest, "records": records, "artifact_sha256": declared}
    if row != verified:
        raise DossierEvidenceArtifactError("evidence artifact is not canonical")
    return verified


def canonical_evidence_bytes(
    artifact: Any, *, plan: dict[str, Any], receipt: dict[str, Any]
) -> bytes:
    """Return canonical UTF-8 JSON only after complete verification."""
    return _canonical_bytes(
        verify_dossier_evidence_artifact(artifact, plan=plan, receipt=receipt)
    )
