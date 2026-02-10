"""Remote twitterapi.io fetching logic for shadow subset audit."""
from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Set, Tuple

import requests

from .models import RemoteResult
from .normalize import normalize_username


def _pick_user_list(payload: object, relation: str) -> List[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    candidates = [relation, "users", "data", "items", "results", "followers", "followings"]
    for key in candidates:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("users", "items", relation):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _extract_next_cursor(payload: object) -> Optional[str]:
    if not isinstance(payload, dict):
        return None

    scopes = [payload]
    if isinstance(payload.get("meta"), dict):
        scopes.append(payload["meta"])

    for scope in scopes:
        for key in ("next_cursor", "nextCursor", "cursor", "next_token", "nextToken"):
            raw = scope.get(key)
            if raw:
                return str(raw)
    return None


def _has_more(payload: object, next_cursor: Optional[str]) -> bool:
    if next_cursor:
        return True
    if not isinstance(payload, dict):
        return False

    scopes = [payload]
    if isinstance(payload.get("meta"), dict):
        scopes.append(payload["meta"])

    for scope in scopes:
        for key in ("has_next_page", "hasNextPage", "has_more", "hasMore"):
            raw = scope.get(key)
            if isinstance(raw, bool):
                return raw
    return False


def _extract_username(item: dict) -> Optional[str]:
    for key in ("username", "userName", "screen_name", "screenName", "handle"):
        candidate = normalize_username(item.get(key))
        if candidate:
            return candidate
    return None


def _candidate_identifiers(username: str, user_id: Optional[str], mode: str) -> List[Tuple[str, str]]:
    candidates: List[Tuple[str, str]] = []
    if mode in ("auto", "username"):
        candidates.extend([("userName", username), ("username", username)])
    if user_id and mode in ("auto", "id"):
        candidates.extend([("userId", user_id), ("id", user_id)])

    seen: Set[Tuple[str, str]] = set()
    unique: List[Tuple[str, str]] = []
    for pair in candidates:
        if pair in seen:
            continue
        seen.add(pair)
        unique.append(pair)
    return unique


def _rate_limit_sleep_seconds(headers: Dict[str, str]) -> int:
    reset = headers.get("x-rate-limit-reset")
    retry_after = headers.get("retry-after")
    if retry_after and retry_after.isdigit():
        return int(retry_after)
    if reset and reset.isdigit():
        return max(int(reset) - int(time.time()) + 1, 1)
    return 0


def fetch_remote_relation(
    *,
    session: requests.Session,
    base_url: str,
    relation: str,
    username: str,
    user_id: Optional[str],
    identifier_mode: str,
    page_size: int,
    max_pages: int,
    timeout_seconds: int,
    wait_on_rate_limit: bool,
    event_callback: Optional[Callable[[Dict[str, object]], None]] = None,
) -> RemoteResult:
    endpoint = f"{base_url.rstrip('/')}/{relation}"
    errors: List[str] = []
    requests_made = 0
    status_codes: List[int] = []

    def emit(event: Dict[str, object]) -> None:
        if event_callback is None:
            return
        event_callback(event)

    for param_name, param_value in _candidate_identifiers(username, user_id, identifier_mode):
        gathered: Set[str] = set()
        pages_fetched = 0
        cursor: Optional[str] = None
        seen_cursors: Set[str] = set()
        local_status_codes: List[int] = []

        for _ in range(max(1, max_pages)):
            params = {param_name: param_value, "pageSize": str(max(1, page_size))}
            if cursor:
                params["cursor"] = cursor

            emit(
                {
                    "event": "request_start",
                    "endpoint": endpoint,
                    "relation": relation,
                    "identifier_param": param_name,
                    "identifier_value": param_value,
                    "page_index": pages_fetched + 1,
                    "cursor": cursor,
                }
            )

            try:
                response = session.get(endpoint, params=params, timeout=timeout_seconds)
            except requests.RequestException as exc:
                requests_made += 1
                detail = f"{type(exc).__name__}: {exc}"
                errors.append(f"{relation}:{param_name} request_error={detail}")
                emit(
                    {
                        "event": "request_exception",
                        "endpoint": endpoint,
                        "relation": relation,
                        "identifier_param": param_name,
                        "cursor": cursor,
                        "detail": detail,
                    }
                )
                break

            requests_made += 1
            local_status_codes.append(response.status_code)
            emit(
                {
                    "event": "response",
                    "endpoint": endpoint,
                    "relation": relation,
                    "identifier_param": param_name,
                    "cursor": cursor,
                    "status_code": response.status_code,
                    "requests_made": requests_made,
                }
            )

            try:
                payload = response.json()
            except ValueError:
                payload = {"raw": response.text[:800]}

            if response.status_code == 429 and wait_on_rate_limit:
                sleep_seconds = _rate_limit_sleep_seconds(response.headers)
                if sleep_seconds > 0:
                    emit(
                        {
                            "event": "rate_limit_wait",
                            "endpoint": endpoint,
                            "relation": relation,
                            "identifier_param": param_name,
                            "cursor": cursor,
                            "sleep_seconds": sleep_seconds,
                        }
                    )
                    time.sleep(sleep_seconds)
                    continue

            if response.status_code != 200:
                detail = payload.get("detail") if isinstance(payload, dict) else str(payload)
                errors.append(f"{relation}:{param_name} status={response.status_code} detail={detail}")
                emit(
                    {
                        "event": "request_failed",
                        "endpoint": endpoint,
                        "relation": relation,
                        "identifier_param": param_name,
                        "cursor": cursor,
                        "status_code": response.status_code,
                        "detail": detail,
                    }
                )
                break

            user_items = _pick_user_list(payload, relation)
            for item in user_items:
                normalized = _extract_username(item)
                if normalized:
                    gathered.add(normalized)
            pages_fetched += 1
            emit(
                {
                    "event": "page_complete",
                    "endpoint": endpoint,
                    "relation": relation,
                    "identifier_param": param_name,
                    "page_index": pages_fetched,
                    "gathered_count": len(gathered),
                }
            )

            next_cursor = _extract_next_cursor(payload)
            if not _has_more(payload, next_cursor):
                break
            if not next_cursor or next_cursor in seen_cursors:
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        if pages_fetched > 0:
            status_codes.extend(local_status_codes)
            emit(
                {
                    "event": "relation_success",
                    "endpoint": endpoint,
                    "relation": relation,
                    "identifier_param": param_name,
                    "pages_fetched": pages_fetched,
                    "requests_made": requests_made,
                    "usernames_count": len(gathered),
                }
            )
            return RemoteResult(
                usernames=gathered,
                pages_fetched=pages_fetched,
                requests_made=requests_made,
                endpoint=endpoint,
                identifier_param=param_name,
                status_codes=status_codes,
                errors=errors,
            )
        status_codes.extend(local_status_codes)

    emit(
        {
            "event": "relation_failed",
            "endpoint": endpoint,
            "relation": relation,
            "pages_fetched": 0,
            "requests_made": requests_made,
            "errors_count": len(errors),
        }
    )
    return RemoteResult(
        usernames=set(),
        pages_fetched=0,
        requests_made=requests_made,
        endpoint=endpoint,
        identifier_param="none",
        status_codes=status_codes,
        errors=errors if errors else [f"{relation}:no-successful-response"],
    )
