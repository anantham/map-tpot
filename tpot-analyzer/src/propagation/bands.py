"""Pure display-band classification and its supported-mode contract."""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

from src.artifacts.propagation_schema import propagation_score_semantics
from src.propagation.entropy import (
    normalized_row_entropy,
    validate_affinity_matrix,
)

logger = logging.getLogger(__name__)

# Classic mode thresholds. These preserve the historical zero-sum classifier;
# they are display heuristics, not calibrated probabilities.
SPECIALIST_MIN_WEIGHT = 0.30
SPECIALIST_MAX_ENTROPY = 0.70
BRIDGE_MIN_WEIGHT = 0.15
BRIDGE_MIN_COMMUNITIES = 2
BRIDGE_MAX_NONE = 0.40
FRONTIER_MIN_WEIGHT = 0.08


class IndependentBandingUndefinedError(RuntimeError):
    """Raised when unvalidated display bands are requested for Lift scores."""


class UnboundAccountBandError(RuntimeError):
    """Raised when an unbound SQLite band table would select external work."""


def reject_unbound_account_band_table(consumer: str) -> None:
    """Block standalone use of bands that lack an artifact receipt."""
    raise UnboundAccountBandError(
        f"{consumer}: account_band is quarantined because its rows are not "
        "bound to an exact propagation digest, mode, taxonomy, thresholds, "
        "and method version"
    )


def propagation_artifact_mode(arrays: Any) -> str:
    """Read an explicitly declared artifact mode.

    Band consumers are release-facing. A missing mode is therefore not
    interpreted as classic merely because that was the historical default.
    """
    mode, _, explicit = propagation_score_semantics(arrays)
    if not explicit:
        raise RuntimeError(
            "propagation artifact mode is undeclared; band consumers require "
            "an explicit classic or independent mode"
        )
    return mode


def require_supported_band_mode(mode: str) -> None:
    """Fail closed when no defensible display-band contract exists."""
    if mode == "independent":
        raise IndependentBandingUndefinedError(
            "independent Lift band classification is undefined: the historical "
            "entropy calculation was scale-dependent, and specialist/bridge "
            "thresholds and precedence have not been validated. Refusing to "
            "create or export new account_band claims."
        )
    if mode != "classic":
        raise ValueError(f"unsupported propagation mode for banding: {mode!r}")


def require_supported_band_artifact(arrays: Any) -> str:
    """Require a dimensionally coherent classic simplex before banding."""
    mode = propagation_artifact_mode(arrays)
    require_supported_band_mode(mode)
    if "memberships" not in arrays:
        raise RuntimeError(
            "classic band artifact is missing the memberships matrix"
        )
    memberships = validate_affinity_matrix(arrays["memberships"])
    if "node_ids" not in arrays:
        raise RuntimeError("classic band artifact is missing node_ids")
    node_ids = np.asarray(arrays["node_ids"])
    if node_ids.ndim != 1:
        raise RuntimeError(
            "classic band artifact node_ids must be one-dimensional: "
            f"shape={node_ids.shape}"
        )
    if memberships.shape[0] != len(node_ids):
        raise RuntimeError(
            "classic band artifact memberships rows must match node_ids: "
            f"memberships={memberships.shape[0]}, node_ids={len(node_ids)}"
        )
    for key in ("abstain_mask", "labeled_mask"):
        if key not in arrays:
            raise RuntimeError(f"classic band artifact is missing {key}")
        mask = np.asarray(arrays[key])
        if mask.shape != (len(node_ids),):
            raise RuntimeError(
                f"classic band artifact {key} must have "
                f"shape={(len(node_ids),)}; got {mask.shape}"
            )
        if mask.dtype != np.bool_:
            raise RuntimeError(
                f"classic band artifact {key} must be boolean; "
                f"got dtype={mask.dtype}"
            )

    identity_keys = [
        key for key in ("community_ids", "community_names") if key in arrays
    ]
    if not identity_keys:
        raise RuntimeError(
            "classic band artifact is missing community_ids/community_names"
        )
    community_counts: dict[str, int] = {}
    for key in identity_keys:
        identities = np.asarray(arrays[key])
        if identities.ndim != 1:
            raise RuntimeError(
                f"classic band artifact {key} must be one-dimensional: "
                f"shape={identities.shape}"
            )
        community_counts[key] = len(identities)
    if len(set(community_counts.values())) > 1:
        raise RuntimeError(
            "classic band artifact community identity lengths disagree: "
            f"{community_counts}"
        )
    community_count = next(iter(community_counts.values()))
    if community_count < 1 or memberships.shape[1] != community_count + 1:
        raise RuntimeError(
            "classic band artifact memberships must contain one column per "
            "community plus a none column: "
            f"memberships={memberships.shape[1]}, communities={community_count}"
        )
    row_sums = memberships.sum(axis=1)
    if np.any(memberships > 1.0) or not np.allclose(
        row_sums,
        1.0,
        rtol=0.0,
        atol=1e-5,
    ):
        max_error = (
            float(np.max(np.abs(row_sums - 1.0)))
            if len(row_sums)
            else 0.0
        )
        raise RuntimeError(
            "classic band artifact must be a probability simplex: "
            f"max_row_sum_error={max_error:.6g}"
        )
    return mode


def compute_normalized_entropy(community_weights: np.ndarray) -> np.ndarray:
    """Compute scale-invariant H/log(K) over community affinities."""
    return normalized_row_entropy(community_weights)


def compute_legacy_classic_entropy(
    community_weights: np.ndarray,
) -> np.ndarray:
    """Reproduce the historical classic partial-mass entropy exactly.

    Classic rows include a final ``none`` probability, while this legacy
    display heuristic excludes that column without renormalizing. It is not a
    compositional concentration measure; retaining it avoids silently
    reclassifying classic artifacts during this independent-mode safety fix.
    """
    values = validate_affinity_matrix(community_weights)
    if values.shape[0] == 0 or values.shape[1] < 2:
        return np.zeros(values.shape[0], dtype=np.float64)
    positive = values > 1e-10
    contributions = np.zeros_like(values)
    contributions[positive] = values[positive] * np.log(values[positive])
    return -contributions.sum(axis=1) / math.log(values.shape[1])


def classify_bands(prop: dict[str, Any]) -> dict[str, np.ndarray]:
    """Classify classic zero-sum memberships into legacy display bands.

    Independent Lift values deliberately fail closed. Defining their bands
    requires an evaluated specialist/bridge contract, not threshold reuse.
    """
    if prop.get("independent_mode", False):
        require_supported_band_mode("independent")
    require_supported_band_artifact(prop)

    node_count = len(prop["node_ids"])
    community_count = prop["memberships"].shape[1] - 1
    community_weights = prop["memberships"][:, :community_count]
    none_weight = prop["memberships"][:, -1]
    labeled = prop["labeled_mask"]
    abstain = prop["abstain_mask"]

    max_weight = community_weights.max(axis=1)
    top_idx = community_weights.argmax(axis=1)
    entropy = compute_legacy_classic_entropy(community_weights)
    n_above_bridge = (community_weights >= BRIDGE_MIN_WEIGHT).sum(axis=1)

    band = np.full(node_count, "unknown", dtype="U12")

    frontier_mask = ~abstain & (max_weight >= FRONTIER_MIN_WEIGHT) & ~labeled
    band[frontier_mask] = "frontier"

    bridge_mask = (
        ~labeled
        & ~abstain
        & (n_above_bridge >= BRIDGE_MIN_COMMUNITIES)
        & (none_weight < BRIDGE_MAX_NONE)
    )
    band[bridge_mask] = "bridge"

    specialist_mask = (
        ~labeled
        & ~abstain
        & (max_weight >= SPECIALIST_MIN_WEIGHT)
        & (entropy < SPECIALIST_MAX_ENTROPY)
    )
    band[specialist_mask] = "specialist"
    band[labeled] = "exemplar"

    return {
        "band": band,
        "top_community_idx": top_idx,
        "top_weight": max_weight,
        "entropy": entropy,
        "none_weight": none_weight,
    }
