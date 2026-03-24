"""Propagation diagnostic report per ADR 012 Phase 0 checklist."""
from __future__ import annotations

import json
import sqlite3

import numpy as np
import scipy.sparse as sp

from src.config import DEFAULT_ARCHIVE_DB, DEFAULT_DATA_DIR
from src.data.adjacency import load_adjacency_cache
from src.propagation.types import PropagationResult


def print_diagnostics(
    result: PropagationResult,
    adjacency: sp.csr_matrix | None = None,
    db_path=None,
    data_dir=None,
) -> dict:
    """Print diagnostic report per ADR 012 Phase 0 checklist.

    Args:
        result: Propagation result to diagnose.
        adjacency: Adjacency matrix (reused from propagation). If None, loads from cache.
        db_path: Path to archive_tweets.db for username lookups.
        data_dir: Path to data directory for Louvain comparison.

    Checks:
      1. Solver convergence
      2. "None" distribution
      3. Absorption ratio
      4. Abstain stats
      5. Uncertainty distribution
      6. Multi-community overlap
      7. Degree-stratified view
      8. Top confident examples
      9. Louvain comparison
    """
    if db_path is None:
        db_path = DEFAULT_ARCHIVE_DB
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR

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
    print(f"\n--- Per-Community Propagation ---")
    print(f"{'Community':30s} {'Seeds':>5s} {'Absorbed':>8s} {'Ratio':>6s} {'Flag':>5s}")
    print("-" * 60)

    absorption = {}
    for c in range(K):
        name = result.community_names[c]
        n_seeds = (labeled & (memberships[:, c] > 0.01)).sum()
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
    if adjacency is not None:
        adj = adjacency
    else:
        adj = load_adjacency_cache()
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

    # 8. Top confident shadow assignments
    print(f"\n--- Top 20 Most Confident Shadow Assignments ---")
    print("  (Review these manually — do the assignments make sense?)")
    shadow_idx = np.flatnonzero(unlabeled & ~result.abstain_mask)
    if len(shadow_idx) > 0:
        shadow_max = memberships[shadow_idx, :K].max(axis=1)
        top20 = shadow_idx[np.argsort(shadow_max)[::-1][:20]]

        conn = sqlite3.connect(str(db_path))
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
            top_comms = [
                (result.community_names[c], round(float(memberships[idx, c]), 3))
                for c in np.argsort(memberships[idx, :K])[::-1][:3]
                if memberships[idx, c] > 0.05
            ]
            comms_str = ", ".join(f"{n}={w}" for n, w in top_comms)
            none_w = round(float(memberships[idx, K]), 3)
            print(f"  @{username:25s} deg={deg:4d} unc={unc:.2f} none={none_w} | {comms_str}")

    # 9. Louvain comparison
    louvain_path = data_dir / "graph_snapshot.louvain.json"
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
