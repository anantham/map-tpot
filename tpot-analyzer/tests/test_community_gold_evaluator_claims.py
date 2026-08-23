"""Construct-validity checks for legacy diagnostic claim metadata."""
from __future__ import annotations

from src.data.community_gold.evaluation_reporting import (
    evaluate_method_result,
)


def test_development_support_alone_never_authorizes_calibration() -> None:
    train_in = ["train-in"]
    train_out = ["train-out"]
    dev_in = [f"dev-in-{index}" for index in range(20)]
    dev_out = [f"dev-out-{index}" for index in range(20)]
    all_ids = train_in + train_out + dev_in + dev_out
    scores = {
        account_id: (
            0.9
            if account_id in set(train_in + dev_in)
            else 0.1
        )
        for account_id in all_ids
    }
    community = {
        "labels": {
            "train": {
                "in": train_in,
                "out": train_out,
                "abstain": [],
            },
            "dev": {
                "in": dev_in,
                "out": dev_out,
                "abstain": [],
            },
        }
    }

    result = evaluate_method_result(
        score_result={"available": True, "scores": scores},
        community=community,
        train_split="train",
        eval_split="dev",
    )

    assert result["available"] is True
    assert result["developmentClassSupportMet"] is True
    assert result["calibrationEligible"] is False
    assert result["probabilityMetricsAvailable"] is False
    assert result["metrics"]["brier"] is None
    assert result["metrics"]["ece"] is None
