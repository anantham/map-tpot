"""Scoring helpers for account-community review queue candidates."""
from __future__ import annotations

import math
from typing import Dict, List

QUEUE_ENTROPY_WEIGHT = 0.7
QUEUE_DISAGREEMENT_WEIGHT = 0.3


def binary_entropy(probability: float) -> float:
    p = min(max(float(probability), 1e-9), 1.0 - 1e-9)
    return float((-(p * math.log2(p)) - ((1.0 - p) * math.log2(1.0 - p))))


def mean_pairwise_distance(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    distances: List[float] = []
    for index, left in enumerate(values):
        for right in values[index + 1:]:
            distances.append(abs(left - right))
    return float(sum(distances) / len(distances)) if distances else 0.0


def summarize_queue_scores(method_scores: Dict[str, float]) -> Dict[str, float]:
    values = list(method_scores.values())
    mean_score = float(sum(values) / len(values)) if values else 0.0
    uncertainty = binary_entropy(mean_score)
    disagreement = mean_pairwise_distance(values)
    return {
        "meanScore": mean_score,
        "uncertainty": uncertainty,
        "disagreement": disagreement,
        "queueScore": (QUEUE_ENTROPY_WEIGHT * uncertainty) + (QUEUE_DISAGREEMENT_WEIGHT * disagreement),
    }
