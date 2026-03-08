"""Community color aggregation for hierarchical clusters.

Given propagation results (.npz) and a list of member IDs in a cluster,
computes the principled rendering quantities defined in ADR-013.

ADR-013 color contract
----------------------
Five quantities jointly determine cluster color:

    signal_strength  = 1 - p_C[none]
    purity           = top1 / sum(avg[:K])   (concentration of dominant)
    ambiguity        = top1 - top2           (margin between top-two communities)
    coverage         = matched / total       (fraction of members with propagation scores)
    confidence       = mean(1 - uncertainty) (per-member propagation quality)

    chroma           = sqrt(signal * confidence * coverage) * concentration
    concentration    = 1 - H_normalized(p[:K] | signal)

All five are returned in CommunityInfo and forwarded by cluster_routes.py to
the frontend. ClusterCanvas uses only `chroma` and `ambiguity` for rendering;
the rest appear in tooltips.

Used by cluster_routes.py to add community fields to the API response.
"""
from __future__ import annotations

import logging
import math
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
    """Per-cluster community composition (ADR-013 contract)."""

    # Dominant community identity
    dominant_name: Optional[str] = None
    dominant_color: Optional[str] = None
    dominant_id: Optional[str] = None
    dominant_weight: float = 0.0        # raw avg membership weight (not a rendering signal)

    # Secondary community (runner-up)
    secondary_name: Optional[str] = None
    secondary_color: Optional[str] = None
    secondary_weight: float = 0.0

    # ADR-013 rendering quantities
    signal_strength: float = 0.0   # 1 - none_weight; how much community signal exists
    purity: float = 0.0            # top1 / sum(K); how concentrated the signal is
    ambiguity: float = 0.0         # top1 - top2; margin between top two (high = clear)
    coverage: float = 0.0          # matched_members / total_members
    confidence: float = 0.0        # mean(1 - uncertainty) for matched members
    chroma: float = 0.0            # final rendering value in [0, 1]

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
    """Compute ADR-013 community quantities for a cluster.

    Averages soft membership vectors across matched members, then derives the
    five rendering quantities (signal_strength, purity, ambiguity, coverage,
    confidence) and the final chroma value.

    Args:
        prop:       Loaded propagation data.
        member_ids: All node IDs claimed by this cluster (may exceed prop coverage).

    Returns:
        CommunityInfo with all ADR-013 fields populated.
    """
    if not member_ids:
        return CommunityInfo()

    # ── Resolve member IDs to matrix indices ─────────────────────────────────
    total_members = len(member_ids)
    indices = []
    for mid in member_ids:
        idx = prop.node_id_to_idx.get(str(mid))
        if idx is not None:
            indices.append(idx)

    if not indices:
        return CommunityInfo(coverage=0.0)

    # ── Aggregate membership vectors ─────────────────────────────────────────
    avg = prop.memberships[indices].mean(axis=0)  # (K+1,)

    K = len(prop.community_names)
    community_weights = avg[:K]           # exclude "none" column
    none_weight = float(avg[K]) if len(avg) > K else 0.0

    # ── Coverage ─────────────────────────────────────────────────────────────
    coverage = len(indices) / total_members

    # ── Confidence ───────────────────────────────────────────────────────────
    confidence = float(np.mean(1.0 - prop.uncertainty[indices]))
    confidence = max(0.0, min(1.0, confidence))

    # ── Signal strength ───────────────────────────────────────────────────────
    signal_strength = max(0.0, 1.0 - none_weight)

    # ── Sort communities by weight ────────────────────────────────────────────
    sorted_indices = np.argsort(community_weights)[::-1]
    top1_w = float(community_weights[sorted_indices[0]]) if K >= 1 else 0.0
    top2_w = float(community_weights[sorted_indices[1]]) if K >= 2 else 0.0

    total_signal = float(community_weights.sum())

    # ── Purity ────────────────────────────────────────────────────────────────
    purity = (top1_w / total_signal) if total_signal > 1e-6 else 0.0

    # ── Ambiguity (high = clear winner, low = contested) ─────────────────────
    ambiguity = top1_w - top2_w

    # ── Concentration via normalised entropy ─────────────────────────────────
    if total_signal > 1e-6 and K > 1:
        p = community_weights / total_signal
        p_safe = np.where(p > 1e-10, p, 1e-10)
        H = -float(np.sum(p * np.log(p_safe)))
        H_max = math.log(K)
        concentration = 1.0 - H / H_max
    else:
        concentration = 0.0
    concentration = max(0.0, min(1.0, concentration))

    # ── Chroma: ADR-013 formula ───────────────────────────────────────────────
    # fill_chroma ∝ sqrt(signal * confidence * coverage) * concentration
    chroma = math.sqrt(signal_strength * confidence * coverage) * concentration
    chroma = max(0.0, min(1.0, chroma))

    # ── Build breakdown ───────────────────────────────────────────────────────
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
        return CommunityInfo(
            signal_strength=round(signal_strength, 4),
            coverage=round(coverage, 4),
            confidence=round(confidence, 4),
            chroma=0.0,
            breakdown=[],
        )

    dominant = breakdown[0]
    info = CommunityInfo(
        dominant_name=dominant["name"],
        dominant_color=dominant["color"],
        dominant_id=dominant["id"],
        dominant_weight=round(top1_w, 4),
        signal_strength=round(signal_strength, 4),
        purity=round(purity, 4),
        ambiguity=round(ambiguity, 4),
        coverage=round(coverage, 4),
        confidence=round(confidence, 4),
        chroma=round(chroma, 4),
        breakdown=breakdown,
    )

    if len(breakdown) > 1:
        secondary = breakdown[1]
        info.secondary_name = secondary["name"]
        info.secondary_color = secondary["color"]
        info.secondary_weight = round(top2_w, 4)

    return info
