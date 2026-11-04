"""Scoring helpers for veil-of-ignorance cross-validation.

The veil test hides known TPOT accounts from the seed set, runs the production
propagation, and asks whether the hidden accounts outscore random non-TPOT
accounts. These helpers are the parts that need no database: fold assignment,
same-run AUC, and a bootstrap that keeps each account's repeated scores together.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import rankdata


def stratified_folds(dominant: dict[str, int], n_folds: int, seed: int) -> list[set[str]]:
    """Partition accounts into folds, spreading each community across folds.

    Every account lands in exactly one fold, so each is held out exactly once.
    """
    rng = np.random.RandomState(seed)
    by_group: dict[int, list[str]] = {}
    for aid in sorted(dominant):
        by_group.setdefault(dominant[aid], []).append(aid)
    folds: list[set[str]] = [set() for _ in range(n_folds)]
    offset = 0
    for group in sorted(by_group):
        members = by_group[group]
        rng.shuffle(members)
        for i, aid in enumerate(members):
            folds[(offset + i) % n_folds].add(aid)
        offset += len(members)
    return folds


def _wins(pos: np.ndarray, neg: np.ndarray) -> float:
    """Pairs where the positive outscores the negative, ties counting half."""
    ranks = rankdata(np.concatenate([pos, neg]))
    return float(ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2)


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """Probability a random positive outscores a random negative (ties count half)."""
    pos, neg = np.ravel(pos), np.ravel(neg)
    if len(pos) == 0 or len(neg) == 0:
        raise ValueError(f"AUC needs both classes (got {len(pos)} positives, {len(neg)} negatives)")
    return _wins(pos, neg) / (len(pos) * len(neg))


def fold_auc(pos: np.ndarray, pos_fold: np.ndarray, neg: np.ndarray) -> float:
    """AUC over same-run pairs only: a positive hidden in fold f meets negatives scored in fold f.

    pos: (n_pos,), pos_fold: (n_pos,) fold index, neg: (n_neg, n_folds).
    Comparing across folds would pit a positive against negatives from runs where
    it was a seed and shaped their scores.
    """
    if len(pos) == 0 or len(neg) == 0:
        raise ValueError(f"AUC needs both classes (got {len(pos)} positives, {len(neg)} negatives)")
    wins = sum(_wins(pos[pos_fold == f], neg[:, f]) for f in np.unique(pos_fold))
    return wins / (len(pos) * len(neg))


def bootstrap_auc(
    pos: np.ndarray, pos_fold: np.ndarray, neg: np.ndarray, *, n_boot: int = 2000, seed: int = 0
) -> dict:
    """Same-run AUC per method with 95% bootstrap intervals, plus each method's gap to method 0.

    pos: (n_pos, n_methods) scores, one row per held-out account; pos_fold: (n_pos,)
        the fold each was hidden in.
    neg: (n_neg, n_folds, n_methods) scores; a negative account is scored once per
        fold, and its rows are resampled together so they don't count as
        independent evidence.
    Methods are scored on the same resampled accounts, so the gaps are paired.
    """
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    pos_fold = np.asarray(pos_fold)
    if pos.ndim != 2 or neg.ndim != 3 or len(pos) == 0 or len(neg) == 0:
        raise ValueError(f"need non-empty pos (n, methods) and neg (n, folds, methods); "
                         f"got {pos.shape} and {neg.shape}")
    n_methods = pos.shape[1]
    point = [fold_auc(pos[:, m], pos_fold, neg[:, :, m]) for m in range(n_methods)]
    rng = np.random.default_rng(seed)
    draws = np.empty((n_boot, n_methods))
    for b in range(n_boot):
        i = rng.integers(0, len(pos), len(pos))
        q = neg[rng.integers(0, len(neg), len(neg))]
        draws[b] = [fold_auc(pos[i, m], pos_fold[i], q[:, :, m]) for m in range(n_methods)]

    def interval(x: np.ndarray) -> list[float]:
        return [float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5))]

    return {
        "auc": point,
        "ci": [interval(draws[:, m]) for m in range(n_methods)],
        "gap_vs_first": [point[m] - point[0] for m in range(n_methods)],
        "gap_ci": [interval(draws[:, m] - draws[:, 0]) for m in range(n_methods)],
        "n_pos": int(len(pos)),
        "n_neg": int(len(neg)),
    }
