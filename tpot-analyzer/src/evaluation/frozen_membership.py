"""Falsifiable diagnostics for the certified frozen membership control."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from src.artifacts.frozen_control_verifier import verify_frozen_control
from src.artifacts.frozen_manifest import verify_frozen_manifest
from src.evaluation.membership_scoring import heldout_metrics, jaccard
from src.evaluation.membership_stress import (
    EDGE_FRACTIONS,
    EDGE_JACCARD_FLOORS,
    RANDOM_SEED,
    measure_edge_loss,
    relevance_scores,
    split_all,
)
from src.graph.tpot_relevance import (
    build_core_halo_mask,
)

def evaluate_control(control, holdout, *, edge_repetitions: int = 10) -> dict:
    """Evaluate preregistered claims against verified control evidence."""
    if edge_repetitions < 1:
        raise ValueError("edge_repetitions must be at least 1")
    arrays = control.propagation.arrays
    heldout, holdout_indices = heldout_metrics(
        arrays,
        control.node_ids,
        holdout,
    )
    scores, median_degree = relevance_scores(arrays, control.adjacency)
    core = scores >= control.tau
    selected = build_core_halo_mask(scores, control.adjacency, control.tau)
    heldout_core = core[holdout_indices]
    heldout_selected = selected[holdout_indices]

    split_memberships, split_converged = split_all(arrays)
    split_arrays = {
        **arrays,
        "memberships": split_memberships,
        "converged": split_converged,
    }
    split_scores, _ = relevance_scores(split_arrays, control.adjacency)
    split_core = split_scores >= control.tau
    split_selected = build_core_halo_mask(
        split_scores, control.adjacency, control.tau
    )
    core_count = int(np.count_nonzero(core))
    taxonomy = {
        "method": "split_each_community_into_two_equal_columns",
        "baseline_communities": int(arrays["memberships"].shape[1] - 1),
        "split_communities": int(split_memberships.shape[1] - 1),
        "baseline_core": core_count,
        "split_core": int(np.count_nonzero(split_core)),
        "core_jaccard": jaccard(core, split_core),
        "core_count_delta_fraction": float(
            abs(np.count_nonzero(split_core) - core_count)
            / max(core_count, 1)
        ),
        "baseline_selected": int(np.count_nonzero(selected)),
        "split_selected": int(np.count_nonzero(split_selected)),
        "selected_jaccard": jaccard(selected, split_selected),
    }
    edge_loss = measure_edge_loss(
        arrays,
        control.adjacency,
        control.tau,
        selected,
        holdout_indices,
        edge_repetitions,
    )
    recalled = int(np.count_nonzero(heldout_selected))
    core_fraction = float(np.count_nonzero(heldout_core) / recalled) if recalled else 0.0
    hypotheses = {
        "soft_target_predictive_agreement": {
            "passed": (
                heldout["model"]["brier"] < heldout["empirical_prior"]["brier"]
                and heldout["model"]["brier"] < heldout["uniform"]["brier"]
                and heldout["model"]["soft_log_loss"] <
                heldout["empirical_prior"]["soft_log_loss"]
                and heldout["model"]["soft_log_loss"] <
                heldout["uniform"]["soft_log_loss"]
            ),
            "falsifier": (
                "model must beat both empirical-prior and uniform Brier "
                "and soft-label log loss"
            ),
        },
        "dominant_class_confidence_calibration": {
            "passed": heldout["ece_5_equal_width"] <= 0.05,
            "falsifier": (
                "five-bin ECE of top-community confidence against hard "
                "dominant-class correctness must be <= 0.05"
            ),
        },
        "calibration_set_core_membership": {
            "passed": core_fraction >= 0.50,
            "falsifier": (
                "at least half of recalled propagation-heldout calibration "
                "accounts must be core"
            ),
        },
        "taxonomy_representation_invariance": {
            "passed": (taxonomy["core_jaccard"] >= 0.95 and
                       taxonomy["core_count_delta_fraction"] <= 0.05),
            "falsifier": (
                "equal split must keep core Jaccard >= 0.95 and "
                "absolute core-count change <= 5%"
            ),
        },
        "edge_loss_robustness": {
            "passed": all(row["min_selected_jaccard"] >= row["jaccard_floor"]
                          for row in edge_loss.values()),
            "falsifier": (
                "minimum selected Jaccard must remain >= 0.95/0.90/0.85 "
                "under 1%/5%/10% CSR-entry deletion"
            ),
        },
    }
    return {
        "method": {
            "random_seed": RANDOM_SEED,
            "stable_ties": "numpy.argsort(-scores, kind='stable')",
            "holdout_truth": "weights plus residual none mass, then normalized",
            "probability_scores": "multiclass Brier and soft-label log loss",
            "empirical_prior_scope": (
                "mean truth vector of this evaluation holdout; descriptive "
                "rather than a deployable fitted baseline"
            ),
            "confidence_calibration": (
                "top-1 confidence versus hard dominant-class correctness; "
                "ECE with 5 equal-width bins"
            ),
            "threshold_evaluation_scope": (
                "propagation-heldout accounts reused by the historical tau "
                "calibration; retrospective, not untouched generalization"
            ),
            "taxonomy_intervention": "split every community column equally in two",
            "edge_loss_sampling": (
                "memberships fixed; recompute degree/relevance/core/halo from "
                "a fresh baseline per repeat; sequential RNG; stored CSR "
                "entries sampled without replacement"
            ),
            "edge_fractions": list(EDGE_FRACTIONS),
            "edge_jaccard_floors": EDGE_JACCARD_FLOORS,
            "edge_repetitions": edge_repetitions,
        },
        "control": {
            "tau": float(control.tau),
            "node_count": int(len(control.node_ids)),
            "adjacency_nnz": int(control.adjacency.nnz),
            "median_degree": float(median_degree),
            "converged_classes": int(np.count_nonzero(arrays["converged"])),
            "total_classes": int(len(arrays["converged"])),
        },
        "heldout": heldout,
        "core_halo": {
            "core": core_count,
            "halo": int(np.count_nonzero(selected & ~core)),
            "total": int(np.count_nonzero(selected)),
            "holdout_core": int(np.count_nonzero(heldout_core)),
            "holdout_halo_only": int(np.count_nonzero(
                heldout_selected & ~heldout_core)),
            "holdout_missed": int(np.count_nonzero(~heldout_selected)),
            "holdout_core_fraction_of_recalled": core_fraction,
        },
        "taxonomy_split_all": taxonomy,
        "edge_loss": edge_loss,
        "hypotheses": hypotheses,
    }

def evaluate_frozen_membership(data_dir: Path, *, edge_repetitions: int = 10
                               ) -> dict:
    """Verify the manifest-selected control, then evaluate its assumptions."""
    data_dir = Path(data_dir)
    manifest = verify_frozen_manifest(data_dir)
    control = verify_frozen_control(
        data_dir, selected_propagation=manifest["selected_propagation"]
    )
    holdout = json.loads((data_dir / "tpot_holdout_seeds.json").read_text())
    result = evaluate_control(control, holdout,
                              edge_repetitions=edge_repetitions)
    result["bundle"] = {
        "bundle_id": manifest.get("bundle_id"),
        "selected_propagation": manifest["selected_propagation"],
    }
    return result

def strict_failures(result: dict) -> list[str]:
    """Return preregistered hypotheses falsified by the experiment."""
    return [name for name, record in result["hypotheses"].items()
            if not record["passed"]]
