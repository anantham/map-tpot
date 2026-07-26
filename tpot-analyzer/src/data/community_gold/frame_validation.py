"""Validation helpers for frozen personal-ontology evaluation frames."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, Mapping, Sequence

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SCOPE_FIELDS = ("userId", "ontologyId", "ontologyVersion", "taskId")


def require_text(value: Any, *, field: str) -> str:
    parsed = str(value or "").strip()
    if not parsed:
        raise ValueError(f"{field} is required")
    return parsed


def require_sha256(value: Any, *, field: str) -> str:
    parsed = str(value or "").strip().lower()
    if not _SHA256_RE.fullmatch(parsed):
        raise ValueError(f"{field} must be a lowercase 64-character SHA-256")
    return parsed


def require_utc_aware(value: Any, *, field: str) -> str:
    parsed = require_text(value, field=field)
    normalized = parsed[:-1] + "+00:00" if parsed.endswith("Z") else parsed
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def unique_ids(values: Sequence[Any], *, field: str) -> list[str]:
    parsed = [require_text(value, field=field) for value in values]
    if len(parsed) != len(set(parsed)):
        raise ValueError(f"{field} contains duplicate account IDs")
    return parsed


def json_value(value: Any, *, field: str) -> Any:
    try:
        return json.loads(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON-serializable") from exc


def normalize_scope(scope: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(scope, Mapping):
        raise ValueError("scope must be an object")
    missing = [field for field in _SCOPE_FIELDS if field not in scope]
    if missing:
        raise ValueError(f"scope is missing required fields: {missing}")
    version = scope["ontologyVersion"]
    if isinstance(version, bool) or not isinstance(version, int) or version <= 0:
        raise ValueError("scope.ontologyVersion must be a positive integer")
    return {
        "userId": require_text(scope["userId"], field="scope.userId"),
        "ontologyId": require_text(
            scope["ontologyId"],
            field="scope.ontologyId",
        ),
        "ontologyVersion": version,
        "taskId": require_text(scope["taskId"], field="scope.taskId"),
    }
