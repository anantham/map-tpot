from __future__ import annotations

from collections import Counter

import numpy as np
import pytest
from scipy.cluster.hierarchy import fcluster, linkage

from src.graph.hierarchy.focus import reveal_leaf_in_visible_set
from src.graph.hierarchy.traversal import find_cluster_leaders


@pytest.mark.unit
def test_reveal_leaf_in_visible_set_splits_path_within_budget() -> None:
    rng = np.random.default_rng(0)
    points = rng.normal(size=(6, 2))
    linkage_matrix = linkage(points, method="ward")
    n_leaves = points.shape[0]

    # fcluster() may return fewer than t clusters if there are distance ties.
    labels = fcluster(linkage_matrix, t=5, criterion="maxclust")
    counts = Counter(int(v) for v in labels)
    multi_label = next(label for label, count in counts.items() if count > 1)
    leaf_idx = int(np.where(labels == multi_label)[0][0])

    leader_map = find_cluster_leaders(linkage_matrix, labels, n_leaves)
    visible_nodes = set(leader_map.values())
    base_visible = len(visible_nodes)
    assert leaf_idx not in visible_nodes  # leaf is inside a merged base cluster

    result = reveal_leaf_in_visible_set(
        visible_nodes=visible_nodes,
        linkage_matrix=linkage_matrix,
        leaf_idx=leaf_idx,
        n_leaves=n_leaves,
        budget=base_visible + 1,
    )

    assert result.ok is True
    assert leaf_idx in visible_nodes
    assert len(visible_nodes) <= base_visible + 1
    assert result.steps >= 1


@pytest.mark.unit
def test_reveal_leaf_in_visible_set_respects_budget() -> None:
    rng = np.random.default_rng(1)
    points = rng.normal(size=(6, 2))
    linkage_matrix = linkage(points, method="ward")
    n_leaves = points.shape[0]

    labels = fcluster(linkage_matrix, t=5, criterion="maxclust")
    counts = Counter(int(v) for v in labels)
    multi_label = next(label for label, count in counts.items() if count > 1)
    leaf_idx = int(np.where(labels == multi_label)[0][0])

    leader_map = find_cluster_leaders(linkage_matrix, labels, n_leaves)
    visible_nodes = set(leader_map.values())
    before = set(visible_nodes)
    base_visible = len(visible_nodes)

    result = reveal_leaf_in_visible_set(
        visible_nodes=visible_nodes,
        linkage_matrix=linkage_matrix,
        leaf_idx=leaf_idx,
        n_leaves=n_leaves,
        budget=base_visible,  # no headroom
    )

    assert result.ok is False
    assert result.reason == "budget_exhausted"
    assert visible_nodes == before
    assert leaf_idx not in visible_nodes


@pytest.mark.unit
def test_reveal_leaf_in_visible_set_requires_container() -> None:
    rng = np.random.default_rng(2)
    points = rng.normal(size=(4, 2))
    linkage_matrix = linkage(points, method="ward")
    n_leaves = points.shape[0]

    visible_nodes = {0}  # leaf 0 only
    result = reveal_leaf_in_visible_set(
        visible_nodes=visible_nodes,
        linkage_matrix=linkage_matrix,
        leaf_idx=1,
        n_leaves=n_leaves,
        budget=10,
    )

    assert result.ok is False
    assert result.reason == "leaf_not_in_visible_subtrees"
