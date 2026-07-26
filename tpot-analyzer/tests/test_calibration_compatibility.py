from __future__ import annotations

import json

import numpy as np

from src.artifacts.provenance import (
    CalibrationCompatibilityError,
    validate_calibration_compatibility,
)
from tests.artifact_provenance_fixtures import (
    build_test_provenance,
    calibration_method_record,
)


def test_accepts_legacy_calibration_for_runtime_count_revalidation(tmp_path):
    provenance, _ = build_test_provenance(tmp_path)
    status = validate_calibration_compatibility(
        {
            "tau": 0.05,
            "calibrated": True,
            "n_nodes_total": 2,
            "n_core": 1,
            "n_halo": 1,
            "n_total": 2,
        },
        provenance,
    )
    assert status == "legacy-runtime-validation-required"


def test_accepts_compatibility_record_bound_calibration(tmp_path):
    provenance, _ = build_test_provenance(tmp_path)
    status = validate_calibration_compatibility(
        {
            "tau": 0.05,
            "calibrated": True,
            "n_nodes_total": 2,
            "n_core": 1,
            "n_halo": 1,
            "n_total": 2,
            "artifact_provenance": provenance,
            "calibration_method": calibration_method_record(),
        },
        provenance,
    )
    assert status == "compatibility-record-bound"


def test_rejects_bound_calibration_without_valid_method_record(tmp_path):
    provenance, _ = build_test_provenance(tmp_path)
    calibration = {
        "tau": 0.05,
        "calibrated": True,
        "n_nodes_total": 2,
        "n_core": 1,
        "n_halo": 1,
        "n_total": 2,
        "artifact_provenance": provenance,
    }
    with np.testing.assert_raises_regex(
        CalibrationCompatibilityError,
        "calibration_method",
    ):
        validate_calibration_compatibility(calibration, provenance)

    calibration["calibration_method"] = {
        **calibration_method_record(),
        "objective": "classification_f1",
    }
    with np.testing.assert_raises_regex(
        CalibrationCompatibilityError,
        "objective",
    ):
        validate_calibration_compatibility(calibration, provenance)


def test_rejects_calibration_node_or_artifact_mismatch(tmp_path):
    provenance, _ = build_test_provenance(tmp_path)
    with np.testing.assert_raises_regex(
        CalibrationCompatibilityError,
        "n_nodes_total=3.*current graph has 2",
    ):
        validate_calibration_compatibility(
            {
                "tau": 0.05,
                "calibrated": True,
                "n_nodes_total": 3,
                "n_core": 1,
                "n_halo": 1,
                "n_total": 2,
            },
            provenance,
        )

    stale = json.loads(json.dumps(provenance))
    stale["graph"]["structure_sha256"] = "x" * 64
    with np.testing.assert_raises_regex(
        CalibrationCompatibilityError,
        "graph.structure_sha256",
    ):
        validate_calibration_compatibility(
            {
                "tau": 0.05,
                "calibrated": True,
                "n_nodes_total": 2,
                "n_core": 1,
                "n_halo": 1,
                "n_total": 2,
                "artifact_provenance": stale,
                "calibration_method": calibration_method_record(),
            },
            provenance,
        )


def test_rejects_missing_or_contradictory_saved_selection_counts(tmp_path):
    provenance, _ = build_test_provenance(tmp_path)
    with np.testing.assert_raises_regex(
        CalibrationCompatibilityError,
        "missing required count n_halo",
    ):
        validate_calibration_compatibility(
            {
                "tau": 0.05,
                "calibrated": True,
                "n_nodes_total": 2,
                "n_core": 1,
                "n_total": 2,
            },
            provenance,
        )
    with np.testing.assert_raises_regex(
        CalibrationCompatibilityError,
        r"n_core \+ n_halo.*n_total",
    ):
        validate_calibration_compatibility(
            {
                "tau": 0.05,
                "calibrated": True,
                "n_nodes_total": 2,
                "n_core": 1,
                "n_halo": 1,
                "n_total": 1,
            },
            provenance,
        )


def test_rejects_uncalibrated_default_threshold(tmp_path):
    provenance, _ = build_test_provenance(tmp_path)
    with np.testing.assert_raises_regex(
        CalibrationCompatibilityError,
        "calibrated=true",
    ):
        validate_calibration_compatibility(
            {
                "tau": 0.05,
                "calibrated": False,
                "n_nodes_total": 2,
                "n_core": 1,
                "n_halo": 1,
                "n_total": 2,
            },
            provenance,
        )
