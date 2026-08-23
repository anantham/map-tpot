"""Pure request, timestamp, and JSON rules for the dossier HTTP adapter."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from .dossier_executor_types import AcquisitionExecutionError


ENDPOINT_PARAMS = {
    "/oapi/my/info": frozenset(),
    "/twitter/user/info": frozenset({"userName"}),
    "/twitter/user/last_tweets": frozenset({"userName"}),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_timestamp(value: Any, phase: str) -> tuple[datetime, str]:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise AcquisitionExecutionError(
            f"{phase} timestamp must be a timezone-aware datetime"
        )
    try:
        utc_value = value.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise AcquisitionExecutionError(f"{phase} timestamp is invalid") from None
    return utc_value, utc_value.isoformat().replace("+00:00", "Z")


def validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        return
    if isinstance(value, float):
        if isfinite(value):
            return
        raise AcquisitionExecutionError("response JSON numbers must be finite")
    if type(value) is list:
        for item in value:
            validate_json_value(item)
        return
    if type(value) is dict:
        if not all(isinstance(key, str) for key in value):
            raise AcquisitionExecutionError(
                "response JSON objects must have string keys"
            )
        for item in value.values():
            validate_json_value(item)
        return
    raise AcquisitionExecutionError("response body contains a non-JSON value")


def validated_params(endpoint: Any, params: Any) -> dict[str, str]:
    if not isinstance(endpoint, str):
        raise AcquisitionExecutionError("transport endpoint is not allowlisted")
    allowed = ENDPOINT_PARAMS.get(endpoint)
    if allowed is None:
        raise AcquisitionExecutionError("transport endpoint is not allowlisted")
    if type(params) is not dict or set(params) != allowed:
        raise AcquisitionExecutionError(
            f"transport parameters do not match the contract for {endpoint}"
        )
    if "userName" in allowed:
        username = params["userName"]
        if not isinstance(username, str) or not username.strip():
            raise AcquisitionExecutionError(
                f"transport userName must be nonempty for {endpoint}"
            )
    return deepcopy(params)
