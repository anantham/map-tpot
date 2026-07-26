"""Behavioral tests for the frozen soft-membership experiment."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from scripts import evaluate_frozen_membership as verifier
from src.evaluation import frozen_membership as evaluator


def _fixture():
    node_ids = np.asarray(["a", "b", "c", "d", "e", "f"])
    memberships = np.asarray(
        [
            [0.80, 0.10, 0.05, 0.05],
            [0.05, 0.80, 0.10, 0.05],
            [0.00, 0.00, 0.00, 1.00],
            [0.55, 0.25, 0.10, 0.10],
            [0.10, 0.55, 0.25, 0.10],
            [0.20, 0.20, 0.20, 0.40],
        ],
        dtype=np.float64,
    )
    arrays = {
        "memberships": memberships,
        "uncertainty": np.zeros(len(node_ids), dtype=np.float64),
        "converged": np.ones(4, dtype=bool),
        "labeled_mask": np.asarray([True, True, False, False, False, False]),
        "community_ids": np.asarray(["c0", "c1", "c2"]),
    }
    rows = np.asarray([0, 1, 1, 2, 2, 3, 3, 4, 4, 5])
    columns = np.asarray([1, 0, 2, 1, 3, 2, 4, 3, 5, 4])
    adjacency = sparse.csr_matrix(
        (np.ones(len(rows)), (rows, columns)), shape=(6, 6)
    )
    control = SimpleNamespace(
        node_ids=node_ids,
        adjacency=adjacency,
        propagation=SimpleNamespace(arrays=arrays),
        tau=0.01,
    )
    holdout = {
        "n_holdout": 2,
        "n_train": 2,
        "holdout_fraction": 0.5,
        "holdout_seed": 42,
        "accounts": {
            "c": {
                "dominant_community_id": "c0",
                "weights": [0.7, 0.2, 0.1],
            },
            "d": {
                "dominant_community_id": "c0",
                "weights": [0.6, 0.3, 0.1],
            },
        },
    }
    return control, holdout


def test_stable_tie_and_metrics_are_derived_from_controlled_inputs():
    control, holdout = _fixture()

    report = evaluator.evaluate_control(control, holdout, edge_repetitions=1)

    assert report["heldout"]["top1_correct"] == 2
    assert report["heldout"]["top3_correct"] == 2
    assert report["heldout"]["zero_community_rows"] == 1
    assert report["method"]["stable_ties"].endswith("kind='stable')")
    assert set(report["hypotheses"]) == {
        "soft_target_predictive_agreement",
        "dominant_class_confidence_calibration",
        "calibration_set_core_membership",
        "taxonomy_representation_invariance",
        "edge_loss_robustness",
    }


def test_edge_loss_is_deterministic_and_does_not_mutate_adjacency():
    control, holdout = _fixture()
    before = control.adjacency.copy()

    first = evaluator.evaluate_control(control, holdout, edge_repetitions=2)
    second = evaluator.evaluate_control(control, holdout, edge_repetitions=2)

    assert first["edge_loss"] == second["edge_loss"]
    assert (control.adjacency != before).nnz == 0


def test_holdout_leakage_is_rejected():
    control, holdout = _fixture()
    holdout["accounts"]["a"] = holdout["accounts"].pop("c")

    with pytest.raises(ValueError, match="holdout leakage"):
        evaluator.evaluate_control(control, holdout, edge_repetitions=1)


def test_invalid_soft_truth_weights_are_rejected():
    control, holdout = _fixture()
    holdout["accounts"]["c"]["weights"][0] = float("nan")

    with pytest.raises(ValueError, match="finite and nonnegative"):
        evaluator.evaluate_control(control, holdout, edge_repetitions=1)


def test_holdout_weight_order_must_match_dominant_community():
    control, holdout = _fixture()
    holdout["accounts"]["c"]["dominant_community_id"] = "c1"

    with pytest.raises(ValueError, match="weight order contradicts"):
        evaluator.evaluate_control(control, holdout, edge_repetitions=1)


def test_manifest_selects_the_propagation_artifact(monkeypatch, tmp_path):
    control, holdout = _fixture()
    selected = []
    monkeypatch.setattr(
        evaluator,
        "verify_frozen_manifest",
        lambda _: {
            "bundle_id": "fixture",
            "selected_propagation": "selected.npz",
        },
    )
    monkeypatch.setattr(
        evaluator,
        "verify_frozen_control",
        lambda _, *, selected_propagation: (
            selected.append(selected_propagation) or control
        ),
    )
    (tmp_path / "tpot_holdout_seeds.json").write_text(json.dumps(holdout))

    report = evaluator.evaluate_frozen_membership(
        tmp_path, edge_repetitions=1
    )

    assert selected == ["selected.npz"]
    assert report["bundle"]["selected_propagation"] == "selected.npz"


def test_json_result_is_no_clobber(tmp_path):
    control, holdout = _fixture()
    report = evaluator.evaluate_control(control, holdout, edge_repetitions=1)
    path = tmp_path / "results" / "membership.json"
    verifier.write_json_no_clobber(path, report)

    assert json.loads(path.read_text())["method"]["random_seed"] == 20260726
    with pytest.raises(FileExistsError):
        verifier.write_json_no_clobber(path, report)


def test_exit_contract_uses_controlled_hypothesis_verdicts(
    monkeypatch, tmp_path
):
    control, holdout = _fixture()
    report = evaluator.evaluate_control(control, holdout, edge_repetitions=1)
    passing = copy.deepcopy(report)
    for hypothesis in passing["hypotheses"].values():
        hypothesis["passed"] = True
    failing = copy.deepcopy(passing)
    failing["hypotheses"]["soft_target_predictive_agreement"]["passed"] = False

    monkeypatch.setattr(
        verifier, "evaluate_frozen_membership", lambda *_args, **_kwargs: passing
    )
    assert verifier.evaluate(tmp_path, strict=True) == 0
    monkeypatch.setattr(
        verifier, "evaluate_frozen_membership", lambda *_args, **_kwargs: failing
    )
    assert verifier.evaluate(tmp_path, strict=False) == 0
    assert verifier.evaluate(tmp_path, strict=True) == 2
    monkeypatch.setattr(
        verifier,
        "evaluate_frozen_membership",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("broken")),
    )
    assert verifier.evaluate(tmp_path) == 1


def test_rejects_zero_edge_repetitions():
    control, holdout = _fixture()

    with pytest.raises(ValueError, match="at least 1"):
        evaluator.evaluate_control(control, holdout, edge_repetitions=0)
