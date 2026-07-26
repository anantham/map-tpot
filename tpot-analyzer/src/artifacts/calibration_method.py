"""Validation helpers for holdout-based TPOT threshold calibration."""
from __future__ import annotations

import math

import numpy as np


class CalibrationMethodError(ValueError):
    """Raised when calibration methodology is invalid or infeasible."""


def validate_holdout_split(holdout, node_id_to_idx, labeled_mask):
    """Return fully resolved holdout indices after leakage checks."""
    if not isinstance(holdout, dict):
        raise CalibrationMethodError("holdout root must be an object")
    accounts = holdout.get("accounts")
    if not isinstance(accounts, dict) or not accounts:
        raise CalibrationMethodError("holdout accounts must be a non-empty object")
    n_holdout = holdout.get("n_holdout")
    if n_holdout != len(accounts):
        raise CalibrationMethodError(
            f"holdout n_holdout={n_holdout!r}, accounts={len(accounts)}"
        )
    n_train = holdout.get("n_train")
    if isinstance(n_train, bool) or not isinstance(n_train, int) or n_train < 1:
        raise CalibrationMethodError(
            f"holdout n_train must be a positive integer; got {n_train!r}"
        )
    fraction = holdout.get("holdout_fraction")
    if (
        isinstance(fraction, bool)
        or not isinstance(fraction, (int, float))
        or not math.isfinite(float(fraction))
        or not 0.0 < float(fraction) < 1.0
    ):
        raise CalibrationMethodError(
            f"holdout_fraction must be finite and in (0, 1); got {fraction!r}"
        )
    seed = holdout.get("holdout_seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise CalibrationMethodError(
            f"holdout_seed must be an integer; got {seed!r}"
        )

    account_ids = [str(account_id) for account_id in accounts]
    unresolved = [
        account_id
        for account_id in account_ids
        if account_id not in node_id_to_idx
    ]
    if unresolved:
        raise CalibrationMethodError(
            f"holdout has unresolved graph accounts: sample={unresolved[:5]}"
        )
    indices = [int(node_id_to_idx[account_id]) for account_id in account_ids]
    mask = np.asarray(labeled_mask)
    if mask.ndim != 1 or any(index >= len(mask) or index < 0 for index in indices):
        raise CalibrationMethodError(
            f"labeled_mask cannot resolve holdout indices: shape={mask.shape}"
        )
    if mask.dtype != np.bool_:
        raise CalibrationMethodError(
            f"labeled_mask must be boolean; got dtype={mask.dtype}"
        )
    if int(mask.sum()) != n_train:
        raise CalibrationMethodError(
            f"holdout n_train={n_train}, but labeled_mask has "
            f"{int(mask.sum())} labeled nodes"
        )
    leaked = [
        account_id
        for account_id, index in zip(account_ids, indices)
        if bool(mask[index])
    ]
    if leaked:
        raise CalibrationMethodError(
            f"holdout leakage: accounts are labeled in propagation: sample={leaked[:5]}"
        )
    return indices


def select_best_feasible_result(results, recall_floor):
    """Return the best recall-floor-feasible threshold result."""
    if (
        isinstance(recall_floor, bool)
        or not isinstance(recall_floor, (int, float))
        or not math.isfinite(float(recall_floor))
        or not 0.0 <= float(recall_floor) <= 1.0
    ):
        raise CalibrationMethodError(
            f"recall_floor must be finite and in [0, 1]; got {recall_floor!r}"
        )
    feasible = []
    for result in results:
        if not isinstance(result, dict):
            raise CalibrationMethodError("calibration result rows must be objects")
        try:
            recall = float(result["recall"])
            score = float(result["objective_score"])
            tau = float(result["tau"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CalibrationMethodError(
                f"malformed calibration result row: {result!r}"
            ) from exc
        if not all(math.isfinite(value) for value in (recall, score, tau)):
            raise CalibrationMethodError(
                f"calibration result values must be finite: {result!r}"
            )
        if recall >= recall_floor:
            feasible.append(result)
    if not feasible:
        raise CalibrationMethodError(
            f"No threshold meets recall floor {float(recall_floor):.3f}"
        )
    return max(feasible, key=lambda result: float(result["objective_score"]))
