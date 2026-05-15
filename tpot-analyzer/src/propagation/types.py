"""Data classes for propagation config and results."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class PropagationConfig:
    """Tunable parameters for label propagation.

    These defaults are starting guesses — Phase 0 exists to find better values.
    Run the script with different settings and compare diagnostics.
    """
    # Softmax temperature: >1 flattens distribution (reduces winner-take-all),
    # <1 sharpens it. T=2 is conservative; T=1 is raw propagation output.
    temperature: float = 2.0

    # Teleport probability for Directed Personalized PageRank.
    # Higher = shorter walks (local niches). Lower = longer walks (macro-clusters).
    alpha: float = 0.15


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
    stability: np.ndarray | None = None             # (n_nodes, K) float [0, 1] — bootstrap stability
    confidence_intervals: np.ndarray | None = None  # (n_nodes, K, 2) float — [low, high] bounds
