"""Shared canonical identity, time, and money rules for acquisition plans."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from typing import Any


class AcquisitionPlanError(ValueError):
    """Raised when a plan cannot be proven safe against its declared cap."""


HANDLE_PATTERN = re.compile(r"[A-Za-z0-9_]{1,15}")
PLAN_HASH_FIELD = "plan_sha256"


def positive_int(value: Any, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise AcquisitionPlanError(f"{field} must be a positive integer")
    return value


def parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise AcquisitionPlanError(f"{field} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AcquisitionPlanError(
            f"{field} must be an RFC3339 timestamp"
        ) from error
    if parsed.tzinfo is None:
        raise AcquisitionPlanError(f"{field} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def format_time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def canonical_plan_bytes(manifest: dict[str, Any]) -> bytes:
    """Return canonical bytes for a plan, excluding its self-hash field."""
    if not isinstance(manifest, dict):
        raise AcquisitionPlanError("plan manifest must be an object")
    payload = {
        key: value
        for key, value in manifest.items()
        if key != PLAN_HASH_FIELD
    }
    try:
        serialized = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise AcquisitionPlanError(
            "plan manifest must contain canonical JSON"
        ) from error
    return serialized.encode("utf-8")


def hash_plan_manifest(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_plan_bytes(manifest)).hexdigest()


def canonical_json_hash(value: dict[str, Any]) -> str:
    try:
        serialized = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise AcquisitionPlanError(
            "price card must contain canonical JSON"
        ) from error
    return hashlib.sha256(serialized).hexdigest()


def normalize_handle(value: Any) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise AcquisitionPlanError(f"invalid X handle: {value!r}")
    candidate = value[1:] if value.startswith("@") else value
    if HANDLE_PATTERN.fullmatch(candidate) is None:
        raise AcquisitionPlanError(f"invalid X handle: {value!r}")
    return candidate.lower()


def parse_hard_cap(value: str, credits_per_usd: int) -> tuple[str, int]:
    if not isinstance(value, str):
        raise AcquisitionPlanError(
            "hard_cap_usd must be an exact decimal string"
        )
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise AcquisitionPlanError(
            "hard_cap_usd must be a positive decimal"
        ) from error
    if not amount.is_finite() or amount <= 0:
        raise AcquisitionPlanError("hard_cap_usd must be a positive decimal")
    credits = int(
        (amount * Decimal(credits_per_usd)).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    if credits <= 0:
        raise AcquisitionPlanError("hard_cap_usd is smaller than one credit")
    return format(amount.normalize(), "f"), credits


def credits_to_usd(credits: int, credits_per_usd: int) -> str:
    return format(
        (Decimal(credits) / Decimal(credits_per_usd)).normalize(),
        "f",
    )
