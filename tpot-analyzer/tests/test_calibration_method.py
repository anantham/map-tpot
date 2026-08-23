from __future__ import annotations

import numpy as np
import pytest

from src.artifacts.calibration_method import (
    CalibrationMethodError,
    select_best_feasible_result,
    validate_holdout_split,
)
from src.artifacts.calibration_record import (
    CalibrationRecordError,
    build_calibration_method_record,
    validate_calibration_code_files,
    validate_calibration_method_record,
)
from src.artifacts.digests import file_sha256


def _holdout(accounts=("a", "c"), n_train=1):
    return {
        "holdout_fraction": 0.2,
        "holdout_seed": 42,
        "n_holdout": len(accounts),
        "n_train": n_train,
        "accounts": {account: {} for account in accounts},
    }


def test_resolves_complete_unlabeled_holdout_split():
    indices = validate_holdout_split(
        _holdout(),
        {"a": 0, "b": 1, "c": 2},
        np.array([False, True, False]),
    )

    assert indices == [0, 2]


def test_rejects_holdout_count_resolution_or_leakage_errors():
    wrong_count = _holdout()
    wrong_count["n_holdout"] = 3
    with pytest.raises(CalibrationMethodError, match="n_holdout=3.*accounts=2"):
        validate_holdout_split(
            wrong_count,
            {"a": 0, "c": 2},
            np.array([False, False, False]),
        )

    with pytest.raises(CalibrationMethodError, match="unresolved.*c"):
        validate_holdout_split(
            _holdout(),
            {"a": 0},
            np.array([False]),
        )

    with pytest.raises(CalibrationMethodError, match="leakage.*a"):
        validate_holdout_split(
            _holdout(),
            {"a": 0, "c": 2},
            np.array([True, False, False]),
        )

    with pytest.raises(CalibrationMethodError, match="must be boolean"):
        validate_holdout_split(
            _holdout(),
            {"a": 0, "c": 2},
            np.array([0, 1, 0]),
        )

    with pytest.raises(CalibrationMethodError, match="n_train=2.*1 labeled"):
        validate_holdout_split(
            _holdout(n_train=2),
            {"a": 0, "c": 2},
            np.array([False, True, False]),
        )


def test_selects_best_feasible_recall_compactness_utility():
    results = [
        {"tau": 0.01, "recall": 0.9, "objective_score": 0.7},
        {"tau": 0.02, "recall": 0.85, "objective_score": 0.8},
        {"tau": 0.03, "recall": 0.8, "objective_score": 0.99},
    ]

    best = select_best_feasible_result(results, recall_floor=0.85)

    assert best["tau"] == 0.02


def test_rejects_infeasible_recall_floor():
    with pytest.raises(CalibrationMethodError, match="No threshold meets"):
        select_best_feasible_result(
            [{"tau": 0.1, "recall": 0.5, "objective_score": 0.8}],
            recall_floor=0.85,
        )


def test_builds_calibration_method_record_with_input_hashes(tmp_path):
    holdout_path = tmp_path / "holdout.json"
    holdout_path.write_text("{}")
    scorer_path = tmp_path / "scorer.py"
    scorer_path.write_text("score = 1")

    record = build_calibration_method_record(
        recall_floor=0.85,
        tau_min=0.01,
        tau_max=0.2,
        tau_steps=20,
        holdout=_holdout(),
        holdout_path=holdout_path,
        code_files={
            "relevance_scorer": scorer_path,
            "threshold_selector": scorer_path,
            "calibrator": scorer_path,
        },
    )

    assert record["name"] == "recall_compactness_harmonic_utility"
    assert record["objective"].startswith("harmonic_mean")
    assert record["holdout_file_sha256"] == file_sha256(holdout_path)
    assert record["code_files"]["relevance_scorer"]["sha256"] == file_sha256(
        scorer_path
    )
    validate_calibration_method_record(record)
    validate_calibration_code_files(
        record,
        {"relevance_scorer": scorer_path},
    )


def test_rejects_misnamed_or_incomplete_calibration_method_record(tmp_path):
    holdout_path = tmp_path / "holdout.json"
    holdout_path.write_text("{}")
    scorer_path = tmp_path / "scorer.py"
    scorer_path.write_text("score = 1")
    record = build_calibration_method_record(
        recall_floor=0.85,
        tau_min=0.01,
        tau_max=0.2,
        tau_steps=20,
        holdout=_holdout(),
        holdout_path=holdout_path,
        code_files={
            "relevance_scorer": scorer_path,
            "threshold_selector": scorer_path,
            "calibrator": scorer_path,
        },
    )

    with pytest.raises(CalibrationRecordError, match="objective"):
        validate_calibration_method_record(
            {**record, "objective": "classification_f1"}
        )

    with pytest.raises(CalibrationRecordError, match="code_files"):
        validate_calibration_method_record({**record, "code_files": {}})
