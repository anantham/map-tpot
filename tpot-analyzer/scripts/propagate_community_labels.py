"""
Phase 0 prototype: Multi-class community label propagation (ADR 012).

=== MOTIVATION ===

We have 14 human-curated TPOT communities (274 accounts in the graph).
The graph has ~72K nodes total, but most are periphery (degree-1 leaves).
The question is NOT "assign every node to a community" — it's
"are there anyone among the ~10K core shadow nodes who belong in one of
our 14 communities but we haven't found them yet?"

This script propagates soft community membership from the 274 labeled
core nodes outward through the follow graph, using the harmonic function
(Laplacian-based label propagation). Each shadow node gets a probability
vector over 14 communities + "none". Most nodes will (correctly) end up
as "none" — they're adjacent to TPOT but not part of any sub-community.

=== APPROACH ===

Harmonic function on graphs (Zhu, Ghahramani, Lafferty 2003):
  - Labeled nodes are "boundary conditions" with known community weights
  - Unlabeled nodes are solved for by minimizing Dirichlet energy
  - Solution: f_U = -L_UU^{-1} * L_UL * f_L  (sparse linear solve)
  - Each of the K+1 classes (14 communities + "none") is solved independently

Key design decisions:
  1. CLASS BALANCING: Large communities (73 members) would dominate small ones
     (4 members) without intervention. We apply inverse-sqrt weighting to
     boundary conditions so small communities get proportionally louder signal.

  2. TEMPERATURE SCALING: Raw propagation tends toward winner-take-all.
     Temperature T > 1 flattens the distribution, making multi-community
     membership more visible. T=2 is the default; T=1 is unmodified.

  3. EXPLICIT "NONE" CLASS: The 15th label competes with all communities.
     Nodes far from all labeled nodes naturally get high "none" probability.
     This prevents false certainty — we don't force every node into a community.

  4. ABSTAIN GATE: Even with "none", some nodes have ambiguous propagation.
     If max community membership < threshold OR uncertainty is too high,
     the node is marked "abstain" — genuinely unknown, distinct from "none."

  5. LOW-DEGREE OVERRIDE: Degree-1 nodes (52K+ leaves) are auto-assigned to
     "none". They connect to exactly one other node; propagation would just
     copy that neighbor's label, which isn't meaningful community membership.

  6. SYMMETRIZATION: The follow graph is directional, but we symmetrize for
     propagation (known limitation, see ADR 012 R2). For TPOT's high-reciprocity
     graph, this is a reasonable first approximation.

=== KNOWN LIMITATIONS ===

  - Seed errors propagate: if a community assignment is wrong, nearby shadows
    will inherit that mistake. Mitigation: fast re-propagation (<1 sec) after
    edits, plus uncertainty surfaces the most questionable assignments.
  - Symmetrization loses directionality (who you follow vs who follows you).
  - 274 labeled nodes across 72K is sparse (1:261 ratio). Propagation is only
    meaningful within ~2 hops of labeled nodes.

Usage:
    cd tpot-analyzer
    .venv/bin/python3 -m scripts.propagate_community_labels
    .venv/bin/python3 -m scripts.propagate_community_labels --temperature 1.0
    .venv/bin/python3 -m scripts.propagate_community_labels --save
"""
from __future__ import annotations

import argparse
import json
import pickle  # NOTE: only used to load our own cached adjacency matrix, not untrusted data
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import cg

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "archive_tweets.db"
SPECTRAL_PATH = DATA_DIR / "graph_snapshot.spectral.npz"
ADJACENCY_PATH = DATA_DIR / "adjacency_matrix_cache.pkl"


@dataclass
class PropagationConfig:
    """Tunable parameters for label propagation.

    These defaults are starting guesses — Phase 0 exists to find better values.
    Run the script with different settings and compare diagnostics.
    """
    # Softmax temperature: >1 flattens distribution (reduces winner-take-all),
    # <1 sharpens it. T=2 is conservative; T=1 is raw propagation output.
    temperature: float = 2.0

    # Propagation mode: "classic" = zero-sum (memberships sum to 1),
    # "independent" = each community propagated independently (no sum constraint).
    # Independent mode enables bridge detection — accounts can score high
    # in multiple communities simultaneously.
    mode: str = "classic"

    # Tikhonov regularization added to L_UU diagonal. Prevents singular systems
    # and biases unlabeled nodes toward the prior (stabilizes sparse regions).
    regularization: float = 1e-3

    # Prior probability for unlabeled nodes before solving. 0 = no bias toward
    # any class; positive values bias toward uniform community membership.
    prior: float = 0.0

    # Conjugate gradient solver parameters
    tolerance: float = 1e-6
    max_iter: int = 800

    # Nodes with degree below this are auto-assigned "none". Degree-1 nodes
    # (52K+ leaves) would just copy their single neighbor's label, which
    # isn't meaningful evidence of community membership.
    min_degree_for_assignment: int = 2

    # Abstain gate: two independent thresholds, either triggers abstain.
    # max_threshold: if the highest community weight is below this, abstain.
    # uncertainty_threshold: if combined uncertainty is above this, abstain.
    abstain_max_threshold: float = 0.15
    abstain_uncertainty_threshold: float = 0.6

    # Inverse-sqrt class balancing: without this, "Qualia Research Folks"
    # (73 members) would absorb ~18x more shadows than "AI Art" (4 members)
    # simply due to having more boundary surface.
    class_balance: bool = True


@dataclass
class PropagationResult:
    """Full output of multi-class propagation."""
    memberships: np.ndarray           # (n_nodes, K+1) soft memberships, rows sum to 1
    uncertainty: np.ndarray           # (n_nodes,) combined uncertainty [0, 1]
    entropy: np.ndarray               # (n_nodes,) normalized entropy [0, 1]
    abstain_mask: np.ndarray          # (n_nodes,) bool — below confidence
    community_ids: list[str]          # K community UUIDs (columns 0..K-1)
    community_names: list[str]        # K community names
    community_colors: list[str]       # K community hex colors
    node_ids: np.ndarray              # (n_nodes,) account IDs matching matrix rows
    labeled_mask: np.ndarray          # (n_nodes,) bool — known community members
    converged: list[bool]             # per-class CG convergence
    cg_iterations: list[int]          # per-class CG iteration count
    config: PropagationConfig
    solve_time_seconds: float
    seed_neighbor_counts: np.ndarray | None = None  # (n_nodes, K) int — only in independent mode


def load_adjacency() -> sp.csr_matrix:
    """Load the cached adjacency matrix (built by cluster_routes.py on startup).

    This pickle file contains our own precomputed sparse matrix — it's generated
    from parquet data we control, not from external/untrusted sources.
    """
    with open(ADJACENCY_PATH, "rb") as f:  # noqa: S301 — our own cached data, not untrusted
        cached = pickle.load(f)  # noqa: S301
    if isinstance(cached, dict) and "adjacency" in cached:
        return cached["adjacency"].tocsr()
    return cached.tocsr()


def build_adjacency_from_archive(
    db_path: Path, weighted: bool = True
) -> tuple[sp.csr_matrix, list[str]]:
    """Build adjacency matrix from archive_tweets.db follow + engagement data.

    Returns (adjacency: csr_matrix, node_ids: list[str])

    The graph includes:
    - All follow edges from account_following (binary or engagement-weighted)
    - Edge weights from account_engagement_agg when available and weighted=True

    Weight formula (engagement-enriched):
      base = 1.0 (follow edge)
      + 0.6 * min(rt_count / 10, 1.0)   — retweets signal strong alignment
      + 0.4 * min(like_count / 50, 1.0)  — likes signal weaker agreement
      + 0.2 * min(reply_count / 5, 1.0)  — replies signal interaction
    """
    conn = sqlite3.connect(str(db_path))

    # 1. Get all unique node IDs from the follow graph
    print("  Loading follow edges from account_following...")
    sources = set(
        r[0] for r in conn.execute(
            "SELECT DISTINCT account_id FROM account_following"
        ).fetchall()
    )
    targets = set(
        r[0] for r in conn.execute(
            "SELECT DISTINCT following_account_id FROM account_following"
        ).fetchall()
    )
    all_nodes = sorted(sources | targets)
    node_idx = {nid: i for i, nid in enumerate(all_nodes)}
    n = len(all_nodes)
    print(f"  Unique nodes: {n:,} ({len(sources):,} sources, {len(targets):,} targets)")

    # 2. Build sparse adjacency from follow edges
    follows = conn.execute(
        "SELECT account_id, following_account_id FROM account_following"
    ).fetchall()
    print(f"  Follow edges: {len(follows):,}")

    row_indices = []
    col_indices = []
    data_values = []
    for src, tgt in follows:
        i = node_idx.get(src)
        j = node_idx.get(tgt)
        if i is not None and j is not None:
            row_indices.append(i)
            col_indices.append(j)
            data_values.append(1.0)

    adj = sp.csr_matrix(
        (np.array(data_values, dtype=np.float32), (row_indices, col_indices)),
        shape=(n, n),
    )

    # 3. Enrich with engagement weights (if available and requested)
    if weighted:
        try:
            # Check if table exists
            table_exists = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='account_engagement_agg'"
            ).fetchone()[0]
            if not table_exists:
                print("  Warning: account_engagement_agg table not found, using unweighted follow graph")
            else:
                print("  Loading engagement weights from account_engagement_agg...")
                engagement = conn.execute("""
                    SELECT source_id, target_id, follow_flag, like_count, reply_count, rt_count
                    FROM account_engagement_agg
                """).fetchall()
                print(f"  Engagement pairs: {len(engagement):,}")

                # Build a COO update for enriched weights
                enrich_rows = []
                enrich_cols = []
                enrich_vals = []
                enriched_count = 0
                for src, tgt, follow, likes, replies, rts in engagement:
                    i = node_idx.get(src)
                    j = node_idx.get(tgt)
                    if i is not None and j is not None:
                        w = 1.0 if follow else 0.0
                        w += 0.6 * min(rts / 10, 1.0) if rts else 0
                        w += 0.4 * min(likes / 50, 1.0) if likes else 0
                        w += 0.2 * min(replies / 5, 1.0) if replies else 0
                        if w > 0:
                            enrich_rows.append(i)
                            enrich_cols.append(j)
                            enrich_vals.append(w)
                            enriched_count += 1

                if enrich_vals:
                    enrich_mat = sp.csr_matrix(
                        (np.array(enrich_vals, dtype=np.float32),
                         (enrich_rows, enrich_cols)),
                        shape=(n, n),
                    )
                    # Take element-wise max: enriched weight >= follow-only weight
                    adj = adj.maximum(enrich_mat).tocsr()
                    print(f"  Enriched {enriched_count:,} edges with engagement weights")
        except Exception as e:
            print(f"  Warning: engagement enrichment failed: {e}")

    conn.close()

    print(f"  Archive graph: {n:,} nodes, {adj.nnz:,} edges")
    return adj, all_nodes


def load_community_labels(
    node_ids: np.ndarray,
    config: PropagationConfig,
    holdout_fraction: float = 0.0,
    holdout_seed: int = 42,
    seed_eligibility: bool = True,
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

    Returns:
        boundary_matrix: (n_labeled, K+1) soft membership boundary conditions
        labeled_indices: (n_labeled,) indices into node_ids array
        community_ids, community_names, community_colors: metadata lists
        holdout_info: dict with holdout account IDs and their community assignments
            (None if holdout_fraction == 0)
    """
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

    conn = sqlite3.connect(str(DB_PATH))
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
    # Why sqrt? Linear inverse would over-boost tiny communities (AI Art with 1 node
    # in graph would get 73x the weight of Qualia Research Folks). Sqrt is a
    # compromise that reduces dominance without creating instability.
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
        # "None" column = how much of this account is NOT in any community.
        # For accounts fully in one community (weight=1.0), none=0.
        # For accounts weakly in multiple communities, none captures the residual.
        boundary[i, K] = max(0.0, 1.0 - balanced.sum())

    # Seed eligibility: weight boundary conditions by concentration
    # Seeds with high entropy (flat across communities) propagate weakly
    # Seeds with concentrated membership propagate strongly
    if seed_eligibility:
        try:
            conn2 = sqlite3.connect(str(DB_PATH))
            eligibility = dict(conn2.execute(
                "SELECT account_id, concentration FROM seed_eligibility"
            ).fetchall())
            conn2.close()

            weighted = 0
            for i, aid in enumerate(labeled_accounts):
                conc = eligibility.get(aid, 1.0)  # default 1.0 if not in table
                boundary[i, :K] *= conc
                # Adjust none column: less concentrated seeds → more "none"
                boundary[i, K] = max(0.0, 1.0 - boundary[i, :K].sum())
                if conc < 1.0:
                    weighted += 1

            if weighted > 0:
                print(f"Seed eligibility: {weighted} seeds weighted by concentration")
        except Exception as e:
            print(f"Seed eligibility table not found, using uniform weighting: {e}")

    return boundary, labeled_indices, community_ids, community_names, community_colors, holdout_info


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


def propagate(
    adjacency: sp.csr_matrix,
    node_ids: np.ndarray,
    config: PropagationConfig,
    holdout_fraction: float = 0.0,
    holdout_seed: int = 42,
    seed_eligibility: bool = True,
) -> tuple[PropagationResult, dict | None]:
    """Run multi-class harmonic label propagation.

    Mathematical formulation:
      For each class c in {community_1, ..., community_K, none}:
        f_U^c = -(L_UU + reg*I)^{-1} * (L_UL * f_L^c - reg * prior)

      where L is the graph Laplacian (D - W), U = unlabeled indices,
      L = labeled indices, f_L^c = boundary conditions for class c.

    The system is solved independently for each class via conjugate gradient
    on the symmetric positive definite matrix (L_UU + reg*I).
    """
    n_nodes = adjacency.shape[0]

    # Load boundary conditions from community database
    boundary, labeled_idx, community_ids, community_names, community_colors, holdout_info = (
        load_community_labels(node_ids, config, holdout_fraction=holdout_fraction, holdout_seed=holdout_seed, seed_eligibility=seed_eligibility)
    )
    K = len(community_ids)
    n_classes = K + 1  # K communities + "none"

    print(f"Nodes: {n_nodes:,}")
    print(f"Labeled (in graph): {len(labeled_idx)}")
    print(f"Communities: {K}")
    print(f"Classes (incl. none): {n_classes}")

    # Symmetrize: max(A, A^T) treats "I follow you" = "you follow me".
    # See ADR 012 R2 for why this is acceptable for now and when we'll fix it.
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
    # We still include them in the solve (they contribute to neighbor propagation)
    # but their own assignments are unreliable.
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
    # and biases isolated nodes toward the prior instead of arbitrary values.
    if config.regularization > 0:
        l_uu = l_uu + config.regularization * sp.eye(n_unlabeled, format="csr")

    t_setup = time.perf_counter() - t0
    print(f"Sub-matrix setup: {t_setup:.2f}s")
    print(f"L_UU: shape={l_uu.shape}, nnz={l_uu.nnz:,}")

    # Solve for each class independently.
    # CG is appropriate because L_UU + reg*I is symmetric positive definite.
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

    # CG can produce small negatives at convergence boundary — clip to 0
    memberships = np.clip(memberships, 0.0, None)

    if config.mode == "independent":
        # ═══ INDEPENDENT MODE (Approach C + E) ═══
        # Keep RAW propagation scores — no per-column normalization.
        # Raw scores are naturally calibrated: more seed neighbors = higher score.
        # This prevents noise inflation where @googlecalendar gets 0.50/0.50.
        #
        # Combine with seed-neighbor counting: for each account, count how many
        # classified neighbors it has per community. This is the interpretable
        # evidence layer — "followed by 12 Qualia seeds and 8 LLM-Whisperer seeds."
        print("  Post-processing: independent mode (raw scores + seed-neighbor counts)")

        # Compute seed-neighbor counts per community
        # For each unlabeled node, count labeled neighbors in each community
        seed_neighbor_counts = np.zeros((n_nodes, K), dtype=np.int32)
        for li in labeled_idx:
            # Get this seed's community assignments (which communities have weight > 0.1)
            for c in range(K):
                if boundary[np.where(labeled_idx == li)[0][0], c] > 0.1:
                    # Find all neighbors of this seed in the symmetric adjacency
                    neighbors = sym[li].nonzero()[1]
                    seed_neighbor_counts[neighbors, c] += 1

        print(f"  Seed-neighbor counts computed for {len(labeled_idx)} seeds")

        # Restore labeled nodes exactly
        memberships[labeled_idx] = boundary

        # Low-degree override: set all community scores to 0
        memberships[low_degree_unlabeled, :] = 0.0
        seed_neighbor_counts[low_degree_unlabeled, :] = 0

        # Uncertainty: degree-based (same as before)
        degree_uncertainty = 1.0 / np.sqrt(degrees + 1.0)
        degree_uncertainty /= degree_uncertainty.max()
        uncertainty = degree_uncertainty
        uncertainty = np.clip(uncertainty, 0.0, 1.0)
        uncertainty[labeled_idx] = 0.0

        # Entropy of raw scores (for diagnostics)
        raw_row_sums = memberships.sum(axis=1, keepdims=True)
        raw_row_sums = np.where(raw_row_sums > 0, raw_row_sums, 1.0)
        entropy = multiclass_entropy(memberships / raw_row_sums)

        # Abstain gate: require BOTH raw score above threshold AND at least
        # 1 seed neighbor in some community. @googlecalendar has 0 seed neighbors.
        max_raw_score = memberships[:, :K].max(axis=1)
        max_seed_neighbors = seed_neighbor_counts.max(axis=1)
        abstain_mask = (
            (max_raw_score < 1e-6)  # no propagation signal at all
            | (max_seed_neighbors < 1)  # no classified neighbors
        ) & ~labeled_mask

        # Store seed_neighbor_counts in result for downstream use
        # (stash in memberships as extra columns would break shape — store separately)
        # We'll attach it to the result object below

    else:
        # ═══ CLASSIC MODE ═══
        # Temperature scaling: raise to power 1/T then re-normalize.
        # T > 1 flattens the distribution (makes multi-community membership visible).
        # T = 1 leaves the raw propagation output.
        # T < 1 sharpens (approaches argmax / hard assignment).
        if config.temperature != 1.0:
            scaled = memberships ** (1.0 / config.temperature)
            row_sums = scaled.sum(axis=1, keepdims=True)
            row_sums = np.where(row_sums > 0, row_sums, 1.0)
            memberships = scaled / row_sums
        else:
            row_sums = memberships.sum(axis=1, keepdims=True)
            row_sums = np.where(row_sums > 0, row_sums, 1.0)
            memberships = memberships / row_sums

        # Restore labeled nodes exactly (propagation shouldn't alter known assignments)
        memberships[labeled_idx] = boundary

        # Low-degree override: degree-1 nodes get "none" regardless of propagation.
        # Their single edge doesn't constitute meaningful community evidence.
        memberships[low_degree_unlabeled, :K] = 0.0
        memberships[low_degree_unlabeled, K] = 1.0

        # Uncertainty: combines entropy (how spread is the distribution?) with
        # degree (how much evidence does this node have?).
        entropy = multiclass_entropy(memberships)
        degree_uncertainty = 1.0 / np.sqrt(degrees + 1.0)
        degree_uncertainty /= degree_uncertainty.max()

        # Weights match existing GRF convention (membership_grf.py)
        uncertainty = 0.7 * entropy + 0.3 * degree_uncertainty
        uncertainty = np.clip(uncertainty, 0.0, 1.0)
        uncertainty[labeled_idx] = 0.0  # labeled nodes have zero uncertainty by definition

        # Abstain gate: nodes where we genuinely can't tell.
        # Different from "none" — "none" means "probably not in any community",
        # "abstain" means "we don't have enough signal to say either way."
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
        seed_neighbor_counts=seed_neighbor_counts if config.mode == "independent" else None,
    )
    return result, holdout_info


# ── Diagnostics ──────────────────────────────────────────────────────────────

def print_diagnostics(result: PropagationResult, adjacency: sp.csr_matrix | None = None) -> dict:
    """Print diagnostic report per ADR 012 Phase 0 checklist.

    Args:
        result: Propagation result to diagnose.
        adjacency: Adjacency matrix (reused from propagation). If None, falls back
            to loading from the pickle cache (legacy behavior).

    Checks:
      1. Solver convergence — did CG converge for all classes?
      2. "None" distribution — are most shadows correctly "none"?
      3. Absorption ratio — is any community grabbing too many shadows?
      4. Abstain stats — how many nodes are genuinely uncertain?
      5. Uncertainty distribution — sanity check on confidence
      6. Multi-community overlap — are overlapping memberships realistic?
      7. Degree-stratified view — does propagation behave differently by degree?
      8. Top confident examples — for human sanity-checking
      9. Louvain comparison — do propagated labels align with structural communities?
    """
    K = len(result.community_ids)
    n = len(result.node_ids)
    memberships = result.memberships
    labeled = result.labeled_mask
    unlabeled = ~labeled

    report = {}
    print("\n" + "=" * 70)
    print("COMMUNITY PROPAGATION DIAGNOSTICS")
    print("=" * 70)

    # 1. Convergence
    print("\n--- Solver Convergence ---")
    all_converged = all(result.converged)
    print(f"All classes converged: {all_converged}")
    print(f"Total solve time: {result.solve_time_seconds:.2f}s")
    report["all_converged"] = all_converged
    report["solve_time_s"] = round(result.solve_time_seconds, 2)

    # 2. "None" class distribution
    # Expectation: most shadow nodes should be "none" (they're adjacent to TPOT,
    # not part of it). If <40% are "none", something is wrong.
    none_col = memberships[:, K]
    shadow_none = none_col[unlabeled]
    n_shadow = unlabeled.sum()
    pct_majority_none = (shadow_none > 0.5).sum() / n_shadow * 100

    print(f"\n--- 'None' Class Distribution (shadow nodes only) ---")
    print(f"Shadow nodes: {n_shadow:,}")
    print(f"Shadow with none > 0.5: {(shadow_none > 0.5).sum():,} ({pct_majority_none:.1f}%)")
    print(f"Shadow with none > 0.9: {(shadow_none > 0.9).sum():,} ({(shadow_none > 0.9).sum()/n_shadow*100:.1f}%)")
    print(f"Mean none weight: {shadow_none.mean():.3f}")
    report["shadow_majority_none_pct"] = round(pct_majority_none, 1)

    # 3. Per-community absorption ratio
    # "Absorption" = how many non-abstain shadow nodes have this community as dominant.
    # Ratio = absorbed / seeds. If > 3x, the community may be over-propagating.
    print(f"\n--- Per-Community Propagation ---")
    print(f"{'Community':30s} {'Seeds':>5s} {'Absorbed':>8s} {'Ratio':>6s} {'Flag':>5s}")
    print("-" * 60)

    absorption = {}
    for c in range(K):
        name = result.community_names[c]
        n_seeds = (labeled & (memberships[:, c] > 0.01)).sum()
        # "Absorbed" = unlabeled, non-abstain nodes where this community is dominant
        dominant = memberships[unlabeled, :K].argmax(axis=1) == c
        non_abstain = ~result.abstain_mask[unlabeled]
        absorbed = (dominant & non_abstain).sum()
        ratio = absorbed / max(n_seeds, 1)
        flag = "!!!" if ratio > 3.0 else ""
        print(f"{name:30s} {n_seeds:5d} {absorbed:8d} {ratio:5.1f}x {flag}")
        absorption[name] = {"seeds": int(n_seeds), "absorbed": int(absorbed), "ratio": round(ratio, 1)}

    report["absorption"] = absorption

    # 4. Abstain statistics
    n_abstain = result.abstain_mask.sum()
    print(f"\n--- Abstain Gate ---")
    print(f"Abstained nodes: {n_abstain:,} ({n_abstain/n*100:.1f}% of all nodes)")
    report["abstain_count"] = int(n_abstain)
    report["abstain_pct"] = round(n_abstain / n * 100, 1)

    # 5. Uncertainty distribution (shadow nodes only)
    shadow_uncertainty = result.uncertainty[unlabeled]
    print(f"\n--- Uncertainty Distribution (shadow nodes) ---")
    print(f"Mean: {shadow_uncertainty.mean():.3f}, Median: {np.median(shadow_uncertainty):.3f}")
    for thresh in [0.3, 0.5, 0.7, 0.9]:
        pct = (shadow_uncertainty > thresh).sum() / n_shadow * 100
        print(f"  > {thresh}: {pct:.1f}%")

    # 6. Multi-community overlap
    # How many non-abstain shadow nodes have significant membership in 2+ communities?
    # Some overlap is expected and healthy (e.g., "EA" + "Coordination").
    non_abstain_shadow = unlabeled & ~result.abstain_mask
    if non_abstain_shadow.any():
        community_memberships = memberships[non_abstain_shadow, :K]
        n_significant = (community_memberships > 0.1).sum(axis=1)
        multi = (n_significant >= 2).sum()
        n_non_abstain = non_abstain_shadow.sum()
        print(f"\n--- Multi-Community Overlap (non-abstain shadows) ---")
        print(f"Non-abstain shadow nodes: {n_non_abstain:,}")
        print(f"In 1 community (>0.1):  {(n_significant == 1).sum():,}")
        print(f"In 2+ communities (>0.1): {multi:,} ({multi/max(n_non_abstain,1)*100:.1f}%)")
        print(f"In 3+ communities (>0.1): {(n_significant >= 3).sum():,}")
        report["multi_community_shadow_count"] = int(multi)

    # 7. Degree-stratified view
    # Propagation should work best for mid/high degree nodes (lots of evidence)
    # and worst for low degree (sparse signal).
    if adjacency is not None:
        adj = adjacency
    else:
        adj = load_adjacency()
    sym = adj.maximum(adj.T)
    degrees = np.asarray(sym.sum(axis=1)).flatten()

    print(f"\n--- Degree-Stratified Summary ---")
    print(f"{'Degree band':20s} {'Nodes':>7s} {'MeanMax':>8s} {'MeanUnc':>8s} {'NoneDom':>8s}")
    print("-" * 55)
    for lo, hi, label in [
        (0, 2, "leaves (0-1)"),
        (2, 10, "low (2-9)"),
        (10, 50, "mid (10-49)"),
        (50, 200, "high (50-199)"),
        (200, 99999, "hubs (200+)"),
    ]:
        band = (degrees >= lo) & (degrees < hi) & unlabeled & ~result.abstain_mask
        n_band = band.sum()
        if n_band == 0:
            print(f"  {label:20s}:       0")
            continue
        mean_max = memberships[band, :K].max(axis=1).mean()
        mean_unc = result.uncertainty[band].mean()
        none_dom = (memberships[band, K] > memberships[band, :K].max(axis=1)).sum()
        print(f"  {label:20s}: {n_band:6,d}  {mean_max:7.3f}  {mean_unc:7.3f}  {none_dom:7,d}")

    # 8. Top confident shadow assignments — for human sanity checking
    # "Does this person actually belong in this community?"
    print(f"\n--- Top 20 Most Confident Shadow Assignments ---")
    print("  (Review these manually — do the assignments make sense?)")
    shadow_idx = np.flatnonzero(unlabeled & ~result.abstain_mask)
    if len(shadow_idx) > 0:
        shadow_max = memberships[shadow_idx, :K].max(axis=1)
        top20 = shadow_idx[np.argsort(shadow_max)[::-1][:20]]

        # Load usernames for readable output
        conn = sqlite3.connect(str(DB_PATH))
        id_to_username = {}
        for aid in result.node_ids[top20]:
            row = conn.execute(
                "SELECT username FROM profiles WHERE account_id = ?", (aid,)
            ).fetchone()
            id_to_username[aid] = row[0] if row else aid[:12] + "..."
        conn.close()

        for idx in top20:
            aid = result.node_ids[idx]
            username = id_to_username.get(aid, aid)
            deg = int(degrees[idx])
            unc = result.uncertainty[idx]
            # Show top 3 communities with weight > 0.05
            top_comms = [
                (result.community_names[c], round(float(memberships[idx, c]), 3))
                for c in np.argsort(memberships[idx, :K])[::-1][:3]
                if memberships[idx, c] > 0.05
            ]
            comms_str = ", ".join(f"{n}={w}" for n, w in top_comms)
            none_w = round(float(memberships[idx, K]), 3)
            print(f"  @{username:25s} deg={deg:4d} unc={unc:.2f} none={none_w} | {comms_str}")

    # 9. Louvain comparison (rough sanity check)
    # Do our communities align with Louvain's structural communities?
    # High purity = our communities capture real structural groups.
    louvain_path = DATA_DIR / "graph_snapshot.louvain.json"
    if louvain_path.exists():
        with open(louvain_path) as f:
            louvain = json.load(f)
        print(f"\n--- Louvain Sanity Check ---")
        print("  (Purity = fraction of labeled nodes in dominant Louvain cluster)")
        labeled_idx_arr = np.flatnonzero(labeled)
        louvain_by_community: dict[str, list[int]] = {}
        for idx in labeled_idx_arr:
            aid = result.node_ids[idx]
            if aid in louvain:
                dom_c = memberships[idx, :K].argmax()
                cname = result.community_names[dom_c]
                if cname not in louvain_by_community:
                    louvain_by_community[cname] = []
                louvain_by_community[cname].append(louvain[aid])

        for cname, lvals in sorted(louvain_by_community.items()):
            n_unique = len(set(lvals))
            dominant = max(set(lvals), key=lvals.count)
            purity = lvals.count(dominant) / len(lvals)
            print(f"  {cname:30s}: {len(lvals):3d} labeled, {n_unique:2d} Louvain clusters, purity={purity:.2f}")

    print("\n" + "=" * 70)
    print("NEXT STEPS FOR HUMAN REVIEW:")
    print("  1. Review absorption ratios — any > 3x? Those communities may be leaking")
    print("  2. Check top 20 assignments — Google the usernames, do they fit?")
    print("  3. Try --temperature 1.0 and --temperature 3.0 to see effect")
    print("  4. Try --no-balance to see raw (unbalanced) propagation")
    print("  5. If results look reasonable, run with --save to persist")
    print("=" * 70)

    return report


def save_results(result: PropagationResult, output_dir: Path) -> Path:
    """Save propagation results as compressed numpy archive.

    Creates two files:
    - Timestamped archive in data/community_propagation_runs/
    - Active pointer at data/community_propagation.npz

    This file is the input for Phase 1 (community-aware embedding) and
    Phase 3 (frontend integration). It contains everything needed to
    color the ClusterView by community membership.
    """
    # Timestamped archive
    archive_dir = output_dir / "community_propagation_runs"
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = archive_dir / f"{timestamp}.npz"

    # Active pointer (stable path for downstream consumers)
    active_path = output_dir / "community_propagation.npz"

    save_arrays = dict(
        memberships=result.memberships.astype(np.float32),
        uncertainty=result.uncertainty.astype(np.float32),
        abstain_mask=result.abstain_mask,
        labeled_mask=result.labeled_mask,
        node_ids=result.node_ids,
        community_ids=np.array(result.community_ids),
        community_names=np.array(result.community_names),
        community_colors=np.array(result.community_colors),
        converged=np.array(result.converged, dtype=bool),
        cg_iterations=np.array(result.cg_iterations, dtype=np.int32),
        mode=np.array(result.config.mode),  # "classic" or "independent"
    )
    if result.seed_neighbor_counts is not None:
        save_arrays["seed_neighbor_counts"] = result.seed_neighbor_counts.astype(np.int16)

    np.savez_compressed(str(archive_path), **save_arrays)
    np.savez_compressed(str(active_path), **save_arrays)

    print(f"\nResults saved:")
    print(f"  Archive: {archive_path}")
    print(f"  Active:  {active_path}")
    print(f"  Size: {active_path.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"  Arrays: {list(save_arrays.keys())}")
    return active_path


def main():
    parser = argparse.ArgumentParser(
        description="Multi-class community label propagation (ADR 012 Phase 0)"
    )
    parser.add_argument("--temperature", type=float, default=2.0,
                        help="Softmax temperature: >1 flattens, <1 sharpens (default: 2.0)")
    parser.add_argument("--reg", type=float, default=1e-3,
                        help="Tikhonov regularization (default: 1e-3)")
    parser.add_argument("--min-degree", type=int, default=2,
                        help="Min degree for community assignment (default: 2)")
    parser.add_argument("--abstain-max", type=float, default=0.15,
                        help="Abstain if max community membership below this (default: 0.15)")
    parser.add_argument("--no-balance", action="store_true",
                        help="Disable class balancing (large communities will dominate)")
    parser.add_argument("--save", action="store_true",
                        help="Save results to data/ directory for downstream use")
    parser.add_argument("--holdout-fraction", type=float, default=0.0,
                        help="Fraction of seeds to hold out per community for threshold calibration (default: 0)")
    parser.add_argument("--holdout-seed", type=int, default=42,
                        help="Random seed for holdout split (default: 42)")
    parser.add_argument("--use-archive-graph", action="store_true", default=True,
                        help="Build graph from archive_tweets.db follow + engagement data (default: True)")
    parser.add_argument("--use-spectral-graph", action="store_true",
                        help="Use spectral snapshot graph instead of archive (legacy)")
    parser.add_argument("--max-cg-iter", type=int, default=2000,
                        help="Max conjugate gradient iterations per class (default: 2000)")
    parser.add_argument("--no-engagement-weights", action="store_true",
                        help="Disable engagement weighting (use binary follow edges only)")
    parser.add_argument("--no-seed-eligibility", action="store_true",
                        help="Disable concentration-based seed weighting")
    parser.add_argument("--mode", choices=["classic", "independent"], default="classic",
                        help="Propagation mode: classic (zero-sum) or independent (multi-label)")
    args = parser.parse_args()

    # --use-spectral-graph overrides --use-archive-graph
    if args.use_spectral_graph:
        args.use_archive_graph = False

    config = PropagationConfig(
        temperature=args.temperature,
        regularization=args.reg,
        min_degree_for_assignment=args.min_degree,
        abstain_max_threshold=args.abstain_max,
        class_balance=not args.no_balance,
        max_iter=args.max_cg_iter,
        mode=args.mode,
    )

    print("=== Community Label Propagation (ADR 012 Phase 0) ===")
    graph_source = "archive" if args.use_archive_graph else "spectral"
    print(f"Config: T={config.temperature}, reg={config.regularization}, "
          f"min_deg={config.min_degree_for_assignment}, balance={config.class_balance}, "
          f"max_cg_iter={config.max_iter}, graph={graph_source}")
    if args.holdout_fraction > 0:
        print(f"Holdout: {args.holdout_fraction:.0%} per community (seed={args.holdout_seed})")
    print()

    # Load graph data
    if args.use_archive_graph or not SPECTRAL_PATH.exists():
        if not DB_PATH.exists():
            print(f"ERROR: archive_tweets.db not found at {DB_PATH}")
            print("  Cannot build archive graph without the database.")
            return None, {}
        print("Building adjacency from archive_tweets.db...")
        adjacency, node_ids_list = build_adjacency_from_archive(
            DB_PATH, weighted=not args.no_engagement_weights,
        )
        node_ids = np.array(node_ids_list)
    else:
        print("Loading spectral snapshot...")
        spec = np.load(str(SPECTRAL_PATH), allow_pickle=True)
        node_ids = spec["node_ids"]
        print("Loading adjacency matrix...")
        adjacency = load_adjacency()
    print(f"Adjacency: {adjacency.shape[0]:,} nodes, {adjacency.nnz:,} edges")

    # Run propagation
    print("\n--- Running Propagation ---")
    result, holdout_info = propagate(
        adjacency, node_ids, config,
        holdout_fraction=args.holdout_fraction,
        holdout_seed=args.holdout_seed,
        seed_eligibility=not args.no_seed_eligibility,
    )

    # Print diagnostics for human review
    report = print_diagnostics(result, adjacency=adjacency)

    # Save if requested
    if args.save:
        if args.holdout_fraction > 0:
            # Train-only output — distinct path from production
            train_path = DATA_DIR / "community_propagation_train.npz"
            save_results(result, DATA_DIR)
            # Rename active pointer to train-specific name
            active_path = DATA_DIR / "community_propagation.npz"
            if active_path.exists():
                import shutil
                shutil.move(str(active_path), str(train_path))
                print(f"  Renamed to train output: {train_path}")

            # Save holdout seeds for calibration
            holdout_path = DATA_DIR / "tpot_holdout_seeds.json"
            holdout_path.write_text(json.dumps(holdout_info, indent=2))
            print(f"  Holdout seeds: {holdout_path} ({holdout_info['n_holdout']} accounts)")
        else:
            save_results(result, DATA_DIR)

    return result, report


if __name__ == "__main__":
    main()
