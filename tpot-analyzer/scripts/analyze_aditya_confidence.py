"""Calculate per-community confidence for @adityaarpitha.

Uses Bootstrap Stability: Runs propagation multiple times with different
seed subsets to see how stable each community score is.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

from src.config import DEFAULT_DATA_DIR
from src.propagation.io import build_adjacency_from_archive
from src.propagation import PropagationConfig, propagate
from src.config import DEFAULT_ARCHIVE_DB

DATA_DIR = DEFAULT_DATA_DIR
DB_PATH = DEFAULT_ARCHIVE_DB
ADITYA_ID = "261659859"

def main():
    print(f"--- Bootstrap Confidence Analysis for @adityaarpitha ({ADITYA_ID}) ---")
    
    # 1. Load Adjacency
    print("Building adjacency...")
    adjacency, node_ids_list = build_adjacency_from_archive(DB_PATH)
    node_ids = np.array(node_ids_list)
    
    if ADITYA_ID not in node_ids_list:
        print(f"ERROR: {ADITYA_ID} not found in graph.")
        return
    
    idx = node_ids_list.index(ADITYA_ID)
    
    # 2. Setup Propagation
    config = PropagationConfig(
        temperature=2.0,
        mode="independent" # Most descriptive for bridges
    )
    
    # 3. Run Bootstrap (10 iterations)
    n_iterations = 10
    all_scores = []
    
    print(f"Running {n_iterations} bootstrap iterations (20% holdout per run)...")
    for i in range(n_iterations):
        print(f"  Iteration {i+1}/{n_iterations}...")
        result, _ = propagate(
            adjacency, node_ids, config,
            holdout_fraction=0.2,
            holdout_seed=42 + i,
            seed_eligibility=True
        )
        # result.memberships is (n, K+1)
        all_scores.append(result.memberships[idx])
        
    all_scores = np.array(all_scores) # (n_iterations, K+1)
    community_names = result.community_names
    K = len(community_names)
    
    # 4. Calculate Stats
    means = np.mean(all_scores, axis=0)
    stds = np.std(all_scores, axis=0)
    
    # 95% CI is roughly mean +/- 2*std
    ci_low = np.percentile(all_scores, 2.5, axis=0)
    ci_high = np.percentile(all_scores, 97.5, axis=0)
    
    # 5. Report
    results = []
    for i in range(K):
        results.append({
            "Community": community_names[i],
            "Mean Score": means[i],
            "Std Dev": stds[i],
            "95% CI Low": ci_low[i],
            "95% CI High": ci_high[i],
            # Stability = 1 - (std / mean) if mean > 0
            "Stability": 1.0 - (stds[i] / means[i]) if means[i] > 1e-6 else 0.0
        })
        
    df = pd.DataFrame(results)
    # Filter for meaningful scores
    df = df[df["Mean Score"] > 0.01].sort_values("Mean Score", ascending=False)
    
    print("\n=== PER-COMMUNITY CONFIDENCE (BOOTSTRAP STABILITY) ===")
    print(f"{'Community':<30} {'Score':<8} {'Stability':<10} {'95% Confidence Interval':<25}")
    print("-" * 80)
    for _, row in df.iterrows():
        ci_str = f"[{row['95% CI Low']:.2f}, {row['95% CI High']:.2f}]"
        print(f"{row['Community']:<30} {row['Mean Score']:<8.2f} {row['Stability']:<10.2f} {ci_str:<25}")

    print("\nNote: Stability > 0.8 is considered 'Solid', < 0.5 is 'Vibe-dependent'.")

if __name__ == "__main__":
    main()
