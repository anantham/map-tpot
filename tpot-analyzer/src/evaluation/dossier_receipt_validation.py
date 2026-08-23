"""Validate completed dossier receipts and derive their expected call sequence."""
from __future__ import annotations

import re
from typing import Any

from .acquisition_manifest import hash_plan_manifest
from .dossier_execution_contract import validate_execution_acceptance
from .dossier_executor_types import AcquisitionExecutionError


class DossierReceiptValidationError(ValueError):
    """Raised when a completed receipt does not reconcile with its plan."""


ReceiptCall = tuple[str, dict[str, str], dict[str, Any]]
_SHA256 = re.compile(r"[0-9a-f]{64}")
_RECEIPT_FIELDS = {
    "schema_version",
    "kind",
    "status",
    "plan_sha256",
    "selection_manifest_sha256",
    "executed_at",
    "accepted_cap",
    "reserved_credits",
    "telemetry",
    "actions",
    "balance",
    "failure",
}
_TELEMETRY_FIELDS = {
    "phase",
    "endpoint",
    "http_status",
    "response_sha256",
    "response_top_level_keys",
    "requested_at",
    "received_at",
}
_ACTION_FIELDS = {
    "sequence",
    "target_handle",
    "kind",
    "endpoint",
    "reserve_credits",
    "status",
    "http_status",
    "response_sha256",
    "response_top_level_keys",
    "returned_count",
    "account_id",
    "requested_at",
    "received_at",
}
_CAP_FIELDS = {"credits", "usd"}
_BALANCE_FIELDS = {"before_credits", "after_credits", "debited_credits"}


def _strict(value: Any, fields: set[str], context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DossierReceiptValidationError(f"{context} must be an object")
    unexpected = set(value) - fields
    if unexpected:
        names = ", ".join(sorted(str(item) for item in unexpected))
        raise DossierReceiptValidationError(
            f"unexpected field(s) in {context}: {names}"
        )
    missing = fields - set(value)
    if missing:
        names = ", ".join(sorted(missing))
        raise DossierReceiptValidationError(
            f"missing field(s) in {context}: {names}"
        )
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise DossierReceiptValidationError(
            f"{field} must be a nonnegative integer"
        )
    return value


def _validate_header(plan: dict[str, Any], receipt: Any) -> dict[str, Any]:
    row = _strict(receipt, _RECEIPT_FIELDS, "execution receipt")
    if (
        row["schema_version"] != 1
        or row["kind"] != "twitterapiio-dossier-execution-receipt"
        or row["status"] != "completed"
        or row["failure"] is not None
    ):
        raise DossierReceiptValidationError(
            "execution receipt must be completed without failure"
        )
    try:
        plan_hash = hash_plan_manifest(plan)
    except ValueError as exc:
        raise DossierReceiptValidationError(
            "plan cannot be canonically hashed"
        ) from exc
    if plan.get("plan_sha256") != plan_hash:
        raise DossierReceiptValidationError("plan_sha256 mismatch")
    if row["plan_sha256"] != plan_hash:
        raise DossierReceiptValidationError("receipt plan_sha256 mismatch")
    selection_hash = plan.get("selection_manifest_sha256")
    if (
        not isinstance(selection_hash, str)
        or _SHA256.fullmatch(selection_hash) is None
        or row["selection_manifest_sha256"] != selection_hash
    ):
        raise DossierReceiptValidationError("receipt selection hash mismatch")
    cap = _strict(row["accepted_cap"], _CAP_FIELDS, "receipt accepted_cap")
    try:
        validate_execution_acceptance(
            plan=plan,
            expected_plan_sha256=plan_hash,
            accepted_max_credits=cap["credits"],
            accepted_max_usd=cap["usd"],
            executed_at=row["executed_at"],
        )
    except (AcquisitionExecutionError, ValueError, TypeError, KeyError) as exc:
        raise DossierReceiptValidationError(
            f"receipt does not satisfy plan acceptance: {exc}"
        ) from exc
    if row["reserved_credits"] != plan["reservation"]["total_credits"]:
        raise DossierReceiptValidationError("receipt reserved_credits mismatch")
    if not isinstance(row["telemetry"], list) or len(row["telemetry"]) != 2:
        raise DossierReceiptValidationError("receipt requires two telemetry calls")
    if not isinstance(row["actions"], list):
        raise DossierReceiptValidationError("receipt actions must be an array")
    balance = _strict(row["balance"], _BALANCE_FIELDS, "receipt balance")
    before = _nonnegative_int(balance["before_credits"], "balance.before_credits")
    after = _nonnegative_int(balance["after_credits"], "balance.after_credits")
    debit = _nonnegative_int(balance["debited_credits"], "balance.debited_credits")
    if debit != max(0, before - after):
        raise DossierReceiptValidationError("receipt balance does not reconcile")
    if debit > cap["credits"]:
        raise DossierReceiptValidationError("receipt debit exceeds accepted cap")
    return row


def _action_calls(
    plan: dict[str, Any],
    receipt: dict[str, Any],
) -> list[ReceiptCall]:
    planned = [
        (target, action)
        for target in plan["targets"]
        for action in target["actions"]
    ]
    if len(receipt["actions"]) != len(planned):
        raise DossierReceiptValidationError(
            "receipt action count does not match plan"
        )
    calls = []
    for index, ((target, action), raw_item) in enumerate(
        zip(planned, receipt["actions"])
    ):
        item = _strict(raw_item, _ACTION_FIELDS, f"receipt actions[{index}]")
        if item["status"] != "validated":
            raise DossierReceiptValidationError(
                f"receipt action {index} status must be validated"
            )
        expected = {
            "sequence": index,
            "target_handle": target["handle"],
            "kind": action["kind"],
            "endpoint": action["endpoint"],
            "reserve_credits": action["reserve_credits"],
        }
        if any(item[field] != value for field, value in expected.items()):
            raise DossierReceiptValidationError(
                f"receipt action {index} does not match planned action"
            )
        _nonnegative_int(item["returned_count"], f"actions[{index}].returned_count")
        if not isinstance(item["account_id"], str) or not item["account_id"]:
            raise DossierReceiptValidationError(
                f"actions[{index}].account_id must be a nonempty string"
            )
        calls.append((
            action["endpoint"],
            {"userName": target["handle"]},
            item,
        ))
    return calls


def validate_completed_receipt_calls(
    plan: dict[str, Any],
    receipt: Any,
) -> tuple[dict[str, Any], list[ReceiptCall]]:
    """Validate one completed receipt and return its exact expected calls."""
    row = _validate_header(plan, receipt)
    telemetry = row["telemetry"]
    boundary_calls = []
    for index, phase in ((0, "before"), (1, "after")):
        item = _strict(
            telemetry[index],
            _TELEMETRY_FIELDS,
            f"telemetry[{index}]",
        )
        if (
            item["phase"] != phase
            or item["endpoint"] != plan["telemetry"]["endpoint"]
        ):
            raise DossierReceiptValidationError(
                "telemetry endpoint or phase mismatch"
            )
        boundary_calls.append((item["endpoint"], {}, item))
    calls = [boundary_calls[0], *_action_calls(plan, row), boundary_calls[1]]
    return row, calls
