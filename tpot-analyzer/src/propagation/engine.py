"""Core propagation solver — harmonic label propagation via conjugate gradient.

Mathematical formulation:
  For each class c in {community_1, ..., community_K, none}:
    f_U^c = -(L_UU + reg*I)^{-1} * (L_UL * f_L^c - reg * prior)

  where L is the graph Laplacian (D - W), U = unlabeled indices,
  L = labeled indices, f_L^c = boundary conditions for class c.
"""
from __future__ import annotations

import sqlite3
import time

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import cg

from src.config import DEFAULT_ARCHIVE_DB
from src.propagation.types import PropagationConfig, PropagationResult


def multiclass_entropy(memberships: np.ndarray) -> np.ndarray:
    """Shannon entropy of each row, normalized to [0, 1] by log2(n_classes)."""
    n_classes = memberships.shape[1]
    p = np.clip(memberships, 1e-10, 1.0)
    raw_entropy = -np.sum(p * np.log2(p), axis=1)
    max_entropy = np.log2(n_classes)
    return raw_entropy / max_entropy if max_entropy > 0 else raw_entropy


class _IterationCounter:
    """Callback for scipy CG solver to count iterations."""
    def __init__(self) -> None:
        self.count = 0
    def __call__(self, _xk: np.ndarray) -> None:
        self.count += 1


def load_community_labels(
    node_ids: np.ndarray,
    config: PropagationConfig,
    holdout_fraction: float = 0.0,
    holdout_seed: int = 42,
    seed_eligibility: bool = True,
    db_path=None,
) -> tuple[np.ndarray, np.ndarray, list[str], list[str], list[str], dict | None]:
    """Load community assignments from DB and build boundary condition matrix.

    The boundary matrix has K+1 columns: one per community + one "none" column.
    Each labeled node gets its NMF-derived weights (0-1 per community), optionally
    class-balanced. The "none" column is the residual (1 - sum of community weights).

    Args:
        node_ids: Array of node IDs matching graph matrix rows.
        config: Propagation config.
        holdout_fraction: Fraction of labeled accounts to hold out per community
            for threshold calibration (0 = no holdout, use all seeds).
        holdout_seed: Random seed for reproducible holdout split.
        seed_eligibility: Whether to weight seeds by concentration.
        db_path: Path to archive_tweets.db. Defaults to DEFAULT_ARCHIVE_DB.

    Returns:
        boundary_matrix: (n_labeled, K+1) soft membership boundary conditions
        labeled_indices: (n_labeled,) indices into node_ids array
        community_ids, community_names, community_colors: metadata lists
        holdout_info: dict with holdout account IDs and their community assignments
            (None if holdout_fraction == 0)
    """
    if db_path is None:
        db_path = DEFAULT_ARCHIVE_DB

    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

    conn = sqlite3.connect(str(db_path))
    try:
        # Communities ordered by member count (descending) for consistent column order
        communities = conn.execute(
            """SELECT c.id, c.name, c.color, COUNT(ca.account_id) as cnt
               FROM community c
               LEFT JOIN community_account ca ON ca.community_id = c.id
               GROUP BY c.id ORDER BY cnt DESC"""
        ).fetchall()

        community_ids = [r[0] for r in communities]
        community_names = [r[1] for r in communities]
        community_colors = [r[2] or "#888888" for r in communities]
        community_sizes = [r[3] for r in communities]
        cid_to_col = {cid: i for i, cid in enumerate(community_ids)}
        K = len(community_ids)

        # All account-community assignments (includes multi-community memberships)
        rows = conn.execute(
            "SELECT community_id, account_id, weight FROM community_account"
        ).fetchall()
    finally:
        conn.close()

    # Build per-account weight vectors (accounts can be in multiple communities)
    account_weights: dict[str, np.ndarray] = {}
    for cid, aid, weight in rows:
        if aid not in id_to_idx:
            continue  # account not in graph snapshot
        if aid not in account_weights:
            account_weights[aid] = np.zeros(K, dtype=np.float64)
        col = cid_to_col[cid]
        # Take max weight if multiple entries for same (account, community)
        account_weights[aid][col] = max(account_weights[aid][col], weight)

    # --- Holdout split (stratified by dominant community) ---
    holdout_info = None
    if holdout_fraction > 0:
        rng = np.random.RandomState(holdout_seed)
        # Group accounts by their dominant community
        community_groups: dict[int, list[str]] = {i: [] for i in range(K)}
        for aid, weights in account_weights.items():
            dominant = int(np.argmax(weights))
            community_groups[dominant].append(aid)

        holdout_accounts: set[str] = set()
        holdout_assignments: dict[str, dict] = {}  # aid -> {community_id, community_name, weights}
        for col_idx, members in community_groups.items():
            n_holdout = max(1, int(len(members) * holdout_fraction))
            # Don't hold out more than half — keep at least some train seeds per community
            n_holdout = min(n_holdout, len(members) // 2)
            if n_holdout > 0:
                rng.shuffle(members)
                for aid in members[:n_holdout]:
                    holdout_accounts.add(aid)
                    holdout_assignments[aid] = {
                        "dominant_community_id": community_ids[col_idx],
                        "dominant_community_name": community_names[col_idx],
                        "weights": account_weights[aid].tolist(),
                    }

        # Remove holdout accounts from the training set
        for aid in holdout_accounts:
            del account_weights[aid]

        holdout_info = {
            "holdout_fraction": holdout_fraction,
            "holdout_seed": holdout_seed,
            "n_holdout": len(holdout_accounts),
            "n_train": len(account_weights),
            "accounts": holdout_assignments,
        }
        print(f"Holdout split: {len(holdout_accounts)} holdout, {len(account_weights)} train "
              f"(fraction={holdout_fraction}, seed={holdout_seed})")
        for col_idx in range(K):
            n_in_holdout = sum(
                1 for a in holdout_assignments.values()
                if a["dominant_community_name"] == community_names[col_idx]
            )
            n_in_train = len(community_groups[col_idx]) - n_in_holdout
            print(f"  {community_names[col_idx]:30s}: {n_in_train} train, {n_in_holdout} holdout")

    # Class balancing: inverse-sqrt of community size.
    balance_weights = np.ones(K, dtype=np.float64)
    if config.class_balance:
        for i, size in enumerate(community_sizes):
            if size > 0:
                balance_weights[i] = 1.0 / np.sqrt(size)
        balance_weights /= balance_weights.max()  # normalize so max = 1

    # Build boundary matrix: K community columns + 1 "none" column
    labeled_accounts = sorted(account_weights.keys())
    labeled_indices = np.array([id_to_idx[aid] for aid in labeled_accounts], dtype=np.int64)
    n_labeled = len(labeled_indices)

    boundary = np.zeros((n_labeled, K + 1), dtype=np.float64)
    for i, aid in enumerate(labeled_accounts):
        raw = account_weights[aid]
        balanced = raw * balance_weights
        # Cap total community weight at 1.0 (can exceed due to multi-membership)
        total = balanced.sum()
        if total > 1.0:
            balanced /= total
        boundary[i, :K] = balanced
        boundary[i, K] = max(0.0, 1.0 - balanced.sum())

    # Seed eligibility: weight boundary conditions by concentration
    if seed_eligibility:
        try:
            conn2 = sqlite3.connect(str(db_path))
            eligibility = dict(conn2.execute(
                "SELECT account_id, concentration FROM seed_eligibility"
            ).fetchall())
            conn2.close()

            weighted = 0
            for i, aid in enumerate(labeled_accounts):
                conc = eligibility.get(aid, 1.0)
                boundary[i, :K] *= conc
                boundary[i, K] = max(0.0, 1.0 - boundary[i, :K].sum())
                if conc < 1.0:
                    weighted += 1

            if weighted > 0:
                print(f"Seed eligibility: {weighted} seeds weighted by concentration")
        except Exception as e:
            print(f"Seed eligibility table not found, using uniform weighting: {e}")

    return boundary, labeled_indices, community_ids, community_names, community_colors, holdout_info


def propagate(
    adjacency: sp.csr_matrix,
    node_ids: np.ndarray,
    config: PropagationConfig,
    holdout_fraction: float = 0.0,
    holdout_seed: int = 42,
    seed_eligibility: bool = True,
    db_path=None,
) -> tuple[PropagationResult, dict | None]:
    """Run multi-class harmonic label propagation.

    Args:
        adjacency: Sparse adjacency matrix (n_nodes x n_nodes).
        node_ids: Array of account IDs matching adjacency rows.
        config: Propagation parameters.
        holdout_fraction: Fraction of seeds to hold out for calibration.
        holdout_seed: Random seed for holdout.
        seed_eligibility: Whether to weight seeds by concentration.
        db_path: Path to archive_tweets.db. Defaults to DEFAULT_ARCHIVE_DB.

    Returns:
        (PropagationResult, holdout_info_or_None)
    """
    n_nodes = adjacency.shape[0]

    # Load boundary conditions from community database
    boundary, labeled_idx, community_ids, community_names, community_colors, holdout_info = (
        load_community_labels(
            node_ids, config,
            holdout_fraction=holdout_fraction,
            holdout_seed=holdout_seed,
            seed_eligibility=seed_eligibility,
            db_path=db_path,
        )
    )
    K = len(community_ids)
    n_classes = K + 1  # K communities + "none"

    print(f"Nodes: {n_nodes:,}")
    print(f"Labeled (in graph): {len(labeled_idx)}")
    print(f"Communities: {K}")
    print(f"Classes (incl. none): {n_classes}")

    # Symmetrize: max(A, A^T) treats "I follow you" = "you follow me".
    sym = adjacency.maximum(adjacency.T).tocsr()
    sym.setdiag(0.0)
    sym.eliminate_zeros()

    degrees = np.asarray(sym.sum(axis=1)).flatten()

    # Graph Laplacian: L = D - W
    laplacian = sp.diags(degrees, format="csr") - sym

    # Partition into labeled / unlabeled
    labeled_mask = np.zeros(n_nodes, dtype=bool)
    labeled_mask[labeled_idx] = True
    unlabeled_idx = np.flatnonzero(~labeled_mask)
    n_unlabeled = len(unlabeled_idx)

    print(f"Unlabeled: {n_unlabeled:,}")

    # Low-degree nodes: will be overridden to "none" after solve.
    low_degree_unlabeled = (degrees < config.min_degree_for_assignment) & ~labeled_mask
    n_low_degree = low_degree_unlabeled.sum()
    print(f"Low-degree (< {config.min_degree_for_assignment}) auto-none: {n_low_degree:,}")

    # Initialize membership matrix
    memberships = np.full((n_nodes, n_classes), config.prior / n_classes, dtype=np.float64)
    memberships[labeled_idx] = boundary

    # Extract Laplacian sub-matrices for the harmonic solve
    print("Building Laplacian sub-matrices...")
    t0 = time.perf_counter()
    l_uu = laplacian[np.ix_(unlabeled_idx, unlabeled_idx)].tocsr()
    l_ul = laplacian[np.ix_(unlabeled_idx, labeled_idx)].tocsr()

    # Tikhonov regularization: makes L_UU positive definite (required for CG)
    if config.regularization > 0:
        l_uu = l_uu + config.regularization * sp.eye(n_unlabeled, format="csr")

    t_setup = time.perf_counter() - t0
    print(f"Sub-matrix setup: {t_setup:.2f}s")
    print(f"L_UU: shape={l_uu.shape}, nnz={l_uu.nnz:,}")

    # Solve for each class independently.
    converged_list = []
    iterations_list = []

    t_solve_start = time.perf_counter()
    for c in range(n_classes):
        class_name = community_names[c] if c < K else "__none__"

        # RHS = -(L_UL * f_L^c) + reg * prior
        rhs = -(l_ul @ boundary[:, c])
        if config.regularization > 0:
            rhs += config.regularization * (config.prior / n_classes)

        counter = _IterationCounter()
        solution, info = cg(
            l_uu, rhs,
            tol=config.tolerance,
            maxiter=config.max_iter,
            callback=counter,
        )
        conv = info == 0
        converged_list.append(conv)
        iterations_list.append(counter.count)
        memberships[unlabeled_idx, c] = solution

        status = "ok" if conv else f"NOT converged (info={info})"
        print(f"  Class {c:2d} ({class_name:25s}): {counter.count:4d} iters, {status}")

    t_solve = time.perf_counter() - t_solve_start
    print(f"Total solve time: {t_solve:.2f}s")

    # Post-processing: clip, scale, normalize
    memberships = np.clip(memberships, 0.0, None)

    seed_neighbor_counts = None

    if config.mode == "independent":
        # ═══ INDEPENDENT MODE (Approach C + E) ═══
        print("  Post-processing: independent mode (raw scores + seed-neighbor counts)")

        seed_neighbor_counts = np.zeros((n_nodes, K), dtype=np.int32)
        for li in labeled_idx:
            li_boundary_idx = np.where(labeled_idx == li)[0][0]
            neighbors = sym[li].nonzero()[1]
            for c in range(K):
                if boundary[li_boundary_idx, c] > 0:
                    seed_neighbor_counts[neighbors, c] += 1

        print(f"  Seed-neighbor counts computed for {len(labeled_idx)} seeds")

        memberships[labeled_idx] = boundary

        memberships[low_degree_unlabeled, :] = 0.0
        seed_neighbor_counts[low_degree_unlabeled, :] = 0

        degree_uncertainty = 1.0 / np.sqrt(degrees + 1.0)
        degree_uncertainty /= degree_uncertainty.max()
        uncertainty = np.clip(degree_uncertainty, 0.0, 1.0)
        uncertainty[labeled_idx] = 0.0

        raw_row_sums = memberships.sum(axis=1, keepdims=True)
        raw_row_sums = np.where(raw_row_sums > 0, raw_row_sums, 1.0)
        entropy = multiclass_entropy(memberships / raw_row_sums)

        max_raw_score = memberships[:, :K].max(axis=1)
        max_seed_neighbors = seed_neighbor_counts.max(axis=1)
        abstain_mask = (
            (max_raw_score < 1e-6)
            | (max_seed_neighbors < 1)
        ) & ~labeled_mask

    else:
        # ═══ CLASSIC MODE ═══
        if config.temperature != 1.0:
            scaled = memberships ** (1.0 / config.temperature)
            row_sums = scaled.sum(axis=1, keepdims=True)
            row_sums = np.where(row_sums > 0, row_sums, 1.0)
            memberships = scaled / row_sums
        else:
            row_sums = memberships.sum(axis=1, keepdims=True)
            row_sums = np.where(row_sums > 0, row_sums, 1.0)
            memberships = memberships / row_sums

        memberships[labeled_idx] = boundary

        memberships[low_degree_unlabeled, :K] = 0.0
        memberships[low_degree_unlabeled, K] = 1.0

        entropy = multiclass_entropy(memberships)
        degree_uncertainty = 1.0 / np.sqrt(degrees + 1.0)
        degree_uncertainty /= degree_uncertainty.max()

        uncertainty = 0.7 * entropy + 0.3 * degree_uncertainty
        uncertainty = np.clip(uncertainty, 0.0, 1.0)
        uncertainty[labeled_idx] = 0.0

        max_community_weight = memberships[:, :K].max(axis=1)
        abstain_mask = (
            (max_community_weight < config.abstain_max_threshold)
            | (uncertainty > config.abstain_uncertainty_threshold)
        ) & ~labeled_mask

    result = PropagationResult(
        memberships=memberships,
        uncertainty=uncertainty,
        entropy=entropy,
        abstain_mask=abstain_mask,
        community_ids=community_ids,
        community_names=community_names,
        community_colors=community_colors,
        node_ids=node_ids,
        labeled_mask=labeled_mask,
        converged=converged_list,
        cg_iterations=iterations_list,
        config=config,
        solve_time_seconds=t_solve,
        seed_neighbor_counts=seed_neighbor_counts,
    )
    return result, holdout_info
