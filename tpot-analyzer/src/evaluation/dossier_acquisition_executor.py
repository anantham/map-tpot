"""Fail-closed execution of an explicitly accepted dossier plan."""
from __future__ import annotations

import re
from typing import Any

from .dossier_execution_contract import validate_execution_acceptance
from .dossier_executor_types import (
    AcquisitionExecutionError,
    AcquisitionTransport,
    TransportResponse,
)
from .dossier_response_contract import (
    parse_balance,
    parse_profile,
    parse_tweets,
    response_receipt,
)


BALANCE_ENDPOINT = "/oapi/my/info"
_DECIMAL_ID = re.compile(r"[0-9]+")


def _validate_holdout_ids(value: Any) -> frozenset[str]:
    if not isinstance(value, frozenset) or not value or any(
        not isinstance(item, str) or _DECIMAL_ID.fullmatch(item) is None
        for item in value
    ):
        raise AcquisitionExecutionError(
            "frozen holdout account IDs must be a frozenset of decimal strings"
        )
    return value


def _request(
    transport: AcquisitionTransport,
    endpoint: str,
    params: dict[str, str],
    label: str,
) -> TransportResponse:
    try:
        return transport.request(endpoint, params)
    except AcquisitionExecutionError as error:
        raise AcquisitionExecutionError(f"{label}: {error}") from None
    except Exception:
        raise AcquisitionExecutionError(
            f"transport request failed during {label}"
        ) from None


def _balance_call(
    transport: AcquisitionTransport,
    phase: str,
) -> tuple[int, dict[str, Any]]:
    response = _request(transport, BALANCE_ENDPOINT, {}, f"{phase} balance telemetry")
    credits, item = parse_balance(response)
    return credits, {"phase": phase, "endpoint": BALANCE_ENDPOINT, **item}


def _receipt(plan: dict[str, Any], acceptance: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "twitterapiio-dossier-execution-receipt",
        "status": "running",
        "plan_sha256": plan["plan_sha256"],
        "selection_manifest_sha256": plan["selection_manifest_sha256"],
        "executed_at": acceptance["executed_at"],
        "accepted_cap": {
            "credits": acceptance["accepted_max_credits"],
            "usd": acceptance["accepted_max_usd"],
        },
        "reserved_credits": acceptance["telemetry_reserve_credits"],
        "telemetry": [],
        "actions": [],
        "balance": None,
        "failure": None,
    }


def _finish_balance(
    *,
    receipt: dict[str, Any],
    before: int,
    after: int,
) -> None:
    change = after - before
    receipt["balance"] = {
        "before_credits": before,
        "after_credits": after,
        "debited_credits": max(0, -change),
    }


def _abort(
    *,
    error: AcquisitionExecutionError,
    receipt: dict[str, Any],
    transport: AcquisitionTransport,
    before: int | None,
    post_balance_attempted: bool,
) -> None:
    receipt["status"] = "aborted"
    receipt["failure"] = {"message": str(error)}
    if before is not None and not post_balance_attempted:
        try:
            after, item = _balance_call(transport, "after")
            receipt["telemetry"].append(item)
            _finish_balance(receipt=receipt, before=before, after=after)
        except AcquisitionExecutionError:
            receipt["failure"]["post_balance_telemetry"] = "unavailable"
    raise AcquisitionExecutionError(str(error), receipt=receipt) from None


def execute_dossier_acquisition_plan(
    *,
    plan: dict[str, Any],
    expected_plan_sha256: str,
    accepted_max_credits: int,
    accepted_max_usd: str,
    executed_at: str,
    frozen_holdout_account_ids: frozenset[str],
    transport: AcquisitionTransport,
) -> dict[str, Any]:
    """Execute a frozen plan through an injected transport."""
    holdout_ids = _validate_holdout_ids(frozen_holdout_account_ids)
    try:
        acceptance = validate_execution_acceptance(
            plan=plan,
            expected_plan_sha256=expected_plan_sha256,
            accepted_max_credits=accepted_max_credits,
            accepted_max_usd=accepted_max_usd,
            executed_at=executed_at,
        )
    except (AcquisitionExecutionError, ValueError) as error:
        if isinstance(error, AcquisitionExecutionError):
            raise
        raise AcquisitionExecutionError(str(error)) from None

    receipt = _receipt(plan, acceptance)
    before: int | None = None
    post_balance_attempted = False
    try:
        before, telemetry = _balance_call(transport, "before")
        receipt["telemetry"].append(telemetry)
        if before < acceptance["total_reserve_credits"]:
            raise AcquisitionExecutionError(
                "provider balance is below the plan's total reserve"
            )

        account_ids: dict[str, str] = {}
        claimed_ids: dict[str, str] = {}
        sequence = 0
        for target in plan["targets"]:
            handle = target["handle"]
            for action in target["actions"]:
                reserve = action["reserve_credits"]
                if receipt["reserved_credits"] + reserve > acceptance[
                    "accepted_max_credits"
                ]:
                    raise AcquisitionExecutionError(
                        f"action @{handle}/{action['kind']} would exceed accepted cap"
                    )
                receipt["reserved_credits"] += reserve
                attempt = {
                    "sequence": sequence,
                    "target_handle": handle,
                    "kind": action["kind"],
                    "endpoint": action["endpoint"],
                    "reserve_credits": reserve,
                    "status": "requesting",
                    "http_status": None,
                    "response_sha256": None,
                    "response_top_level_keys": None,
                    "returned_count": None,
                    "account_id": None,
                }
                receipt["actions"].append(attempt)
                sequence += 1
                try:
                    response = _request(
                        transport,
                        action["endpoint"],
                        {"userName": handle},
                        f"@{handle} {action['kind']}",
                    )
                except AcquisitionExecutionError:
                    attempt["status"] = "transport_error"
                    raise
                try:
                    attempt.update(response_receipt(response))
                    attempt["status"] = "response_received"
                    if action["kind"] == "profile":
                        account_id, item = parse_profile(response, handle)
                        if account_id in holdout_ids:
                            raise AcquisitionExecutionError(
                                "resolved profile belongs to the frozen holdout"
                            )
                        prior_handle = claimed_ids.get(account_id)
                        if prior_handle is not None and prior_handle != handle:
                            raise AcquisitionExecutionError(
                                "account id collision between "
                                f"@{prior_handle} and @{handle}"
                            )
                        claimed_ids[account_id] = handle
                        account_ids[handle] = account_id
                    else:
                        _, item = parse_tweets(
                            response,
                            expected_handle=handle,
                            expected_account_id=account_ids[handle],
                            maximum_returned=action["maximum_returned"],
                        )
                    attempt.update(item)
                    attempt["status"] = "validated"
                except AcquisitionExecutionError:
                    attempt["status"] = "response_rejected"
                    raise

        post_balance_attempted = True
        after, telemetry = _balance_call(transport, "after")
        receipt["telemetry"].append(telemetry)
        _finish_balance(receipt=receipt, before=before, after=after)
        if receipt["balance"]["debited_credits"] > acceptance["accepted_max_credits"]:
            raise AcquisitionExecutionError(
                "observed provider debit exceeds the explicitly accepted cap"
            )
        receipt["status"] = "completed"
        return receipt
    except AcquisitionExecutionError as error:
        _abort(
            error=error,
            receipt=receipt,
            transport=transport,
            before=before,
            post_balance_attempted=post_balance_attempted,
        )
