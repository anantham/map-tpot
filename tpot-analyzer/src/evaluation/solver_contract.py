"""Bounded measurements for the propagation solver's scientific contract."""
from __future__ import annotations

import inspect
import io
import sqlite3
import tempfile
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import sparse

from src.artifacts.frozen_manifest import verify_frozen_manifest
from src.data.adjacency import load_adjacency_cache
from src.propagation.engine import compute_ppr, propagate
from src.propagation.types import PropagationConfig


@dataclass(frozen=True)
class ContractCheck:
    """One hypothesis, its falsifier, and observed bounded metrics."""

    name: str
    hypothesis: str
    falsifier: str
    accepted: bool
    metrics: dict[str, object]


@dataclass(frozen=True)
class SolverContractReport:
    """Completed measurements against one frozen bundle."""

    bundle_id: str
    checks: tuple[ContractCheck, ...]

    @property
    def valid_contract(self) -> bool:
        return all(check.accepted for check in self.checks)


def historical_uncertainty(
    adjacency: sparse.csr_matrix,
    memberships: np.ndarray,
    labeled_mask: np.ndarray,
) -> np.ndarray:
    """Reconstruct the legacy CG producer's uncertainty formula."""
    memberships = np.asarray(memberships, dtype=np.float64)
    labeled_mask = np.asarray(labeled_mask, dtype=bool)
    if memberships.ndim != 2 or memberships.shape[1] < 2:
        raise ValueError("memberships must be a two-dimensional K+1 matrix")
    if adjacency.shape != (len(memberships), len(memberships)):
        raise ValueError(
            "adjacency shape must match membership rows: "
            f"adjacency={adjacency.shape}, memberships={memberships.shape}"
        )
    if labeled_mask.shape != (len(memberships),):
        raise ValueError(
            "labeled_mask must have one value per membership row: "
            f"mask={labeled_mask.shape}, rows={len(memberships)}"
        )

    sym = adjacency.maximum(adjacency.T).tocsr()
    diagonal = sym.diagonal()
    if np.any(diagonal):
        sym = sym - sparse.diags(diagonal, format="csr")
    sym.eliminate_zeros()
    degrees = np.asarray(sym.sum(axis=1)).ravel()
    probabilities = np.clip(memberships, 1e-10, 1.0)
    entropy = -np.sum(
        probabilities * np.log2(probabilities), axis=1
    ) / np.log2(memberships.shape[1])
    degree_uncertainty = 1.0 / np.sqrt(degrees + 1.0)
    degree_uncertainty /= degree_uncertainty.max()
    result = np.clip(
        0.7 * entropy + 0.3 * degree_uncertainty,
        0.0,
        1.0,
    )
    result[labeled_mask] = 0.0
    return result


def measure_legacy_fingerprint(
    adjacency: sparse.csr_matrix,
    memberships: np.ndarray,
    stored_uncertainty: np.ndarray,
    labeled_mask: np.ndarray,
    *,
    tolerance: float = 1e-6,
) -> ContractCheck:
    """Test whether uncertainty carries the historical post-processing fingerprint."""
    reconstructed = historical_uncertainty(
        adjacency,
        memberships,
        labeled_mask,
    )
    stored = np.asarray(stored_uncertainty, dtype=np.float64)
    if stored.shape != reconstructed.shape:
        raise ValueError(
            "stored uncertainty shape differs from reconstruction: "
            f"stored={stored.shape}, reconstructed={reconstructed.shape}"
        )
    difference = np.abs(reconstructed - stored)
    max_abs = float(difference.max()) if difference.size else 0.0
    return ContractCheck(
        name="legacy-uncertainty-postprocessing-fingerprint",
        hypothesis=(
            "Frozen uncertainty uses the historical entropy-plus-degree "
            "post-processing formula."
        ),
        falsifier=(
            "Reject if reconstructed uncertainty differs by more than "
            f"{tolerance:g} at any node."
        ),
        accepted=bool(np.isfinite(difference).all() and max_abs <= tolerance),
        metrics={
            "nodes": int(len(stored)),
            "max_abs_error": max_abs,
            "mean_abs_error": float(difference.mean()),
            "q99_abs_error": float(np.percentile(difference, 99)),
            "cells_above_tolerance": int((difference > tolerance).sum()),
            "tolerance": tolerance,
        },
    )


def _write_probe_database(path: Path) -> None:
    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(
            """
            CREATE TABLE community (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, color TEXT
            );
            CREATE TABLE community_account (
                community_id TEXT, account_id TEXT, weight REAL
            );
            INSERT INTO community VALUES ('c-a', 'Alpha', '#ff0000');
            INSERT INTO community VALUES ('c-b', 'Beta', '#00ff00');
            INSERT INTO community_account VALUES ('c-a', 'node-0', 0.8);
            INSERT INTO community_account VALUES ('c-b', 'node-3', 0.8);
            """
        )
        connection.commit()
    finally:
        connection.close()


def measure_iteration_plumbing() -> ContractCheck:
    """Observe whether PropagationConfig iteration controls reach PPR."""
    n_nodes = 6
    rows = np.arange(n_nodes)
    adjacency = sparse.csr_matrix(
        (np.ones(n_nodes), (rows, (rows + 1) % n_nodes)),
        shape=(n_nodes, n_nodes),
    )
    node_ids = np.array([f"node-{index}" for index in range(n_nodes)])
    requested_max_iter = 1
    requested_tolerance = 1e9
    config = PropagationConfig(
        alpha=0.15,
        max_iter=requested_max_iter,
        tolerance=requested_tolerance,
        min_degree_for_assignment=0,
        class_balance=False,
    )
    with tempfile.TemporaryDirectory(prefix="tpot-solver-contract-") as folder:
        database = Path(folder) / "probe.sqlite"
        _write_probe_database(database)
        with redirect_stdout(io.StringIO()):
            result, _ = propagate(
                adjacency,
                node_ids,
                config,
                seed_eligibility=False,
                db_path=database,
            )

    iterations = tuple(int(value) for value in result.cg_iterations)
    converged = tuple(bool(value) for value in result.converged)
    positive = [value for value in iterations if value > 0]
    observed_max = max(positive, default=0)
    signature = inspect.signature(compute_ppr)
    accepted = bool(
        positive
        and observed_max <= requested_max_iter
        and all(converged)
    )
    return ContractCheck(
        name="iteration-config-plumbing",
        hypothesis=(
            "PropagationConfig.max_iter and tolerance govern every "
            "non-empty per-class PPR solve."
        ),
        falsifier=(
            "Reject if a class exceeds max_iter=1 under the deliberately "
            "permissive requested tolerance=1e9."
        ),
        accepted=accepted,
        metrics={
            "requested_max_iter": requested_max_iter,
            "requested_tolerance": requested_tolerance,
            "observed_iterations": iterations,
            "observed_converged": converged,
            "observed_max_nonempty_iterations": observed_max,
            "compute_ppr_default_max_iter": (
                signature.parameters["max_iter"].default
            ),
            "compute_ppr_default_tolerance": (
                signature.parameters["tol"].default
            ),
        },
    )


def measure_dangling_mass(*, tolerance: float = 1e-9) -> ContractCheck:
    """Measure probability-mass conservation with a reversed-graph sink."""
    dangling = sparse.csr_matrix([[0.0, 1.0], [0.0, 0.0]])
    control = sparse.csr_matrix([[0.0, 1.0], [1.0, 0.0]])
    vector, iterations, converged = compute_ppr(
        dangling, alpha=0.15, max_iter=200, tol=1e-12
    )
    control_vector, _, control_converged = compute_ppr(
        control, alpha=0.15, max_iter=200, tol=1e-12
    )
    mass = float(vector.sum())
    deficit = float(abs(1.0 - mass))
    reversed_out_degree = np.asarray(dangling.T.sum(axis=1)).ravel()
    accepted = bool(
        converged
        and control_converged
        and np.isfinite(vector).all()
        and (vector >= 0).all()
        and deficit <= tolerance
    )
    return ContractCheck(
        name="dangling-node-mass-conservation",
        hypothesis=(
            "Directed PPR preserves unit probability mass when the reversed "
            "walk graph contains dangling nodes."
        ),
        falsifier=(
            f"Reject if |sum(PPR)-1| exceeds {tolerance:g} after convergence."
        ),
        accepted=accepted,
        metrics={
            "dangling_node_count": int((reversed_out_degree == 0).sum()),
            "converged": bool(converged),
            "iterations": int(iterations),
            "probability_mass": mass,
            "mass_deficit": deficit,
            "control_probability_mass": float(control_vector.sum()),
            "tolerance": tolerance,
        },
    )


def measure_solver_contract(data_dir: Path) -> SolverContractReport:
    """Run all bounded probes after verifying frozen artifact identity."""
    data_dir = Path(data_dir)
    manifest = verify_frozen_manifest(data_dir)
    adjacency = load_adjacency_cache(data_dir / "adjacency_matrix_cache.pkl")
    path = data_dir / manifest["selected_propagation"]
    with np.load(path, allow_pickle=False) as artifact:
        fingerprint = measure_legacy_fingerprint(
            adjacency,
            artifact["memberships"],
            artifact["uncertainty"],
            artifact["labeled_mask"],
        )
    return SolverContractReport(
        bundle_id=str(manifest.get("bundle_id", "unknown")),
        checks=(
            fingerprint,
            measure_iteration_plumbing(),
            measure_dangling_mass(),
        ),
    )
