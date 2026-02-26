"""Community color aggregation for hierarchical clusters.

Given propagation results (.npz) and a list of member IDs in a cluster,
computes the dominant and secondary community color and intensity.

Used by cluster_routes.py to add community fields to the API response.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PropagationData:
    """Loaded propagation .npz with fast node-ID lookup."""

    memberships: np.ndarray       # (n, K+1) soft memberships
    uncertainty: np.ndarray       # (n,)
    community_names: list[str]    # K names (no "none")
    community_colors: list[str]   # K hex colors
    community_ids: list[str]      # K UUIDs
    node_id_to_idx: dict[str, int]
    converged: np.ndarray         # (K+1,) bool


@dataclass
class CommunityInfo:
    """Per-cluster community composition."""

    dominant_name: Optional[str] = None
    dominant_color: Optional[str] = None
    dominant_id: Optional[str] = None
    dominant_intensity: float = 0.0

    secondary_name: Optional[str] = None
    secondary_color: Optional[str] = None
    secondary_intensity: float = 0.0

    breakdown: list[dict] = field(default_factory=list)


def load_propagation(path: Path) -> Optional[PropagationData]:
    """Load propagation .npz from disk.

    Returns None if path doesn't exist or is unreadable.
    """
    if not path.exists():
        logger.warning("Propagation file not found: %s", path)
        return None

    try:
        data = np.load(str(path), allow_pickle=True)
    except Exception:
        logger.exception("Failed to load propagation file: %s", path)
        return None

    node_ids = data["node_ids"]
    node_id_to_idx = {str(nid): i for i, nid in enumerate(node_ids)}

    return PropagationData(
        memberships=data["memberships"],
        uncertainty=data["uncertainty"],
        community_names=list(data["community_names"]),
        community_colors=list(data["community_colors"]),
        community_ids=list(data["community_ids"]),
        node_id_to_idx=node_id_to_idx,
        converged=data["converged"],
    )


def compute_cluster_community(
    prop: PropagationData,
    member_ids: list[str],
) -> CommunityInfo:
    """Compute community composition for a cluster of nodes.

    Averages M_render vectors across all member_ids found in the propagation
    data. Extracts dominant and secondary communities (excluding "none" column
    for color, but "none" weight affects intensity).
    """
    if not member_ids:
        return CommunityInfo()

    # Resolve member IDs to matrix indices
    indices = []
    for mid in member_ids:
        idx = prop.node_id_to_idx.get(str(mid))
        if idx is not None:
            indices.append(idx)

    if not indices:
        return CommunityInfo()

    # Average membership vectors across cluster members
    avg = prop.memberships[indices].mean(axis=0)  # (K+1,)

    K = len(prop.community_names)
    community_weights = avg[:K]  # exclude "none" column

    # Build breakdown (sorted descending by weight, exclude near-zero)
    breakdown = []
    for i in range(K):
        w = float(community_weights[i])
        if w > 0.005:
            breakdown.append({
                "name": prop.community_names[i],
                "color": prop.community_colors[i],
                "id": prop.community_ids[i],
                "weight": round(w, 4),
            })
    breakdown.sort(key=lambda x: x["weight"], reverse=True)

    if not breakdown:
        return CommunityInfo(breakdown=[])

    # Dominant community
    dominant = breakdown[0]
    # Intensity = the dominant community's weight (0..1)
    dominant_intensity = dominant["weight"]

    info = CommunityInfo(
        dominant_name=dominant["name"],
        dominant_color=dominant["color"],
        dominant_id=dominant["id"],
        dominant_intensity=round(dominant_intensity, 4),
        breakdown=breakdown,
    )

    # Secondary community (if exists and significant)
    if len(breakdown) > 1:
        secondary = breakdown[1]
        info.secondary_name = secondary["name"]
        info.secondary_color = secondary["color"]
        info.secondary_intensity = round(secondary["weight"], 4)

    return info
