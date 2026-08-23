from __future__ import annotations

import json

import pytest

from src.artifacts.tpot_calibration import load_bound_threshold


def test_returns_explicit_threshold_without_calibration_file(tmp_path):
    result = load_bound_threshold(
        tmp_path,
        explicit_tau=0.2,
        calibration_path=None,
        provenance={},
        relevance_scorer_path=tmp_path / "unused.py",
    )

    assert result.tau == 0.2
    assert result.calibration is None
    assert result.record["status"] == "explicit-override"


def test_loads_legacy_threshold_for_runtime_validation(tmp_path):
    calibration_path = tmp_path / "tpot_calibration.json"
    calibration_path.write_text(
        json.dumps(
            {
                "tau": 0.1,
                "calibrated": True,
                "n_nodes_total": 2,
                "n_core": 1,
                "n_halo": 1,
                "n_total": 2,
            }
        )
    )
    provenance = {"graph": {"node_count": 2}}

    result = load_bound_threshold(
        tmp_path,
        explicit_tau=None,
        calibration_path=None,
        provenance=provenance,
        relevance_scorer_path=tmp_path / "unused.py",
    )

    assert result.tau == 0.1
    assert result.record["status"] == "legacy-runtime-validation-required"


def test_rejects_absent_default_calibration(tmp_path):
    with pytest.raises(FileNotFoundError, match="No calibration found"):
        load_bound_threshold(
            tmp_path,
            explicit_tau=None,
            calibration_path=None,
            provenance={},
            relevance_scorer_path=tmp_path / "unused.py",
        )
