"""Public transport and failure types for bounded dossier execution."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class TransportResponse:
    """Credential-free response boundary supplied by an external adapter."""

    status_code: int
    body: dict[str, Any]
    requested_at: str
    received_at: str


class AcquisitionTransport(Protocol):
    def request(
        self,
        endpoint: str,
        params: dict[str, str],
    ) -> TransportResponse: ...


class AcquisitionExecutionError(RuntimeError):
    """Fail-closed execution error carrying a sanitized partial receipt."""

    def __init__(self, message: str, receipt: dict[str, Any] | None = None):
        super().__init__(message)
        self.receipt = receipt
