"""Holdout scoring primitives for frozen soft-membership evaluation."""
from __future__ import annotations

import numpy as np

from src.artifacts.calibration_method import validate_holdout_split


def jaccard(left: np.ndarray, right: np.ndarray) -> float:
    union = np.count_nonzero(left | right)
    return float(np.count_nonzero(left & right) / union) if union else 1.0


def _probability_scores(
    predictions: np.ndarray,
    truth: np.ndarray,
) -> dict[str, float]:
    clipped = np.clip(predictions, 1e-15, 1.0)
    return {
        "brier": float(np.mean(np.sum((predictions - truth) ** 2, axis=1))),
        "soft_log_loss": float(
            np.mean(-np.sum(truth * np.log(clipped), axis=1))
        ),
    }


def _ece5(confidence: np.ndarray, correct: np.ndarray) -> float:
    result = 0.0
    edges = np.linspace(0.0, 1.0, 6)
    for lower, upper in zip(edges[:-1], edges[1:]):
        selected = (confidence >= lower) & (
            (confidence < upper) if upper < 1.0 else (confidence <= upper)
        )
        if np.any(selected):
            result += float(np.mean(selected)) * abs(
                float(np.mean(correct[selected]))
                - float(np.mean(confidence[selected]))
            )
    return result


def heldout_metrics(
    arrays: dict,
    node_ids: np.ndarray,
    holdout: dict,
) -> tuple[dict, np.ndarray]:
    """Measure discrimination and probability scores on a leakage-free holdout."""
    memberships = np.asarray(arrays["memberships"], dtype=np.float64)
    node_index = {str(value): index for index, value in enumerate(node_ids)}
    community_ids = [str(value) for value in arrays["community_ids"]]
    community_index = {
        value: index for index, value in enumerate(community_ids)
    }
    indices = np.asarray(
        validate_holdout_split(
            holdout,
            node_index,
            np.asarray(arrays["labeled_mask"]),
        ),
        dtype=np.int64,
    )
    predicted_full = memberships[indices]
    predicted_community = predicted_full[:, :-1]
    community_sums = predicted_community.sum(axis=1, keepdims=True)
    denominator = np.where(community_sums > 1e-12, community_sums, 1.0)
    conditional = predicted_community / denominator
    truth_full, hard_truth = [], []
    for record in holdout["accounts"].values():
        weights = np.asarray(record["weights"], dtype=np.float64)
        if weights.shape != (memberships.shape[1] - 1,):
            raise ValueError(
                "holdout weights do not match membership columns: "
                f"{weights.shape} vs {memberships.shape}"
            )
        if not np.all(np.isfinite(weights)) or np.any(weights < 0):
            raise ValueError("holdout weights must be finite and nonnegative")
        community_id = str(record["dominant_community_id"])
        if community_id not in community_index:
            raise ValueError(f"holdout community is absent: {community_id}")
        dominant_index = community_index[community_id]
        if weights[dominant_index] < float(weights.max()) - 1e-12:
            raise ValueError(
                "holdout weight order contradicts dominant community: "
                f"community={community_id}, index={dominant_index}"
            )
        vector = np.r_[weights, max(0.0, 1.0 - float(weights.sum()))]
        if vector.sum() <= 0:
            raise ValueError("holdout truth vector has no positive mass")
        truth_full.append(vector / vector.sum())
        hard_truth.append(dominant_index)
    truth_full = np.asarray(truth_full)
    hard_truth = np.asarray(hard_truth)

    orders = np.asarray(
        [np.argsort(-row, kind="stable") for row in conditional]
    )
    correct = orders[:, 0] == hard_truth
    top3 = np.asarray(
        [truth in order[:3] for truth, order in zip(hard_truth, orders)]
    )
    confidence = conditional.max(axis=1)
    prior = np.broadcast_to(truth_full.mean(axis=0), truth_full.shape)
    uniform = np.full(truth_full.shape, 1.0 / truth_full.shape[1])
    return {
        "n_holdout": int(len(indices)),
        "leaked_labels": 0,
        "zero_community_rows": int(np.count_nonzero(community_sums <= 1e-12)),
        "top1_correct": int(np.count_nonzero(correct)),
        "top1_accuracy": float(np.mean(correct)),
        "top3_correct": int(np.count_nonzero(top3)),
        "top3_accuracy": float(np.mean(top3)),
        "mean_top1_confidence": float(np.mean(confidence)),
        "ece_5_equal_width": _ece5(confidence, correct),
        "model": _probability_scores(predicted_full, truth_full),
        "empirical_prior": _probability_scores(prior, truth_full),
        "uniform": _probability_scores(uniform, truth_full),
    }, indices
