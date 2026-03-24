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

Core logic lives in src/propagation/ — this file is a thin CLI wrapper.
"""
from __future__ import annotations

import argparse
import json
import shutil

import numpy as np

from src.config import DEFAULT_DATA_DIR, DEFAULT_ARCHIVE_DB
from src.data.adjacency import load_adjacency_cache
from src.propagation import PropagationConfig, propagate
from src.propagation.diagnostics import print_diagnostics
from src.propagation.io import save_results, build_adjacency_from_archive

DATA_DIR = DEFAULT_DATA_DIR
DB_PATH = DEFAULT_ARCHIVE_DB
SPECTRAL_PATH = DATA_DIR / "graph_snapshot.spectral.npz"


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
                        help="Fraction of seeds to hold out per community (default: 0)")
    parser.add_argument("--holdout-seed", type=int, default=42,
                        help="Random seed for holdout split (default: 42)")
    parser.add_argument("--use-archive-graph", action="store_true", default=True,
                        help="Build graph from archive_tweets.db (default: True)")
    parser.add_argument("--use-spectral-graph", action="store_true",
                        help="Use spectral snapshot graph instead (legacy)")
    parser.add_argument("--max-cg-iter", type=int, default=2000,
                        help="Max conjugate gradient iterations per class (default: 2000)")
    parser.add_argument("--no-engagement-weights", action="store_true",
                        help="Disable engagement weighting (binary follow edges only)")
    parser.add_argument("--no-seed-eligibility", action="store_true",
                        help="Disable concentration-based seed weighting")
    parser.add_argument("--mode", choices=["classic", "independent"], default="classic",
                        help="Propagation mode: classic (zero-sum) or independent (multi-label)")
    args = parser.parse_args()

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
        adjacency = load_adjacency_cache()
    print(f"Adjacency: {adjacency.shape[0]:,} nodes, {adjacency.nnz:,} edges")

    # Run propagation
    print("\n--- Running Propagation ---")
    result, holdout_info = propagate(
        adjacency, node_ids, config,
        holdout_fraction=args.holdout_fraction,
        holdout_seed=args.holdout_seed,
        seed_eligibility=not args.no_seed_eligibility,
    )

    # Diagnostics
    report = print_diagnostics(result, adjacency=adjacency)

    # Save if requested
    if args.save:
        if args.holdout_fraction > 0:
            save_results(result, DATA_DIR)
            active_path = DATA_DIR / "community_propagation.npz"
            train_path = DATA_DIR / "community_propagation_train.npz"
            if active_path.exists():
                shutil.move(str(active_path), str(train_path))
                print(f"  Renamed to train output: {train_path}")
            holdout_path = DATA_DIR / "tpot_holdout_seeds.json"
            holdout_path.write_text(json.dumps(holdout_info, indent=2))
            print(f"  Holdout seeds: {holdout_path} ({holdout_info['n_holdout']} accounts)")
        else:
            save_results(result, DATA_DIR)

    return result, report


if __name__ == "__main__":
    main()
