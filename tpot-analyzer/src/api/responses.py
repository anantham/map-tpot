"""Standardized API response helpers.

All route handlers should use these helpers for consistent error and success
response formatting. This ensures frontend clients can rely on a single
parsing strategy.

Error contract:
    {"error": "Human-readable message"}                          # simple
    {"error": "message", "code": "ERROR_CODE"}                   # with code
    {"error": "message", "code": "CODE", "details": {...}}       # with details

Success contract (writes/mutations):
    {"status": "ok", ...extra_fields}

Success contract (reads):
    Raw data (array or object) — no envelope.
"""
from __future__ import annotations

from typing import Any, Optional

from flask import jsonify, Response


def error_response(
    message: str,
    *,
    status: int = 400,
    code: Optional[str] = None,
    details: Optional[Any] = None,
) -> tuple[Response, int]:
    """Return a JSON error response with consistent structure.

    Args:
        message: Human-readable error description.
        status: HTTP status code (default 400).
        code: Optional machine-readable error code (e.g. "VALIDATION_ERROR").
        details: Optional structured context for debugging.
    """
    body: dict[str, Any] = {"error": message}
    if code is not None:
        body["code"] = code
    if details is not None:
        body["details"] = details
    return jsonify(body), status


def ok_response(**fields: Any) -> Response:
    """Return a JSON success response for mutations.

    Always includes {"status": "ok"} plus any additional fields.
    """
    body = {"status": "ok", **fields}
    return jsonify(body)
