#!/usr/bin/env python3
"""Veil-of-ignorance cross-validation with ROC analysis.

Holds out known TPOT accounts, propagates without them, then measures
how well different scoring methods can distinguish the hidden TPOT
accounts from random non-TPOT accounts.

Produces ROC curves (TPR vs FPR) and AUC for each scoring method:
  1. Raw propagation score (max community weight)
  2. Seed-neighbor count (max across communities)
  3. Composite: score × neighbors
  4. Composite with degree normalization

Usage:
    .venv/bin/python3 -m scripts.verify_veil_cv
    .venv/bin/python3 -m scripts.verify_veil_cv --n-folds 5 --holdout-frac 0.2
    .venv/bin/python3 -m scripts.verify_veil_cv --output data/veil_cv_results.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import cg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from src.config import DEFAULT_ARCHIVE_DB

logger = logging.getLogger(__name__)

DB_PATH = DEFAULT_ARCHIVE_DB
REGULARIZATION = 1e-3
MIN_DEGREE = 2
MAX_CG_ITER = 800
CG_TOL = 1e-6
N_NEGATIVE_SAMPLES = 500  # random non-TPOT accounts for FPR estimation


# ── Data loading (reuse from verify_bootstrap_cv) ────────────────────────────

def load_categories():
    """Load Cat1/2/3 and community metadata."""
    db = sqlite3.connect(str(DB_PATH))
    archive_rows = db.execute(
        "SELECT account_id, community_id, weight FROM community_account"
    ).fetchall()
    archive_ids = {r[0] for r in archive_rows}
    archive_weights = {}
    for aid, cid, weight in archive_rows:
        if aid not in archive_weights:
            archive_weights[aid] = {}
        archive_weights[aid][cid] = max(archive_weights[aid].get(cid, 0.0), weight)

    dir_ids = {r[0] for r in db.execute(
        "SELECT account_id FROM tpot_directory_holdout WHERE account_id IS NOT NULL"
    ).fetchall()}

    cat1 = archive_ids & dir_ids
    cat2 = dir_ids - archive_ids
    cat3 = archive_ids - dir_ids

    communities = db.execute(
        """SELECT c.id, c.name FROM community c
           LEFT JOIN community_account ca ON ca.community_id = c.id
           GROUP BY c.id ORDER BY COUNT(ca.account_id) DESC"""
    ).fetchall()
    community_ids = [r[0] for r in communities]
    community_names = [r[1] for r in communities]

    try:
        eligibility = dict(db.execute(
            "SELECT account_id, concentration FROM seed_eligibility"
        ).fetchall())
    except sqlite3.OperationalError:
        eligibility = {}

    db.close()
    return cat1, cat2, cat3, archive_weights, community_ids, community_names, eligibility


def build_graph():
    """Build engagement-weighted adjacency. Returns (adj, node_ids)."""
    db = sqlite3.connect(str(DB_PATH))
    follows = db.execute(
        "SELECT account_id, following_account_id FROM account_following"
    ).fetchall()
    all_nodes = sorted({r[0] for r in follows} | {r[1] for r in follows})
    node_idx = {nid: i for i, nid in enumerate(all_nodes)}
    n = len(all_nodes)

    rows_i = [node_idx[r[0]] for r in follows]
    cols_j = [node_idx[r[1]] for r in follows]
    adj = sp.csr_matrix(
        (np.ones(len(follows), dtype=np.float32), (rows_i, cols_j)),
        shape=(n, n),
    )

    try:
        eng = db.execute("""
            SELECT source_id, target_id, follow_flag, like_count, reply_count, rt_count
            FROM account_engagement_agg
        """).fetchall()
        er, ec, ev = [], [], []
        for src, tgt, follow, likes, replies, rts in eng:
            i, j = node_idx.get(src), node_idx.get(tgt)
            if i is not None and j is not None:
                w = (1.0 if follow else 0.0) + \
                    0.6 * min(rts / 10, 1.0) * (rts > 0) + \
                    0.4 * min(likes / 50, 1.0) * (likes > 0) + \
                    0.2 * min(replies / 5, 1.0) * (replies > 0)
                if w > 0:
                    er.append(i); ec.append(j); ev.append(w)
        if ev:
            enrich = sp.csr_matrix(
                (np.array(ev, dtype=np.float32), (er, ec)), shape=(n, n)
            )
            adj = adj.maximum(enrich).tocsr()
    except Exception:
        pass

    db.close()
    return adj, np.array(all_nodes)


# ── Propagation (classic mode for CV — matches original) ────────────────────

def propagate_fold(
    laplacian, degrees, node_ids, seed_ids, archive_weights,
    community_ids, eligibility,
):
    """Run one propagation fold. Returns (memberships, labeled_mask, seed_neighbor_counts)."""
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    K = len(community_ids)
    cid_to_col = {cid: i for i, cid in enumerate(community_ids)}
    n_nodes = len(node_ids)

    # Build boundary (same logic as verify_bootstrap_cv)
    comm_sizes = np.zeros(K)
    for aid in seed_ids:
        weights = archive_weights.get(aid, {})
        if weights:
            col = cid_to_col.get(max(weights, key=weights.get))
            if col is not None:
                comm_sizes[col] += 1

    balance = np.ones(K)
    for col in range(K):
        if comm_sizes[col] > 0:
            balance[col] = 1.0 / np.sqrt(comm_sizes[col])
    if balance.max() > 0:
        balance /= balance.max()

    labeled_list, boundary_list, raw_weights_list = [], [], []
    for aid in sorted(seed_ids):
        idx = id_to_idx.get(aid)
        weights = archive_weights.get(aid, {})
        if idx is None or not weights:
            continue
        raw = np.zeros(K)
        for cid, w in weights.items():
            col = cid_to_col.get(cid)
            if col is not None:
                raw[col] = max(raw[col], w)

        balanced = raw * balance
        balanced *= eligibility.get(aid, 1.0)
        if balanced.sum() > 1.0:
            balanced /= balanced.sum()

        row = np.empty(K + 1)
        row[:K] = balanced
        row[K] = max(0.0, 1.0 - balanced.sum())
        labeled_list.append(idx)
        boundary_list.append(row)
        raw_weights_list.append(raw)

    labeled_indices = np.array(labeled_list, dtype=np.int64)
    boundary = np.array(boundary_list)
    raw_weights = np.array(raw_weights_list)

    # Solve
    labeled_mask = np.zeros(n_nodes, dtype=bool)
    labeled_mask[labeled_indices] = True
    unlabeled_idx = np.flatnonzero(~labeled_mask)
    low_degree = (degrees < MIN_DEGREE) & ~labeled_mask

    l_uu = laplacian[np.ix_(unlabeled_idx, unlabeled_idx)].tocsr()
    l_ul = laplacian[np.ix_(unlabeled_idx, labeled_indices)].tocsr()
    l_uu = l_uu + REGULARIZATION * sp.eye(len(unlabeled_idx), format="csr")

    memberships = np.zeros((n_nodes, K + 1))
    memberships[labeled_indices] = boundary

    for c in range(K + 1):
        rhs = -(l_ul @ boundary[:, c])
        solution, _ = cg(l_uu, rhs, tol=CG_TOL, maxiter=MAX_CG_ITER)
        memberships[unlabeled_idx, c] = solution

    memberships = np.clip(memberships, 0.0, None)
    row_sums = memberships.sum(axis=1, keepdims=True)
    memberships /= np.where(row_sums > 0, row_sums, 1.0)
    memberships[labeled_indices] = boundary
    memberships[low_degree, :K] = 0.0
    memberships[low_degree, K] = 1.0

    # Seed-neighbor counts (using raw weights, not balanced)
    sym = laplacian.diagonal()[:, None]  # not needed, use adj
    # Rebuild symmetrized adjacency from laplacian for neighbor lookup
    adj_sym = sp.diags(degrees) - laplacian
    seed_neighbor_counts = np.zeros((n_nodes, K), dtype=np.int32)
    for li_pos, li in enumerate(labeled_indices):
        neighbors = adj_sym[li].nonzero()[1]
        for c in range(K):
            if raw_weights[li_pos, c] > 0:
                seed_neighbor_counts[neighbors, c] += 1

    return memberships, labeled_mask, seed_neighbor_counts


# ── Scoring methods ──────────────────────────────────────────────────────────

def compute_scores(memberships, seed_neighbor_counts, degrees, K):
    """Compute multiple scoring methods for all accounts.

    Returns dict of {method_name: scores_array}.
    """
    comm = memberships[:, :K]
    max_score = comm.max(axis=1)
    max_snc = seed_neighbor_counts.max(axis=1).astype(float)
    total_snc = seed_neighbor_counts.sum(axis=1).astype(float)

    # Composite: score × neighbors
    composite = max_score * max_snc

    # Degree-normalized: composite / sqrt(degree)
    safe_deg = np.maximum(degrees, 1.0)
    normalized = composite / np.sqrt(safe_deg)

    return {
        "raw_score": max_score,
        "seed_neighbors": max_snc,
        "composite": composite,
        "normalized": normalized,
    }


# ── ROC computation ──────────────────────────────────────────────────────────

def compute_roc(pos_scores, neg_scores, n_points=200):
    """Compute ROC curve from positive and negative score arrays.

    Returns (fpr, tpr, thresholds, auc).
    """
    all_scores = np.concatenate([pos_scores, neg_scores])
    thresholds = np.linspace(all_scores.max() + 1e-10, all_scores.min() - 1e-10, n_points)

    tpr_list, fpr_list = [], []
    for t in thresholds:
        tp = (pos_scores >= t).sum()
        fp = (neg_scores >= t).sum()
        tpr_list.append(tp / max(len(pos_scores), 1))
        fpr_list.append(fp / max(len(neg_scores), 1))

    fpr = np.array(fpr_list)
    tpr = np.array(tpr_list)

    # AUC via trapezoidal rule
    sorted_idx = np.argsort(fpr)
    fpr_sorted = fpr[sorted_idx]
    tpr_sorted = tpr[sorted_idx]
    auc = float(np.trapz(tpr_sorted, fpr_sorted))

    return fpr.tolist(), tpr.tolist(), thresholds.tolist(), auc


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Veil-of-ignorance CV with ROC analysis")
    parser.add_argument("--n-folds", type=int, default=5)
    parser.add_argument("--holdout-frac", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    print("=" * 72)
    print("VEIL-OF-IGNORANCE CROSS-VALIDATION WITH ROC ANALYSIS")
    print("=" * 72)

    cat1, cat2, cat3, archive_weights, community_ids, community_names, eligibility = load_categories()
    K = len(community_ids)
    cid_to_col = {cid: i for i, cid in enumerate(community_ids)}

    print(f"  Cat 1 (archive ∩ directory): {len(cat1)}")
    print(f"  Cat 2 (directory only):      {len(cat2)}")
    print(f"  Cat 3 (archive only):        {len(cat3)}")
    print(f"  Folds: {args.n_folds}, holdout: {args.holdout_frac:.0%}")
    print()

    print("Building graph (once)...")
    t0 = time.perf_counter()
    adj, node_ids = build_graph()
    node_idx = {nid: i for i, nid in enumerate(node_ids)}
    sym = adj.maximum(adj.T).tocsr()
    sym.setdiag(0.0)
    sym.eliminate_zeros()
    degrees = np.asarray(sym.sum(axis=1)).flatten()
    laplacian = sp.diags(degrees, format="csr") - sym
    print(f"  {len(node_ids):,} nodes, built in {time.perf_counter()-t0:.1f}s")

    # Select negative samples: random non-TPOT accounts with degree >= 2
    all_tpot = cat1 | cat2 | cat3
    non_tpot_in_graph = [
        nid for nid in node_ids
        if nid not in all_tpot and degrees[node_idx[nid]] >= MIN_DEGREE
    ]
    rng = np.random.RandomState(args.seed)
    neg_sample_ids = set(rng.choice(
        non_tpot_in_graph,
        size=min(N_NEGATIVE_SAMPLES, len(non_tpot_in_graph)),
        replace=False,
    ))
    print(f"  Negative samples: {len(neg_sample_ids)} random non-TPOT (degree >= {MIN_DEGREE})")
    print()

    # Accumulate scores across folds
    all_pos_scores = {m: [] for m in ["raw_score", "seed_neighbors", "composite", "normalized"]}
    all_neg_scores = {m: [] for m in ["raw_score", "seed_neighbors", "composite", "normalized"]}
    fold_recalls = {m: [] for m in all_pos_scores}

    for fold in range(args.n_folds):
        fold_rng = np.random.RandomState(args.seed + fold)

        # Stratified holdout of Cat1
        groups = {}
        for aid in cat1:
            weights = archive_weights.get(aid, {})
            col = cid_to_col.get(max(weights, key=weights.get), -1) if weights else -1
            groups.setdefault(col, []).append(aid)

        holdout = set()
        for members in groups.values():
            n_hold = min(max(1, int(len(members) * args.holdout_frac)), max(1, len(members) // 2))
            fold_rng.shuffle(members)
            holdout.update(members[:n_hold])

        train_seeds = (cat1 - holdout) | cat3
        holdout_in_graph = {aid for aid in holdout if aid in node_idx}

        print(f"Fold {fold+1}/{args.n_folds}: train={len(train_seeds)}, "
              f"holdout={len(holdout)} ({len(holdout_in_graph)} in graph)")

        t_fold = time.perf_counter()
        memberships, labeled_mask, snc = propagate_fold(
            laplacian, degrees, node_ids, train_seeds,
            archive_weights, community_ids, eligibility,
        )
        elapsed = time.perf_counter() - t_fold

        # Score all accounts
        scores = compute_scores(memberships, snc, degrees, K)

        # Collect positive scores (held-out TPOT)
        for aid in holdout_in_graph:
            idx = node_idx[aid]
            if labeled_mask[idx]:
                continue  # shouldn't happen
            for method, arr in scores.items():
                all_pos_scores[method].append(float(arr[idx]))

        # Collect negative scores (random non-TPOT)
        for aid in neg_sample_ids:
            idx = node_idx.get(aid)
            if idx is None or labeled_mask[idx]:
                continue
            for method, arr in scores.items():
                all_neg_scores[method].append(float(arr[idx]))

        # Per-fold recall at a few thresholds
        for method, arr in scores.items():
            found = sum(
                1 for aid in holdout_in_graph
                if not labeled_mask[node_idx[aid]] and arr[node_idx[aid]] > 0.01
            )
            fold_recalls[method].append(found / max(len(holdout_in_graph), 1))

        print(f"  Time: {elapsed:.0f}s")
        for method in scores:
            pos_vals = [scores[method][node_idx[aid]] for aid in holdout_in_graph
                        if not labeled_mask[node_idx[aid]]]
            print(f"  {method:>15s}: pos_median={np.median(pos_vals):.4f}, "
                  f"recall@0.01={fold_recalls[method][-1]:.0%}")
        print()

    # Compute ROC curves
    print("=" * 72)
    print("ROC ANALYSIS")
    print("=" * 72)

    results = {}
    for method in all_pos_scores:
        pos = np.array(all_pos_scores[method])
        neg = np.array(all_neg_scores[method])
        fpr, tpr, thresholds, auc = compute_roc(pos, neg)
        results[method] = {
            "auc": auc,
            "fpr": fpr,
            "tpr": tpr,
            "thresholds": thresholds,
            "pos_count": len(pos),
            "neg_count": len(neg),
            "pos_median": float(np.median(pos)) if len(pos) > 0 else 0,
            "neg_median": float(np.median(neg)) if len(neg) > 0 else 0,
            "recall_per_fold": fold_recalls[method],
        }
        print(f"\n  {method}:")
        print(f"    AUC = {auc:.3f}")
        print(f"    Positive median: {np.median(pos):.4f}  (n={len(pos)})")
        print(f"    Negative median: {np.median(neg):.4f}  (n={len(neg)})")
        print(f"    Separation: {np.median(pos)/max(np.median(neg), 1e-10):.1f}x")

        # Key operating points
        for target_fpr in [0.01, 0.05, 0.10, 0.20]:
            # Find threshold that gives ~target_fpr
            for i in range(len(fpr)):
                if fpr[i] >= target_fpr:
                    print(f"    At FPR={fpr[i]:.2f}: TPR={tpr[i]:.2f} (threshold={thresholds[i]:.4f})")
                    break

    # Save results
    output_path = args.output or Path("data/veil_cv_results.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "config": {
                "n_folds": args.n_folds,
                "holdout_frac": args.holdout_frac,
                "seed": args.seed,
                "n_negative_samples": N_NEGATIVE_SAMPLES,
                "cat1": len(cat1),
                "cat2": len(cat2),
                "cat3": len(cat3),
            },
            "methods": results,
        }, f, indent=2)
    print(f"\nResults saved to {output_path}")

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"{'method':>15s}  {'AUC':>6s}  {'separation':>12s}  {'TPR@5%FPR':>10s}")
    print("-" * 50)
    for method, r in sorted(results.items(), key=lambda x: -x[1]["auc"]):
        sep = r["pos_median"] / max(r["neg_median"], 1e-10)
        # TPR at ~5% FPR
        tpr_at_5 = 0
        for i in range(len(r["fpr"])):
            if r["fpr"][i] >= 0.05:
                tpr_at_5 = r["tpr"][i]
                break
        print(f"{method:>15s}  {r['auc']:6.3f}  {sep:11.1f}x  {tpr_at_5:10.0%}")


if __name__ == "__main__":
    main()
