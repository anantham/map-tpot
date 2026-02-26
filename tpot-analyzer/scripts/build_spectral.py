"""Precompute spectral embedding, linkage, and Louvain assignments."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, Tuple

import networkx as nx
import numpy as np
import pandas as pd
import scipy.sparse as sp

from src.api.snapshot_loader import SnapshotLoader
from src.communities.cluster_colors import load_propagation
from src.graph.community_affinity import (
    blend_affinity,
    build_m_bias,
    build_semantic_adjacency,
)
from src.graph.metrics import compute_louvain_communities
from src.graph.spectral import (
    SpectralConfig,
    compute_spectral_embedding,
    save_spectral_result,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def load_snapshot(data_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load nodes/edges parquet from data_dir."""
    loader = SnapshotLoader(snapshot_dir=data_dir)
    if not loader.snapshot_exists():
        raise FileNotFoundError(f"Snapshot files not found in {data_dir}")
    nodes_df = pd.read_parquet(loader.nodes_path)
    edges_df = pd.read_parquet(loader.edges_path)
    return nodes_df, edges_df


def build_adjacency(nodes_df: pd.DataFrame, edges_df: pd.DataFrame) -> Tuple[sp.csr_matrix, np.ndarray]:
    """Build directed adjacency matrix in CSR form."""
    node_ids = nodes_df["node_id"].astype(str).tolist()
    id_to_idx: Dict[str, int] = {nid: i for i, nid in enumerate(node_ids)}

    rows, cols = [], []
    data = []
    for _, row in edges_df.iterrows():
        src = id_to_idx.get(str(row["source"]))
        tgt = id_to_idx.get(str(row["target"]))
        if src is None or tgt is None:
            continue
        weight = 1.0
        rows.append(src)
        cols.append(tgt)
        data.append(weight)
    adjacency = sp.csr_matrix((data, (rows, cols)), shape=(len(node_ids), len(node_ids)))
    return adjacency, np.array(node_ids)


def build_louvain(edges_df: pd.DataFrame, nodes_df: pd.DataFrame) -> Dict[str, int]:
    """Compute Louvain assignments using NetworkX on undirected view."""
    G = nx.Graph()
    G.add_nodes_from(nodes_df["node_id"].astype(str))
    for _, row in edges_df.iterrows():
        G.add_edge(str(row["source"]), str(row["target"]))
    return compute_louvain_communities(G)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build spectral embedding + Louvain.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="Directory containing graph_snapshot.*")
    parser.add_argument("--n-dims", type=int, default=30)
    parser.add_argument("--maxiter", type=int, default=5000)
    parser.add_argument("--tol", type=float, default=1e-10)
    parser.add_argument("--resolution", type=float, default=1.0, help="Louvain resolution")
    parser.add_argument("--output-prefix", type=Path, default=None, help="Base path for spectral output (default data/graph_snapshot)")
    parser.add_argument("--limit-nodes", type=int, default=None, help="Limit nodes for fixture generation")
    parser.add_argument("--stability-runs", type=int, default=1, help="Number of stability runs (ARI) >=1")
    parser.add_argument("--birch-threshold", type=float, default=0.3, help="BIRCH clustering threshold (lower = more micro-clusters, default 0.3)")
    parser.add_argument("--max-linkage-nodes", type=int, default=12000, help="Max nodes for direct Ward linkage (default 12000)")
    parser.add_argument("--alpha", type=float, default=0.0, help="Community blending weight [0,1]. 0=pure topology (default)")
    parser.add_argument("--propagation", type=Path, default=None, help="Path to community_propagation.npz (required if alpha>0)")
    args = parser.parse_args()

    data_dir = args.data_dir
    out_prefix = args.output_prefix or (data_dir / "graph_snapshot")

    nodes_df, edges_df = load_snapshot(data_dir)
    if args.limit_nodes:
        nodes_df = nodes_df.head(args.limit_nodes).copy()
        keep_ids = set(nodes_df["node_id"].astype(str))
        edges_df = edges_df[edges_df["source"].astype(str).isin(keep_ids) & edges_df["target"].astype(str).isin(keep_ids)]
        logger.info("Limiting to %s nodes, %s edges for fixture", len(nodes_df), len(edges_df))

    adjacency, node_ids = build_adjacency(nodes_df, edges_df)

    # Community-aware blending (when alpha > 0)
    if args.alpha > 0:
        if args.propagation is None:
            args.propagation = data_dir / "community_propagation.npz"
        prop = load_propagation(args.propagation)
        if prop is None:
            raise FileNotFoundError(f"Propagation file not found: {args.propagation}")

        logger.info("Blending with alpha=%.2f from %s", args.alpha, args.propagation)

        # Align propagation node ordering to adjacency node ordering
        prop_idx_map = prop.node_id_to_idx
        n = len(node_ids)
        aligned_indices = []
        for nid in node_ids:
            idx = prop_idx_map.get(str(nid))
            if idx is not None:
                aligned_indices.append(idx)
            else:
                aligned_indices.append(-1)  # will get zero row

        aligned_indices = np.array(aligned_indices)
        valid_mask = aligned_indices >= 0
        logger.info("Node alignment: %d/%d matched", valid_mask.sum(), n)

        # Extract aligned memberships
        aligned_memberships = np.zeros((n, prop.memberships.shape[1]), dtype=np.float32)
        aligned_memberships[valid_mask] = prop.memberships[aligned_indices[valid_mask]]

        aligned_uncertainty = np.zeros(n, dtype=np.float32)
        aligned_uncertainty[valid_mask] = prop.uncertainty[aligned_indices[valid_mask]]

        # Build M_bias and A_sem
        m_bias = build_m_bias(aligned_memberships, prop.converged, aligned_uncertainty)
        a_sem = build_semantic_adjacency(m_bias, top_k=20)

        # Symmetrize A_topo for blending (spectral needs undirected)
        a_topo = adjacency.maximum(adjacency.T).tocsr()
        adjacency = blend_affinity(a_topo, a_sem, args.alpha)
        logger.info("Blended adjacency: %d nonzeros", adjacency.nnz)

        # Adjust output prefix
        alpha_tag = f".a{int(args.alpha * 100)}"
        out_prefix = Path(str(out_prefix) + alpha_tag)
        logger.info("Output prefix: %s", out_prefix)

    cfg = SpectralConfig(
        n_dims=args.n_dims,
        eigensolver_tol=args.tol,
        eigensolver_maxiter=args.maxiter,
        stability_runs=max(1, args.stability_runs),
        birch_threshold=args.birch_threshold,
        max_linkage_nodes=args.max_linkage_nodes,
    )
    result = compute_spectral_embedding(adjacency, node_ids, cfg)
    save_spectral_result(result, Path(out_prefix))

    logger.info("Computing Louvain communities (resolution=%s)...", args.resolution)
    louvain = build_louvain(edges_df, nodes_df)
    lou_path = Path(out_prefix).with_suffix(".louvain.json")
    lou_path.write_text(json.dumps(louvain))
    logger.info("Saved Louvain assignments to %s", lou_path)


if __name__ == "__main__":
    main()
