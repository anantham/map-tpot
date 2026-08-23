from __future__ import annotations

import json

import numpy as np
import pytest
from scipy import sparse

from src.artifacts.calibration_output import save_calibration_outputs


def _method_record():
    return {
        "name": "recall_compactness_harmonic_utility",
        "objective": (
            "harmonic_mean(holdout_positive_recall,"
            "one_minus_selected_graph_fraction)"
        ),
        "recall_floor": 0.85,
        "tau_min": 0.001,
        "tau_max": 0.5,
        "tau_steps": 100,
        "holdout_file": "holdout.json",
        "holdout_file_sha256": "a" * 64,
        "holdout_fraction": 0.2,
        "holdout_seed": 42,
        "n_holdout": 2,
        "n_train": 8,
        "code_files": {
            "relevance_scorer": {
                "file": "scorer.py",
                "sha256": "b" * 64,
            },
            "threshold_selector": {
                "file": "selector.py",
                "sha256": "c" * 64,
            },
            "calibrator": {
                "file": "calibrator.py",
                "sha256": "d" * 64,
            },
        },
    }


def test_saves_new_calibration_generation_without_clobber(tmp_path):
    record = save_calibration_outputs(
        tmp_path,
        np.array([0.7, 0.1]),
        sparse.csr_matrix((2, 2)),
        tau=0.5,
        artifact_provenance={"schema_version": 1},
        calibration_method=_method_record(),
        results=[{"tau": 0.5}],
    )

    assert record["calibrated"] is True
    assert record["n_nodes_total"] == 2
    assert record["n_core"] == 1
    assert record["n_halo"] == 0
    assert record["n_total"] == 1
    assert json.loads((tmp_path / "tpot_calibration.json").read_text()) == record
    np.testing.assert_allclose(
        np.load(tmp_path / "tpot_relevance_scores.npy"),
        np.array([0.7, 0.1], dtype=np.float32),
    )

    with pytest.raises(FileExistsError, match="Refusing to replace"):
        save_calibration_outputs(
            tmp_path,
            np.array([0.7, 0.1]),
            sparse.csr_matrix((2, 2)),
            tau=0.5,
            artifact_provenance={"schema_version": 1},
            calibration_method=_method_record(),
        )
