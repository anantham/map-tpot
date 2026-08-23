"""Sanitized journal observations for one bounded HTTP call."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any, Protocol

from .dossier_executor_types import AcquisitionExecutionError


class CallJournal(Protocol):
    def begin_call(
        self, endpoint: str, params: dict[str, str], requested_at: str
    ) -> int: ...

    def record_response(self, call_id: int, record: dict[str, Any]) -> None: ...

    def finish_call(self, call_id: int, observation: dict[str, Any]) -> None: ...


class JournalWriter:
    """Sanitize journal adapter failures and preserve the no-call boundary."""

    def __init__(self, target: CallJournal | None):
        self._target = target

    def begin(
        self, endpoint: str, params: dict[str, str], requested_at: str
    ) -> int | None:
        if self._target is None:
            return None
        try:
            return self._target.begin_call(endpoint, deepcopy(params), requested_at)
        except Exception:
            raise AcquisitionExecutionError(
                "request journal failed before HTTP attempt"
            ) from None

    def record(self, call_id: int | None, record: dict[str, Any]) -> None:
        if self._target is None or call_id is None:
            return
        try:
            self._target.record_response(call_id, deepcopy(record))
        except Exception:
            raise AcquisitionExecutionError(
                "full response journal failed after HTTP attempt"
            ) from None

    def finish(self, call_id: int | None, observation: dict[str, Any]) -> None:
        if self._target is None or call_id is None:
            return
        try:
            self._target.finish_call(call_id, observation)
        except Exception:
            raise AcquisitionExecutionError(
                "response journal failed after HTTP attempt"
            ) from None


def raw_fingerprint(response: Any) -> tuple[str | None, int | None]:
    """Hash response bytes without retaining or rendering their contents."""
    try:
        content = response.content
    except Exception:
        return None, None
    if not isinstance(content, bytes):
        return None, None
    return hashlib.sha256(content).hexdigest(), len(content)


def call_observation(
    *,
    outcome: str,
    status_code: int | None,
    received_at: str,
    raw_hash: str | None,
    raw_bytes: int | None,
    response_hash: str | None,
    failure_code: str | None,
) -> dict[str, Any]:
    """Return the exact body-free event shape accepted by the bundle."""
    return {
        "outcome": outcome,
        "status_code": status_code,
        "received_at": received_at,
        "raw_body_sha256": raw_hash,
        "raw_body_bytes": raw_bytes,
        "response_sha256": response_hash,
        "failure_code": failure_code,
    }
