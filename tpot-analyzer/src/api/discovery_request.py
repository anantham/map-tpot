"""Bounded discovery request schema, independent of graph computation."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from src.graph.scoring import process_weights, DEFAULT_WEIGHTS

MAX_SEEDS = 20
MAX_LIMIT = 500
MAX_OFFSET = 10000


@dataclass
class DiscoveryRequest:
    seeds: list[str]
    weights: dict[str, float]
    filters: dict[str, Any]
    limit: int
    offset: int
    use_cache: bool
    debug: bool


def validate_request(data):
    if not isinstance(data, dict):
        return None, ["Request body must be a JSON object"]
    errors = []
    seeds = data.get("seeds", [])
    if not isinstance(seeds, list):
        errors.append("seeds: must be an array")
    elif not seeds:
        errors.append("seeds: required field")
    elif len(seeds) > MAX_SEEDS:
        errors.append(f"seeds: maximum {MAX_SEEDS} seeds allowed")
    elif any(not isinstance(seed, str) or not 1 <= len(seed.strip()) <= 50 for seed in seeds):
        errors.append("seeds: invalid handle type, empty handle, or handle too long (maximum 50 characters)")

    raw_weights = data.get("weights", {})
    if not isinstance(raw_weights, dict):
        errors.append("weights: must be an object")
        raw_weights = {}
    for name, value in raw_weights.items():
        if name not in DEFAULT_WEIGHTS:
            errors.append(f"weights: unknown weight {name}")
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            errors.append(f"weights.{name}: must be finite and non-negative")

    filters = data.get("filters", {})
    if not isinstance(filters, dict):
        errors.append("filters: must be an object")
        filters = {}
    numeric_filters = {"max_distance": (1, 4), "min_overlap": (0, 20),
                       "min_followers": (0, 1000000000), "max_followers": (0, 1000000000)}
    allowed = set(numeric_filters) | {"include_shadow", "exclude_following", "include_communities", "exclude_communities"}
    for name, value in filters.items():
        if name not in allowed:
            errors.append(f"filters: unknown filter {name}")
        elif name in numeric_filters:
            low, high = numeric_filters[name]
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                errors.append(f"filters.{name}: must be an integer between {low} and {high}")
        elif name in {"include_shadow", "exclude_following"}:
            if not isinstance(value, bool):
                errors.append(f"filters.{name}: must be boolean")
        elif not isinstance(value, list) or len(value) > 100 or any(not isinstance(v, int) for v in value):
            errors.append(f"filters.{name}: must contain at most 100 integer community IDs")

    limit, offset = data.get("limit", 100), data.get("offset", 0)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        errors.append("limit: must be a positive integer")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        errors.append("offset: must be a non-negative integer")
    use_cache, debug = data.get("use_cache", True), data.get("debug", False)
    if not isinstance(use_cache, bool) or not isinstance(debug, bool):
        errors.append("use_cache and debug must be booleans")
    if errors:
        return None, errors
    return DiscoveryRequest(seeds, process_weights(raw_weights), filters,
                            min(limit, MAX_LIMIT), min(offset, MAX_OFFSET), use_cache, debug), None
