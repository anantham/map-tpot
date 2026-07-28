"""Truthful observed-following coverage for account affinity evidence."""
from __future__ import annotations

import math
from typing import Any, Dict


def estimate_following_coverage(
    *,
    expected_following: Any,
    observed_following: int,
) -> Dict[str, Any]:
    """Return unknown when the denominator is absent or nonpositive."""

    observed = max(0, int(observed_following))
    try:
        expected = float(expected_following)
    except (TypeError, ValueError):
        expected = math.nan
    if not math.isfinite(expected) or expected <= 0:
        return {
            "value": None,
            "status": "unknown",
            "reason": "missing_expected_following",
            "observedFollowing": observed,
            "expectedFollowing": None,
        }
    value = max(0.0, min(1.0, observed / expected))
    return {
        "value": value,
        "status": "observed_fraction",
        "reason": None,
        "observedFollowing": observed,
        "expectedFollowing": expected,
    }
