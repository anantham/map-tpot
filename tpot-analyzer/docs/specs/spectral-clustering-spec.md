# Technical Specification: Spectral Clustering Visualization

**Version**: 1.0  
**Date**: 2024-12-05  
**Status**: Draft

## Table of Contents

1. [Overview](#overview)
2. [Data Structures](#data-structures)
3. [Backend Components](#backend-components)
4. [API Contracts](#api-contracts)
5. [Frontend Components](#frontend-components)
6. [State Management](#state-management)
7. [Implementation Plan](#implementation-plan)
8. [File Changes](#file-changes)

---

## Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        PRECOMPUTATION                           │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐ │
│  │ Graph Data  │───▶│  Spectral   │───▶│ spectral.npy        │ │
│  │ (parquet)   │    │  Embedding  │    │ linkage.npy         │ │
│  └─────────────┘    └─────────────┘    │ cluster_meta.json   │ │
│         │                              └─────────────────────┘ │
│         │           ┌─────────────┐    ┌─────────────────────┐ │
│         └──────────▶│   Louvain   │───▶│ louvain.json        │ │
│                     │  (existing) │    └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                          RUNTIME                                │
│  ┌──────────┐   ┌─────────────┐   ┌──────────────────────────┐ │
│  │ Frontend │◀─▶│  Flask API  │◀─▶│ Precomputed Data         │ │
│  │ (React)  │   │             │   │ + SQLite (labels, state) │ │
│  └──────────┘   └─────────────┘   └──────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Key Flows

1. **Precomputation**: Generate spectral embedding and hierarchy from graph
2. **Initial Load**: Frontend requests cluster structure at default granularity
3. **Semantic Zoom**: User zooms → new granularity → re-cut hierarchy → update view
4. **Drill Down**: User double-clicks cluster → expand in place → finer granularity for that region
5. **Labeling**: User renames cluster → persist to SQLite → reflect in UI

---

## Data Structures

### Spectral Embedding Storage

**File**: `data/graph_snapshot.spectral.npz`

```python
# NumPy compressed archive containing:
{
    'embedding': np.ndarray,      # shape (n_nodes, n_dims), float32
    'node_ids': np.ndarray,       # shape (n_nodes,), string node IDs
    'eigenvalues': np.ndarray,    # shape (n_dims,), for diagnostics
    'linkage': np.ndarray,        # scipy linkage matrix, shape (n_nodes-1, 4)
}
```

### Spectral Metadata

**File**: `data/graph_snapshot.spectral_meta.json`

```json
{
    "generated_at": "2024-12-05T10:30:00Z",
    "n_nodes": 71761,
    "n_dims": 30,
    "method": "normalized_laplacian",
    "eigensolver": "arpack",
    "eigensolver_params": {
        "tol": 1e-10,
        "maxiter": 5000,
        "ncv": null
    },
    "linkage_method": "ward",
    "computation_time_seconds": 847.3,
    "eigenvalue_gap": 0.0234,
    "convergence_info": {
        "iterations": 2341,
        "residual_norm": 1.2e-11
    },
    "stability_check": {
        "n_runs": 3,
        "mean_ari": 0.97,
        "std_ari": 0.02
    }
}
```

### Cluster Labels Storage

**Table**: `cluster_labels` in `data/clusters.db`

```sql
CREATE TABLE cluster_labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_key TEXT UNIQUE NOT NULL,  -- e.g., "spectral_n50_c12"
    user_label TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cluster_key ON cluster_labels(cluster_key);
```

### Runtime Cluster Structure

```typescript
interface ClusterNode {
    id: string;                    // e.g., "cluster_12"
    type: 'cluster' | 'individual';
    members: string[];             // node IDs in this cluster
    memberCount: number;
    centroid: number[];            // spectral coordinates
    label: string;                 // auto or user-assigned
    labelSource: 'auto' | 'user';
    representativeHandles: string[];  // top 3 by followers
    containsEgo: boolean;
    softMemberships?: Record<string, number>;  // for boundary nodes
}

interface ClusterEdge {
    source: string;                // cluster or node ID
    target: string;
    weight: number;                // soft-membership-weighted count
    rawCount: number;              // actual edge count
    opacity: number;               // derived from weight for rendering
}

interface ClusterViewState {
    granularity: number;           // N visible items
    ego: string | null;
    focusCluster: string | null;   // for drill-down state
    clusters: ClusterNode[];
    edges: ClusterEdge[];
    individualNodes: NodeData[];   // nodes shown as individuals
}
```

### Authoritative Input Schemas

**Primary source**: `data/graph_snapshot.nodes.parquet` and `data/graph_snapshot.edges.parquet`.  
**Fallback**: `shadow_account` and `shadow_edge` tables in `data/cache.db` (via `ShadowStore`), which mirror these shapes.

**Nodes (`graph_snapshot.nodes.parquet`, 71,761 rows):**
- `node_id` (string), `username` (string), `display_name` (string)
- `num_followers`, `num_following`, `num_likes`, `num_tweets` (double)
- `bio`, `location`, `website` (string), `profile_image_url` (nullable), `provenance` (string), `shadow` (bool), `fetched_at` (string)

**Edges (`graph_snapshot.edges.parquet`, 230,764 rows):**
- `source` (string), `target` (string)
- `direction_label` (string) — directed orientation; `mutual` (bool) indicates reciprocity
- `provenance` (string), `shadow` (bool), `metadata` (string JSON), `fetched_at` (string)

**Louvain assignments**: not present in snapshots. Persist during precompute as `data/graph_snapshot.louvain.json` `{ node_id: community_id }` and optionally denormalize to a `louvain_comm` column when exporting nodes parquet.

**Adjacency loading**: build a directed CSR from `source/target`, applying `direction_label`; include `weight` from `metadata` if present, else default to 1. If snapshots are absent, hydrate from `shadow_edge` (`source_id`, `target_id`, `direction`, `weight`, `metadata`) and `shadow_account` for node metadata.

---

## Backend Components

### New File: `src/graph/spectral.py`

```python
"""
Spectral embedding and hierarchical clustering for graph visualization.

This module provides:
1. Spectral embedding computation (Laplacian eigenvectors)
2. Hierarchical clustering on embeddings
3. Soft membership computation
4. Instrumentation for tracking computation quality
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import eigsh, ArpackNoConvergence
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import cdist
from sklearn.preprocessing import normalize
from sklearn.metrics import adjusted_rand_score

logger = logging.getLogger(__name__)


@dataclass
class SpectralConfig:
    """Configuration for spectral embedding computation."""
    n_dims: int = 30
    eigensolver_tol: float = 1e-10
    eigensolver_maxiter: int = 5000
    linkage_method: str = 'ward'
    stability_runs: int = 3
    random_seed: int = 42


@dataclass 
class SpectralResult:
    """Result of spectral embedding computation."""
    embedding: np.ndarray           # (n_nodes, n_dims)
    node_ids: np.ndarray            # (n_nodes,)
    eigenvalues: np.ndarray         # (n_dims,)
    linkage_matrix: np.ndarray      # (n_nodes-1, 4)
    metadata: Dict[str, Any]


@dataclass
class ComputationMetrics:
    """Instrumentation metrics for computation."""
    total_time_seconds: float
    laplacian_time_seconds: float
    eigensolver_time_seconds: float
    linkage_time_seconds: float
    eigensolver_iterations: int
    eigensolver_residual: float
    eigenvalue_gap: float           # gap between k-th and (k+1)-th eigenvalue
    stability_ari_mean: float       # adjusted rand index across runs
    stability_ari_std: float


def compute_normalized_laplacian(adjacency: csr_matrix) -> csr_matrix:
    """
    Compute symmetric normalized Laplacian.
    
    L_sym = I - D^{-1/2} A D^{-1/2}
    
    Args:
        adjacency: Sparse adjacency matrix (can be directed, will be symmetrized)
    
    Returns:
        Sparse normalized Laplacian matrix
    """
    # Symmetrize if directed
    A = (adjacency + adjacency.T) / 2
    A = A.tocsr()
    
    # Compute degree
    degrees = np.array(A.sum(axis=1)).flatten()
    degrees[degrees == 0] = 1  # avoid division by zero
    
    # D^{-1/2}
    d_inv_sqrt = 1.0 / np.sqrt(degrees)
    D_inv_sqrt = csr_matrix((d_inv_sqrt, (range(len(degrees)), range(len(degrees)))))
    
    # L = I - D^{-1/2} A D^{-1/2}
    n = adjacency.shape[0]
    I = csr_matrix((np.ones(n), (range(n), range(n))))
    L = I - D_inv_sqrt @ A @ D_inv_sqrt
    
    return L


def compute_spectral_embedding(
    adjacency: csr_matrix,
    node_ids: List[str],
    config: SpectralConfig = None
) -> SpectralResult:
    """
    Compute spectral embedding for graph nodes.
    
    Args:
        adjacency: Sparse adjacency matrix
        node_ids: List of node identifiers (same order as adjacency rows)
        config: Configuration parameters
    
    Returns:
        SpectralResult with embedding, linkage, and metadata
    """
    config = config or SpectralConfig()
    metrics = {}
    
    start_total = time.time()
    logger.info(f"Starting spectral embedding: {len(node_ids)} nodes, {config.n_dims} dims")
    
    # Step 1: Compute Laplacian
    start_lap = time.time()
    L = compute_normalized_laplacian(adjacency)
    metrics['laplacian_time_seconds'] = time.time() - start_lap
    logger.info(f"Laplacian computed in {metrics['laplacian_time_seconds']:.2f}s")
    
    # Step 2: Eigendecomposition
    start_eig = time.time()
    
    # Request k+1 eigenvectors (first one is trivial)
    k = config.n_dims + 1
    
    try:
        eigenvalues, eigenvectors = eigsh(
            L, 
            k=k, 
            which='SM',  # smallest magnitude
            tol=config.eigensolver_tol,
            maxiter=config.eigensolver_maxiter,
            return_eigenvectors=True
        )
        
        # Sort by eigenvalue
        idx = np.argsort(eigenvalues)
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]
        
        # Skip first eigenvector (constant)
        eigenvalues = eigenvalues[1:]
        eigenvectors = eigenvectors[:, 1:]
        
        metrics['eigensolver_iterations'] = 'converged'
        metrics['eigensolver_residual'] = float(config.eigensolver_tol)
        
    except ArpackNoConvergence as e:
        logger.warning(f"Eigensolver did not fully converge: {e}")
        eigenvalues = e.eigenvalues[1:]
        eigenvectors = e.eigenvectors[:, 1:]
        metrics['eigensolver_iterations'] = config.eigensolver_maxiter
        metrics['eigensolver_residual'] = 'not_converged'
    
    metrics['eigensolver_time_seconds'] = time.time() - start_eig
    logger.info(f"Eigendecomposition completed in {metrics['eigensolver_time_seconds']:.2f}s")
    
    # Compute eigenvalue gap (indicator of cluster separability)
    if len(eigenvalues) > config.n_dims:
        metrics['eigenvalue_gap'] = float(eigenvalues[config.n_dims] - eigenvalues[config.n_dims - 1])
    else:
        metrics['eigenvalue_gap'] = float(eigenvalues[-1] - eigenvalues[-2]) if len(eigenvalues) > 1 else 0.0
    
    # Step 3: Normalize embedding rows
    embedding = eigenvectors[:, :config.n_dims]
    embedding = normalize(embedding, axis=1)
    
    # Step 4: Hierarchical clustering
    start_link = time.time()
    linkage_matrix = linkage(embedding, method=config.linkage_method)
    metrics['linkage_time_seconds'] = time.time() - start_link
    logger.info(f"Hierarchical clustering completed in {metrics['linkage_time_seconds']:.2f}s")
    
    # Step 5: Stability check (optional, for instrumentation)
    if config.stability_runs > 1:
        ari_scores = []
        base_labels = fcluster(linkage_matrix, t=50, criterion='maxclust')
        
        for run in range(config.stability_runs - 1):
            # Add small noise to embedding
            noisy_embedding = embedding + np.random.normal(0, 0.001, embedding.shape)
            noisy_embedding = normalize(noisy_embedding, axis=1)
            noisy_linkage = linkage(noisy_embedding, method=config.linkage_method)
            noisy_labels = fcluster(noisy_linkage, t=50, criterion='maxclust')
            
            ari = adjusted_rand_score(base_labels, noisy_labels)
            ari_scores.append(ari)
        
        metrics['stability_ari_mean'] = float(np.mean(ari_scores))
        metrics['stability_ari_std'] = float(np.std(ari_scores))
    else:
        metrics['stability_ari_mean'] = 1.0
        metrics['stability_ari_std'] = 0.0
    
    metrics['total_time_seconds'] = time.time() - start_total
    logger.info(f"Total spectral embedding time: {metrics['total_time_seconds']:.2f}s")
    
    # Build metadata
    metadata = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'n_nodes': len(node_ids),
        'n_dims': config.n_dims,
        'method': 'normalized_laplacian',
        'eigensolver': 'arpack',
        'eigensolver_params': {
            'tol': config.eigensolver_tol,
            'maxiter': config.eigensolver_maxiter,
        },
        'linkage_method': config.linkage_method,
        'computation_metrics': metrics,
    }
    
    return SpectralResult(
        embedding=embedding.astype(np.float32),
        node_ids=np.array(node_ids),
        eigenvalues=eigenvalues.astype(np.float32),
        linkage_matrix=linkage_matrix.astype(np.float32),
        metadata=metadata
    )


def save_spectral_result(result: SpectralResult, base_path: Path):
    """Save spectral result to disk."""
    # Save arrays
    np.savez_compressed(
        base_path.with_suffix('.spectral.npz'),
        embedding=result.embedding,
        node_ids=result.node_ids,
        eigenvalues=result.eigenvalues,
        linkage=result.linkage_matrix
    )
    
    # Save metadata
    meta_path = base_path.with_suffix('.spectral_meta.json')
    with open(meta_path, 'w') as f:
        json.dump(result.metadata, f, indent=2)
    
    logger.info(f"Saved spectral result to {base_path}")


def load_spectral_result(base_path: Path) -> SpectralResult:
    """Load spectral result from disk."""
    # Load arrays
    data = np.load(base_path.with_suffix('.spectral.npz'))
    
    # Load metadata
    meta_path = base_path.with_suffix('.spectral_meta.json')
    with open(meta_path, 'r') as f:
        metadata = json.load(f)
    
    return SpectralResult(
        embedding=data['embedding'],
        node_ids=data['node_ids'],
        eigenvalues=data['eigenvalues'],
        linkage_matrix=data['linkage'],
        metadata=metadata
    )
```

### New File: `src/graph/clusters.py`

```python
"""
Cluster management for hierarchical graph visualization.

This module provides:
1. Cutting hierarchy at arbitrary granularity
2. Soft membership computation
3. Inter-cluster edge aggregation
4. Cluster label management
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from scipy.cluster.hierarchy import fcluster
from scipy.spatial.distance import cdist

logger = logging.getLogger(__name__)


@dataclass
class ClusterInfo:
    """Information about a single cluster."""
    id: str
    member_indices: List[int]
    member_ids: List[str]
    centroid: np.ndarray
    size: int
    label: str
    label_source: str  # 'auto' or 'user'
    representative_handles: List[str]
    contains_ego: bool = False


@dataclass
class ClusterEdge:
    """Edge between clusters with soft-membership weighting."""
    source_id: str
    target_id: str
    weight: float          # soft-membership-weighted
    raw_count: int         # actual edge count
    direction: str         # 'forward', 'backward', or 'mutual'


@dataclass
class ClusterViewData:
    """Complete data for rendering a cluster view."""
    clusters: List[ClusterInfo]
    individual_nodes: List[str]  # nodes shown as individuals (small clusters)
    edges: List[ClusterEdge]
    ego_cluster_id: Optional[str]
    granularity: int
    total_nodes: int


# Minimum cluster size to show as cluster (below this, show individuals)
MIN_CLUSTER_SIZE = 4


def cut_hierarchy_at_granularity(
    linkage_matrix: np.ndarray,
    n_clusters: int
) -> np.ndarray:
    """
    Cut dendrogram to get specified number of clusters.
    
    Args:
        linkage_matrix: Scipy linkage matrix
        n_clusters: Desired number of clusters
    
    Returns:
        Array of cluster labels (1-indexed)
    """
    return fcluster(linkage_matrix, t=n_clusters, criterion='maxclust')


def compute_soft_memberships(
    embedding: np.ndarray,
    cluster_labels: np.ndarray,
    temperature: float = 1.0
) -> np.ndarray:
    """
    Compute soft cluster memberships based on distance to centroids.
    
    Args:
        embedding: (n_nodes, n_dims) spectral coordinates
        cluster_labels: (n_nodes,) hard cluster assignments
        temperature: Softmax temperature (lower = harder assignments)
    
    Returns:
        (n_nodes, n_clusters) membership probabilities
    """
    unique_labels = np.unique(cluster_labels)
    n_clusters = len(unique_labels)
    
    # Compute centroids
    centroids = np.zeros((n_clusters, embedding.shape[1]))
    for i, label in enumerate(unique_labels):
        mask = cluster_labels == label
        centroids[i] = embedding[mask].mean(axis=0)
    
    # Compute distances to all centroids
    distances = cdist(embedding, centroids, metric='euclidean')
    
    # Convert to probabilities via softmax
    similarities = np.exp(-distances / temperature)
    memberships = similarities / similarities.sum(axis=1, keepdims=True)
    
    return memberships


def compute_cluster_edges(
    adjacency: np.ndarray,  # or sparse matrix
    cluster_labels: np.ndarray,
    soft_memberships: np.ndarray,
    node_ids: np.ndarray,
    min_weight: float = 0.01
) -> List[ClusterEdge]:
    """
    Compute weighted edges between clusters.
    
    Edge weight = sum over all node pairs of:
        membership(i, cluster_A) * membership(j, cluster_B) * has_edge(i, j)
    
    Args:
        adjacency: Adjacency matrix (directed)
        cluster_labels: Hard cluster assignments
        soft_memberships: (n_nodes, n_clusters) membership probabilities
        node_ids: Node identifier array
        min_weight: Minimum weight to include edge
    
    Returns:
        List of ClusterEdge objects
    """
    unique_labels = np.unique(cluster_labels)
    n_clusters = len(unique_labels)
    label_to_idx = {label: i for i, label in enumerate(unique_labels)}
    
    # Initialize weight matrices (directed)
    weights = np.zeros((n_clusters, n_clusters))
    raw_counts = np.zeros((n_clusters, n_clusters), dtype=int)
    
    # Get edges from adjacency
    if hasattr(adjacency, 'tocoo'):
        adj_coo = adjacency.tocoo()
        edges = list(zip(adj_coo.row, adj_coo.col))
    else:
        edges = list(zip(*np.nonzero(adjacency)))
    
    # Accumulate weights
    for i, j in edges:
        # Raw count goes to hard-assigned clusters
        ci = label_to_idx[cluster_labels[i]]
        cj = label_to_idx[cluster_labels[j]]
        raw_counts[ci, cj] += 1
        
        # Weighted count uses soft membership
        for ci in range(n_clusters):
            for cj in range(n_clusters):
                weights[ci, cj] += soft_memberships[i, ci] * soft_memberships[j, cj]
    
    # Build edge list
    edges = []
    for ci in range(n_clusters):
        for cj in range(n_clusters):
            if ci == cj:
                continue  # skip self-loops
            
            weight = weights[ci, cj]
            if weight < min_weight:
                continue
            
            edges.append(ClusterEdge(
                source_id=f"cluster_{unique_labels[ci]}",
                target_id=f"cluster_{unique_labels[cj]}",
                weight=float(weight),
                raw_count=int(raw_counts[ci, cj]),
                direction='forward'
            ))
    
    return edges


def get_representative_handles(
    member_ids: List[str],
    node_metadata: Dict[str, Dict],
    n: int = 3
) -> List[str]:
    """
    Get top N handles by follower count for cluster labeling.
    
    Args:
        member_ids: Node IDs in cluster
        node_metadata: Dict mapping node_id to metadata (including num_followers)
        n: Number of handles to return
    
    Returns:
        List of handles, sorted by follower count descending
    """
    members_with_followers = []
    
    for node_id in member_ids:
        meta = node_metadata.get(node_id, {})
        handle = meta.get('username') or meta.get('handle') or node_id
        followers = meta.get('num_followers') or 0
        members_with_followers.append((handle, followers))
    
    # Sort by followers descending
    members_with_followers.sort(key=lambda x: x[1], reverse=True)
    
    return [handle for handle, _ in members_with_followers[:n]]


def generate_auto_label(cluster_id: int, representative_handles: List[str]) -> str:
    """Generate automatic cluster label from representative handles."""
    if not representative_handles:
        return f"Cluster {cluster_id}"
    
    handles_str = ", ".join(f"@{h}" for h in representative_handles[:3])
    return f"Cluster {cluster_id}: {handles_str}"


class ClusterLabelStore:
    """SQLite-backed storage for user-assigned cluster labels."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cluster_labels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_key TEXT UNIQUE NOT NULL,
                    user_label TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cluster_key 
                ON cluster_labels(cluster_key)
            """)
    
    def get_label(self, cluster_key: str) -> Optional[str]:
        """Get user-assigned label for cluster."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT user_label FROM cluster_labels WHERE cluster_key = ?",
                (cluster_key,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
    
    def set_label(self, cluster_key: str, label: str):
        """Set or update user-assigned label."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO cluster_labels (cluster_key, user_label)
                VALUES (?, ?)
                ON CONFLICT(cluster_key) DO UPDATE SET
                    user_label = excluded.user_label,
                    updated_at = CURRENT_TIMESTAMP
            """, (cluster_key, label))
    
    def delete_label(self, cluster_key: str):
        """Remove user-assigned label (revert to auto)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM cluster_labels WHERE cluster_key = ?",
                (cluster_key,)
            )
    
    def get_all_labels(self) -> Dict[str, str]:
        """Get all user-assigned labels."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT cluster_key, user_label FROM cluster_labels")
            return {row[0]: row[1] for row in cursor.fetchall()}


def build_cluster_view(
    embedding: np.ndarray,
    linkage_matrix: np.ndarray,
    node_ids: np.ndarray,
    adjacency,  # sparse or dense
    node_metadata: Dict[str, Dict],
    granularity: int,
    ego_node_id: Optional[str] = None,
    label_store: Optional[ClusterLabelStore] = None,
    louvain_communities: Optional[Dict[str, int]] = None,
    signal_weights: Optional[Dict[str, float]] = None
) -> ClusterViewData:
    """
    Build complete cluster view data for a given granularity.
    
    Args:
        embedding: Spectral embedding matrix
        linkage_matrix: Hierarchical clustering linkage
        node_ids: Array of node identifiers
        adjacency: Graph adjacency matrix
        node_metadata: Metadata for each node
        granularity: Target number of visible items
        ego_node_id: ID of ego node (for highlighting)
        label_store: SQLite store for user labels
        louvain_communities: Optional Louvain assignments for hybrid signal
        signal_weights: Weights for combining signals (default: spectral only)
    
    Returns:
        ClusterViewData ready for frontend rendering
    """
    # Default signal weights
    if signal_weights is None:
        signal_weights = {'spectral': 1.0, 'louvain': 0.0}
    
    # Cut hierarchy
    cluster_labels = cut_hierarchy_at_granularity(linkage_matrix, granularity)
    unique_labels = np.unique(cluster_labels)
    
    # Compute soft memberships
    soft_memberships = compute_soft_memberships(embedding, cluster_labels)
    
    # Find ego's cluster
    ego_cluster_label = None
    if ego_node_id is not None:
        ego_idx = np.where(node_ids == ego_node_id)[0]
        if len(ego_idx) > 0:
            ego_cluster_label = cluster_labels[ego_idx[0]]
    
    # Build cluster info
    clusters = []
    individual_nodes = []
    user_labels = label_store.get_all_labels() if label_store else {}
    
    for label in unique_labels:
        mask = cluster_labels == label
        member_indices = np.where(mask)[0].tolist()
        member_ids = node_ids[mask].tolist()
        
        # Check if cluster is too small
        if len(member_ids) < MIN_CLUSTER_SIZE:
            individual_nodes.extend(member_ids)
            continue
        
        # Compute centroid
        centroid = embedding[mask].mean(axis=0)
        
        # Get representative handles
        rep_handles = get_representative_handles(member_ids, node_metadata)
        
        # Determine label
        cluster_key = f"spectral_n{granularity}_c{label}"
        user_label = user_labels.get(cluster_key)
        
        if user_label:
            final_label = user_label
            label_source = 'user'
        else:
            final_label = generate_auto_label(label, rep_handles)
            label_source = 'auto'
        
        clusters.append(ClusterInfo(
            id=f"cluster_{label}",
            member_indices=member_indices,
            member_ids=member_ids,
            centroid=centroid,
            size=len(member_ids),
            label=final_label,
            label_source=label_source,
            representative_handles=rep_handles,
            contains_ego=(label == ego_cluster_label)
        ))
    
    # Compute inter-cluster edges
    edges = compute_cluster_edges(
        adjacency,
        cluster_labels,
        soft_memberships,
        node_ids,
        min_weight=0.01
    )
    
    # Determine ego cluster ID
    ego_cluster_id = None
    if ego_cluster_label is not None:
        ego_cluster_id = f"cluster_{ego_cluster_label}"
    
    return ClusterViewData(
        clusters=clusters,
        individual_nodes=individual_nodes,
        edges=edges,
        ego_cluster_id=ego_cluster_id,
        granularity=granularity,
        total_nodes=len(node_ids)
    )
```

### New File: `src/api/cluster_routes.py`

```python
"""
Flask routes for cluster visualization API.
"""

from flask import Blueprint, request, jsonify
from pathlib import Path
import numpy as np

from src.graph.spectral import load_spectral_result
from src.graph.clusters import (
    build_cluster_view,
    ClusterLabelStore,
    ClusterInfo,
    ClusterEdge
)

cluster_bp = Blueprint('clusters', __name__, url_prefix='/api/clusters')

# Global state (loaded on startup)
_spectral_result = None
_adjacency = None
_node_metadata = None
_label_store = None


def init_cluster_routes(app, data_dir: Path):
    """Initialize cluster routes with data."""
    global _spectral_result, _adjacency, _node_metadata, _label_store
    
    # Load spectral result
    _spectral_result = load_spectral_result(data_dir / 'graph_snapshot')
    
    # Load adjacency (from existing parquet)
    # TODO: Load from graph_snapshot.edges.parquet
    
    # Load node metadata
    # TODO: Load from graph_snapshot.nodes.parquet
    
    # Initialize label store
    _label_store = ClusterLabelStore(data_dir / 'clusters.db')
    
    app.register_blueprint(cluster_bp)


@cluster_bp.route('', methods=['GET'])
def get_clusters():
    """
    Get cluster structure at specified granularity.
    
    Query params:
        n: int - number of visible items (default 25)
        ego: str - ego node ID (optional)
        focus: str - focus cluster ID for drill-down (optional)
    
    Returns:
        ClusterViewData as JSON
    """
    granularity = request.args.get('n', 25, type=int)
    ego = request.args.get('ego', None, type=str)
    focus = request.args.get('focus', None, type=str)
    
    # Validate granularity
    granularity = max(5, min(500, granularity))
    
    # Build cluster view
    view_data = build_cluster_view(
        embedding=_spectral_result.embedding,
        linkage_matrix=_spectral_result.linkage_matrix,
        node_ids=_spectral_result.node_ids,
        adjacency=_adjacency,
        node_metadata=_node_metadata,
        granularity=granularity,
        ego_node_id=ego,
        label_store=_label_store
    )
    
    # Serialize for JSON
    return jsonify({
        'clusters': [_serialize_cluster(c) for c in view_data.clusters],
        'individual_nodes': view_data.individual_nodes,
        'edges': [_serialize_edge(e) for e in view_data.edges],
        'ego_cluster_id': view_data.ego_cluster_id,
        'granularity': view_data.granularity,
        'total_nodes': view_data.total_nodes,
        'meta': {
            'spectral_dims': _spectral_result.embedding.shape[1],
            'generated_at': _spectral_result.metadata.get('generated_at')
        }
    })


@cluster_bp.route('/<cluster_id>/members', methods=['GET'])
def get_cluster_members(cluster_id: str):
    """
    Get members of a specific cluster.
    
    Query params:
        limit: int - max members to return (default 100)
        offset: int - pagination offset (default 0)
    
    Returns:
        List of member node IDs with metadata
    """
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    # TODO: Implement member lookup
    
    return jsonify({
        'cluster_id': cluster_id,
        'members': [],
        'total': 0
    })


@cluster_bp.route('/<cluster_id>/label', methods=['POST'])
def set_cluster_label(cluster_id: str):
    """
    Set user-assigned label for cluster.
    
    Body:
        { "label": "Jhana Bros" }
    
    Returns:
        Updated cluster info
    """
    data = request.get_json()
    label = data.get('label', '').strip()
    
    if not label:
        return jsonify({'error': 'Label cannot be empty'}), 400
    
    # Extract granularity from cluster_id or request
    granularity = request.args.get('granularity', 25, type=int)
    cluster_key = f"spectral_n{granularity}_{cluster_id}"
    
    _label_store.set_label(cluster_key, label)
    
    return jsonify({
        'cluster_id': cluster_id,
        'label': label,
        'label_source': 'user'
    })


@cluster_bp.route('/<cluster_id>/label', methods=['DELETE'])
def delete_cluster_label(cluster_id: str):
    """Remove user-assigned label (revert to auto)."""
    granularity = request.args.get('granularity', 25, type=int)
    cluster_key = f"spectral_n{granularity}_{cluster_id}"
    
    _label_store.delete_label(cluster_key)
    
    return jsonify({'status': 'deleted'})


def _serialize_cluster(cluster: ClusterInfo) -> dict:
    """Serialize ClusterInfo for JSON response."""
    return {
        'id': cluster.id,
        'size': cluster.size,
        'label': cluster.label,
        'labelSource': cluster.label_source,
        'representativeHandles': cluster.representative_handles,
        'containsEgo': cluster.contains_ego,
        'centroid': cluster.centroid.tolist()
    }


def _serialize_edge(edge: ClusterEdge) -> dict:
    """Serialize ClusterEdge for JSON response."""
    return {
        'source': edge.source_id,
        'target': edge.target_id,
        'weight': edge.weight,
        'rawCount': edge.raw_count,
        'opacity': min(1.0, edge.weight / 10.0)  # normalize to [0, 1]
    }
```

### Caching, Cuts, and Performance Policy

- **Cluster cuts**: compute on-demand from the spectral linkage; cache results in-memory with an LRU keyed by `(granularity, ego, weight_bucket, focus)` where `weight_bucket` snaps sliders to 0.1 steps. Cache entries include cluster view data and 2D positions.
- **Cache bounds**: max 20 entries, TTL 10 minutes; evict LRU on overflow. Cold misses rebuild from preloaded spectral + adjacency; adjacency and embeddings are loaded at app start into CSR/ndarray.
- **Member lookup**: reuse the cached cluster view for the requested granularity; keep a per-view map `{cluster_id -> member_ids}` to serve `/api/clusters/{id}/members` without recomputing the cut. No global precompute of all granularities to avoid blowup.
- **Louvain storage**: load from `data/graph_snapshot.louvain.json` if present; if absent, compute during precompute, persist, and expose as an optional column when exporting nodes parquet.
- **Performance targets**: `/api/clusters` p95 ≤ 400 ms when served from cache; cold build ≤ 2 s on the 70K snapshot with data preloaded. Member endpoint p95 ≤ 250 ms from cache. Log timings and hit/miss status for every request for observability.

---

## Hybrid Signal Policy (Spectral + Louvain)

- **Blending approach**: edge-weight fusion (clusters stay spectral; edges respond to slider).
- **Weights**: user slider sets `w_spectral` and `w_louvain` with `w_spectral + w_louvain = 1`. Slider is continuous in UI but bucketed to 0.1 steps for caching.
- **Fusion formula**:
  - Compute spectral soft-membership–based edge weights as baseline.
  - For node pair (i, j), Louvain factor `f = 1 + w_louvain` if `comm_i == comm_j`, else `f = 1 - w_louvain` (clamp at ≥ 0).
  - Effective weight = baseline * `f`; aggregate to cluster-level edges; derive opacity from fused weight.
- **Cache bucketing**: `weight_bucket = round(w_louvain, 1)`; LRU key includes this bucket. Edges recompute per bucket; cluster assignments/layout remain fixed.
- **Label key convention**: `spectral_w{ws}_l{wl}_n{granularity}_c{label}` using bucketed weights (`ws`, `wl` with one decimal). Example: `spectral_w0.9_l0.1_n25_c7`. Rationale: stable keys per bucket, ready for future reclustering if ever needed.

---

## Layout / 2D Projection

- **Decision**: project cluster centroids (not all nodes) via PCA to 2D for clarity and stability; optionally allow UMAP with fixed `random_state` for similar effect. Spectral clusters remain fixed; only positions are projected.
- **Computation**: compute centroids in spectral space per cluster cut; run PCA (default) over the centroid set; cache resulting positions keyed by `(granularity, weight_bucket, focus)` alongside the cluster view. If PCA fails, fallback to first two spectral dimensions.
- **Overlap handling**: optional light repel pass (short force step) to de-overlap points without changing relative geometry; cache post-repel positions.
- **Rationale**: stable across zoom levels, inexpensive (few hundred centroids), deterministic with seed, avoids running full force layout per change.

---

## API Contracts

### GET /api/clusters

**Request:**
```
GET /api/clusters?n=25&ego=adityaarpitha&focus=cluster_7
```

**Response:**
```json
{
    "clusters": [
        {
            "id": "cluster_1",
            "size": 1247,
            "label": "Cluster 1: @eigenrobot, @visakanv, @nosilverv",
            "labelSource": "auto",
            "representativeHandles": ["eigenrobot", "visakanv", "nosilverv"],
            "containsEgo": true,
            "centroid": [0.123, -0.456, ...]
        },
        ...
    ],
    "individualNodes": ["node_123", "node_456"],
    "edges": [
        {
            "source": "cluster_1",
            "target": "cluster_2",
            "weight": 23.7,
            "rawCount": 147,
            "opacity": 0.8
        },
        ...
    ],
    "egoClusterId": "cluster_1",
    "granularity": 25,
    "totalNodes": 71761,
    "meta": {
        "spectralDims": 30,
        "generatedAt": "2024-12-05T10:30:00Z"
    }
}
```

### POST /api/clusters/{id}/label

**Request:**
```json
{
    "label": "Jhana Bros"
}
```

**Response:**
```json
{
    "clusterId": "cluster_7",
    "label": "Jhana Bros",
    "labelSource": "user"
}
```

### GET /api/clusters/{id}/members

**Request:**
```
GET /api/clusters/cluster_7/members?limit=50&offset=0
```

**Response:**
```json
{
    "clusterId": "cluster_7",
    "members": [
        {
            "id": "123456",
            "username": "jhana_master",
            "displayName": "Jhana Master",
            "numFollowers": 12000
        },
        ...
    ],
    "total": 487,
    "hasMore": true
}
```

---

## Frontend Components

### New File: `graph-explorer/src/ClusterView.jsx`

Core visualization component for clustered view. Will use canvas rendering for performance.

**Key responsibilities:**
- Render cluster nodes (circles with size proportional to member count)
- Render curved directed edges with gradient coloring
- Handle semantic zoom (scroll wheel)
- Handle pan (click-drag)
- Handle drill-down (double-click)
- Show member list panel (single-click)
- Context menu for renaming (right-click)
- Maintain ego cluster highlighting (purple)

### New File: `graph-explorer/src/ClusterNode.jsx`

Rendering logic for individual cluster nodes.

**Props:**
- `cluster`: ClusterInfo object
- `isEgo`: boolean
- `isSelected`: boolean
- `position`: {x, y} in canvas coords
- `onClick`, `onDoubleClick`, `onContextMenu`

### New File: `graph-explorer/src/ClusterEdge.jsx`

Rendering logic for directed cluster edges.

**Props:**
- `edge`: ClusterEdge object
- `sourcePos`, `targetPos`: coordinates
- `opacity`: derived from weight

**Rendering:**
- Curved bezier path
- Gradient from dark (source) to light (target)
- Arrow head at target

### New File: `graph-explorer/src/MemberListPanel.jsx`

Side panel showing cluster members.

**Props:**
- `cluster`: ClusterInfo or null
- `onClose`
- `onNodeClick`: navigate to individual

### New File: `graph-explorer/src/ClusterLabelEditor.jsx`

Inline editor for cluster labels.

**Props:**
- `cluster`: ClusterInfo
- `onSave`: (newLabel) => void
- `onCancel`

### Modified: `graph-explorer/src/App.jsx`

Add routing/toggle between GraphExplorer and ClusterView.

```jsx
// Add state for view mode
const [viewMode, setViewMode] = useState('cluster'); // 'cluster' | 'force'

// Render based on mode
{viewMode === 'cluster' ? (
    <ClusterView 
        ego={selectedEgo}
        onViewModeChange={setViewMode}
    />
) : (
    <GraphExplorer 
        onViewModeChange={setViewMode}
    />
)}
```

---

## State Management

### URL State

```
/explore?view=cluster&n=25&ego=adityaarpitha&focus=cluster_7

Parameters:
- view: 'cluster' | 'force'
- n: granularity (5-500)
- ego: ego node ID
- focus: focused cluster ID (for drill-down)
```

### React State (ClusterView)

```typescript
interface ClusterViewState {
    // Data from API
    clusters: ClusterInfo[];
    edges: ClusterEdge[];
    individualNodes: string[];
    
    // View state
    granularity: number;
    ego: string | null;
    focusCluster: string | null;
    
    // Interaction state
    selectedCluster: string | null;  // for member list panel
    pan: { x: number; y: number };
    
    // UI state
    showMemberPanel: boolean;
    editingLabel: string | null;
    contextMenu: { x: number; y: number; clusterId: string } | null;
}
```

### Zoom-to-Granularity Mapping

```typescript
// Adaptive: N = viewport capacity / average node visual size
function granularityFromZoom(
    viewportWidth: number,
    viewportHeight: number,
    minNodeSize: number = 80  // pixels
): number {
    const area = viewportWidth * viewportHeight;
    const nodeArea = minNodeSize * minNodeSize;
    const capacity = Math.floor(area / nodeArea);
    
    // Clamp to reasonable range
    return Math.max(10, Math.min(200, capacity));
}
```

---

## Implementation Plan

### Phase 1: Backend Foundation (Days 1-3)

**Day 1:**
- [ ] Create `src/graph/spectral.py` with core functions
- [ ] Unit tests for `compute_normalized_laplacian`
- [ ] Unit tests for `compute_spectral_embedding` (small test graph)

**Day 2:**
- [ ] Create `src/graph/clusters.py` with cluster management
- [ ] Unit tests for `cut_hierarchy_at_granularity`
- [ ] Unit tests for `compute_soft_memberships`
- [ ] Unit tests for `compute_cluster_edges`

**Day 3:**
- [ ] Create `scripts/build_spectral.py` to run precomputation
- [ ] Run spectral embedding on full graph (may take hours)
- [ ] Validate output, check stability metrics

### Phase 2: API Layer (Days 4-5)

**Day 4:**
- [ ] Create `src/api/cluster_routes.py`
- [ ] Integrate with existing Flask server
- [ ] Create `clusters.db` SQLite for labels
- [ ] Integration tests for `/api/clusters` endpoint

**Day 5:**
- [ ] Implement `/api/clusters/{id}/label` endpoints
- [ ] Implement `/api/clusters/{id}/members` endpoint
- [ ] Add URL state handling
- [ ] Test full API flow

### Phase 3: Frontend Core (Days 6-9)

**Day 6:**
- [ ] Create `ClusterView.jsx` skeleton
- [ ] Implement cluster data fetching
- [ ] Basic canvas rendering (circles for clusters)

**Day 7:**
- [ ] Implement curved edge rendering with gradients
- [ ] Implement opacity based on weight
- [ ] Implement pan (click-drag)

**Day 8:**
- [ ] Implement semantic zoom (scroll wheel)
- [ ] Granularity state management
- [ ] API refetch on granularity change

**Day 9:**
- [ ] Implement single-click (show member panel)
- [ ] Implement double-click (drill-down)
- [ ] Implement ego cluster highlighting

### Phase 4: Polish & Integration (Days 10-12)

**Day 10:**
- [ ] Create `MemberListPanel.jsx`
- [ ] Create `ClusterLabelEditor.jsx`
- [ ] Implement right-click context menu

**Day 11:**
- [ ] Add view mode toggle in `App.jsx`
- [ ] Implement URL state sync
- [ ] Cross-test with existing GraphExplorer

**Day 12:**
- [ ] Performance testing with full dataset
- [ ] Bug fixes
- [ ] Documentation updates

---

## File Changes Summary

### New Files

| File | Purpose |
|------|---------|
| `src/graph/spectral.py` | Spectral embedding computation |
| `src/graph/clusters.py` | Cluster management and view building |
| `src/api/cluster_routes.py` | Flask API routes for clusters |
| `scripts/build_spectral.py` | Precomputation script |
| `graph-explorer/src/ClusterView.jsx` | Main cluster visualization |
| `graph-explorer/src/ClusterNode.jsx` | Cluster node rendering |
| `graph-explorer/src/ClusterEdge.jsx` | Directed edge rendering |
| `graph-explorer/src/MemberListPanel.jsx` | Member list sidebar |
| `graph-explorer/src/ClusterLabelEditor.jsx` | Label editing |
| `graph-explorer/src/hooks/useClusterData.js` | Data fetching hook |
| `docs/adr/001-spectral-clustering-visualization.md` | This ADR |
| `docs/specs/spectral-clustering-spec.md` | This spec |
| `docs/test-plans/spectral-clustering-tests.md` | Test plan |

### Modified Files

| File | Changes |
|------|---------|
| `src/api/server.py` | Import and register cluster blueprint |
| `graph-explorer/src/App.jsx` | Add view mode toggle, routing |
| `graph-explorer/src/data.js` | Add cluster API functions |
| `scripts/build_snapshot.py` | Optionally trigger spectral build |

### New Data Files

| File | Contents |
|------|----------|
| `data/graph_snapshot.spectral.npz` | Embedding, linkage, node_ids |
| `data/graph_snapshot.spectral_meta.json` | Computation metadata |
| `data/clusters.db` | SQLite for user labels |

---

## Performance & Verification Scope (Anti-Goodhart)

- **CI scope**: small synthetic fixtures (50–500 nodes) plus one medium fixture (1–5k) with realistic structure; assert correctness and sub-second cluster view build. Do not run 70k in CI.
- **Slow suite**: optional `--slow` includes 10k–20k synthetic graphs to track scaling trends; not part of default CI.
- **Full graph**: 70k runs are manual “out-of-band performance validation” only; record findings separately.
- **Verification script**: add `scripts/verify_clusters.py` to run unit + medium integration on fixtures, emit ✓/✗ with timings and suggested next steps (pasteable into chat) per AGENTS rule.

---

## Appendix: Instrumentation Queries

To compare stability across runs:

```python
# scripts/compare_spectral_runs.py

import json
from pathlib import Path
import numpy as np
from sklearn.metrics import adjusted_rand_score

def compare_runs(run_dirs: list[Path], n_clusters: int = 50):
    """Compare clustering stability across multiple runs."""
    
    results = []
    for run_dir in run_dirs:
        meta_path = run_dir / 'graph_snapshot.spectral_meta.json'
        data_path = run_dir / 'graph_snapshot.spectral.npz'
        
        with open(meta_path) as f:
            meta = json.load(f)
        
        data = np.load(data_path)
        labels = fcluster(data['linkage'], t=n_clusters, criterion='maxclust')
        
        results.append({
            'dir': str(run_dir),
            'time': meta['computation_metrics']['total_time_seconds'],
            'eigenvalue_gap': meta['computation_metrics']['eigenvalue_gap'],
            'labels': labels
        })
    
    # Pairwise ARI comparison
    print("Pairwise Adjusted Rand Index:")
    for i, r1 in enumerate(results):
        for j, r2 in enumerate(results):
            if i < j:
                ari = adjusted_rand_score(r1['labels'], r2['labels'])
                print(f"  {r1['dir']} vs {r2['dir']}: ARI = {ari:.4f}")
    
    return results
```
