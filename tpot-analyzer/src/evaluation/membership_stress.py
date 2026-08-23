"""Taxonomy and edge-loss interventions for membership evaluation."""
from __future__ import annotations

import numpy as np
from scipy import sparse

from src.evaluation.membership_scoring import jaccard
from src.graph.tpot_relevance import (
    build_core_halo_mask,
    compute_relevance,
    compute_symmetrized_degree_stats,
)


RANDOM_SEED = 20260726
EDGE_FRACTIONS = (0.01, 0.05, 0.10)
EDGE_JACCARD_FLOORS = {0.01: 0.95, 0.05: 0.90, 0.10: 0.85}


def relevance_scores(
    arrays: dict,
    adjacency: sparse.csr_matrix,
) -> tuple[np.ndarray, float]:
    _, degrees, median_degree = compute_symmetrized_degree_stats(adjacency)
    scores = compute_relevance(
        arrays["memberships"],
        arrays["uncertainty"],
        arrays["converged"],
        degrees,
        median_degree,
    )
    return scores, median_degree


def split_all(arrays: dict) -> tuple[np.ndarray, np.ndarray]:
    """Duplicate every community into information-equivalent equal halves."""
    memberships = np.asarray(arrays["memberships"], dtype=np.float64)
    converged = np.asarray(arrays["converged"], dtype=bool)
    communities = memberships[:, :-1]
    split = np.stack(
        [communities / 2.0, communities / 2.0],
        axis=2,
    ).reshape(len(communities), -1)
    paired = np.column_stack([converged[:-1], converged[:-1]])
    return (
        np.c_[split, memberships[:, -1]],
        np.r_[paired.ravel(), converged[-1]],
    )


def measure_edge_loss(
    arrays: dict,
    adjacency: sparse.csr_matrix,
    tau: float,
    baseline_selected: np.ndarray,
    holdout_indices: np.ndarray,
    repetitions: int,
) -> dict:
    """Delete stored edges while holding propagated memberships fixed."""
    rng = np.random.RandomState(RANDOM_SEED)
    results = {}
    for fraction in EDGE_FRACTIONS:
        observations = []
        for _ in range(repetitions):
            perturbed = adjacency.copy()
            n_drop = int(round(fraction * perturbed.nnz))
            drop = rng.choice(perturbed.nnz, size=n_drop, replace=False)
            perturbed.data[drop] = 0
            perturbed.eliminate_zeros()
            scores, _ = relevance_scores(arrays, perturbed)
            core = scores >= tau
            selected = build_core_halo_mask(scores, perturbed, tau)
            observations.append(
                {
                    "core": int(np.count_nonzero(core)),
                    "selected": int(np.count_nonzero(selected)),
                    "selected_jaccard": jaccard(selected, baseline_selected),
                    "holdout": int(
                        np.count_nonzero(selected[holdout_indices])
                    ),
                }
            )
        key = f"{fraction:.2f}"
        jaccards = [row["selected_jaccard"] for row in observations]
        results[key] = {
            "fraction": fraction,
            "repetitions": repetitions,
            "dropped_entries": int(round(fraction * adjacency.nnz)),
            "jaccard_floor": EDGE_JACCARD_FLOORS[fraction],
            "min_selected_jaccard": float(min(jaccards)),
            "mean_selected_jaccard": float(np.mean(jaccards)),
            "core_count_range": [
                min(row["core"] for row in observations),
                max(row["core"] for row in observations),
            ],
            "selected_count_range": [
                min(row["selected"] for row in observations),
                max(row["selected"] for row in observations),
            ],
            "holdout_selected_range": [
                min(row["holdout"] for row in observations),
                max(row["holdout"] for row in observations),
            ],
        }
    return results
