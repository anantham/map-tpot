"""Inspect compositional spread in a historical classic propagation artifact.

The output is a candidate list from uncalibrated legacy scores. Entropy and
``1 - entropy`` describe row composition; they are not confidence, posterior
uncertainty, true bridge status, or membership.

Usage:
    .venv/bin/python3 -m scripts.analyze_frontier_confidence
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import DEFAULT_DATA_DIR, DEFAULT_ARCHIVE_DB
from src.propagation.bands import (
    require_supported_band_artifact,
)

DATA_DIR = DEFAULT_DATA_DIR
DB_PATH = DEFAULT_ARCHIVE_DB
PROP_PATH = DATA_DIR / "community_propagation.npz"


def load_propagation(path: Path):
    """Load the propagation artifact used by this analysis."""
    propagation = np.load(str(path), allow_pickle=True)
    require_supported_band_artifact(propagation)
    return propagation


def load_usernames(db_path: Path) -> dict[str, str]:
    """Load {account_id: username} from profiles and resolved_accounts."""
    lookup = {}
    if not db_path.exists():
        return lookup
    
    conn = sqlite3.connect(str(db_path))
    try:
        # profiles has priority
        rows = conn.execute("SELECT account_id, username FROM profiles").fetchall()
        for aid, uname in rows:
            lookup[str(aid)] = uname
            
        # resolved_accounts as fallback
        rows = conn.execute("SELECT account_id, username FROM resolved_accounts WHERE username IS NOT NULL").fetchall()
        for aid, uname in rows:
            if str(aid) not in lookup:
                lookup[str(aid)] = uname
    finally:
        conn.close()
    return lookup

def main():
    parser = argparse.ArgumentParser(
        description="Inspect classic-score composition candidates"
    )
    parser.add_argument("--top-n", type=int, default=50, help="Number of high-entropy accounts to show")
    parser.add_argument("--min-score", type=float, default=0.01, help="Min score for community overlap")
    args = parser.parse_args()

    if not PROP_PATH.exists():
        print(f"ERROR: Propagation results not found at {PROP_PATH}")
        return

    print(f"Loading propagation results from {PROP_PATH}...")
    prop = load_propagation(PROP_PATH)
    
    memberships = prop["memberships"]  # (n, K+1)
    
    from src.propagation.engine import multiclass_entropy
    if "entropy" in prop:
        entropy = prop["entropy"]
    else:
        print("Calculating entropy from memberships...")
        entropy = multiclass_entropy(memberships)
        
    node_ids = prop["node_ids"]        # (n,)
    community_names = prop["community_names"] # list of K strings
    labeled_mask = prop["labeled_mask"] # (n,) bool
    
    K = len(community_names)
    n_nodes = len(node_ids)
    
    # Resolve usernames
    print(f"Resolving usernames from {DB_PATH}...")
    usernames = load_usernames(DB_PATH)
    
    # Descriptive row concentration only; not calibrated confidence.
    concentration = (1.0 - entropy).clip(0.0, 1.0)
    
    # Filter out labeled seeds and abstained nodes (if any)
    # Note: entropy is already 0 for seeds in classic mode
    unlabeled_mask = ~labeled_mask
    
    # Create a DataFrame for analysis
    df = pd.DataFrame({
        "node_id": node_ids,
        "entropy": entropy,
        "concentration": concentration,
    })
    
    # Add username
    df["username"] = df["node_id"].apply(lambda x: usernames.get(str(x), f"id:{x}"))
    
    # Get top 2 community assignments for each node
    comm_scores = memberships[:, :K]
    top1_idx = np.argmax(comm_scores, axis=1)
    top1_score = np.max(comm_scores, axis=1)
    
    # To get top2, we temporarily zero out top1
    tmp = comm_scores.copy()
    rows = np.arange(n_nodes)
    tmp[rows, top1_idx] = 0
    top2_idx = np.argmax(tmp, axis=1)
    top2_score = np.max(tmp, axis=1)
    
    df["primary_comm"] = [community_names[i] for i in top1_idx]
    df["primary_score"] = top1_score
    df["secondary_comm"] = [community_names[i] for i in top2_idx]
    df["secondary_score"] = top2_score
    df["none_score"] = memberships[:, -1]

    # 1. Surface high-spread overlap candidates.
    print(f"\n=== TOP {args.top_n} HIGH-SPREAD LEGACY OVERLAP CANDIDATES ===")
    print(
        "Two score columns clear the legacy filter. These are inspection "
        "candidates, not validated bridges."
    )

    # Historical candidate gates only; none and community scores are not
    # calibrated relevance or membership probabilities.
    overlap_mask = (
        unlabeled_mask
        & (df["none_score"] < 0.5)
        & (df["secondary_score"] > 0.02)
    )
    overlap_candidates = (
        df[overlap_mask].sort_values("entropy", ascending=False).head(args.top_n)
    )

    print(f"{'Username':<20} {'Entropy':<8} {'Conc':<6} {'Primary (Score)':<30} {'Secondary (Score)':<30}")
    print("-" * 105)
    for _, row in overlap_candidates.iterrows():
        p_str = f"{row['primary_comm']} ({row['primary_score']:.2f})"
        s_str = f"{row['secondary_comm']} ({row['secondary_score']:.2f})"
        print(f"{row['username']:<20} {row['entropy']:<8.3f} {row['concentration']:<6.2f} "
              f"{p_str:<30} {s_str:<30}")

    # 2. Low-spread single-peak candidates.
    print(f"\n=== TOP {args.top_n} LOW-SPREAD LEGACY SINGLE-PEAK CANDIDATES ===")
    print(
        "One score dominates the legacy row. This does not establish "
        "membership or correctness."
    )
    
    # Filter for:
    # - Not a seed
    # - High primary score (> 0.5)
    # - Low entropy (< 0.3)
    single_peak_mask = (
        unlabeled_mask
        & (df["primary_score"] > 0.5)
        & (df["entropy"] < 0.3)
    )
    single_peak = (
        df[single_peak_mask]
        .sort_values("primary_score", ascending=False)
        .head(args.top_n)
    )

    print(f"{'Username':<20} {'Entropy':<8} {'Conc':<6} {'Primary Community':<25} {'Score':<6}")
    print("-" * 75)
    for _, row in single_peak.iterrows():
        print(f"{row['username']:<20} {row['entropy']:<8.3f} {row['concentration']:<6.2f} "
              f"{row['primary_comm']:<25} {row['primary_score']:<6.2f}")

    # 3. Community Overlap Matrix
    print("\n=== LEGACY COMMUNITY OVERLAP (MEAN CROSS-SCORE) ===")
    print(
        "Higher values are a descriptive classic-score overlap, not "
        "cross-membership."
    )
    
    overlap = np.zeros((K, K))
    # Use nodes with strong signal to calculate overlap
    for i in range(K):
        mask = (top1_idx == i) & (top1_score > 0.1) & unlabeled_mask
        if not np.any(mask):
            continue
        mean_scores = comm_scores[mask].mean(axis=0)
        overlap[i] = mean_scores

    # Find top overlaps (excluding diagonal)
    overlaps = []
    for i in range(K):
        for j in range(i + 1, K):
            # Harmonic mean of cross-affinities to find mutual overlap
            v_ij = overlap[i, j]
            v_ji = overlap[j, i]
            if v_ij + v_ji > 0:
                h_mean = 2 * (v_ij * v_ji) / (v_ij + v_ji)
                overlaps.append((community_names[i], community_names[j], h_mean))
    
    overlaps.sort(key=lambda x: x[2], reverse=True)
    print(f"\n{'Community A':<30} {'Community B':<30} {'Mutual Affinity':<15}")
    print("-" * 80)
    for a, b, v in overlaps[:15]:
        print(f"{a:<30} {b:<30} {v:<15.3f}")

    # 3. Overall compositional concentration stats.
    print("\n=== COMPOSITIONAL CONCENTRATION STATS ===")
    print(
        "Mean concentration (unlabeled): "
        f"{df[unlabeled_mask]['concentration'].mean():.3f}"
    )
    print(
        "Median concentration (unlabeled): "
        f"{df[unlabeled_mask]['concentration'].median():.3f}"
    )

    # Distribution of descriptive concentration.
    bins = [0, 0.2, 0.4, 0.6, 0.8, 1.0]
    dist = (
        pd.cut(df[unlabeled_mask]["concentration"], bins)
        .value_counts()
        .sort_index()
    )
    print("\nConcentration distribution:")
    for b, count in dist.items():
        print(f"  {str(b):<12}: {count:6,} accounts")

if __name__ == "__main__":
    main()
