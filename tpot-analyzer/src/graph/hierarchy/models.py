"""Data models for hierarchical clustering."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set

import numpy as np


@dataclass
class HierarchicalCluster:
    """A cluster with hierarchy info for navigation."""
    
    id: str  # Dendrogram node ID: "d_XXX"
    dendrogram_node: int  # Raw node index in dendrogram
    parent_id: Optional[str]  # Parent dendrogram node ID
    children_ids: Optional[Tuple[str, str]]  # Child dendrogram node IDs (if internal node)
    member_micro_indices: List[int]  # Which micro-clusters belong to this cluster
    member_node_ids: List[str]  # Which original nodes belong to this cluster
    centroid: np.ndarray
    size: int
    label: str
    label_source: str
    representative_handles: List[str]
    contains_ego: bool = False
    is_leaf: bool = False  # True if cannot expand further (no internal structure)
    is_individual: bool = False  # True if this represents a single account, not a cluster
    expansion_strategy: Optional[str] = None  # How this cluster was created (for UI hints)


@dataclass 
class HierarchicalEdge:
    """Edge between clusters with connectivity metric."""
    
    source_id: str
    target_id: str
    raw_count: int  # Actual edge count between clusters
    connectivity: float  # Normalized: raw_count / sqrt(size_A * size_B)
    

@dataclass
class HierarchicalViewData:
    """Complete data for hierarchical cluster view."""
    
    clusters: List[HierarchicalCluster]
    edges: List[HierarchicalEdge]
    ego_cluster_id: Optional[str]
    total_nodes: int
    n_micro_clusters: int
    positions: Dict[str, List[float]]
    expanded_ids: List[str]  # Which clusters have been expanded (show children)
    collapsed_ids: List[str]  # Which clusters have been collapsed upward (merged into parent)
    budget: int  # Max clusters allowed
    budget_remaining: int  # How many more can be added
