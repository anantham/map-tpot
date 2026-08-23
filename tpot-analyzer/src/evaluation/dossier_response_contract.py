"""Strict response validation for the bounded dossier executor."""
from __future__ import annotations

import re
from typing import Any

from .acquisition_manifest import (
    AcquisitionPlanError,
    canonical_json_hash,
    format_time,
    normalize_handle,
    parse_time,
)
from .dossier_executor_types import AcquisitionExecutionError, TransportResponse


_DECIMAL_ID = re.compile(r"[0-9]+")


def _canonical_utc_time(value: Any, field: str):
    try:
        parsed = parse_time(value, field)
    except AcquisitionPlanError as error:
        raise AcquisitionExecutionError(
            f"{field} must be canonical UTC RFC3339"
        ) from error
    if not isinstance(value, str) or not value.endswith("Z"):
        raise AcquisitionExecutionError(
            f"{field} must be canonical UTC RFC3339"
        )
    if format_time(parsed) != value:
        raise AcquisitionExecutionError(
            f"{field} must be canonical UTC RFC3339"
        )
    return parsed


def _decimal_identifier(value: Any, field: str) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or _DECIMAL_ID.fullmatch(value) is None:
        raise AcquisitionExecutionError(f"{field} must be a decimal string")
    return value


def response_envelope(response: TransportResponse, label: str) -> dict[str, Any]:
    if not isinstance(response, TransportResponse):
        raise AcquisitionExecutionError(f"{label} returned an invalid response type")
    if type(response.status_code) is not int or response.status_code != 200:
        raise AcquisitionExecutionError(
            f"{label} returned HTTP {response.status_code!r}; expected 200"
        )
    if not isinstance(response.body, dict):
        raise AcquisitionExecutionError(f"{label} response body must be an object")
    return response.body


def response_receipt(response: TransportResponse) -> dict[str, Any]:
    if not isinstance(response, TransportResponse):
        raise AcquisitionExecutionError("response fingerprint requires response object")
    if not isinstance(response.body, dict):
        raise AcquisitionExecutionError("response fingerprint requires object body")
    if not all(isinstance(key, str) for key in response.body):
        raise AcquisitionExecutionError("response object keys must be strings")
    requested = _canonical_utc_time(response.requested_at, "requested_at")
    received = _canonical_utc_time(response.received_at, "received_at")
    if received < requested:
        raise AcquisitionExecutionError("received_at precedes requested_at")
    try:
        digest = canonical_json_hash(response.body)
    except AcquisitionPlanError as error:
        raise AcquisitionExecutionError(
            "response body cannot be canonically hashed"
        ) from error
    return {
        "http_status": response.status_code,
        "response_sha256": digest,
        "response_top_level_keys": sorted(response.body),
        "requested_at": response.requested_at,
        "received_at": response.received_at,
    }


def parse_balance(response: TransportResponse) -> tuple[int, dict[str, Any]]:
    body = response_envelope(response, "balance telemetry")
    credits = body.get("recharge_credits")
    if type(credits) is not int or credits < 0:
        raise AcquisitionExecutionError(
            "balance telemetry requires nonnegative integer recharge_credits"
        )
    return credits, response_receipt(response)


def parse_profile(
    response: TransportResponse,
    expected_handle: str,
) -> tuple[str, dict[str, Any]]:
    body = response_envelope(response, f"profile @{expected_handle}")
    if body.get("status") != "success":
        raise AcquisitionExecutionError(
            f"profile @{expected_handle} returned non-success provider status"
        )
    data = body.get("data")
    if not isinstance(data, dict):
        raise AcquisitionExecutionError(
            f"profile @{expected_handle} requires top-level data object"
        )
    if data.get("unavailable") is True:
        raise AcquisitionExecutionError(
            f"profile @{expected_handle} is unavailable"
        )
    account_id = _decimal_identifier(data.get("id"), "profile decimal account id")
    returned_handle = data.get("userName")
    try:
        normalized = normalize_handle(returned_handle)
    except ValueError as error:
        raise AcquisitionExecutionError(
            f"profile @{expected_handle} returned an invalid userName"
        ) from error
    if normalized != expected_handle:
        raise AcquisitionExecutionError(
            f"profile identity mismatch: expected @{expected_handle}, "
            f"received @{normalized}"
        )
    receipt = {
        **response_receipt(response),
        "returned_count": 1,
        "account_id": account_id,
    }
    return account_id, receipt


def parse_tweets(
    response: TransportResponse,
    *,
    expected_handle: str,
    expected_account_id: str,
    maximum_returned: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    body = response_envelope(response, f"recent tweets @{expected_handle}")
    if body.get("status") != "success":
        raise AcquisitionExecutionError(
            f"recent tweets @{expected_handle} returned non-success provider status"
        )
    data = body.get("data")
    if not isinstance(data, dict):
        raise AcquisitionExecutionError(
            f"recent tweets @{expected_handle} requires top-level data object"
        )
    tweets = data.get("tweets")
    if not isinstance(tweets, list):
        raise AcquisitionExecutionError(
            f"recent tweets @{expected_handle} requires data.tweets list"
        )
    if len(tweets) > maximum_returned:
        raise AcquisitionExecutionError(
            f"recent tweets @{expected_handle} returned {len(tweets)} items; "
            f"maximum is {maximum_returned}"
        )
    seen_ids: set[str] = set()
    for index, tweet in enumerate(tweets):
        if not isinstance(tweet, dict):
            raise AcquisitionExecutionError(
                f"recent tweets @{expected_handle} item {index} must be an object"
            )
        tweet_id = _decimal_identifier(
            tweet.get("id"),
            f"recent tweets @{expected_handle} item {index} decimal tweet id",
        )
        if tweet_id in seen_ids:
            raise AcquisitionExecutionError(
                f"recent tweets @{expected_handle} contains duplicate tweet id"
            )
        seen_ids.add(tweet_id)
        author = tweet.get("author")
        if not isinstance(author, dict):
            raise AcquisitionExecutionError(
                f"recent tweets @{expected_handle} item {index} lacks author identity"
            )
        author_id = _decimal_identifier(
            author.get("id"),
            f"recent tweets @{expected_handle} item {index} decimal account id",
        )
        try:
            author_handle = normalize_handle(author.get("userName"))
        except ValueError as error:
            raise AcquisitionExecutionError(
                f"recent tweets @{expected_handle} item {index} has invalid author"
            ) from error
        if author_id != expected_account_id or author_handle != expected_handle:
            raise AcquisitionExecutionError(
                f"recent tweets @{expected_handle} item {index} failed identity binding"
            )
    return tweets, {
        **response_receipt(response),
        "returned_count": len(tweets),
        "account_id": expected_account_id,
    }
