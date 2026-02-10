"""Validation and policy helpers for extension routes."""
from __future__ import annotations

import os
import secrets
from typing import Any, Optional, Set, Tuple

from flask import Request

from src.data.feed_scope_policy import FeedScopePolicy


def require_scope(request: Request) -> Tuple[str, str]:
    ego = (request.args.get("ego") or "").strip()
    if not ego:
        raise ValueError("ego query param is required")
    workspace_id = request.args.get("workspace_id") or request.args.get("workspace") or "default"
    workspace_id = str(workspace_id).strip() or "default"
    return workspace_id, ego


def parse_json_body(request: Request) -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    return payload


def parse_positive_int(
    request: Request,
    name: str,
    default: int,
    *,
    minimum: int = 1,
    maximum: int = 3650,
) -> int:
    raw = request.args.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer; received '{raw}'") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be in [{minimum}, {maximum}]")
    return value


def parse_iso_optional(request: Request, name: str) -> Optional[str]:
    raw = request.args.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    return str(raw).strip()


def require_bool(name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{name} must be boolean")


def require_string_list(name: str, value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array of strings")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def resolve_allowlist_accounts(policy: FeedScopePolicy, *, tagged_accounts: list[str]) -> Optional[Set[str]]:
    if not policy.allowlist_enabled:
        return None
    accounts = set(policy.allowlist_accounts)
    accounts.update(tagged_accounts)
    return accounts


def require_ingest_auth(policy: FeedScopePolicy, request: Request) -> None:
    if policy.ingestion_mode == "open":
        return
    expected_token = (os.getenv("TPOT_EXTENSION_TOKEN") or "").strip()
    if not expected_token:
        raise RuntimeError("Guarded mode requires TPOT_EXTENSION_TOKEN to be configured")
    received_token = (request.headers.get("X-TPOT-Extension-Token") or "").strip()
    if not received_token or not secrets.compare_digest(received_token, expected_token):
        raise PermissionError("missing or invalid extension token")
