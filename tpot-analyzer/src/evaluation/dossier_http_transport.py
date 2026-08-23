"""Bounded twitterapi.io transport for pre-registered dossier acquisition."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Callable, Protocol

import httpx

from .dossier_executor_types import AcquisitionExecutionError, TransportResponse
from .acquisition_manifest import canonical_json_hash
from .dossier_transport_observation import (
    CallJournal,
    JournalWriter,
    call_observation,
    raw_fingerprint,
)
from .dossier_transport_contract import (
    canonical_timestamp,
    utc_now,
    validate_json_value,
    validated_params,
)


BASE_URL = "https://api.twitterapi.io"
TIMEOUT_SECONDS = 20.0


class _HttpResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...


class _HttpClient(Protocol):
    def get(self, url: str, **kwargs: Any) -> _HttpResponse: ...


class TwitterApiIoHttpTransport:
    """No-retry HTTP adapter with durable journal and defensive response copies."""

    def __init__(
        self,
        api_key: str,
        *,
        client: _HttpClient | None = None,
        clock: Callable[[], datetime] | None = None,
        journal: CallJournal | None = None,
    ):
        if not isinstance(api_key, str) or not api_key.strip():
            raise AcquisitionExecutionError("twitterapi.io API key must be provided")
        self._api_key = api_key
        self._client = client if client is not None else httpx.Client()
        self._clock = clock if clock is not None else utc_now
        self._journal = JournalWriter(journal)
        self._records: list[dict[str, Any]] = []

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(base_url={BASE_URL!r}, "
            f"response_records={len(self._records)})"
        )

    def _read_clock(self, phase: str) -> tuple[datetime, str]:
        try:
            value = self._clock()
        except Exception:
            raise AcquisitionExecutionError(f"{phase} timestamp clock failed") from None
        return canonical_timestamp(value, phase)

    def _contains_api_key(self, value: Any) -> bool:
        if isinstance(value, str):
            return self._api_key in value
        if type(value) is list:
            return any(self._contains_api_key(item) for item in value)
        if type(value) is dict:
            return any(
                self._contains_api_key(key) or self._contains_api_key(item)
                for key, item in value.items()
            )
        return False

    def _rejected_response(
        self,
        *,
        call_id: int | None,
        message: str,
        failure_code: str,
        status_code: int | None,
        received_at: str,
        raw_hash: str | None,
        raw_bytes: int | None,
    ) -> None:
        self._journal.finish(call_id, call_observation(
            outcome="rejected_response",
            status_code=status_code,
            received_at=received_at,
            raw_hash=raw_hash,
            raw_bytes=raw_bytes,
            response_hash=None,
            failure_code=failure_code,
        ))
        raise AcquisitionExecutionError(message)

    def request(
        self,
        endpoint: str,
        params: dict[str, str],
    ) -> TransportResponse:
        safe_params = validated_params(endpoint, params)
        requested_value, requested_at = self._read_clock("request")
        call_id = self._journal.begin(endpoint, safe_params, requested_at)
        try:
            response = self._client.get(
                f"{BASE_URL}{endpoint}",
                params=deepcopy(safe_params),
                headers={"X-API-Key": self._api_key},
                timeout=TIMEOUT_SECONDS,
            )
        except Exception:
            try:
                _, failed_at = self._read_clock("failure")
            except AcquisitionExecutionError:
                failed_at = requested_at
            self._journal.finish(call_id, call_observation(
                outcome="request_failed",
                status_code=None,
                received_at=failed_at,
                raw_hash=None,
                raw_bytes=None,
                response_hash=None,
                failure_code="http_request_failed",
            ))
            raise AcquisitionExecutionError(
                f"twitterapi.io HTTP request failed for {endpoint}"
            ) from None
        raw_hash, raw_bytes = raw_fingerprint(response)
        try:
            raw_status = getattr(response, "status_code", None)
        except Exception:
            raw_status = None
        safe_status = raw_status if type(raw_status) is int else None
        try:
            received_value, received_at = self._read_clock("response")
        except AcquisitionExecutionError:
            self._rejected_response(
                call_id=call_id,
                message="twitterapi.io response timestamp could not be recorded",
                failure_code="timestamp_failed",
                status_code=safe_status,
                received_at=requested_at,
                raw_hash=raw_hash,
                raw_bytes=raw_bytes,
            )
        if received_value < requested_value:
            self._rejected_response(
                call_id=call_id,
                message="response timestamp cannot precede request timestamp",
                failure_code="timestamp_regression",
                status_code=safe_status,
                received_at=received_at,
                raw_hash=raw_hash,
                raw_bytes=raw_bytes,
            )

        status_code = raw_status
        if type(status_code) is not int:
            self._rejected_response(
                call_id=call_id,
                message=f"twitterapi.io returned a non-integer HTTP status for {endpoint}",
                failure_code="invalid_status",
                status_code=None,
                received_at=received_at,
                raw_hash=raw_hash,
                raw_bytes=raw_bytes,
            )
        try:
            body = response.json()
        except Exception:
            self._rejected_response(
                call_id=call_id,
                message=f"twitterapi.io returned invalid JSON for {endpoint}",
                failure_code="invalid_json",
                status_code=status_code,
                received_at=received_at,
                raw_hash=raw_hash,
                raw_bytes=raw_bytes,
            )
        if type(body) is not dict:
            self._rejected_response(
                call_id=call_id,
                message=f"twitterapi.io response for {endpoint} must be a JSON object",
                failure_code="non_object_json",
                status_code=status_code,
                received_at=received_at,
                raw_hash=raw_hash,
                raw_bytes=raw_bytes,
            )
        try:
            validate_json_value(body)
        except AcquisitionExecutionError as error:
            self._rejected_response(
                call_id=call_id,
                message=str(error),
                failure_code="invalid_json_value",
                status_code=status_code,
                received_at=received_at,
                raw_hash=raw_hash,
                raw_bytes=raw_bytes,
            )
        if self._contains_api_key(body):
            self._rejected_response(
                call_id=call_id,
                message="twitterapi.io response contained the injected credential",
                failure_code="credential_echo",
                status_code=status_code,
                received_at=received_at,
                raw_hash=raw_hash,
                raw_bytes=raw_bytes,
            )
        body_for_response = deepcopy(body)
        record = {
            "endpoint": endpoint,
            "params": deepcopy(safe_params),
            "status_code": status_code,
            "requested_at": requested_at,
            "received_at": received_at,
            "body": deepcopy(body),
        }
        self._records.append(deepcopy(record))
        self._journal.record(call_id, record)
        self._journal.finish(call_id, call_observation(
            outcome="safe_response",
            status_code=status_code,
            received_at=received_at,
            raw_hash=raw_hash,
            raw_bytes=raw_bytes,
            response_hash=canonical_json_hash(body),
            failure_code=None,
        ))
        return TransportResponse(
            status_code=status_code,
            body=body_for_response,
            requested_at=requested_at,
            received_at=received_at,
        )

    def response_records(self) -> list[dict[str, Any]]:
        """Return defensive copies suitable for an exclusive private artifact."""
        return deepcopy(self._records)
