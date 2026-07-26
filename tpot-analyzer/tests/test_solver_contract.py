"""Behavioral tests for bounded propagation solver-contract measurements."""
from __future__ import annotations

import numpy as np
from scipy import sparse

from scripts import verify_propagation_solver_contract as verifier
from src.evaluation.solver_contract import (
    ContractCheck,
    SolverContractReport,
    historical_uncertainty,
    measure_dangling_mass,
    measure_iteration_plumbing,
    measure_legacy_fingerprint,
)


def _fingerprint_fixture():
    adjacency = sparse.csr_matrix(
        [
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 1.0],
            [0.0, 1.0, 0.0],
        ]
    )
    memberships = np.array(
        [
            [0.8, 0.1, 0.1],
            [0.2, 0.6, 0.2],
            [0.1, 0.2, 0.7],
        ]
    )
    labeled = np.array([True, False, False])
    return adjacency, memberships, labeled


def test_historical_uncertainty_zeros_labeled_rows():
    adjacency, memberships, labeled = _fingerprint_fixture()

    observed = historical_uncertainty(adjacency, memberships, labeled)

    assert observed.shape == (3,)
    assert observed[0] == 0.0
    assert np.all((observed >= 0.0) & (observed <= 1.0))


def test_legacy_fingerprint_accepts_matching_observable_output():
    adjacency, memberships, labeled = _fingerprint_fixture()
    stored = historical_uncertainty(adjacency, memberships, labeled)

    check = measure_legacy_fingerprint(
        adjacency,
        memberships,
        stored.astype(np.float32),
        labeled,
    )

    assert check.accepted is True
    assert check.metrics["cells_above_tolerance"] == 0


def test_legacy_fingerprint_rejects_changed_uncertainty_method():
    adjacency, memberships, labeled = _fingerprint_fixture()
    stored = historical_uncertainty(adjacency, memberships, labeled)
    stored[1] += 0.01

    check = measure_legacy_fingerprint(
        adjacency,
        memberships,
        stored,
        labeled,
    )

    assert check.accepted is False
    assert check.metrics["max_abs_error"] >= 0.01


def test_iteration_probe_derives_verdict_from_observed_contract():
    check = measure_iteration_plumbing()

    assert check.metrics["requested_max_iter"] == 1
    assert check.metrics["requested_tolerance"] == 1e9
    expected = (
        check.metrics["observed_max_nonempty_iterations"]
        <= check.metrics["requested_max_iter"]
        and all(check.metrics["observed_converged"])
    )
    assert check.accepted is expected


def test_dangling_probe_derives_verdict_and_keeps_control():
    check = measure_dangling_mass()

    assert check.metrics["dangling_node_count"] == 1
    np.testing.assert_allclose(
        check.metrics["control_probability_mass"],
        1.0,
        atol=1e-9,
    )
    expected = (
        check.metrics["converged"]
        and check.metrics["mass_deficit"] <= check.metrics["tolerance"]
    )
    assert check.accepted is expected


def _rejected_report() -> SolverContractReport:
    return SolverContractReport(
        bundle_id="fixture",
        checks=(
            ContractCheck(
                name="example-rejection",
                hypothesis="The example remains valid.",
                falsifier="Reject when observed=false.",
                accepted=False,
                metrics={"observed": False},
            ),
        ),
    )


def test_verifier_default_succeeds_after_falsification(
    tmp_path,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        verifier,
        "measure_solver_contract",
        lambda _data_dir: _rejected_report(),
    )

    assert verifier.verify(tmp_path) == 0
    output = capsys.readouterr().out
    assert "✗ example-rejection: hypothesis rejected" in output
    assert "Hypothesis:" in output
    assert "Falsifier:" in output
    assert "Observed:" in output
    assert "✓ Measurement completed" in output


def test_verifier_strict_mode_fails_on_rejected_contract(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        verifier,
        "measure_solver_contract",
        lambda _data_dir: _rejected_report(),
    )

    assert verifier.verify(tmp_path, require_valid_contract=True) == 2
