"""Core propagation solver — Directed Personalized PageRank (PPR) + Lift.

Mathematical formulation:
  Instead of solving the symmetric Laplacian, we compute Directed PPR on the 
  weighted adjacency matrix. 
  
  PPR_c = (1 - alpha) * P^T * PPR_c + alpha * f_L^c
  
  where P is the row-stochastic transition matrix (D_out^-1 * A).
  
  To solve the "hub penalty" (where mega-accounts absorb all probability mass),
  we normalize against a Null Model (Global PageRank):
  
  Lift_c = PPR_c / Global_PR
  
  This isolates the *specific* community affinity from the *general* popularity.
"""
from __future__ import annotations

import sqlite3
import time
import warnings

import numpy as np
import scipy.sparse as sp

from src.config import DEFAULT_ARCHIVE_DB
from src.propagation.types import PropagationConfig, PropagationResult


def multiclass_entropy(memberships: np.ndarray) -> np.ndarray:
    """Shannon entropy of each row, normalized to [0, 1] by log2(n_classes)."""
    n_classes = memberships.shape[1]
    p = np.clip(memberships, 1e-10, 1.0)
    # Normalize rows to sum to 1 for entropy calculation
    row_sums = p.sum(axis=1, keepdims=True)
    row_sums = np.where(row_sums > 0, row_sums, 1.0)
    p = p / row_sums
    
    raw_entropy = -np.sum(p * np.log2(p), axis=1)
    max_entropy = np.log2(n_classes)
    return raw_entropy / max_entropy if max_entropy > 0 else raw_entropy


def compute_ppr(
    adj: sp.csr_matrix,
    teleport_vector: np.ndarray | None = None,
    alpha: float = 0.15,
    max_iter: int = 200,
    tol: float = 1e-6
) -> tuple[np.ndarray, int, bool]:
    """Compute Directed Personalized PageRank via Power Iteration.
    
    Args:
        adj: Sparse adjacency matrix (n_nodes x n_nodes).
        teleport_vector: Vector of restart probabilities. If None, uniform (Global PR).
        alpha: Teleport probability.
    
    Returns:
        (ppr_vector, iterations, converged)
    """
    n = adj.shape[0]
    
    # We walk backwards to find people who *follow* the community.
    # A_ij means i follows j. We want probability to flow from j to i.
    # So we use adj.T as the transition structure.
    adj_T = adj.T.tocsr()
    
    # Compute out-degrees
    out_degrees = np.array(adj_T.sum(axis=1)).flatten()
    
    # Handle sink nodes (nodes with 0 out-degree in the reversed graph, i.e., no followers)
    # They will artificially drain probability mass. We add a small epsilon or self-loop.
    out_degrees[out_degrees == 0] = 1.0
    
    # Transition matrix P (row stochastic)
    inv_D = sp.diags(1.0 / out_degrees)
    P = inv_D @ adj_T
    
    # Transpose for power iteration: x_{k+1} = (1-alpha) P^T x_k + alpha * v
    PT = P.T.tocsr()
    
    if teleport_vector is None:
        v = np.ones(n, dtype=np.float64) / n
    else:
        v = teleport_vector.astype(np.float64).copy()
        v_sum = v.sum()
        if v_sum > 0:
            v /= v_sum
        else:
            v = np.ones(n, dtype=np.float64) / n
            
    x = v.copy()
    
    converged = False
    iters = 0
    for i in range(max_iter):
        x_next = (1 - alpha) * (PT @ x) + alpha * v
            
        diff = np.linalg.norm(x_next - x, ord=1)
        x = x_next
        iters += 1
        if diff < tol:
            converged = True
            break
            
    return x, iters, converged


def load_community_labels(
    node_ids: np.ndarray,
    config: PropagationConfig,
    holdout_fraction: float = 0.0,
    holdout_seed: int = 42,
    seed_eligibility: bool = True,
    db_path=None,
) -> tuple[np.ndarray, np.ndarray, list[str], list[str], list[str], dict | None, np.ndarray]:
    if db_path is None:
        db_path = DEFAULT_ARCHIVE_DB

    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

    conn = sqlite3.connect(str(db_path))
    try:
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

        rows = conn.execute(
            "SELECT community_id, account_id, weight FROM community_account"
        ).fetchall()
    finally:
        conn.close()

    account_weights: dict[str, np.ndarray] = {}
    for cid, aid, weight in rows:
        if aid not in id_to_idx:
            continue
        if aid not in account_weights:
            account_weights[aid] = np.zeros(K, dtype=np.float64)
        col = cid_to_col[cid]
        account_weights[aid][col] = max(account_weights[aid][col], weight)

    holdout_info = None
    if holdout_fraction > 0:
        rng = np.random.RandomState(holdout_seed)
        community_groups: dict[int, list[str]] = {i: [] for i in range(K)}
        for aid, weights in account_weights.items():
            dominant = int(np.argmax(weights))
            community_groups[dominant].append(aid)

        holdout_accounts: set[str] = set()
        holdout_assignments: dict[str, dict] = {}
        for col_idx, members in community_groups.items():
            n_holdout = max(1, int(len(members) * holdout_fraction))
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

        for aid in holdout_accounts:
            del account_weights[aid]

        holdout_info = {
            "holdout_fraction": holdout_fraction,
            "holdout_seed": holdout_seed,
            "n_holdout": len(holdout_accounts),
            "n_train": len(account_weights),
            "accounts": holdout_assignments,
        }

    balance_weights = np.ones(K, dtype=np.float64)
    if config.class_balance:
        for i, size in enumerate(community_sizes):
            if size > 0:
                balance_weights[i] = 1.0 / np.sqrt(size)
        balance_weights /= balance_weights.max()

    labeled_accounts = sorted(account_weights.keys())
    labeled_indices = np.array([id_to_idx[aid] for aid in labeled_accounts], dtype=np.int64)
    n_labeled = len(labeled_indices)

    boundary = np.zeros((n_labeled, K + 1), dtype=np.float64)
    raw_seed_weights = np.zeros((n_labeled, K), dtype=np.float64)
    
    for i, aid in enumerate(labeled_accounts):
        raw = account_weights[aid]
        raw_seed_weights[i] = raw
        balanced = raw * balance_weights
        total = balanced.sum()
        if total > 1.0:
            balanced /= total
        boundary[i, :K] = balanced
        boundary[i, K] = max(0.0, 1.0 - balanced.sum())

    if seed_eligibility:
        try:
            conn2 = sqlite3.connect(str(db_path))
            eligibility = dict(conn2.execute(
                "SELECT account_id, concentration FROM seed_eligibility"
            ).fetchall())
            conn2.close()

            for i, aid in enumerate(labeled_accounts):
                conc = eligibility.get(aid, 1.0)
                boundary[i, :K] *= conc
                boundary[i, K] = max(0.0, 1.0 - boundary[i, :K].sum())
        except Exception:
            pass

    return boundary, labeled_indices, community_ids, community_names, community_colors, holdout_info, raw_seed_weights


def propagate(
    adjacency: sp.csr_matrix,
    node_ids: np.ndarray,
    config: PropagationConfig,
    holdout_fraction: float = 0.0,
    holdout_seed: int = 42,
    seed_eligibility: bool = True,
    db_path=None,
) -> tuple[PropagationResult, dict | None]:
    """Run Directed PPR + Lift label propagation."""
    n_nodes = adjacency.shape[0]

    boundary, labeled_idx, community_ids, community_names, community_colors, holdout_info, raw_seed_weights = (
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

    labeled_mask = np.zeros(n_nodes, dtype=bool)
    labeled_mask[labeled_idx] = True

    # High-degree filtering: using both out-degree and in-degree
    out_deg = np.asarray(adjacency.sum(axis=1)).flatten()
    in_deg = np.asarray(adjacency.sum(axis=0)).flatten()
    degrees = out_deg + in_deg
    low_degree_unlabeled = (degrees < config.min_degree_for_assignment) & ~labeled_mask

    print("\nComputing Global PageRank (Null Model)...")
    t0 = time.perf_counter()
    global_pr, g_iters, g_conv = compute_ppr(adjacency, teleport_vector=None, alpha=0.15)
    print(f"Global PR: {g_iters} iters, {time.perf_counter() - t0:.2f}s")
    
    # Avoid division by zero when calculating Lift
    global_pr = np.clip(global_pr, 1e-12, None)

    memberships = np.zeros((n_nodes, n_classes), dtype=np.float64)
    converged_list = []
    iterations_list = []

    print("\nComputing Directed PPR per community...")
    t_solve_start = time.perf_counter()
    
    for c in range(n_classes):
        class_name = community_names[c] if c < K else "__none__"
        
        teleport = np.zeros(n_nodes, dtype=np.float64)
        teleport[labeled_idx] = boundary[:, c]
        
        if teleport.sum() == 0:
            warnings.warn(f"Community {class_name} has 0 boundary weight! Skipping.")
            memberships[:, c] = 0.0
            converged_list.append(True)
            iterations_list.append(0)
            continue

        ppr_c, iters, conv = compute_ppr(adjacency, teleport_vector=teleport, alpha=0.15)
        
        # Lift = PPR_c / Global_PR
        lift_c = ppr_c / global_pr
        
        memberships[:, c] = lift_c
        converged_list.append(conv)
        iterations_list.append(iters)

        status = "ok" if conv else "NOT converged"
        print(f"  Class {c:2d} ({class_name:25s}): {iters:4d} iters, max lift = {lift_c.max():.1f}x")

    t_solve = time.perf_counter() - t_solve_start
    print(f"Total solve time: {t_solve:.2f}s")

    seed_neighbor_counts = None
    if config.mode == "independent":
        print("  Post-processing: independent mode (Lift scores + seed-neighbor counts)")
        
        seed_neighbor_counts = np.zeros((n_nodes, K), dtype=np.int32)
        # Using undirected adjacency for seed neighbors to maintain compatibility
        sym = adjacency.maximum(adjacency.T).tocsr()
        sym.setdiag(0.0)
        sym.eliminate_zeros()
        
        for li_pos, li in enumerate(labeled_idx):
            neighbors = sym[li].nonzero()[1]
            for c in range(K):
                if raw_seed_weights[li_pos, c] > 0:
                    seed_neighbor_counts[neighbors, c] += 1

        memberships[low_degree_unlabeled, :] = 0.0
        seed_neighbor_counts[low_degree_unlabeled, :] = 0

        uncertainty = np.zeros(n_nodes)  # Lift naturally handles uncertainty
        entropy = multiclass_entropy(memberships)

        max_raw_score = memberships[:, :K].max(axis=1)
        max_seed_neighbors = seed_neighbor_counts.max(axis=1)
        # For now, default abstain logic. We will tune this via veil CV.
        abstain_mask = (
            (max_raw_score < 1.0)
            | (max_seed_neighbors < 1)
        ) & ~labeled_mask

    else:
        # Classic mode (Scale to 1.0)
        row_sums = memberships.sum(axis=1, keepdims=True)
        row_sums = np.where(row_sums > 0, row_sums, 1.0)
        memberships = memberships / row_sums

        memberships[labeled_idx] = boundary
        memberships[low_degree_unlabeled, :K] = 0.0
        memberships[low_degree_unlabeled, K] = 1.0

        entropy = multiclass_entropy(memberships)
        uncertainty = np.zeros(n_nodes)

        max_community_weight = memberships[:, :K].max(axis=1)
        abstain_mask = (max_community_weight < 0.15) & ~labeled_mask

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
