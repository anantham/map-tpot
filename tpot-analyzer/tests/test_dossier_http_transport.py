"""Behavioral contracts for the bounded twitterapi.io HTTP adapter."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from src.evaluation.dossier_executor_types import AcquisitionExecutionError
from src.evaluation.dossier_http_transport import TwitterApiIoHttpTransport


API_KEY = "super-secret-test-key"
BASE_URL = "https://api.twitterapi.io"


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        body: Any = None,
        json_error: Exception | None = None,
    ):
        self.status_code = status_code
        self._body = body
        self._json_error = json_error

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return deepcopy(self._body)


class RecordingClient:
    def __init__(self, responses: list[FakeResponse] | None = None):
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **deepcopy(kwargs)})
        if not self.responses:
            raise AssertionError("unexpected HTTP call")
        return self.responses.pop(0)


class RaisingClient:
    def __init__(self, error: Exception):
        self.error = error
        self.calls = 0

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls += 1
        raise self.error


class SequenceClock:
    def __init__(self, values: list[datetime]):
        self.values = list(values)

    def __call__(self) -> datetime:
        if not self.values:
            raise AssertionError("unexpected clock call")
        return self.values.pop(0)


def _times(count: int) -> list[datetime]:
    start = datetime(2026, 7, 31, 14, 0, tzinfo=timezone.utc)
    return [start + timedelta(seconds=index) for index in range(count)]


def test_requests_only_fixed_allowlisted_urls_and_captures_defensive_records() -> None:
    bodies = [
        {"recharge_credits": 9000},
        {"data": {"id": "42", "userName": "pilot"}},
        {"tweets": [{"id": "t1"}]},
    ]
    client = RecordingClient([FakeResponse(200, body) for body in bodies])
    transport = TwitterApiIoHttpTransport(
        API_KEY,
        client=client,
        clock=SequenceClock(_times(6)),
    )

    balance = transport.request("/oapi/my/info", {})
    profile = transport.request("/twitter/user/info", {"userName": "pilot"})
    tweets = transport.request(
        "/twitter/user/last_tweets", {"userName": "pilot"}
    )

    assert [call["url"] for call in client.calls] == [
        f"{BASE_URL}/oapi/my/info",
        f"{BASE_URL}/twitter/user/info",
        f"{BASE_URL}/twitter/user/last_tweets",
    ]
    assert all(call["timeout"] == 20.0 for call in client.calls)
    assert all(call["headers"] == {"X-API-Key": API_KEY} for call in client.calls)
    assert [call["params"] for call in client.calls] == [
        {},
        {"userName": "pilot"},
        {"userName": "pilot"},
    ]
    assert balance.requested_at == "2026-07-31T14:00:00Z"
    assert balance.received_at == "2026-07-31T14:00:01Z"
    assert profile.requested_at == "2026-07-31T14:00:02Z"
    assert tweets.received_at == "2026-07-31T14:00:05Z"

    balance.body["recharge_credits"] = 0
    first_copy = transport.response_records()
    assert first_copy[0]["body"] == bodies[0]
    assert first_copy[0] == {
        "endpoint": "/oapi/my/info",
        "params": {},
        "status_code": 200,
        "requested_at": "2026-07-31T14:00:00Z",
        "received_at": "2026-07-31T14:00:01Z",
        "body": bodies[0],
    }
    first_copy[0]["body"]["recharge_credits"] = -1
    assert transport.response_records()[0]["body"] == bodies[0]
    assert API_KEY not in repr(transport)
    assert API_KEY not in repr(transport.response_records())


@pytest.mark.parametrize(
    ("endpoint", "params", "message"),
    [
        ("/unknown", {}, "endpoint is not allowlisted"),
        (None, {}, "endpoint is not allowlisted"),
        ("/oapi/my/info", {"userName": "pilot"}, "parameters"),
        ("/twitter/user/info", {}, "parameters"),
        ("/twitter/user/info", {"userName": "pilot", "extra": "x"}, "parameters"),
        ("/twitter/user/last_tweets", {"userName": ""}, "userName"),
        ("/twitter/user/last_tweets", {"userName": 42}, "userName"),
    ],
)
def test_endpoint_and_parameter_contract_fails_before_http(
    endpoint: str,
    params: dict[str, Any],
    message: str,
) -> None:
    client = RecordingClient()
    transport = TwitterApiIoHttpTransport(
        API_KEY,
        client=client,
        clock=SequenceClock(_times(2)),
    )

    with pytest.raises(AcquisitionExecutionError, match=message):
        transport.request(endpoint, params)

    assert client.calls == []
    assert transport.response_records() == []


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (FakeResponse(200, json_error=ValueError("bad JSON")), "valid JSON"),
        (FakeResponse(200, [1, 2]), "JSON object"),
        (FakeResponse(200, {1: "not-json"}), "string keys"),
        (FakeResponse(True, {}), "integer HTTP status"),
    ],
)
def test_response_parsing_is_strict_and_never_retries(
    response: FakeResponse,
    message: str,
) -> None:
    client = RecordingClient([response])
    transport = TwitterApiIoHttpTransport(
        API_KEY,
        client=client,
        clock=SequenceClock(_times(2)),
    )

    with pytest.raises(AcquisitionExecutionError, match=message) as raised:
        transport.request("/oapi/my/info", {})

    assert len(client.calls) == 1
    assert transport.response_records() == []
    assert API_KEY not in str(raised.value)


def test_client_failure_is_sanitized_and_never_retried() -> None:
    client = RaisingClient(RuntimeError(f"provider echoed {API_KEY}"))
    transport = TwitterApiIoHttpTransport(
        API_KEY,
        client=client,
        clock=SequenceClock(_times(1)),
    )

    with pytest.raises(AcquisitionExecutionError, match="HTTP request failed") as raised:
        transport.request("/oapi/my/info", {})

    assert client.calls == 1
    assert API_KEY not in str(raised.value)
    assert API_KEY not in repr(raised.value)
    assert transport.response_records() == []


def test_provider_cannot_echo_api_key_into_response_or_records() -> None:
    client = RecordingClient([FakeResponse(401, {"error": API_KEY})])
    transport = TwitterApiIoHttpTransport(
        API_KEY,
        client=client,
        clock=SequenceClock(_times(2)),
    )

    with pytest.raises(AcquisitionExecutionError, match="credential") as raised:
        transport.request("/oapi/my/info", {})

    assert API_KEY not in str(raised.value)
    assert API_KEY not in repr(raised.value)
    assert API_KEY not in repr(transport.response_records())
    assert transport.response_records() == []


@pytest.mark.parametrize(
    "values",
    [
        [datetime(2026, 7, 31, 14, 0)],
        [
            datetime(2026, 7, 31, 14, 0, 1, tzinfo=timezone.utc),
            datetime(2026, 7, 31, 14, 0, 0, tzinfo=timezone.utc),
        ],
    ],
)
def test_timestamps_must_be_aware_and_monotonic(values: list[datetime]) -> None:
    client = RecordingClient([FakeResponse(200, {})])
    transport = TwitterApiIoHttpTransport(
        API_KEY,
        client=client,
        clock=SequenceClock(values),
    )

    with pytest.raises(AcquisitionExecutionError, match="timestamp"):
        transport.request("/oapi/my/info", {})

    assert transport.response_records() == []


@pytest.mark.parametrize("api_key", ["", "   ", None, 123])
def test_api_key_must_be_injected_as_nonempty_text(api_key: Any) -> None:
    with pytest.raises(AcquisitionExecutionError, match="API key"):
        TwitterApiIoHttpTransport(api_key, client=RecordingClient())
