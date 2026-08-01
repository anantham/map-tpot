"""Runtime falsifiers for the fail-closed dossier executor."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

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

    def request(self, endpoint: str, params: dict[str, str]) -> TransportResponse:
        self.calls.append((endpoint, params))
        if not self.responses:
            raise AssertionError("unexpected transport call")
        return self.responses.pop(0)


def _response(
    body: dict,
    status: int = 200,
    *,
    requested_at: str = "2026-07-31T13:00:00Z",
    received_at: str = "2026-07-31T13:00:01Z",
) -> TransportResponse:
    return TransportResponse(
        status_code=status,
        body=body,
        requested_at=requested_at,
        received_at=received_at,
    )


def _plan() -> dict:
    price_card = json.loads(PRICE_CARD_PATH.read_text(encoding="utf-8"))
    return build_dossier_acquisition_plan(
        targets=[{
            "handle": "pilotacct",
            "fetch_profile": True,
            "recent_tweets_limit": 20,
        }],
        price_card=price_card,
        selection_manifest_sha256="a" * 64,
        planned_at="2026-07-31T12:20:24Z",
        hard_cap_usd="0.05",
        max_price_age_days=7,
    )


def _execute(transport: ScriptedTransport, **overrides) -> dict:
    plan = _plan()
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


def _profile(handle: str = "pilotacct", account_id: str = "42") -> dict:
    return {
        "data": {"id": account_id, "userName": handle, "bio": "private"},
        "status": "success",
    }


def _tweet(author_id: str = "42", handle: str = "pilotacct") -> dict:
    return {
        "id": "101",
        "text": "raw private post",
        "author": {"id": author_id, "userName": handle},
    }


def test_profile_identity_mismatch_aborts_before_tweets_and_redacts_body() -> None:
    transport = ScriptedTransport([
        _response({"recharge_credits": 10_000}),
        _response(_profile(handle="different")),
        _response({"recharge_credits": 9_982}),
    ])

    with pytest.raises(AcquisitionExecutionError, match="identity mismatch") as caught:
        _execute(transport)

    assert [call[0] for call in transport.calls] == [
        "/oapi/my/info",
        "/twitter/user/info",
        "/oapi/my/info",
    ]
    assert caught.value.receipt["status"] == "aborted"
    assert caught.value.receipt["reserved_credits"] == 48
    assert len(caught.value.receipt["actions"]) == 1
    assert caught.value.receipt["actions"][0]["status"] == "response_rejected"
    assert len(caught.value.receipt["actions"][0]["response_sha256"]) == 64
    assert "private" not in json.dumps(caught.value.receipt)


def test_only_documented_nested_tweets_and_bound_authors_are_accepted() -> None:
    transport = ScriptedTransport([
        _response({"recharge_credits": 10_000}),
        _response(_profile()),
        _response({"data": {"tweets": [_tweet()]}, "status": "success"}),
        _response({"recharge_credits": 9_982}),
    ])

    receipt = _execute(transport)

    assert [item["status"] for item in receipt["actions"]] == [
        "validated", "validated",
    ]
    assert "raw private post" not in json.dumps(receipt)

    mismatch = ScriptedTransport([
        _response({"recharge_credits": 10_000}),
        _response(_profile()),
        _response({
            "data": {"tweets": [_tweet(author_id="99")]},
            "status": "success",
        }),
        _response({"recharge_credits": 9_952}),
    ])
    with pytest.raises(AcquisitionExecutionError, match="identity binding"):
        _execute(mismatch)


def test_insufficient_balance_stops_before_any_evidence_request() -> None:
    transport = ScriptedTransport([
        _response({"recharge_credits": 300}),
        _response({"recharge_credits": 300}),
    ])

    with pytest.raises(AcquisitionExecutionError, match="below.*reserve") as caught:
        _execute(transport)

    assert [call[0] for call in transport.calls] == [
        "/oapi/my/info",
        "/oapi/my/info",
    ]
    assert caught.value.receipt["actions"] == []


def test_observed_debit_over_cap_aborts_with_complete_sanitized_receipt() -> None:
    transport = ScriptedTransport([
        _response({"recharge_credits": 10_000}),
        _response(_profile()),
        _response({"data": {"tweets": [_tweet()]}, "status": "success"}),
        _response({"recharge_credits": 4_000}),
    ])

    with pytest.raises(AcquisitionExecutionError, match="debit exceeds") as caught:
        _execute(transport)

    receipt = caught.value.receipt
    assert receipt["status"] == "aborted"
    assert receipt["balance"]["debited_credits"] == 6_000
    assert len(receipt["actions"]) == 2
    assert "raw private post" not in json.dumps(receipt)


def test_malformed_post_balance_is_not_retried_beyond_frozen_plan() -> None:
    transport = ScriptedTransport([
        _response({"recharge_credits": 10_000}),
        _response(_profile()),
        _response({"data": {"tweets": [_tweet()]}, "status": "success"}),
        _response({"unexpected": 9_952}),
    ])

    with pytest.raises(AcquisitionExecutionError, match="recharge_credits") as caught:
        _execute(transport)

    assert len(transport.calls) == 4
    assert caught.value.receipt["status"] == "aborted"


@pytest.mark.parametrize(
    "requested_at, received_at, message",
    [
        (None, "2026-07-31T13:00:01Z", "canonical UTC RFC3339"),
        (
            "2026-07-31T13:00:00+00:00",
            "2026-07-31T13:00:01Z",
            "canonical UTC RFC3339",
        ),
        (
            "2026-07-31T13:00:02Z",
            "2026-07-31T13:00:01Z",
            "received_at precedes requested_at",
        ),
    ],
)
def test_transport_timestamps_are_required_canonical_utc_and_ordered(
    requested_at,
    received_at: str,
    message: str,
) -> None:
    transport = ScriptedTransport([
        _response(
            {"recharge_credits": 10_000},
            requested_at=requested_at,
            received_at=received_at,
        ),
    ])

    with pytest.raises(AcquisitionExecutionError, match=message):
        _execute(transport)

    assert len(transport.calls) == 1


def test_profile_and_tweet_ids_must_be_decimal_strings() -> None:
    bad_profile = ScriptedTransport([
        _response({"recharge_credits": 10_000}),
        _response(_profile(account_id="account-42")),
        _response({"recharge_credits": 9_982}),
    ])
    with pytest.raises(AcquisitionExecutionError, match="decimal account id"):
        _execute(bad_profile)

    bad_tweet = ScriptedTransport([
        _response({"recharge_credits": 10_000}),
        _response(_profile()),
        _response({
            "data": {"tweets": [{**_tweet(), "id": "tweet-101"}]},
            "status": "success",
        }),
        _response({"recharge_credits": 9_952}),
    ])
    with pytest.raises(AcquisitionExecutionError, match="decimal tweet id"):
        _execute(bad_tweet)


@pytest.mark.parametrize(
    "body,message",
    [
        ({**_profile(), "status": "error"}, "provider status"),
        (
            {
                **_profile(),
                "data": {**_profile()["data"], "unavailable": True},
            },
            "unavailable",
        ),
    ],
)
def test_error_or_unavailable_profile_never_validates(body: dict, message: str) -> None:
    transport = ScriptedTransport([
        _response({"recharge_credits": 10_000}),
        _response(body),
        _response({"recharge_credits": 9_982}),
    ])

    with pytest.raises(AcquisitionExecutionError, match=message):
        _execute(transport)


@pytest.mark.parametrize(
    "body,message",
    [
        ({"data": {"tweets": [_tweet()]}, "status": "error"}, "provider status"),
        ({"tweets": [_tweet()], "status": "success"}, "top-level data object"),
    ],
)
def test_invalid_tweet_envelopes_never_validate(body: dict, message: str) -> None:
    transport = ScriptedTransport([
        _response({"recharge_credits": 10_000}),
        _response(_profile()),
        _response(body),
        _response({"recharge_credits": 9_952}),
    ])

    with pytest.raises(AcquisitionExecutionError, match=message):
        _execute(transport)
