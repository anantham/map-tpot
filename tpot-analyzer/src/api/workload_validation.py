"""Validated, bounded metric requests before graph construction."""
import math


def parse_graph_filters(data):
    include_shadow = data.get("include_shadow", True)
    mutual_only = data.get("mutual_only", False)
    if not isinstance(include_shadow, bool) or not isinstance(mutual_only, bool):
        raise ValueError("graph filters must be booleans")
    raw = data.get("min_followers", 0)
    if isinstance(raw, bool):
        raise ValueError("min_followers must be an integer")
    try:
        minimum = int(raw)
    except (TypeError, ValueError):
        raise ValueError("min_followers must be an integer") from None
    if not 0 <= minimum <= 1000000000:
        raise ValueError("min_followers must be between 0 and 1000000000")
    return include_shadow, mutual_only, minimum


def parse_metrics(data):
    if not isinstance(data, dict) or not data:
        raise ValueError("Invalid JSON object")
    seeds = data.get("seeds", [])
    if not isinstance(seeds, list) or len(seeds) > 20 or any(not isinstance(s, str) or len(s) > 50 for s in seeds):
        raise ValueError("seeds must contain at most 20 strings of up to 50 characters")
    weights = data.get("weights", [.4, .3, .3])
    if not isinstance(weights, list) or len(weights) != 3:
        raise ValueError("weights must contain exactly three values")
    try:
        weights = [float(w) for w in weights]
        alpha = float(data.get("alpha", .85))
    except (TypeError, ValueError):
        raise ValueError("weights and alpha must be numeric") from None
    if any(not math.isfinite(w) or not 0 <= w <= 1 for w in weights) or sum(weights) <= 0:
        raise ValueError("weights must be finite values between 0 and 1 with positive sum")
    if not math.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be finite and between 0 and 1 exclusive")
    return seeds, weights, alpha, parse_graph_filters(data)
