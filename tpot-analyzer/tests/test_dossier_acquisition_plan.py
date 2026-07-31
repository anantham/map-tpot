"""Behavioral contract for the formative-dossier acquisition plan."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evaluation.acquisition_plan_contract import AcquisitionPlanError
from src.evaluation.dossier_acquisition_plan import (
    build_dossier_acquisition_plan,
)


PRICE_CARD_PATH = (
    Path(__file__).parents[1]
    / "data"
    / "manifests"
    / "twitterapiio_price_card_20260730.json"
)


def _price_card() -> dict:
    return json.loads(PRICE_CARD_PATH.read_text(encoding="utf-8"))


def _targets(count: int = 12) -> list[dict]:
    return [
        {
            "handle": f"pilotacct{index:02d}",
            "fetch_profile": True,
            "recent_tweets_limit": 20,
        }
        for index in range(count)
    ]


def _build(**overrides) -> dict:
    inputs = {
        "targets": _targets(),
        "price_card": _price_card(),
        "selection_manifest_sha256": "a" * 64,
        "planned_at": "2026-07-31T12:20:24Z",
        "hard_cap_usd": "0.05",
        "max_price_age_days": 7,
    }
    inputs.update(overrides)
    return build_dossier_acquisition_plan(**inputs)


def test_twelve_standardized_dossiers_reserve_less_than_four_cents() -> None:
    plan = _build()

    assert plan["kind"] == "twitterapiio-formative-dossier-plan"
    assert plan["authorizes_execution"] is False
    assert plan["selection_manifest_sha256"] == "a" * 64
    assert plan["reservation"] == {
        "request_count": 24,
        "profile_count": 12,
        "maximum_tweet_count": 240,
        "total_credits": 3816,
        "total_usd": "0.03816",
        "hard_cap_credits": 5000,
        "hard_cap_usd": "0.05",
        "remaining_credits": 1184,
    }
    assert all(target["target_reserve_credits"] == 318 for target in plan["targets"])
    assert len(plan["price_card"]["sha256"]) == 64
    assert len(plan["plan_sha256"]) == 64


def test_plan_is_deterministic_across_target_order_and_handle_case() -> None:
    forward = _build()
    reversed_targets = list(reversed(_targets()))
    reversed_targets[0]["handle"] = reversed_targets[0]["handle"].upper()

    reordered = _build(targets=reversed_targets)

    assert reordered == forward


def test_each_target_declares_atomic_profile_and_tweet_actions() -> None:
    target = _build(targets=_targets(1))["targets"][0]

    assert target["actions"] == [
        {
            "endpoint": "/twitter/user/info",
            "kind": "profile",
            "maximum_returned": 1,
            "reserve_credits": 18,
        },
        {
            "endpoint": "/twitter/user/last_tweets",
            "kind": "recent_tweets",
            "maximum_returned": 20,
            "reserve_credits": 300,
        },
    ]


def test_cap_overflow_fails_closed_before_execution() -> None:
    with pytest.raises(AcquisitionPlanError, match="exceeds hard cap"):
        _build(hard_cap_usd="0.03")


@pytest.mark.parametrize("limit", [21, -1, True, "20"])
def test_recent_tweet_limit_must_fit_one_documented_page(limit: object) -> None:
    targets = _targets(1)
    targets[0]["recent_tweets_limit"] = limit
    with pytest.raises(AcquisitionPlanError, match="recent_tweets_limit"):
        _build(targets=targets)


def test_duplicate_handles_and_empty_actions_fail_closed() -> None:
    duplicate = _targets(2)
    duplicate[1]["handle"] = duplicate[0]["handle"].upper()
    with pytest.raises(AcquisitionPlanError, match="duplicate"):
        _build(targets=duplicate)

    with pytest.raises(AcquisitionPlanError, match="at least one action"):
        _build(
            targets=[{
                "handle": "empty_action",
                "fetch_profile": False,
                "recent_tweets_limit": 0,
            }]
        )


def test_missing_or_drifted_dossier_prices_fail_closed() -> None:
    missing = _price_card()
    missing.pop("user_last_tweets")
    with pytest.raises(AcquisitionPlanError, match="user_last_tweets"):
        _build(price_card=missing)

    drifted = _price_card()
    drifted["user_info"]["endpoint"] = "/unexpected"
    with pytest.raises(AcquisitionPlanError, match="user_info endpoint"):
        _build(price_card=drifted)


def test_selection_manifest_must_be_content_addressed() -> None:
    with pytest.raises(AcquisitionPlanError, match="selection_manifest_sha256"):
        _build(selection_manifest_sha256="not-a-sha256")
