"""Durability contracts at the paid HTTP-attempt boundary."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from src.evaluation.dossier_executor_types import AcquisitionExecutionError
from src.evaluation.dossier_http_transport import TwitterApiIoHttpTransport


KEY = "journal-test-secret"


class Response:
    def __init__(self, body: Any, *, status: int = 200, raw: bytes | None = None):
        self.status_code = status
        self._body = body
        self.content = raw if raw is not None else json.dumps(body).encode()

    def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return deepcopy(self._body)


class Journal:
    def __init__(self):
        self.events: list[tuple[str, Any]] = []

    def begin_call(self, endpoint: str, params: dict, requested_at: str) -> int:
        self.events.append(("attempt", endpoint, deepcopy(params), requested_at))
        return len([event for event in self.events if event[0] == "attempt"]) - 1

    def finish_call(self, call_id: int, observation: dict) -> None:
        self.events.append(("observation", call_id, deepcopy(observation)))

    def record_response(self, call_id: int, record: dict) -> None:
        self.events.append(("response", call_id, deepcopy(record)))


class Client:
    def __init__(self, response: Response | Exception, journal: Journal):
        self.response = response
        self.journal = journal
        self.calls = 0

    def get(self, *args: Any, **kwargs: Any) -> Response:
        self.calls += 1
        assert self.journal.events[0][0] == "attempt"
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _clock():
    current = datetime(2026, 7, 31, 14, 0, tzinfo=timezone.utc)

    def read() -> datetime:
        nonlocal current
        value = current
        current += timedelta(seconds=1)
        return value

    return read


def test_attempt_is_journaled_before_http_and_safe_response_afterward() -> None:
    raw = b'{"recharge_credits":9000}'
    journal = Journal()
    client = Client(Response({"recharge_credits": 9000}, raw=raw), journal)
    transport = TwitterApiIoHttpTransport(
        KEY, client=client, clock=_clock(), journal=journal
    )

    response = transport.request("/oapi/my/info", {})

    assert response.body == {"recharge_credits": 9000}
    assert [event[0] for event in journal.events] == [
        "attempt", "response", "observation"
    ]
    durable_response = journal.events[1][2]
    assert durable_response["body"] == {"recharge_credits": 9000}
    observation = journal.events[2][2]
    assert observation == {
        "outcome": "safe_response",
        "status_code": 200,
        "received_at": "2026-07-31T14:00:01Z",
        "raw_body_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_body_bytes": len(raw),
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "failure_code": None,
    }
    assert KEY not in json.dumps(journal.events)
    assert "recharge_credits" not in json.dumps(observation)


def test_invalid_json_writes_sanitized_raw_hash_without_retry() -> None:
    raw = b'{"private post text":'
    journal = Journal()
    client = Client(Response(ValueError("private post text"), raw=raw), journal)
    transport = TwitterApiIoHttpTransport(
        KEY, client=client, clock=_clock(), journal=journal
    )

    with pytest.raises(AcquisitionExecutionError, match="invalid JSON") as raised:
        transport.request("/oapi/my/info", {})

    assert client.calls == 1
    observation = journal.events[1][2]
    assert observation["outcome"] == "rejected_response"
    assert observation["failure_code"] == "invalid_json"
    assert observation["raw_body_sha256"] == hashlib.sha256(raw).hexdigest()
    assert "private post text" not in json.dumps(observation)
    assert "private post text" not in str(raised.value)


def test_client_failure_is_observed_once_without_secret_or_retry() -> None:
    journal = Journal()
    client = Client(RuntimeError(f"echo {KEY}"), journal)
    transport = TwitterApiIoHttpTransport(
        KEY, client=client, clock=_clock(), journal=journal
    )

    with pytest.raises(AcquisitionExecutionError, match="HTTP request failed"):
        transport.request("/oapi/my/info", {})

    assert client.calls == 1
    observation = journal.events[1][2]
    assert observation["failure_code"] == "http_request_failed"
    assert observation["raw_body_sha256"] is None
    assert KEY not in json.dumps(journal.events)


def test_failed_attempt_journal_prevents_the_http_call() -> None:
    class BrokenJournal(Journal):
        def begin_call(self, endpoint: str, params: dict, requested_at: str) -> int:
            raise OSError("disk unavailable")

    journal = BrokenJournal()
    client = Client(Response({}), journal)
    transport = TwitterApiIoHttpTransport(
        KEY, client=client, clock=_clock(), journal=journal
    )

    with pytest.raises(AcquisitionExecutionError, match="journal"):
        transport.request("/oapi/my/info", {})

    assert client.calls == 0


@pytest.mark.parametrize(
    ("times", "failure_code"),
    [
        (
            [
                datetime(2026, 7, 31, 14, 0, tzinfo=timezone.utc),
                datetime(2026, 7, 31, 14, 0),
            ],
            "timestamp_failed",
        ),
        (
            [
                datetime(2026, 7, 31, 14, 0, 1, tzinfo=timezone.utc),
                datetime(2026, 7, 31, 14, 0, 0, tzinfo=timezone.utc),
            ],
            "timestamp_regression",
        ),
    ],
)
def test_response_clock_failure_still_records_sanitized_observation(
    times: list[datetime], failure_code: str
) -> None:
    values = iter(times)
    raw = b'{"private":"body"}'
    journal = Journal()
    client = Client(Response({"private": "body"}, raw=raw), journal)
    transport = TwitterApiIoHttpTransport(
        KEY,
        client=client,
        clock=lambda: next(values),
        journal=journal,
    )

    with pytest.raises(AcquisitionExecutionError, match="timestamp"):
        transport.request("/oapi/my/info", {})

    observation = journal.events[1][2]
    assert observation["failure_code"] == failure_code
    assert observation["raw_body_sha256"] == hashlib.sha256(raw).hexdigest()
    assert '"private"' not in json.dumps(observation)
    assert [event[0] for event in journal.events] == ["attempt", "observation"]
