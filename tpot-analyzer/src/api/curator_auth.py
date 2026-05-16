"""Auth gate for curator-only mutating endpoints.

Fail-closed by design: if `TPOT_CURATOR_TOKEN` is not configured, mutating
endpoints return 503 rather than silently accepting unauthenticated writes.
This forces operators to set a secret before deploy and prevents the
"forgot to configure auth" footgun that would otherwise expose the curator
dataset to anonymous mutation.

Usage:
    from src.api.curator_auth import curator_only

    @bp.route("/resource", methods=["PUT"])
    @curator_only
    def update_resource():
        ...
"""
from __future__ import annotations

import os
import secrets
from functools import wraps
from typing import Callable

from flask import Request, request

from src.api.responses import error_response

CURATOR_TOKEN_ENV = "TPOT_CURATOR_TOKEN"
CURATOR_TOKEN_HEADER = "X-TPOT-Curator-Token"


class CuratorAuthError(Exception):
    """Base for curator-auth failures."""

    status: int = 401


class CuratorMisconfiguredError(CuratorAuthError):
    """Raised when TPOT_CURATOR_TOKEN is not set on the server."""

    status = 503


class CuratorUnauthorizedError(CuratorAuthError):
    """Raised when the request token header is missing or wrong."""

    status = 401


def require_curator_auth(req: Request) -> None:
    """Reject non-curator callers on mutating endpoints.

    Raises CuratorMisconfiguredError if TPOT_CURATOR_TOKEN is unset; this
    fails closed so a misconfigured deployment cannot silently accept writes.
    """
    expected = (os.getenv(CURATOR_TOKEN_ENV) or "").strip()
    if not expected:
        raise CuratorMisconfiguredError(
            f"{CURATOR_TOKEN_ENV} is not configured; curator endpoints disabled"
        )
    received = (req.headers.get(CURATOR_TOKEN_HEADER) or "").strip()
    if not received or not secrets.compare_digest(received, expected):
        raise CuratorUnauthorizedError("missing or invalid curator token")


def curator_only(view_fn: Callable) -> Callable:
    """Decorator: require a valid curator token on this view."""

    @wraps(view_fn)
    def wrapper(*args, **kwargs):
        try:
            require_curator_auth(request)
        except CuratorAuthError as exc:
            return error_response(str(exc), status=exc.status)
        return view_fn(*args, **kwargs)

    return wrapper
