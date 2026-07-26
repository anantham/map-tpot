"""Shape contract for propagation NPZ arrays."""
from __future__ import annotations

import numpy as np


REQUIRED_KEYS = {
    "node_ids",
    "memberships",
    "uncertainty",
    "converged",
    "community_ids",
    "community_names",
    "community_colors",
}
NODE_ARRAY_KEYS = {
    "memberships",
    "uncertainty",
    "abstain_mask",
    "labeled_mask",
    "seed_neighbor_counts",
    "stability",
    "confidence_intervals",
}
GLOBAL_ARRAY_KEYS = {
    "community_ids",
    "community_names",
    "community_colors",
    "converged",
    "cg_iterations",
    "mode",
}


def propagation_score_semantics(arrays: dict) -> tuple[str, str, bool]:
    """Return mode, score semantics, and whether mode was explicitly saved."""
    raw_mode = arrays.get("mode")
    if raw_mode is None:
        return "classic", "probability_simplex", False
    mode_array = np.asarray(raw_mode)
    if mode_array.size != 1:
        raise ValueError(
            f"mode must be a scalar value; got shape={mode_array.shape}"
        )
    raw_value = mode_array.reshape(-1)[0]
    if isinstance(raw_value, bytes):
        raw_value = raw_value.decode("utf-8")
    mode = str(raw_value)
    semantics = {
        "classic": "probability_simplex",
        "independent": "independent_lift",
    }.get(mode)
    if semantics is None:
        raise ValueError(
            f"mode must be 'classic' or 'independent'; got {mode!r}"
        )
    return mode, semantics, True


def validate_propagation_shapes(arrays: dict, n_source: int) -> None:
    """Reject ambiguous or dimensionally inconsistent propagation arrays."""
    unsupported = sorted(
        key
        for key, array in arrays.items()
        if key not in NODE_ARRAY_KEYS | GLOBAL_ARRAY_KEYS | {"node_ids"}
        and array.ndim > 0
        and array.shape[0] == n_source
    )
    if unsupported:
        raise ValueError(
            "unsupported node-indexed arrays require an explicit alignment "
            f"contract: {unsupported}"
        )

    memberships = arrays["memberships"]
    if memberships.ndim != 2 or memberships.shape[0] != n_source:
        raise ValueError(
            "memberships rows must match source node_ids: "
            f"memberships={memberships.shape}, nodes={n_source}"
        )
    n_classes = memberships.shape[1]
    if n_classes < 2:
        raise ValueError(
            f"memberships must contain a community and none column: {memberships.shape}"
        )

    expected_shapes = {
        "uncertainty": (n_source,),
        "abstain_mask": (n_source,),
        "labeled_mask": (n_source,),
        "seed_neighbor_counts": (n_source, n_classes - 1),
        "stability": (n_source, n_classes - 1),
        "confidence_intervals": (n_source, n_classes - 1, 2),
        "converged": (n_classes,),
        "community_ids": (n_classes - 1,),
        "community_names": (n_classes - 1,),
        "community_colors": (n_classes - 1,),
        "cg_iterations": (n_classes,),
    }
    for key, expected in expected_shapes.items():
        if key in arrays and arrays[key].shape != expected:
            raise ValueError(
                f"{key} must have shape={expected}; got {arrays[key].shape}"
            )

    if not np.issubdtype(memberships.dtype, np.number) or not np.all(
        np.isfinite(memberships)
    ):
        raise ValueError("memberships must contain finite numeric values")
    mode, score_semantics, _ = propagation_score_semantics(arrays)
    if np.any(memberships < 0.0):
        raise ValueError(f"{mode} memberships must be non-negative")
    if score_semantics == "probability_simplex":
        if np.any(memberships > 1.0):
            raise ValueError("classic memberships must be in [0, 1]")
        row_sums = memberships.sum(axis=1)
        if not np.allclose(row_sums, 1.0, rtol=0.0, atol=1e-5):
            max_error = float(np.max(np.abs(row_sums - 1.0)))
            raise ValueError(
                "classic memberships rows must sum to 1 within 1e-5; "
                f"max_abs_error={max_error}"
            )

    uncertainty = arrays["uncertainty"]
    if (
        not np.issubdtype(uncertainty.dtype, np.number)
        or not np.all(np.isfinite(uncertainty))
        or np.any(uncertainty < 0.0)
        or np.any(uncertainty > 1.0)
    ):
        raise ValueError("uncertainty must be finite and in [0, 1]")
    for key in ("abstain_mask", "labeled_mask", "converged"):
        if key in arrays and arrays[key].dtype != np.bool_:
            raise ValueError(f"{key} must be boolean; got {arrays[key].dtype}")

    community_ids = np.asarray([str(value) for value in arrays["community_ids"]])
    if any(not value.strip() for value in community_ids):
        raise ValueError("community_ids must be non-empty")
    if len(np.unique(community_ids)) != len(community_ids):
        raise ValueError("community_ids must be unique")
