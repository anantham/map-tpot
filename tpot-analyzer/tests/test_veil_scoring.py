"""Veil cross-validation scoring helpers.

Test intent:
- Folds partition the accounts: each is held out exactly once, and every
  community is spread across folds.
- AUC matches its definition, including half credit for ties, and refuses an
  empty class instead of returning a number.
- Fold AUC only compares a positive with negatives from the run it was hidden
  in; a negative that scores high only in other folds' runs doesn't count.
- The bootstrap brackets the point estimate, reports a paired gap of zero for
  identical methods, and widens when there are fewer accounts.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.propagation.veil import auc, bootstrap_auc, fold_auc, stratified_folds


def test_folds_partition_accounts_and_spread_communities():
    dominant = {f"a{i}": i % 3 for i in range(30)}
    folds = stratified_folds(dominant, n_folds=5, seed=1)

    assert sorted(a for f in folds for a in f) == sorted(dominant)
    assert sum(len(f) for f in folds) == 30
    for f in folds:
        assert {dominant[a] for a in f} == {0, 1, 2}


def test_auc_definition_and_ties():
    assert auc(np.array([3.0, 4.0]), np.array([1.0, 2.0])) == 1.0
    assert auc(np.array([1.0]), np.array([1.0])) == 0.5
    # pairs: (2>1) (2<3) (2=2) -> (1 + 0 + 0.5) / 3
    assert auc(np.array([2.0]), np.array([1.0, 3.0, 2.0])) == pytest.approx(0.5)
    with pytest.raises(ValueError, match="both classes"):
        auc(np.array([]), np.array([1.0]))


def test_bootstrap_brackets_estimate_and_pairs_methods():
    rng = np.random.default_rng(0)
    signal = rng.normal(1.0, 1.0, 60)
    pos = np.stack([signal, signal], axis=1)
    noise = rng.normal(0.0, 1.0, (200, 3))
    neg = np.stack([noise, noise], axis=2)

    out = bootstrap_auc(pos, np.arange(60) % 3, neg, n_boot=300, seed=0)

    lo, hi = out["ci"][0]
    assert lo < out["auc"][0] < hi
    assert out["gap_vs_first"][1] == 0.0
    assert out["gap_ci"][1] == [0.0, 0.0]
    assert (out["n_pos"], out["n_neg"]) == (60, 200)


def test_bootstrap_interval_widens_with_fewer_accounts():
    rng = np.random.default_rng(1)
    big = bootstrap_auc(rng.normal(1, 1, (200, 1)), np.zeros(200, int), rng.normal(0, 1, (400, 1, 1)), n_boot=300)
    small = bootstrap_auc(rng.normal(1, 1, (20, 1)), np.zeros(20, int), rng.normal(0, 1, (40, 1, 1)), n_boot=300)

    width = lambda r: r["ci"][0][1] - r["ci"][0][0]
    assert width(small) > width(big)


def test_fold_auc_ignores_negatives_from_other_runs():
    # Positive hidden in fold 0 scores 1.0. The negative scores 0.0 in fold 0's run
    # but 5.0 in fold 1's run (where the positive was a seed). Only fold 0 counts.
    pos, pos_fold = np.array([1.0]), np.array([0])
    neg = np.array([[0.0, 5.0]])
    assert fold_auc(pos, pos_fold, neg) == 1.0
    assert auc(pos, neg) == 0.5  # pooling across runs would halve it


def test_bootstrap_rejects_empty_positives_with_a_clear_error():
    with pytest.raises(ValueError, match="non-empty"):
        bootstrap_auc(np.array([]), np.array([]), np.zeros((5, 1, 1)))
