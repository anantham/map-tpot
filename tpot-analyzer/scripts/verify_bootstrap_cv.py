#!/usr/bin/env python3
"""Bootstrap cross-validation: measure propagation generalization.

Holds out a random fraction of Cat 1 seeds per iteration, propagates
using remaining Cat 1 + all Cat 3, and measures recall on:
  - Held-out Cat 1 (known TPOT, temporarily removed from seeds)
  - Cat 2 accounts (directory-only, never seeded — true holdout TPOT)

Category definitions:
  Cat 1 (strongest): account_id in BOTH community_account AND tpot_directory_holdout
  Cat 2 (directory-only): in tpot_directory_holdout, NOT in community_account
  Cat 3 (archive-only): in community_account, NOT in tpot_directory_holdout

Results answer: "given a random 80% of known TPOT accounts as seeds,
does propagation discover the remaining 20% + the directory-only accounts?"

Usage:
    .venv/bin/python3 -m scripts.verify_bootstrap_cv
    .venv/bin/python3 -m scripts.verify_bootstrap_cv --n-iter 10
    .venv/bin/python3 -m scripts.verify_bootstrap_cv --holdout-frac 0.3
"""
from __future__ import annotations

import argparse
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

DB_PATH = DEFAULT_ARCHIVE_DB

RECALL_THRESHOLD = 0.05  # min community weight to count as "found" (matches verify_holdout_recall.py)
REGULARIZATION = 1e-3
MIN_DEGREE = 2
MAX_CG_ITER = 800
CG_TOL = 1e-6


# ── Data loading ──────────────────────────────────────────────────────────────

def load_categories() -> tuple[set, set, set, dict, list, list, dict]:
    """Load Cat 1/2/3 account sets and community metadata.

    Returns:
        cat1: archive ∩ directory  (seeds + evaluation target)
        cat2: directory only       (evaluation only — never seed)
        cat3: archive only         (always seeded, not evaluated as Cat 2)
        archive_weights: {account_id: {community_id: weight}}
        community_ids, community_names: metadata (consistent column order)
        eligibility: {account_id: concentration} from seed_eligibility
    """
    db = sqlite3.connect(str(DB_PATH))

    archive_rows = db.execute(
        "SELECT account_id, community_id, weight FROM community_account"
    ).fetchall()
    archive_ids = {r[0] for r in archive_rows}
    archive_weights: dict[str, dict[str, float]] = {}
    for aid, cid, weight in archive_rows:
        if aid not in archive_weights:
            archive_weights[aid] = {}
        archive_weights[aid][cid] = max(archive_weights[aid].get(cid, 0.0), weight)

    dir_ids = {
        r[0]
        for r in db.execute(
            "SELECT account_id FROM tpot_directory_holdout WHERE account_id IS NOT NULL"
        ).fetchall()
    }

    cat1 = archive_ids & dir_ids
    cat2 = dir_ids - archive_ids
    cat3 = archive_ids - dir_ids

    communities = db.execute(
        """SELECT c.id, c.name, COUNT(ca.account_id) as cnt
           FROM community c
           LEFT JOIN community_account ca ON ca.community_id = c.id
           GROUP BY c.id ORDER BY cnt DESC"""
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


def build_graph() -> tuple[sp.csr_matrix, np.ndarray]:
    """Build engagement-weighted adjacency matrix from archive DB.

    Identical logic to propagate_community_labels.build_adjacency_from_archive.
    Returns (adjacency, node_ids_array).
    """
    db = sqlite3.connect(str(DB_PATH))

    print("  Loading follow edges from account_following...")
    follows = db.execute(
        "SELECT account_id, following_account_id FROM account_following"
    ).fetchall()
    all_nodes = sorted({r[0] for r in follows} | {r[1] for r in follows})
    node_idx = {nid: i for i, nid in enumerate(all_nodes)}
    n = len(all_nodes)
    print(f"  Nodes: {n:,}   Follow edges: {len(follows):,}")

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
            i = node_idx.get(src)
            j = node_idx.get(tgt)
            if i is not None and j is not None:
                w = 1.0 if follow else 0.0
                w += 0.6 * min(rts / 10, 1.0) if rts else 0.0
                w += 0.4 * min(likes / 50, 1.0) if likes else 0.0
                w += 0.2 * min(replies / 5, 1.0) if replies else 0.0
                if w > 0:
                    er.append(i); ec.append(j); ev.append(w)
        if ev:
            enrich = sp.csr_matrix(
                (np.array(ev, dtype=np.float32), (er, ec)), shape=(n, n)
            )
            adj = adj.maximum(enrich).tocsr()
            print(f"  Enriched {len(ev):,} edges with engagement weights")
    except Exception as e:
        print(f"  Warning: engagement enrichment skipped: {e}")

    db.close()
    return adj, np.array(all_nodes)


def build_laplacian(adj: sp.csr_matrix) -> tuple[sp.csr_matrix, np.ndarray]:
    """Symmetrize adjacency and return (Laplacian, degrees). Computed once."""
    sym = adj.maximum(adj.T).tocsr()
    sym.setdiag(0.0)
    sym.eliminate_zeros()
    degrees = np.asarray(sym.sum(axis=1)).flatten()
    return sp.diags(degrees, format="csr") - sym, degrees


# ── Boundary condition building ───────────────────────────────────────────────

def build_boundary(
    node_ids: np.ndarray,
    seed_ids: set[str],
    archive_weights: dict,
    community_ids: list[str],
    eligibility: dict,
) -> tuple[np.ndarray, np.ndarray]:
    """Build (labeled_indices, boundary_matrix) for a given seed set.

    Applies inverse-sqrt class balancing and seed eligibility concentration,
    matching the logic in propagate_community_labels.load_community_labels.
    """
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    K = len(community_ids)
    cid_to_col = {cid: i for i, cid in enumerate(community_ids)}

    comm_sizes = np.zeros(K, dtype=np.float64)
    for aid in seed_ids:
        weights = archive_weights.get(aid, {})
        if weights:
            col = cid_to_col.get(max(weights, key=weights.get))
            if col is not None:
                comm_sizes[col] += 1

    balance = np.ones(K, dtype=np.float64)
    for col in range(K):
        if comm_sizes[col] > 0:
            balance[col] = 1.0 / np.sqrt(comm_sizes[col])
    if balance.max() > 0:
        balance /= balance.max()

    labeled_list: list[int] = []
    boundary_list: list[np.ndarray] = []

    for aid in sorted(seed_ids):
        idx = id_to_idx.get(aid)
        weights = archive_weights.get(aid, {})
        if idx is None or not weights:
            continue

        raw = np.zeros(K, dtype=np.float64)
        for cid, w in weights.items():
            col = cid_to_col.get(cid)
            if col is not None:
                raw[col] = max(raw[col], w)

        balanced = raw * balance
        if balanced.sum() > 1.0:
            balanced /= balanced.sum()

        balanced *= eligibility.get(aid, 1.0)

        row = np.empty(K + 1, dtype=np.float64)
        row[:K] = balanced
        row[K] = max(0.0, 1.0 - balanced.sum())
        labeled_list.append(idx)
        boundary_list.append(row)

    if not labeled_list:
        raise ValueError("No seed accounts found in graph")

    return np.array(labeled_list, dtype=np.int64), np.array(boundary_list, dtype=np.float64)


# ── Propagation solve ─────────────────────────────────────────────────────────

def solve(
    laplacian: sp.csr_matrix,
    degrees: np.ndarray,
    labeled_indices: np.ndarray,
    boundary: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Harmonic label propagation via conjugate gradient.

    Returns (memberships: (n_nodes, K+1), labeled_mask: (n_nodes,) bool).
    """
    n_nodes = laplacian.shape[0]
    K_plus_1 = boundary.shape[1]
    K = K_plus_1 - 1

    labeled_mask = np.zeros(n_nodes, dtype=bool)
    labeled_mask[labeled_indices] = True
    unlabeled_idx = np.flatnonzero(~labeled_mask)
    low_degree = (degrees < MIN_DEGREE) & ~labeled_mask

    l_uu = laplacian[np.ix_(unlabeled_idx, unlabeled_idx)].tocsr()
    l_ul = laplacian[np.ix_(unlabeled_idx, labeled_indices)].tocsr()
    l_uu = l_uu + REGULARIZATION * sp.eye(len(unlabeled_idx), format="csr")

    memberships = np.zeros((n_nodes, K_plus_1), dtype=np.float64)
    memberships[labeled_indices] = boundary

    for c in range(K_plus_1):
        rhs = -(l_ul @ boundary[:, c])
        solution, _ = cg(l_uu, rhs, tol=CG_TOL, maxiter=MAX_CG_ITER)
        memberships[unlabeled_idx, c] = solution

    memberships = np.clip(memberships, 0.0, None)
    row_sums = memberships.sum(axis=1, keepdims=True)
    memberships /= np.where(row_sums > 0, row_sums, 1.0)
    memberships[labeled_indices] = boundary
    memberships[low_degree, :K] = 0.0
    memberships[low_degree, K] = 1.0

    return memberships, labeled_mask


# ── Evaluation ────────────────────────────────────────────────────────────────

def measure_recall(
    memberships: np.ndarray,
    node_idx: dict[str, int],
    eval_accounts: set[str],
    labeled_mask: np.ndarray,
) -> dict:
    """Recall of propagation on eval_accounts.

    "Found" = in graph, not a seed this iteration, max community weight >= RECALL_THRESHOLD.
    """
    found = missed = not_in_graph = 0
    for aid in eval_accounts:
        idx = node_idx.get(aid)
        if idx is None:
            not_in_graph += 1
            continue
        if labeled_mask[idx]:
            continue  # this account is a seed this iteration
        if float(memberships[idx, :-1].max()) >= RECALL_THRESHOLD:
            found += 1
        else:
            missed += 1
    total = found + missed
    return {
        "found": found, "missed": missed,
        "not_in_graph": not_in_graph, "total_in_graph": total,
        "recall": found / total if total > 0 else 0.0,
    }


# ── Bootstrap holdout split ───────────────────────────────────────────────────

def stratified_holdout(
    cat1: set[str],
    archive_weights: dict,
    community_ids: list[str],
    frac: float,
    rng: np.random.RandomState,
) -> tuple[set[str], set[str]]:
    """Hold out `frac` of Cat 1, stratified by dominant community."""
    cid_to_col = {cid: i for i, cid in enumerate(community_ids)}
    groups: dict[int, list[str]] = {}
    for aid in cat1:
        weights = archive_weights.get(aid, {})
        col = cid_to_col.get(max(weights, key=weights.get), -1) if weights else -1
        groups.setdefault(col, []).append(aid)

    holdout: set[str] = set()
    for members in groups.values():
        n_hold = min(max(1, int(len(members) * frac)), max(1, len(members) // 2))
        rng.shuffle(members)
        holdout.update(members[:n_hold])

    return cat1 - holdout, holdout


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap CV for propagation generalization.")
    parser.add_argument("--n-iter", type=int, default=5)
    parser.add_argument("--holdout-frac", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    print("=" * 72)
    print("BOOTSTRAP CROSS-VALIDATION — PROPAGATION GENERALIZATION")
    print("=" * 72)
    print(f"  Iterations:        {args.n_iter}")
    print(f"  Holdout fraction:  {args.holdout_frac:.0%} of Cat 1 per iteration")
    print(f"  Recall threshold:  >= {RECALL_THRESHOLD}")
    print()

    print("Loading categories...")
    cat1, cat2, cat3, archive_weights, community_ids, community_names, eligibility = load_categories()
    print(f"  Cat 1 (archive ∩ directory): {len(cat1)}")
    print(f"  Cat 2 (directory only):      {len(cat2)}")
    print(f"  Cat 3 (archive only):        {len(cat3)}")
    print()

    if len(cat1) < 10:
        print("ERROR: Too few Cat 1 accounts for meaningful cross-validation.")
        return

    print("Building graph from archive DB (computed once)...")
    t0 = time.perf_counter()
    adj, node_ids = build_graph()
    node_idx = {nid: i for i, nid in enumerate(node_ids)}
    laplacian, degrees = build_laplacian(adj)
    print(f"  Graph + Laplacian built in {time.perf_counter() - t0:.1f}s")

    cat2_in_graph = sum(1 for aid in cat2 if aid in node_idx)
    print(f"  Cat 2 in graph: {cat2_in_graph} / {len(cat2)} "
          f"({cat2_in_graph / max(len(cat2), 1) * 100:.0f}%)")
    print()

    recalls_cat1, recalls_cat2, recalls_comb = [], [], []
    iter_times = []

    for it in range(args.n_iter):
        rng = np.random.RandomState(args.seed + it)
        cat1_train, cat1_holdout = stratified_holdout(
            cat1, archive_weights, community_ids, args.holdout_frac, rng
        )
        print(f"Iteration {it + 1}/{args.n_iter}:  "
              f"seeds={len(cat1_train)} Cat1 + {len(cat3)} Cat3,  "
              f"holdout={len(cat1_holdout)} Cat1")

        t_iter = time.perf_counter()
        labeled_indices, boundary = build_boundary(
            node_ids, cat1_train | cat3, archive_weights, community_ids, eligibility
        )
        memberships, labeled_mask = solve(laplacian, degrees, labeled_indices, boundary)

        r1 = measure_recall(memberships, node_idx, cat1_holdout, labeled_mask)
        r2 = measure_recall(memberships, node_idx, cat2, labeled_mask)
        rc = measure_recall(memberships, node_idx, cat1_holdout | cat2, labeled_mask)
        elapsed = time.perf_counter() - t_iter
        iter_times.append(elapsed)

        print(f"  Held-out Cat1: {r1['recall']:.1%}  "
              f"({r1['found']}/{r1['total_in_graph']} in-graph, {r1['not_in_graph']} not in graph)")
        print(f"  Cat 2:         {r2['recall']:.1%}  "
              f"({r2['found']}/{r2['total_in_graph']} in-graph, {r2['not_in_graph']} not in graph)")
        print(f"  Combined:      {rc['recall']:.1%}  ({rc['found']}/{rc['total_in_graph']})")
        print(f"  Time: {elapsed:.1f}s")
        print()

        recalls_cat1.append(r1["recall"])
        recalls_cat2.append(r2["recall"])
        recalls_comb.append(rc["recall"])

    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)

    def _s(vals: list[float]) -> str:
        a = np.array(vals)
        return f"{a.mean():.1%} ± {a.std():.1%}  [min={a.min():.1%}  max={a.max():.1%}]"

    print(f"  Held-out Cat 1 recall: {_s(recalls_cat1)}")
    print(f"  Cat 2 recall:          {_s(recalls_cat2)}")
    print(f"  Combined recall:       {_s(recalls_comb)}")
    print(f"  Mean iteration time:   {np.mean(iter_times):.1f}s")
    print()

    cat2_mean = float(np.mean(recalls_cat2))
    if cat2_mean < 0.10:
        print("  CAT 2 RECALL IS LOW (<10%)")
        print("  Most directory accounts are not reachable in the current follow graph.")
        print("  Highest ROI fix: fetch following lists for top frontier accounts (API enrichment).")
    elif cat2_mean < 0.30:
        print("  Cat 2 recall is moderate (10-30%).")
        print("  Frontier enrichment + mention/quote graph integration would improve coverage.")
    else:
        print("  Cat 2 recall is healthy (>=30%).")
        print("  Propagation is reaching directory-only accounts via the follow graph.")


if __name__ == "__main__":
    main()
