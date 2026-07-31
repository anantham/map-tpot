"""Behavioral contract for credential-free acquisition planning.

Test intent:
- Pin the exact dated twitterapi.io card used for every estimate.
- Reserve the maximum billable outcome for every planned page.
- Produce a deterministic manifest across harmless ordering/case differences.
- Fail closed on stale prices, bad identities, duplicates, and cap overflow.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evaluation.acquisition_plan_contract import (
    AcquisitionPlanError,
    build_acquisition_plan,
    canonical_plan_bytes,
    hash_plan_manifest,
    worst_case_request_credits,
)


PRICE_CARD_PATH = (
    Path(__file__).parents[1]
    / "data"
    / "manifests"
    / "twitterapiio_price_card_20260730.json"
)
PINNED_PRICE_CARD_SHA256 = (
    "eab5a0810df86593164562636d82f616947984c79a67ce9a32eccfe13d2a9ab2"
)


def _price_card() -> dict:
    return json.loads(PRICE_CARD_PATH.read_text(encoding="utf-8"))


def _build(
    targets: list[dict] | None = None,
    *,
    planned_at: str = "2026-07-31T12:20:24Z",
    hard_cap_usd: str = "0.25",
    price_card: dict | None = None,
) -> dict:
    return build_acquisition_plan(
        targets=targets
        or [
            {"handle": "RomeoStevens76", "page_limit": 2},
            {"handle": "@TVachaW", "page_limit": 1},
        ],
        price_card=price_card or _price_card(),
        planned_at=planned_at,
        hard_cap_usd=hard_cap_usd,
        max_price_age_days=7,
    )


def test_plan_pins_card_and_reserves_worst_case_for_every_page() -> None:
    card = _price_card()
    manifest = _build(price_card=card)

    assert worst_case_request_credits(card) == 398
    assert (
        "https://docs.twitterapi.io/api-reference/endpoint/"
        "get_user_by_username"
    ) in card["official_sources"]
    assert manifest["price_card"] == {
        "card_id": "twitterapiio-2026-07-30",
        "sha256": PINNED_PRICE_CARD_SHA256,
        "verified_at": "2026-07-30T12:20:24Z",
    }
    assert manifest["policy"] == {"max_price_age_days": 7}
    assert manifest["targets"] == [
        {
            "handle": "romeostevens76",
            "page_limit": 2,
            "page_reserve_credits": 398,
            "target_reserve_credits": 796,
        },
        {
            "handle": "tvachaw",
            "page_limit": 1,
            "page_reserve_credits": 398,
            "target_reserve_credits": 398,
        },
    ]
    assert manifest["reservation"] == {
        "request_count": 3,
        "total_credits": 1194,
        "total_usd": "0.01194",
        "hard_cap_credits": 25000,
        "hard_cap_usd": "0.25",
        "remaining_credits": 23806,
    }
    assert manifest["plan_sha256"] == hash_plan_manifest(manifest)


def test_manifest_hash_is_canonical_across_order_case_and_embedded_hash() -> None:
    first = _build()
    second = _build(
        [
            {"handle": "tvachaw", "page_limit": 1},
            {"handle": "@ROMEOSTEVENS76", "page_limit": 2},
        ]
    )

    assert canonical_plan_bytes(first) == canonical_plan_bytes(second)
    assert first["plan_sha256"] == second["plan_sha256"]
    assert hash_plan_manifest({**first, "plan_sha256": "tampered"}) == first[
        "plan_sha256"
    ]


def test_stale_or_future_price_card_is_rejected() -> None:
    with pytest.raises(AcquisitionPlanError, match="stale"):
        _build(planned_at="2026-08-07T12:20:25Z")

    with pytest.raises(AcquisitionPlanError, match="future"):
        _build(planned_at="2026-07-29T12:20:24Z")


@pytest.mark.parametrize(
    "handle",
    [
        "",
        "has space",
        "bad-name",
        "https://x.com/validname",
        "sixteencharacters",
        "@@double",
        "méditation",
    ],
)
def test_malformed_handles_are_rejected(handle: str) -> None:
    with pytest.raises(AcquisitionPlanError, match="handle"):
        _build([{"handle": handle, "page_limit": 1}])


def test_duplicate_normalized_targets_are_rejected() -> None:
    with pytest.raises(AcquisitionPlanError, match="duplicate"):
        _build(
            [
                {"handle": "@SuttaSlime", "page_limit": 1},
                {"handle": "suttaslime", "page_limit": 2},
            ]
        )


def test_plan_is_rejected_when_worst_case_reserve_exceeds_cap() -> None:
    with pytest.raises(
        AcquisitionPlanError,
        match=r"reserve 398 credits.*hard cap 100 credits",
    ):
        _build(
            [{"handle": "realityacid108", "page_limit": 1}],
            hard_cap_usd="0.001",
        )


@pytest.mark.parametrize("page_limit", [0, -1, True, 1.5, "1"])
def test_page_limit_must_be_a_positive_integer(page_limit: object) -> None:
    with pytest.raises(AcquisitionPlanError, match="page_limit"):
        _build([{"handle": "realityacid108", "page_limit": page_limit}])


def test_price_card_tiers_must_cover_every_billable_return_count() -> None:
    card = _price_card()
    card["user_followings"]["tiers"][1]["returned_min"] = 101

    with pytest.raises(AcquisitionPlanError, match="cover"):
        _build(price_card=card)
