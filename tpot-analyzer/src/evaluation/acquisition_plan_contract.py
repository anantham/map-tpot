"""Pure followings planning contract with no execution capability."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from .acquisition_manifest import (
    AcquisitionPlanError,
    PLAN_HASH_FIELD,
    canonical_json_hash,
    canonical_plan_bytes,
    credits_to_usd,
    format_time,
    hash_plan_manifest,
    normalize_handle,
    parse_hard_cap,
    parse_time,
    positive_int,
)


def _validate_price_card(price_card: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(price_card, dict) or price_card.get("schema_version") != 1:
        raise AcquisitionPlanError("price card schema_version must be 1")
    if price_card.get("provider") != "twitterapi.io":
        raise AcquisitionPlanError("price card provider must be twitterapi.io")
    if price_card.get("currency") != "USD":
        raise AcquisitionPlanError("price card currency must be USD")
    card_id = price_card.get("card_id")
    if not isinstance(card_id, str) or not card_id:
        raise AcquisitionPlanError("price card requires a nonempty card_id")
    verified_at = parse_time(price_card.get("verified_at"), "verified_at")
    credits_per_usd = positive_int(
        price_card.get("credits_per_usd"), "credits_per_usd"
    )
    endpoint = price_card.get("user_followings")
    if not isinstance(endpoint, dict):
        raise AcquisitionPlanError("price card requires user_followings")
    if endpoint.get("endpoint") != "/twitter/user/followings":
        raise AcquisitionPlanError("price card has an unexpected followings endpoint")
    page_size = positive_int(
        endpoint.get("maximum_page_size"), "maximum_page_size"
    )
    minimum = endpoint.get("minimum_call_credits")
    if type(minimum) is not int or minimum < 0:
        raise AcquisitionPlanError(
            "minimum_call_credits must be a nonnegative integer"
        )
    raw_tiers = endpoint.get("tiers")
    if not isinstance(raw_tiers, list) or not raw_tiers:
        raise AcquisitionPlanError("price card requires nonempty pricing tiers")

    tiers: list[tuple[int, int, int]] = []
    for tier in raw_tiers:
        if not isinstance(tier, dict):
            raise AcquisitionPlanError("each price tier must be an object")
        lower = tier.get("returned_min")
        upper = tier.get("returned_max")
        rate = tier.get("credits_per_item")
        if (
            type(lower) is not int
            or type(upper) is not int
            or type(rate) is not int
            or lower < 1
            or upper < lower
            or upper > page_size
            or rate <= 0
        ):
            raise AcquisitionPlanError("price tiers contain invalid integer bounds")
        tiers.append((lower, upper, rate))
    tiers.sort()
    for previous, current in zip(tiers, tiers[1:]):
        if current[0] != previous[1] + 1:
            raise AcquisitionPlanError(
                "price tiers must cover every billable return count without overlap"
            )
    if tiers[-1][1] != page_size:
        raise AcquisitionPlanError(
            "price tiers must cover every billable return count through page size"
        )
    return {
        "card_id": card_id,
        "verified_at": verified_at,
        "credits_per_usd": credits_per_usd,
        "endpoint": endpoint["endpoint"],
        "page_size": page_size,
        "minimum": minimum,
        "tiers": tiers,
    }


def worst_case_request_credits(price_card: dict[str, Any]) -> int:
    """Return the largest possible credit charge for one followings page."""
    card = _validate_price_card(price_card)
    charges = [card["minimum"]]
    for lower, upper, rate in card["tiers"]:
        charges.extend(
            max(card["minimum"], returned * rate)
            for returned in range(lower, upper + 1)
        )
    return max(charges)


def build_acquisition_plan(
    *,
    targets: list[dict[str, Any]],
    price_card: dict[str, Any],
    planned_at: str,
    hard_cap_usd: str,
    max_price_age_days: int = 7,
) -> dict[str, Any]:
    """Build a credential-free manifest with worst-case credit reserves."""
    card = _validate_price_card(price_card)
    if type(max_price_age_days) is not int or max_price_age_days < 0:
        raise AcquisitionPlanError("max_price_age_days must be nonnegative")
    planned = parse_time(planned_at, "planned_at")
    price_age = planned - card["verified_at"]
    if price_age < timedelta(0):
        raise AcquisitionPlanError("price card verified_at is in the future")
    if price_age > timedelta(days=max_price_age_days):
        raise AcquisitionPlanError(
            f"price card is stale: age exceeds {max_price_age_days} days"
        )
    cap_usd, cap_credits = parse_hard_cap(
        hard_cap_usd, card["credits_per_usd"]
    )
    if not isinstance(targets, list) or not targets:
        raise AcquisitionPlanError("targets must be a nonempty list")

    page_reserve = worst_case_request_credits(price_card)
    normalized_targets = []
    seen: set[str] = set()
    for target in targets:
        if not isinstance(target, dict):
            raise AcquisitionPlanError("each target must be an object")
        handle = normalize_handle(target.get("handle"))
        page_limit = positive_int(target.get("page_limit"), "page_limit")
        if handle in seen:
            raise AcquisitionPlanError(f"duplicate normalized target: @{handle}")
        seen.add(handle)
        normalized_targets.append(
            {
                "handle": handle,
                "page_limit": page_limit,
                "page_reserve_credits": page_reserve,
                "target_reserve_credits": page_limit * page_reserve,
            }
        )
    normalized_targets.sort(key=lambda target: target["handle"])
    request_count = sum(target["page_limit"] for target in normalized_targets)
    total_credits = sum(
        target["target_reserve_credits"] for target in normalized_targets
    )
    if total_credits > cap_credits:
        raise AcquisitionPlanError(
            f"worst-case reserve {total_credits} credits exceeds "
            f"hard cap {cap_credits} credits"
        )

    manifest = {
        "schema_version": 1,
        "kind": "twitterapiio-followings-plan",
        "mode": "plan_only",
        "authorizes_execution": False,
        "provider": "twitterapi.io",
        "endpoint": card["endpoint"],
        "planned_at": format_time(planned),
        "price_card": {
            "card_id": card["card_id"],
            "sha256": canonical_json_hash(price_card),
            "verified_at": format_time(card["verified_at"]),
        },
        "policy": {"max_price_age_days": max_price_age_days},
        "targets": normalized_targets,
        "reservation": {
            "request_count": request_count,
            "total_credits": total_credits,
            "total_usd": credits_to_usd(
                total_credits, card["credits_per_usd"]
            ),
            "hard_cap_credits": cap_credits,
            "hard_cap_usd": cap_usd,
            "remaining_credits": cap_credits - total_credits,
        },
    }
    return {**manifest, PLAN_HASH_FIELD: hash_plan_manifest(manifest)}
