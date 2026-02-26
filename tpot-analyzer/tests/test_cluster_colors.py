"""Tests for community color aggregation per cluster."""
import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.communities.cluster_colors import (
    CommunityInfo,
    PropagationData,
    compute_cluster_community,
    load_propagation,
)

# --- Helpers ---

NAMES = ["Alpha", "Beta", "Gamma"]
COLORS = ["#ff0000", "#00ff00", "#0000ff"]


def _make_npz(tmp_path: Path, memberships, node_ids=None, converged=None):
    """Create a fake propagation .npz file for testing."""
    n = memberships.shape[0]
    K = memberships.shape[1] - 1  # last col is "none"
    if node_ids is None:
        node_ids = np.array([str(i) for i in range(n)])
    if converged is None:
        converged = np.ones(K + 1, dtype=bool)

    path = tmp_path / "test_prop.npz"
    np.savez_compressed(
        str(path),
        memberships=memberships.astype(np.float32),
        uncertainty=np.zeros(n, dtype=np.float32),
        abstain_mask=np.zeros(n, dtype=bool),
        labeled_mask=np.zeros(n, dtype=bool),
        node_ids=node_ids,
        community_ids=np.array([f"id-{i}" for i in range(K)]),
        community_names=np.array(NAMES[:K]),
        community_colors=np.array(COLORS[:K]),
        converged=converged,
        cg_iterations=np.zeros(K + 1, dtype=np.int32),
    )
    return path


# --- Loading ---


def test_loads_from_path(tmp_path):
    """Load a valid .npz and verify PropagationData fields."""
    memberships = np.array([
        [0.5, 0.3, 0.1, 0.1],
        [0.1, 0.6, 0.2, 0.1],
    ])
    path = _make_npz(tmp_path, memberships)
    prop = load_propagation(path)

    assert prop is not None
    assert isinstance(prop, PropagationData)
    assert prop.memberships.shape == (2, 4)
    assert len(prop.community_names) == 3
    assert len(prop.community_colors) == 3
    # node_id_to_idx lookup works
    assert prop.node_id_to_idx["0"] == 0
    assert prop.node_id_to_idx["1"] == 1


def test_returns_none_for_missing_file():
    """Missing path returns None, not an exception."""
    result = load_propagation(Path("/nonexistent/path.npz"))
    assert result is None


# --- Strong community cluster ---


def test_strong_community_cluster(tmp_path):
    """4 nodes strongly in Alpha -> dominant=Alpha, intensity > 0.5."""
    memberships = np.array([
        [0.8, 0.1, 0.0, 0.1],
        [0.7, 0.1, 0.1, 0.1],
        [0.9, 0.0, 0.0, 0.1],
        [0.6, 0.2, 0.1, 0.1],
    ])
    path = _make_npz(tmp_path, memberships)
    prop = load_propagation(path)

    info = compute_cluster_community(prop, ["0", "1", "2", "3"])

    assert info.dominant_name == "Alpha"
    assert info.dominant_color == "#ff0000"
    assert info.dominant_intensity > 0.5


# --- Peripheral cluster ---


def test_peripheral_cluster(tmp_path):
    """3 nodes mostly 'none' -> low intensity."""
    memberships = np.array([
        [0.05, 0.05, 0.05, 0.85],
        [0.03, 0.02, 0.05, 0.90],
        [0.10, 0.05, 0.00, 0.85],
    ])
    path = _make_npz(tmp_path, memberships)
    prop = load_propagation(path)

    info = compute_cluster_community(prop, ["0", "1", "2"])

    # Intensity should be low — these nodes are mostly "none"
    assert info.dominant_intensity < 0.3


# --- Mixed cluster ---


def test_mixed_cluster_has_secondary(tmp_path):
    """Mix of Alpha + Beta -> secondary exists."""
    memberships = np.array([
        [0.5, 0.3, 0.1, 0.1],
        [0.4, 0.4, 0.1, 0.1],
        [0.6, 0.2, 0.1, 0.1],
    ])
    path = _make_npz(tmp_path, memberships)
    prop = load_propagation(path)

    info = compute_cluster_community(prop, ["0", "1", "2"])

    assert info.dominant_name == "Alpha"
    assert info.secondary_name == "Beta"
    assert info.secondary_color == "#00ff00"
    assert info.secondary_intensity > 0.1


# --- Unknown member IDs ---


def test_unknown_member_ids_skipped(tmp_path):
    """Unknown IDs are gracefully skipped, known IDs still counted."""
    memberships = np.array([
        [0.8, 0.1, 0.0, 0.1],
        [0.7, 0.2, 0.0, 0.1],
    ])
    path = _make_npz(tmp_path, memberships)
    prop = load_propagation(path)

    # "unknown_99" doesn't exist in node_ids
    info = compute_cluster_community(prop, ["0", "unknown_99", "1"])

    assert info.dominant_name == "Alpha"
    assert info.dominant_intensity > 0.5


# --- Empty members ---


def test_empty_members_returns_gray(tmp_path):
    """Empty member list -> null color, 0 intensity."""
    memberships = np.array([[0.5, 0.3, 0.1, 0.1]])
    path = _make_npz(tmp_path, memberships)
    prop = load_propagation(path)

    info = compute_cluster_community(prop, [])

    assert info.dominant_color is None
    assert info.dominant_name is None
    assert info.dominant_intensity == 0.0
    assert info.breakdown == []


# --- Breakdown structure ---


def test_breakdown_sorted_by_weight(tmp_path):
    """Breakdown should be sorted descending by weight, excluding 'none'."""
    memberships = np.array([
        [0.2, 0.5, 0.2, 0.1],
        [0.1, 0.6, 0.2, 0.1],
    ])
    path = _make_npz(tmp_path, memberships)
    prop = load_propagation(path)

    info = compute_cluster_community(prop, ["0", "1"])

    assert len(info.breakdown) > 0
    # First entry has highest weight
    assert info.breakdown[0]["name"] == "Beta"
    # Weights are descending
    weights = [b["weight"] for b in info.breakdown]
    assert weights == sorted(weights, reverse=True)
