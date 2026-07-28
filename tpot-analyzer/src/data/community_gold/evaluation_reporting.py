"""Honest coverage and claim metadata for legacy train-to-dev diagnostics."""
from __future__ import annotations

from typing import Any, Dict

import numpy as np

from .metrics import summarize_binary_metrics, tune_threshold

MIN_DEVELOPMENT_CLASS_SUPPORT = 20
DIAGNOSTIC_METRICS_INTERPRETATION = "diagnostic_only_not_calibrated"


def _coverage(
    *,
    expected_ids: list[str],
    scores: Dict[str, float],
) -> tuple[list[str], Dict[str, Any]]:
    scored = [
        account_id
        for account_id in expected_ids
        if account_id in scores and np.isfinite(float(scores[account_id]))
    ]
    missing = [
        account_id
        for account_id in expected_ids
        if account_id not in scored
    ]
    return scored, {
        "expectedCount": len(expected_ids),
        "scoredCount": len(scored),
        "missingCount": len(missing),
        "coverageRate": (
            len(scored) / len(expected_ids)
            if expected_ids
            else None
        ),
        "missingAccountSample": missing[:10],
    }


def _claim_metadata(
    *,
    community: Dict[str, Any],
    eval_split: str,
) -> Dict[str, Any]:
    in_count = len(community["labels"][eval_split]["in"])
    out_count = len(community["labels"][eval_split]["out"])
    support_met = (
        in_count >= MIN_DEVELOPMENT_CLASS_SUPPORT
        and out_count >= MIN_DEVELOPMENT_CLASS_SUPPORT
    )
    return {
        "developmentClassSupportMet": support_met,
        "calibrationEligible": False,
        "calibrationReason": (
            "legacy development support alone cannot authorize calibration; "
            "a registered calibration protocol and untouched terminal-test "
            "support are required"
        ),
        "calibrated": False,
        "probabilityMetricsAvailable": False,
        "probabilityMetricsReason": (
            "Brier score and calibration error require registered calibrated "
            "probabilities; these scores are uncalibrated diagnostics"
        ),
        "metricsInterpretation": DIAGNOSTIC_METRICS_INTERPRETATION,
    }


def evaluate_method_result(
    *,
    score_result: Dict[str, Any],
    community: Dict[str, Any],
    train_split: str,
    eval_split: str,
) -> Dict[str, Any]:
    method_metadata = {
        key: value
        for key, value in score_result.items()
        if key not in {"available", "scores"}
    }
    claims = _claim_metadata(
        community=community,
        eval_split=eval_split,
    )
    train_ids = (
        community["labels"][train_split]["in"]
        + community["labels"][train_split]["out"]
    )
    eval_ids = (
        community["labels"][eval_split]["in"]
        + community["labels"][eval_split]["out"]
    )
    if not score_result.get("available"):
        return {
            **method_metadata,
            "available": False,
            **claims,
            "predictionCoverage": {
                train_split: {
                    "expectedCount": len(train_ids),
                    "scoredCount": 0,
                    "missingCount": len(train_ids),
                    "coverageRate": 0.0 if train_ids else None,
                    "missingAccountSample": train_ids[:10],
                },
                eval_split: {
                    "expectedCount": len(eval_ids),
                    "scoredCount": 0,
                    "missingCount": len(eval_ids),
                    "coverageRate": 0.0 if eval_ids else None,
                    "missingAccountSample": eval_ids[:10],
                },
            },
        }

    scores = {
        str(account_id): float(score)
        for account_id, score in score_result["scores"].items()
    }
    scored_train, train_coverage = _coverage(
        expected_ids=train_ids,
        scores=scores,
    )
    scored_eval, eval_coverage = _coverage(
        expected_ids=eval_ids,
        scores=scores,
    )
    prediction_coverage = {
        train_split: train_coverage,
        eval_split: eval_coverage,
    }
    train_positive = set(community["labels"][train_split]["in"])
    train_labels = np.asarray(
        [1 if account_id in train_positive else 0 for account_id in scored_train],
        dtype=np.int64,
    )
    train_scores = np.asarray(
        [scores[account_id] for account_id in scored_train],
        dtype=np.float64,
    )
    if train_labels.size == 0 or len(np.unique(train_labels)) < 2:
        return {
            **method_metadata,
            **claims,
            "available": False,
            "reason": (
                "need scored positive and negative train labels; missing "
                "method output remains unknown rather than score zero"
            ),
            "predictionCoverage": prediction_coverage,
        }
    threshold, threshold_source = tune_threshold(
        train_labels,
        train_scores,
    )

    eval_positive = set(community["labels"][eval_split]["in"])
    eval_labels = np.asarray(
        [1 if account_id in eval_positive else 0 for account_id in scored_eval],
        dtype=np.int64,
    )
    eval_scores = np.asarray(
        [scores[account_id] for account_id in scored_eval],
        dtype=np.float64,
    )
    if eval_labels.size == 0 or len(np.unique(eval_labels)) < 2:
        return {
            **method_metadata,
            **claims,
            "available": False,
            "reason": (
                "need scored positive and negative eval labels; missing "
                "method output remains unknown rather than score zero"
            ),
            "threshold": threshold,
            "thresholdSource": threshold_source,
            "predictionCoverage": prediction_coverage,
        }
    return {
        **method_metadata,
        **claims,
        "available": True,
        "threshold": threshold,
        "thresholdSource": threshold_source,
        "trainSampleCount": int(train_labels.size),
        "evalSampleCount": int(eval_labels.size),
        "predictionCoverage": prediction_coverage,
        "metrics": summarize_binary_metrics(
            labels=eval_labels,
            scores=eval_scores,
            threshold=threshold,
            include_probability_metrics=False,
        ),
    }
