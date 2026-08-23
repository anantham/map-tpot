"""Preflight validation for explicit acceptance of a frozen dossier quote."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from .acquisition_manifest import (
    AcquisitionPlanError,
    hash_plan_manifest,
    normalize_handle,
    parse_time,
)
from .dossier_executor_types import AcquisitionExecutionError


_SHA256 = re.compile(r"[0-9a-f]{64}")
_KINDS = {
    "profile": "/twitter/user/info",
    "recent_tweets": "/twitter/user/last_tweets",
}
_BALANCE_ENDPOINT = "/oapi/my/info"


def _integer(value: Any, field: str, *, positive: bool = False) -> int:
    minimum = 1 if positive else 0
    if type(value) is not int or value < minimum:
        qualifier = "positive" if positive else "nonnegative"
        raise AcquisitionExecutionError(f"{field} must be a {qualifier} integer")
    return value


def _money(value: Any, field: str) -> Decimal:
    if not isinstance(value, str):
        raise AcquisitionExecutionError(f"{field} must be an exact decimal string")
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise AcquisitionExecutionError(f"{field} is not a decimal") from error
    if not amount.is_finite() or amount <= 0:
        raise AcquisitionExecutionError(f"{field} must be positive")
    return amount


def _validate_actions(targets: Any) -> dict[str, int]:
    if not isinstance(targets, list) or not targets:
        raise AcquisitionExecutionError("plan targets must be a nonempty list")
    previous = ""
    reserve = 0
    request_count = 0
    profile_count = 0
    maximum_tweet_count = 0
    for target in targets:
        if not isinstance(target, dict):
            raise AcquisitionExecutionError("each plan target must be an object")
        raw_handle = target.get("handle")
        try:
            handle = normalize_handle(raw_handle)
        except AcquisitionPlanError as error:
            raise AcquisitionExecutionError("plan target has invalid handle") from error
        if raw_handle != handle:
            raise AcquisitionExecutionError(
                "plan target handle must use canonical lowercase form"
            )
        if handle <= previous:
            raise AcquisitionExecutionError("plan targets must be uniquely sorted")
        previous = handle
        actions = target.get("actions")
        if not isinstance(actions, list) or not actions:
            raise AcquisitionExecutionError(f"plan target @{handle} has no actions")
        kinds = [action.get("kind") for action in actions if isinstance(action, dict)]
        if kinds not in (["profile"], ["profile", "recent_tweets"]):
            raise AcquisitionExecutionError(
                f"plan target @{handle} must bind profile before tweets"
            )
        target_reserve = 0
        for action in actions:
            kind = action.get("kind")
            if action.get("endpoint") != _KINDS.get(kind):
                raise AcquisitionExecutionError(
                    f"plan target @{handle} has an unapproved endpoint"
                )
            maximum = _integer(action.get("maximum_returned"), "maximum_returned")
            if kind == "profile" and maximum != 1:
                raise AcquisitionExecutionError("profile maximum_returned must be 1")
            request_count += 1
            profile_count += kind == "profile"
            if kind == "recent_tweets":
                maximum_tweet_count += maximum
            target_reserve += _integer(
                action.get("reserve_credits"), "reserve_credits", positive=True
            )
        if target.get("target_reserve_credits") != target_reserve:
            raise AcquisitionExecutionError(
                f"plan target @{handle} reserve does not match its actions"
            )
        reserve += target_reserve
    return {
        "reserve": reserve,
        "request_count": request_count,
        "profile_count": profile_count,
        "maximum_tweet_count": maximum_tweet_count,
    }


def validate_execution_acceptance(
    *,
    plan: dict[str, Any],
    expected_plan_sha256: str,
    accepted_max_credits: int,
    accepted_max_usd: str,
    executed_at: str,
) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise AcquisitionExecutionError("plan must be an object")
    if _SHA256.fullmatch(expected_plan_sha256 or "") is None:
        raise AcquisitionExecutionError("expected_plan_sha256 must be lowercase SHA-256")
    actual_hash = hash_plan_manifest(plan)
    if plan.get("plan_sha256") != actual_hash or actual_hash != expected_plan_sha256:
        raise AcquisitionExecutionError("plan hash does not match explicit acceptance")
    if (
        plan.get("schema_version") != 2
        or plan.get("kind") != "twitterapiio-formative-dossier-plan"
        or plan.get("provider") != "twitterapi.io"
        or plan.get("mode") != "plan_only"
    ):
        raise AcquisitionExecutionError("plan identity or mode is not executable")
    if plan.get("authorizes_execution") is not False:
        raise AcquisitionExecutionError(
            "plan quote must remain non-authorizing; acceptance is supplied separately"
        )
    if _SHA256.fullmatch(plan.get("selection_manifest_sha256", "")) is None:
        raise AcquisitionExecutionError(
            "selection_manifest_sha256 must bind a frozen selection"
        )
    card = plan.get("price_card")
    policy = plan.get("policy")
    if not isinstance(card, dict) or not isinstance(policy, dict):
        raise AcquisitionExecutionError("plan lacks verified price-card policy")
    if not isinstance(card.get("card_id"), str) or not card["card_id"]:
        raise AcquisitionExecutionError("plan lacks verified price-card identity")
    if _SHA256.fullmatch(card.get("sha256", "")) is None:
        raise AcquisitionExecutionError("plan lacks verified price-card hash")
    maximum_age = _integer(policy.get("max_price_age_days"), "max_price_age_days")
    execution_time = parse_time(executed_at, "executed_at")
    verified_time = parse_time(card.get("verified_at"), "price_card.verified_at")
    planned_time = parse_time(plan.get("planned_at"), "planned_at")
    if planned_time > execution_time:
        raise AcquisitionExecutionError("plan was created after execution time")
    age = execution_time - verified_time
    if age < timedelta(0) or age > timedelta(days=maximum_age):
        raise AcquisitionExecutionError("price verification is stale at execution time")

    action_metrics = _validate_actions(plan.get("targets"))
    action_reserve = action_metrics["reserve"]
    telemetry = plan.get("telemetry")
    if not isinstance(telemetry, dict):
        raise AcquisitionExecutionError("plan lacks balance telemetry reservation")
    telemetry_reserve = _integer(
        telemetry.get("total_reserve_credits"),
        "telemetry.total_reserve_credits",
        positive=True,
    )
    if (
        telemetry.get("endpoint") != _BALANCE_ENDPOINT
        or telemetry.get("kind") != "balance"
        or telemetry.get("balance_field") != "recharge_credits"
        or telemetry.get("request_count") != 2
        or telemetry.get("pricing_status") != "conservative_unverified"
        or telemetry_reserve
        != 2 * _integer(
            telemetry.get("reserve_credits_per_request"),
            "telemetry.reserve_credits_per_request",
            positive=True,
        )
    ):
        raise AcquisitionExecutionError("plan balance telemetry contract is unapproved")
    reservation = plan.get("reservation")
    if not isinstance(reservation, dict):
        raise AcquisitionExecutionError("plan lacks reservation")
    total = _integer(reservation.get("total_credits"), "total_credits", positive=True)
    hard_credits = _integer(
        reservation.get("hard_cap_credits"), "hard_cap_credits", positive=True
    )
    if (
        reservation.get("evidence_credits") != action_reserve
        or reservation.get("telemetry_reserve_credits") != telemetry_reserve
        or reservation.get("evidence_request_count")
        != action_metrics["request_count"]
        or reservation.get("telemetry_request_count") != 2
        or reservation.get("request_count") != action_metrics["request_count"] + 2
        or reservation.get("profile_count") != action_metrics["profile_count"]
        or reservation.get("maximum_tweet_count")
        != action_metrics["maximum_tweet_count"]
        or action_reserve + telemetry_reserve != total
        or total > hard_credits
    ):
        raise AcquisitionExecutionError(
            "plan request_count or reserve metrics do not match declared budget"
        )
    total_usd = _money(reservation.get("total_usd"), "total_usd")
    hard_usd = _money(reservation.get("hard_cap_usd"), "hard_cap_usd")
    accepted_usd = _money(accepted_max_usd, "accepted_max_usd")
    accepted_credits = _integer(
        accepted_max_credits, "accepted_max_credits", positive=True
    )
    credits_per_usd = Decimal(hard_credits) / hard_usd
    if total_usd * credits_per_usd != Decimal(total):
        raise AcquisitionExecutionError(
            "plan USD reservation does not match its credit reservation"
        )
    if reservation.get("remaining_credits") != hard_credits - total:
        raise AcquisitionExecutionError("plan remaining_credits does not reconcile")
    if not (total <= accepted_credits <= hard_credits):
        raise AcquisitionExecutionError("accepted credit cap is outside plan bounds")
    if not (total_usd <= accepted_usd <= hard_usd):
        raise AcquisitionExecutionError("accepted USD cap is outside plan bounds")
    if accepted_usd * credits_per_usd != Decimal(accepted_credits):
        raise AcquisitionExecutionError("accepted credit and USD caps disagree")
    return {
        "executed_at": executed_at,
        "accepted_max_credits": accepted_credits,
        "accepted_max_usd": accepted_max_usd,
        "action_reserve_credits": action_reserve,
        "telemetry_reserve_credits": telemetry_reserve,
        "total_reserve_credits": total,
    }
