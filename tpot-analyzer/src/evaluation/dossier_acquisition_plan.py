"""Credential-free planning contract for a bounded account-dossier fetch."""
from __future__ import annotations

from datetime import timedelta
import re
from typing import Any

from .acquisition_manifest import (
    AcquisitionPlanError,
    canonical_json_hash,
    credits_to_usd,
    format_time,
    hash_plan_manifest,
    normalize_handle,
    parse_hard_cap,
    parse_time,
)


_SHA256 = re.compile(r"[0-9a-f]{64}")
_BALANCE_TELEMETRY_REQUESTS = 2
_BALANCE_TELEMETRY_RESERVE_PER_REQUEST = 15
_BALANCE_TELEMETRY = {
    "endpoint": "/oapi/my/info",
    "kind": "balance",
    "balance_field": "recharge_credits",
    "request_count": _BALANCE_TELEMETRY_REQUESTS,
    "reserve_credits_per_request": _BALANCE_TELEMETRY_RESERVE_PER_REQUEST,
    "total_reserve_credits": (
        _BALANCE_TELEMETRY_REQUESTS * _BALANCE_TELEMETRY_RESERVE_PER_REQUEST
    ),
    "pricing_status": "conservative_unverified",
    "reserve_basis": "one published tweet-call minimum per request",
    "documentation_url": (
        "https://docs.twitterapi.io/api-reference/endpoint/get_my_info"
    ),
}


def _nonnegative_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise AcquisitionPlanError(f"{field} must be a nonnegative integer")
    return value


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
    credits_per_usd = price_card.get("credits_per_usd")
    if type(credits_per_usd) is not int or credits_per_usd <= 0:
        raise AcquisitionPlanError("credits_per_usd must be a positive integer")

    profile = price_card.get("user_info")
    if not isinstance(profile, dict):
        raise AcquisitionPlanError("price card requires user_info")
    if profile.get("endpoint") != "/twitter/user/info":
        raise AcquisitionPlanError("price card has an unexpected user_info endpoint")
    profile_credits = profile.get("credits_per_profile")
    profile_minimum = profile.get("minimum_call_credits")
    if (
        type(profile_credits) is not int
        or profile_credits <= 0
        or profile_minimum != profile_credits
    ):
        raise AcquisitionPlanError("user_info prices must be matching positive integers")

    tweets = price_card.get("user_last_tweets")
    if not isinstance(tweets, dict):
        raise AcquisitionPlanError("price card requires user_last_tweets")
    if tweets.get("endpoint") != "/twitter/user/last_tweets":
        raise AcquisitionPlanError(
            "price card has an unexpected user_last_tweets endpoint"
        )
    page_size = tweets.get("maximum_page_size")
    tweet_credits = tweets.get("credits_per_tweet")
    tweet_minimum = tweets.get("minimum_call_credits")
    if (
        type(page_size) is not int
        or page_size <= 0
        or type(tweet_credits) is not int
        or tweet_credits <= 0
        or type(tweet_minimum) is not int
        or tweet_minimum <= 0
    ):
        raise AcquisitionPlanError("user_last_tweets prices must be positive integers")
    return {
        "card_id": card_id,
        "verified_at": verified_at,
        "credits_per_usd": credits_per_usd,
        "profile_endpoint": profile["endpoint"],
        "profile_credits": profile_credits,
        "tweets_endpoint": tweets["endpoint"],
        "tweet_page_size": page_size,
        "tweet_credits": tweet_credits,
        "tweet_minimum": tweet_minimum,
    }


def build_dossier_acquisition_plan(
    *,
    targets: list[dict[str, Any]],
    price_card: dict[str, Any],
    selection_manifest_sha256: str,
    planned_at: str,
    hard_cap_usd: str,
    max_price_age_days: int = 7,
) -> dict[str, Any]:
    """Build a plan without credentials, network access, or execution rights."""
    card = _validate_price_card(price_card)
    if (
        not isinstance(selection_manifest_sha256, str)
        or _SHA256.fullmatch(selection_manifest_sha256) is None
    ):
        raise AcquisitionPlanError(
            "selection_manifest_sha256 must be a lowercase SHA-256 digest"
        )
    if type(max_price_age_days) is not int or max_price_age_days < 0:
        raise AcquisitionPlanError("max_price_age_days must be nonnegative")
    planned = parse_time(planned_at, "planned_at")
    age = planned - card["verified_at"]
    if age < timedelta(0):
        raise AcquisitionPlanError("price card verified_at is in the future")
    if age > timedelta(days=max_price_age_days):
        raise AcquisitionPlanError(
            f"price card is stale: age exceeds {max_price_age_days} days"
        )
    cap_usd, cap_credits = parse_hard_cap(
        hard_cap_usd,
        card["credits_per_usd"],
    )
    if not isinstance(targets, list) or not targets:
        raise AcquisitionPlanError("targets must be a nonempty list")

    normalized_targets = []
    seen: set[str] = set()
    for target in targets:
        if not isinstance(target, dict):
            raise AcquisitionPlanError("each target must be an object")
        handle = normalize_handle(target.get("handle"))
        if handle in seen:
            raise AcquisitionPlanError(f"duplicate normalized target: @{handle}")
        seen.add(handle)
        fetch_profile = target.get("fetch_profile")
        if type(fetch_profile) is not bool:
            raise AcquisitionPlanError("fetch_profile must be boolean")
        tweet_limit = _nonnegative_int(
            target.get("recent_tweets_limit"),
            "recent_tweets_limit",
        )
        if tweet_limit > card["tweet_page_size"]:
            raise AcquisitionPlanError(
                "recent_tweets_limit exceeds one documented page: "
                f"limit={tweet_limit}, page_size={card['tweet_page_size']}"
            )
        actions = []
        if fetch_profile:
            actions.append(
                {
                    "endpoint": card["profile_endpoint"],
                    "kind": "profile",
                    "maximum_returned": 1,
                    "reserve_credits": card["profile_credits"],
                }
            )
        if tweet_limit:
            actions.append(
                {
                    "endpoint": card["tweets_endpoint"],
                    "kind": "recent_tweets",
                    "maximum_returned": tweet_limit,
                    "reserve_credits": max(
                        card["tweet_minimum"],
                        tweet_limit * card["tweet_credits"],
                    ),
                }
            )
        if not actions:
            raise AcquisitionPlanError(
                f"target @{handle} must request at least one action"
            )
        normalized_targets.append(
            {
                "handle": handle,
                "actions": actions,
                "target_reserve_credits": sum(
                    action["reserve_credits"] for action in actions
                ),
            }
        )
    normalized_targets.sort(key=lambda target: target["handle"])
    evidence_credits = sum(
        target["target_reserve_credits"] for target in normalized_targets
    )
    telemetry_credits = _BALANCE_TELEMETRY["total_reserve_credits"]
    total_credits = evidence_credits + telemetry_credits
    if total_credits > cap_credits:
        raise AcquisitionPlanError(
            f"worst-case reserve {total_credits} credits exceeds hard cap "
            f"{cap_credits} credits"
        )
    profile_count = sum(
        action["kind"] == "profile"
        for target in normalized_targets
        for action in target["actions"]
    )
    maximum_tweet_count = sum(
        action["maximum_returned"]
        for target in normalized_targets
        for action in target["actions"]
        if action["kind"] == "recent_tweets"
    )
    evidence_request_count = sum(
        len(target["actions"]) for target in normalized_targets
    )
    request_count = evidence_request_count + _BALANCE_TELEMETRY["request_count"]
    manifest = {
        "schema_version": 2,
        "kind": "twitterapiio-formative-dossier-plan",
        "mode": "plan_only",
        "authorizes_execution": False,
        "provider": "twitterapi.io",
        "selection_manifest_sha256": selection_manifest_sha256,
        "planned_at": format_time(planned),
        "price_card": {
            "card_id": card["card_id"],
            "sha256": canonical_json_hash(price_card),
            "verified_at": format_time(card["verified_at"]),
        },
        "policy": {"max_price_age_days": max_price_age_days},
        "telemetry": dict(_BALANCE_TELEMETRY),
        "targets": normalized_targets,
        "reservation": {
            "request_count": request_count,
            "evidence_request_count": evidence_request_count,
            "telemetry_request_count": _BALANCE_TELEMETRY["request_count"],
            "profile_count": profile_count,
            "maximum_tweet_count": maximum_tweet_count,
            "evidence_credits": evidence_credits,
            "telemetry_reserve_credits": telemetry_credits,
            "total_credits": total_credits,
            "total_usd": credits_to_usd(
                total_credits,
                card["credits_per_usd"],
            ),
            "hard_cap_credits": cap_credits,
            "hard_cap_usd": cap_usd,
            "remaining_credits": cap_credits - total_credits,
        },
    }
    return {**manifest, "plan_sha256": hash_plan_manifest(manifest)}
