"""Small, shared validation contract for persisted discovery feedback."""
from __future__ import annotations

import json
import math

MAX_CONTEXT_BYTES = 4096


def validate_feedback(account_id, signal_name, score, user_label, context):
    if not isinstance(account_id, str) or not 1 <= len(account_id.strip()) <= 128:
        raise ValueError("account_id must be 1..128 characters")
    if not isinstance(signal_name, str) or not 1 <= len(signal_name.strip()) <= 64:
        raise ValueError("signal_name must be 1..64 characters")
    if user_label not in {"tpot", "not_tpot"}:
        raise ValueError("user_label must be one of: tpot, not_tpot")
    if isinstance(score, bool):
        raise ValueError("score must be numeric")
    try:
        score = float(score)
    except (ValueError, TypeError):
        raise ValueError("score must be numeric") from None
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("score must be finite and between 0 and 1")
    if not isinstance(context, dict):
        raise ValueError("context must be an object")
    try:
        encoded = json.dumps(context, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise ValueError("context must contain finite JSON values") from None
    if len(encoded.encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise ValueError(f"context exceeds {MAX_CONTEXT_BYTES} bytes")
    return encoded
