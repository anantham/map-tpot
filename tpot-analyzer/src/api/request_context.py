"""Request-scoped context helpers for logging correlation.

This module provides a context-local request id (req_id) and a logging Filter
that injects it into every LogRecord so logs can be grepped by request.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

_REQ_ID: ContextVar[str] = ContextVar("tpot_req_id", default="-")


def set_req_id(req_id: str) -> None:
    _REQ_ID.set(req_id)


def get_req_id() -> str:
    return _REQ_ID.get()


def clear_req_id() -> None:
    _REQ_ID.set("-")


class RequestIdFilter(logging.Filter):
    """Inject `req_id` into log records (always present)."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - required by logging.Filter
        record.req_id = get_req_id()
        return True

