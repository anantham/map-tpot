"""Helpers for focusing a hierarchical view on a specific leaf cluster."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Set

import numpy as np

from src.graph.hierarchy.traversal import get_children, is_descendant, subtree_size


@dataclass(frozen=True)
class RevealLeafResult:
    ok: bool
    steps: int
    reason: Optional[str] = None
    container_before: Optional[int] = None
    container_after: Optional[int] = None


def reveal_leaf_in_visible_set(
    *,
    visible_nodes: Set[int],
    linkage_matrix: np.ndarray,
    leaf_idx: int,
    n_leaves: int,
    budget: int,
) -> RevealLeafResult:
    """Ensure `leaf_idx` is visible by splitting its visible ancestor along the path.

    This is a deterministic, path-directed split (unlike the greedy expansion logic).

    Returns a result describing whether the leaf ended up visible.
    """
    if leaf_idx in visible_nodes:
        return RevealLeafResult(ok=True, steps=0, container_before=leaf_idx, container_after=leaf_idx)

    subtree_cache: dict[int, int] = {}
    containers = [n for n in visible_nodes if is_descendant(linkage_matrix, leaf_idx, n, n_leaves)]
    if not containers:
        return RevealLeafResult(ok=False, steps=0, reason="leaf_not_in_visible_subtrees")

    # Prefer the smallest visible subtree that still contains the leaf (deepest container).
    container = min(containers, key=lambda n: subtree_size(linkage_matrix, n, n_leaves, subtree_cache))
    container_before = container
    steps = 0

    while container != leaf_idx:
        if len(visible_nodes) + 1 > budget:
            return RevealLeafResult(
                ok=False,
                steps=steps,
                reason="budget_exhausted",
                container_before=container_before,
                container_after=container,
            )

        children = get_children(linkage_matrix, container, n_leaves)
        if not children:
            return RevealLeafResult(
                ok=False,
                steps=steps,
                reason="container_has_no_children",
                container_before=container_before,
                container_after=container,
            )

        left, right = children
        if is_descendant(linkage_matrix, leaf_idx, left, n_leaves):
            next_container = left
        else:
            next_container = right

        visible_nodes.discard(container)
        visible_nodes.add(left)
        visible_nodes.add(right)
        container = next_container
        steps += 1

    return RevealLeafResult(
        ok=True,
        steps=steps,
        container_before=container_before,
        container_after=container,
    )

