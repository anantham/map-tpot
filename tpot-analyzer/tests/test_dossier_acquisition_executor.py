"""Behavioral tests for bounded dossier execution."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.evaluation.acquisition_manifest import hash_plan_manifest
from src.evaluation.dossier_acquisition_executor import (
    execute_dossier_acquisition_plan,
)
from src.evaluation.dossier_acquisition_plan import (
    build_dossier_acquisition_plan,
)
from src.evaluation.dossier_executor_types import (
    AcquisitionExecutionError,
    TransportResponse,
)


PRICE_CARD_PATH = (
    Path(__file__).parents[1]
    / "data"
    / "manifests"
    / "twitterapiio_price_card_20260730.json"
)


class ScriptedTransport:
    def __init__(self, responses: list[TransportResponse]):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, str]]] = []

    def request(
        self,
        endpoint: str,
        params: dict[str, str],
    ) -> TransportResponse:
        self.calls.append((endpoint, params))
        return self.responses.pop(0)


class SanitizedFailureTransport:
    def __init__(self):
        self.calls = 0

    def request(self, endpoint: str, params: dict[str, str]) -> TransportResponse:
        self.calls += 1
        raise AcquisitionExecutionError("provider returned invalid JSON")


def _plan() -> dict:
    price_card = json.loads(PRICE_CARD_PATH.read_text(encoding="utf-8"))
    return build_dossier_acquisition_plan(
        targets=[{
            "handle": "PilotAcct",
            "fetch_profile": True,
            "recent_tweets_limit": 20,
        }],
        price_card=price_card,
        selection_manifest_sha256="a" * 64,
        planned_at="2026-07-31T12:20:24Z",
        hard_cap_usd="0.05",
        max_price_age_days=7,
    )


def _response(
    status_code: int,
    body: dict,
    *,
    requested_at: str = "2026-07-31T13:00:00Z",
    received_at: str = "2026-07-31T13:00:01Z",
) -> TransportResponse:
    return TransportResponse(
        status_code=status_code,
        body=body,
        requested_at=requested_at,
        received_at=received_at,
    )


def _rehash(plan: dict) -> dict:
    plan["plan_sha256"] = hash_plan_manifest(plan)
    return plan


def _execute(plan: dict, transport: ScriptedTransport, **overrides) -> dict:
    arguments = {
        "plan": plan,
        "expected_plan_sha256": plan["plan_sha256"],
        "accepted_max_credits": plan["reservation"]["hard_cap_credits"],
        "accepted_max_usd": plan["reservation"]["hard_cap_usd"],
        "executed_at": "2026-07-31T13:00:00Z",
        "frozen_holdout_account_ids": frozenset({"999"}),
        "transport": transport,
    }
    arguments.update(overrides)
    return execute_dossier_acquisition_plan(**arguments)


def test_executes_profile_then_tweets_with_sanitized_receipt() -> None:
    plan = _plan()
    transport = ScriptedTransport([
        _response(200, {"recharge_credits": 10_000}),
        _response(200, {
            "data": {"id": 42, "userName": "PilotAcct", "description": "bio"},
            "status": "success",
        }),
        _response(200, {
            "tweets": [
                {"id": "101", "text": "secret text", "author": {
                    "id": 42, "userName": "PilotAcct"
                }},
                {"id": 102, "text": "more text", "author": {
                    "id": "42", "userName": "pilotacct"
                }},
            ],
            "status": "success",
        }),
        _response(200, {"recharge_credits": 9_952}),
    ])

    receipt = _execute(
        plan,
        transport,
        accepted_max_credits=plan["reservation"]["total_credits"],
        accepted_max_usd=plan["reservation"]["total_usd"],
    )

    assert transport.calls == [
        ("/oapi/my/info", {}),
        ("/twitter/user/info", {"userName": "pilotacct"}),
        ("/twitter/user/last_tweets", {"userName": "pilotacct"}),
        ("/oapi/my/info", {}),
    ]
    assert receipt["status"] == "completed"
    assert receipt["accepted_cap"] == {"credits": 348, "usd": "0.00348"}
    assert receipt["reserved_credits"] == 348
    assert receipt["plan_sha256"] == plan["plan_sha256"]
    assert receipt["balance"] == {
        "before_credits": 10_000,
        "after_credits": 9_952,
        "debited_credits": 48,
    }
    assert [item["returned_count"] for item in receipt["actions"]] == [1, 2]
    assert [item["account_id"] for item in receipt["actions"]] == ["42", "42"]
    serialized = json.dumps(receipt)
    assert "secret text" not in serialized
    assert "more text" not in serialized
    assert all(len(item["response_sha256"]) == 64 for item in receipt["actions"])
    for item in receipt["telemetry"] + receipt["actions"]:
        assert item["requested_at"] == "2026-07-31T13:00:00Z"
        assert item["received_at"] == "2026-07-31T13:00:01Z"


def test_resolved_holdout_id_aborts_before_tweets_or_next_target() -> None:
    plan = _plan()
    transport = ScriptedTransport([
        _response(200, {"recharge_credits": 10_000}),
        _response(200, {
            "data": {"id": "42", "userName": "pilotacct"},
            "status": "success",
        }),
        _response(200, {"recharge_credits": 9_982}),
    ])

    with pytest.raises(AcquisitionExecutionError, match="frozen holdout") as caught:
        _execute(
            plan,
            transport,
            frozen_holdout_account_ids=frozenset({"42"}),
        )

    assert [call[0] for call in transport.calls] == [
        "/oapi/my/info", "/twitter/user/info", "/oapi/my/info",
    ]
    assert len(caught.value.receipt["actions"]) == 1
    assert caught.value.receipt["actions"][0]["status"] == "response_rejected"
    assert "42" not in str(caught.value)


@pytest.mark.parametrize(
    "holdout_ids",
    [frozenset(), frozenset({"not-decimal"}), {"999"}],
)
def test_frozen_holdout_ids_are_required_and_strict(holdout_ids) -> None:
    plan = _plan()
    transport = ScriptedTransport([])

    with pytest.raises(AcquisitionExecutionError, match="frozen holdout"):
        _execute(
            plan,
            transport,
            frozen_holdout_account_ids=holdout_ids,
        )

    assert transport.calls == []


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda plan: plan.update(authorizes_execution=True), "non-authorizing"),
        (
            lambda plan: plan.update(selection_manifest_sha256="not-a-hash"),
            "selection_manifest_sha256",
        ),
        (
            lambda plan: plan["reservation"].update(request_count=999),
            "request_count",
        ),
        (
            lambda plan: plan["reservation"].update(total_usd="0.00001"),
            "USD reservation",
        ),
        (
            lambda plan: plan["targets"][0].update(handle="PilotAcct"),
            "canonical lowercase",
        ),
        (
            lambda plan: plan["telemetry"].update(endpoint="/wrong"),
            "telemetry contract",
        ),
    ],
)
def test_rehashed_but_invalid_plans_fail_before_transport(mutation, message) -> None:
    plan = deepcopy(_plan())
    mutation(plan)
    _rehash(plan)
    transport = ScriptedTransport([])

    with pytest.raises(AcquisitionExecutionError, match=message):
        _execute(plan, transport)

    assert transport.calls == []


def test_hash_mismatch_and_stale_prices_fail_before_transport() -> None:
    plan = _plan()
    transport = ScriptedTransport([])

    with pytest.raises(AcquisitionExecutionError, match="explicit acceptance"):
        _execute(plan, transport, expected_plan_sha256="b" * 64)
    with pytest.raises(AcquisitionExecutionError, match="stale"):
        _execute(plan, transport, executed_at="2026-08-10T13:00:00Z")

    assert transport.calls == []


@pytest.mark.parametrize(
    "credits, usd, message",
    [
        (347, "0.00347", "credit cap"),
        (5_001, "0.05001", "credit cap"),
        (348, "0.004", "credit and USD"),
    ],
)
def test_explicit_caps_must_be_sufficient_bounded_and_consistent(
    credits: int,
    usd: str,
    message: str,
) -> None:
    plan = _plan()
    transport = ScriptedTransport([])

    with pytest.raises(AcquisitionExecutionError, match=message):
        _execute(
            plan,
            transport,
            accepted_max_credits=credits,
            accepted_max_usd=usd,
        )

    assert transport.calls == []


def test_sanitized_transport_reason_survives_in_partial_receipt() -> None:
    plan = _plan()
    transport = SanitizedFailureTransport()

    with pytest.raises(AcquisitionExecutionError, match="invalid JSON") as caught:
        _execute(plan, transport)

    assert transport.calls == 1
    assert caught.value.receipt["status"] == "aborted"
    assert caught.value.receipt["failure"]["message"].endswith(
        "provider returned invalid JSON"
    )
