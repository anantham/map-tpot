"""Spectral embedding and hierarchical clustering utilities."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import eigsh, ArpackNoConvergence
from sklearn.cluster import Birch
from sklearn.metrics import adjusted_rand_score

logger = logging.getLogger(__name__)


@dataclass
class SpectralConfig:
    """Configuration for spectral embedding computation."""

    n_dims: int = 30
    eigensolver_tol: float = 1e-10
    eigensolver_maxiter: int = 5000
    linkage_method: str = "ward"
    stability_runs: int = 1  # >=2 enables stability ARI check
    max_linkage_nodes: int = 12000  # above this, use approximate method
    birch_threshold: float = 0.3  # BIRCH clustering threshold


@dataclass
class SpectralResult:
    """Result of spectral embedding computation."""

    embedding: np.ndarray  # (n_nodes, n_dims)
    node_ids: np.ndarray  # (n_nodes,)
    eigenvalues: np.ndarray  # (n_dims,)
    linkage_matrix: np.ndarray  # (n_nodes - 1, 4) OR (n_micro - 1, 4) for approx
    metadata: Dict[str, Any]
    # For approximate mode (large graphs):
    micro_labels: Optional[np.ndarray] = None  # (n_nodes,) micro-cluster assignments
    micro_centroids: Optional[np.ndarray] = None  # (n_micro, n_dims)


def _row_normalize(matrix: np.ndarray) -> np.ndarray:
    """Normalize rows to unit length."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def compute_normalized_laplacian(adjacency: csr_matrix) -> csr_matrix:
    """
    Compute symmetric normalized Laplacian.

    L_sym = I - D^{-1/2} A D^{-1/2}
    """
    # Symmetrize
    A = (adjacency + adjacency.T) / 2
    A = A.tocsr()

    degrees = np.array(A.sum(axis=1)).flatten()
    degrees[degrees == 0] = 1  # avoid division by zero

    d_inv_sqrt = 1.0 / np.sqrt(degrees)
    n = adjacency.shape[0]
    D_inv_sqrt = csr_matrix((d_inv_sqrt, (np.arange(n), np.arange(n))))
    I = csr_matrix((np.ones(n), (np.arange(n), np.arange(n))))

    L = I - D_inv_sqrt @ A @ D_inv_sqrt
    return L


def compute_spectral_embedding(
    adjacency: csr_matrix,
    node_ids: Iterable[str],
    config: Optional[SpectralConfig] = None,
) -> SpectralResult:
    """Compute spectral embedding and linkage for clustering."""
    cfg = config or SpectralConfig()
    node_ids = np.array(list(node_ids))

    metrics: Dict[str, Any] = {}
    start_total = time.time()
    n_nodes = adjacency.shape[0]
    
    logger.info(
        "Starting spectral embedding: %s nodes, %s dims",
        n_nodes,
        cfg.n_dims,
    )

    # Laplacian
    start = time.time()
    L = compute_normalized_laplacian(adjacency)
    metrics["laplacian_time_seconds"] = time.time() - start

    # Eigendecomposition (k = n_dims + 1, drop first)
    start = time.time()
    if n_nodes <= 2:
        # tiny graphs: fall back to dense eigh
        vals, vecs = np.linalg.eigh(L.toarray())
        converged = True
    else:
        k = min(cfg.n_dims + 1, max(1, n_nodes - 1))  # ARPACK requires k < N
        try:
            vals, vecs = eigsh(
                L,
                k=k,
                which="SM",
                tol=cfg.eigensolver_tol,
                maxiter=cfg.eigensolver_maxiter,
                return_eigenvectors=True,
            )
            converged = True
        except ArpackNoConvergence as exc:
            logger.warning("ARPACK did not fully converge: %s", exc)
            vals, vecs = exc.eigenvalues, exc.eigenvectors
            converged = False
    metrics["eigensolver_time_seconds"] = time.time() - start
    metrics["eigensolver_converged"] = converged

    # Sort and drop trivial eigenvector
    idx = np.argsort(vals)
    eigenvalues = vals[idx]
    eigenvectors = vecs[:, idx]
    use_dims = min(cfg.n_dims, max(0, eigenvectors.shape[1] - 1))
    eigenvalues = eigenvalues[1 : use_dims + 1]
    eigenvectors = eigenvectors[:, 1 : use_dims + 1]

    if len(eigenvalues) >= 2:
        metrics["eigenvalue_gap"] = float(eigenvalues[-1] - eigenvalues[-2])
    else:
        metrics["eigenvalue_gap"] = 0.0

    embedding = _row_normalize(eigenvectors.astype(np.float32))

    # Hierarchical clustering on embedding
    start = time.time()
    micro_labels = None
    micro_centroids = None
    
    if n_nodes <= cfg.max_linkage_nodes:
        # Direct hierarchical clustering (fits in memory)
        logger.info("Using direct Ward linkage for %d nodes", n_nodes)
        linkage_matrix = linkage(embedding, method=cfg.linkage_method)
        metrics["linkage_method_used"] = "direct_ward"
    else:
        # Approximate hierarchical clustering for large graphs
        # Use BIRCH to create micro-clusters, then cluster those
        logger.info(
            "Using BIRCH approximate clustering for %d nodes (threshold=%.2f)",
            n_nodes, cfg.birch_threshold
        )
        
        # Target ~8000-10000 micro-clusters for reasonable memory
        birch = Birch(
            n_clusters=None,  # Let BIRCH decide based on threshold
            threshold=cfg.birch_threshold,
            branching_factor=50
        )
        micro_labels = birch.fit_predict(embedding)
        micro_centroids = birch.subcluster_centers_
        n_micro = len(micro_centroids)
        
        logger.info("BIRCH created %d micro-clusters from %d nodes", n_micro, n_nodes)
        
        # If still too many, reduce with k-means
        if n_micro > cfg.max_linkage_nodes:
            logger.info("Reducing %d micro-clusters to %d with k-means", n_micro, cfg.max_linkage_nodes)
            from sklearn.cluster import MiniBatchKMeans
            kmeans = MiniBatchKMeans(n_clusters=cfg.max_linkage_nodes, random_state=42, batch_size=1000)
            # Re-cluster nodes directly
            micro_labels = kmeans.fit_predict(embedding)
            micro_centroids = kmeans.cluster_centers_
            n_micro = len(micro_centroids)
        
        # Hierarchical clustering on micro-cluster centroids
        logger.info("Computing Ward linkage on %d micro-cluster centroids", n_micro)
        linkage_matrix = linkage(micro_centroids, method=cfg.linkage_method)
        
        metrics["linkage_method_used"] = "birch_approximate"
        metrics["n_micro_clusters"] = n_micro
    
    metrics["linkage_time_seconds"] = time.time() - start

    # Stability check (optional)
    stability_mean = 1.0
    stability_std = 0.0
    if cfg.stability_runs and cfg.stability_runs > 1 and n_nodes <= cfg.max_linkage_nodes:
        # Only run stability check for direct linkage (expensive otherwise)
        base_labels = fcluster(
            linkage_matrix,
            t=min(50, embedding.shape[0]),
            criterion="maxclust",
        )
        ari_scores = []
        for _ in range(cfg.stability_runs - 1):
            noise = np.random.normal(0, 0.001, embedding.shape)
            noisy_embed = _row_normalize(embedding + noise.astype(np.float32))
            noisy_linkage = linkage(noisy_embed, method=cfg.linkage_method)
            cut = fcluster(noisy_linkage, t=min(50, noisy_embed.shape[0]), criterion="maxclust")
            ari_scores.append(adjusted_rand_score(base_labels, cut))
        if ari_scores:
            stability_mean = float(np.mean(ari_scores))
            stability_std = float(np.std(ari_scores))
    metrics["stability_ari_mean"] = stability_mean
    metrics["stability_ari_std"] = stability_std

    metrics["total_time_seconds"] = time.time() - start_total

    metadata = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "n_nodes": len(node_ids),
        "n_dims": cfg.n_dims,
        "method": "normalized_laplacian",
        "eigensolver": "arpack",
        "eigensolver_params": {
            "tol": cfg.eigensolver_tol,
            "maxiter": cfg.eigensolver_maxiter,
        },
        "linkage_method": cfg.linkage_method,
        "approximate_clustering": n_nodes > cfg.max_linkage_nodes,
        "computation_metrics": metrics,
    }

    return SpectralResult(
        embedding=embedding,
        node_ids=node_ids,
        eigenvalues=eigenvalues.astype(np.float32),
        linkage_matrix=linkage_matrix.astype(np.float64),
        metadata=metadata,
        micro_labels=micro_labels,
        micro_centroids=micro_centroids.astype(np.float32) if micro_centroids is not None else None,
    )


def save_spectral_result(result: SpectralResult, base_path: Path) -> None:
    """Persist spectral result arrays and metadata."""
    save_dict = {
        "embedding": result.embedding,
        "node_ids": result.node_ids,
        "eigenvalues": result.eigenvalues,
        "linkage": result.linkage_matrix,
    }
    
    # Save micro-cluster data if using approximate mode
    if result.micro_labels is not None:
        save_dict["micro_labels"] = result.micro_labels
    if result.micro_centroids is not None:
        save_dict["micro_centroids"] = result.micro_centroids
    
    np.savez_compressed(
        base_path.with_suffix(".spectral.npz"),
        **save_dict
    )
    meta_path = base_path.with_suffix(".spectral_meta.json")
    meta_path.write_text(json.dumps(result.metadata, indent=2))
    logger.info("Saved spectral result to %s(.spectral.*)", base_path)


def load_spectral_result(base_path: Path) -> SpectralResult:
    """Load spectral result from disk."""
    data = np.load(base_path.with_suffix(".spectral.npz"))
    meta_path = base_path.with_suffix(".spectral_meta.json")
    metadata = json.loads(meta_path.read_text())

    # NpzFile doesn't have .get(), check keys explicitly
    micro_labels = data["micro_labels"] if "micro_labels" in data.files else None
    micro_centroids = data["micro_centroids"] if "micro_centroids" in data.files else None

    return SpectralResult(
        embedding=data["embedding"],
        node_ids=data["node_ids"],
        eigenvalues=data["eigenvalues"],
        linkage_matrix=data["linkage"],
        metadata=metadata,
        micro_labels=micro_labels,
        micro_centroids=micro_centroids,
    )
