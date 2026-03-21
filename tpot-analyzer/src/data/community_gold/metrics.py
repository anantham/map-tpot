"""Metric helpers for account-community evaluation."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple

import numpy as np
from sklearn.metrics import average_precision_score


def brier_score(labels: np.ndarray, scores: np.ndarray) -> float:
    return float(np.mean((scores - labels) ** 2))


def expected_calibration_error(labels: np.ndarray, scores: np.ndarray, *, n_bins: int = 10) -> float:
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = max(1, len(labels))
    for start, end in zip(bins[:-1], bins[1:]):
        if end >= 1.0:
            mask = (scores >= start) & (scores <= end)
        else:
            mask = (scores >= start) & (scores < end)
        if not np.any(mask):
            continue
        bucket_scores = scores[mask]
        bucket_labels = labels[mask]
        confidence = float(np.mean(bucket_scores))
        accuracy = float(np.mean(bucket_labels))
        ece += abs(confidence - accuracy) * (len(bucket_scores) / n)
    return float(ece)


def precision_recall_f1(labels: np.ndarray, scores: np.ndarray, threshold: float) -> Tuple[float, float, float]:
    predicted = scores >= threshold
    tp = int(np.sum((predicted == 1) & (labels == 1)))
    fp = int(np.sum((predicted == 1) & (labels == 0)))
    fn = int(np.sum((predicted == 0) & (labels == 1)))
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    if precision + recall == 0:
        return precision, recall, 0.0
    return precision, recall, 2.0 * precision * recall / (precision + recall)


def tune_threshold(labels: np.ndarray, scores: np.ndarray) -> Tuple[float, str]:
    unique_scores = sorted({0.0, 0.5, 1.0, *[float(v) for v in scores.tolist()]})
    if labels.size == 0 or len(np.unique(labels)) < 2:
        return 0.5, "default_insufficient_train_labels"

    best_threshold = 0.5
    best_f1 = -1.0
    for threshold in unique_scores:
        _, _, f1 = precision_recall_f1(labels, scores, float(threshold))
        if f1 > best_f1 or (f1 == best_f1 and abs(threshold - 0.5) < abs(best_threshold - 0.5)):
            best_threshold = float(threshold)
            best_f1 = float(f1)
    return best_threshold, "train_max_f1"


def summarize_binary_metrics(
    *,
    labels: np.ndarray,
    scores: np.ndarray,
    threshold: float,
) -> Dict[str, Any]:
    precision, recall, f1 = precision_recall_f1(labels, scores, threshold)
    return {
        "aucPr": float(average_precision_score(labels, scores)),
        "brier": brier_score(labels, scores),
        "ece": expected_calibration_error(labels, scores),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "threshold": float(threshold),
    }


def macro_average(rows: Iterable[Dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    if not values:
        return None
    return float(np.mean(values))
