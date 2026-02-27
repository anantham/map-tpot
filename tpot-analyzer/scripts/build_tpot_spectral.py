"""Build spectral embedding for the TPOT-focused subgraph.

Loads propagation + calibrated threshold, computes relevance scores,
builds core+halo subgraph with reweighted adjacency W' = D_r^{1/2} W D_r^{1/2},
then runs spectral embedding on the filtered+reweighted graph.

Usage:
    # After calibration:
    .venv/bin/python3 -m scripts.build_tpot_spectral
    .venv/bin/python3 -m scripts.build_tpot_spectral --tau 0.08
"""
from __future__ import annotations

import argparse
import json
import logging
import pickle  # NOTE: only loads our own cached adjacency matrix, not untrusted data
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

from src.graph.spectral import SpectralConfig, compute_spectral_embedding, save_spectral_result
from src.graph.tpot_relevance import build_core_halo_mask, compute_relevance, reweight_adjacency

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def load_adjacency(path: Path) -> sp.csr_matrix:
    """Load cached adjacency matrix (our own precomputed data)."""
    with open(path, "rb") as f:
        cached = pickle.load(f)
    if isinstance(cached, dict) and "adjacency" in cached:
        return cached["adjacency"].tocsr()
    return cached.tocsr()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build TPOT-focused spectral embedding")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--tau", type=float, default=None,
                        help="Relevance threshold (default: from tpot_calibration.json)")
    parser.add_argument("--n-dims", type=int, default=30)
    parser.add_argument("--maxiter", type=int, default=5000)
    parser.add_argument("--tol", type=float, default=1e-10)
    parser.add_argument("--birch-threshold", type=float, default=0.3)
    parser.add_argument("--max-linkage-nodes", type=int, default=12000)
    parser.add_argument("--output-prefix", type=Path, default=None,
                        help="Output prefix (default: data/graph_snapshot_tpot)")
    args = parser.parse_args()

    data_dir = args.data_dir
    out_prefix = args.output_prefix or (data_dir / "graph_snapshot_tpot")

    # --- Load threshold ---
    tau = args.tau
    if tau is None:
        cal_path = data_dir / "tpot_calibration.json"
        if cal_path.exists():
            cal = json.loads(cal_path.read_text())
            tau = cal["tau"]
            logger.info("Using calibrated tau=%.4f from %s", tau, cal_path)
        else:
            tau = 0.05
            logger.warning("No calibration found, using default tau=%.4f", tau)

    # --- Load propagation ---
    # Prefer production propagation (all seeds) for the actual build
    prop_path = data_dir / "community_propagation.npz"
    if not prop_path.exists():
        prop_path = data_dir / "community_propagation_train.npz"
    logger.info("Loading propagation: %s", prop_path)
    prop = np.load(str(prop_path), allow_pickle=True)
    memberships = prop["memberships"]
    uncertainty = prop["uncertainty"]
    converged = prop["converged"]
    node_ids = prop["node_ids"]
    n_total = len(node_ids)

    # --- Load adjacency ---
    adj_path = data_dir / "adjacency_matrix_cache.pkl"
    logger.info("Loading adjacency: %s", adj_path)
    adjacency = load_adjacency(adj_path)

    # Symmetrize for spectral (needs undirected)
    adjacency_sym = adjacency.maximum(adjacency.T).tocsr()

    # --- Compute degrees and relevance ---
    degrees = np.asarray(adjacency_sym.sum(axis=1)).flatten()
    median_deg = float(np.median(degrees[degrees > 0]))
    logger.info("Median degree (nonzero): %.1f", median_deg)

    r = compute_relevance(memberships, uncertainty, converged, degrees, median_deg)

    # --- Build core+halo mask ---
    mask = build_core_halo_mask(r, adjacency_sym, tau)
    n_selected = mask.sum()
    n_core = (r >= tau).sum()
    logger.info("TPOT subgraph: %d core + %d halo = %d total (%.1f%% of %d)",
                n_core, n_selected - n_core, n_selected,
                100.0 * n_selected / n_total, n_total)

    # --- Extract subgraph ---
    selected_indices = np.flatnonzero(mask)
    sub_adjacency = adjacency_sym[np.ix_(selected_indices, selected_indices)].tocsr()
    sub_node_ids = node_ids[selected_indices]
    sub_r = r[selected_indices]

    # --- Reweight adjacency: W' = D_r^{1/2} W D_r^{1/2} ---
    # For halo nodes with r=0, set a small floor so they still contribute weakly
    sub_r_floored = np.maximum(sub_r, 0.01)
    reweighted = reweight_adjacency(sub_adjacency, sub_r_floored)
    logger.info("Reweighted adjacency: %d nodes, %d nonzeros", reweighted.shape[0], reweighted.nnz)

    # --- Run spectral embedding ---
    cfg = SpectralConfig(
        n_dims=args.n_dims,
        eigensolver_tol=args.tol,
        eigensolver_maxiter=args.maxiter,
        birch_threshold=args.birch_threshold,
        max_linkage_nodes=args.max_linkage_nodes,
    )
    logger.info("Computing spectral embedding (%d dims)...", cfg.n_dims)
    result = compute_spectral_embedding(reweighted, sub_node_ids, cfg)

    # --- Save ---
    save_spectral_result(result, Path(out_prefix))
    logger.info("Saved TPOT spectral to %s.*", out_prefix)

    # Save node mapping (for backend to look up original metadata)
    mapping = {
        "tau": float(tau),
        "n_total_graph": int(n_total),
        "n_tpot_subgraph": int(n_selected),
        "n_core": int(n_core),
        "n_halo": int(n_selected - n_core),
        "tpot_node_ids": [str(nid) for nid in sub_node_ids],
    }
    mapping_path = Path(str(out_prefix) + ".mapping.json")
    mapping_path.write_text(json.dumps(mapping))
    logger.info("Saved TPOT node mapping: %s", mapping_path)

    # Also save filtered nodes parquet for downstream use
    nodes_full = pd.read_parquet(data_dir / "graph_snapshot.nodes.parquet")
    sub_ids_set = set(str(nid) for nid in sub_node_ids)
    nodes_tpot = nodes_full[nodes_full["node_id"].astype(str).isin(sub_ids_set)]
    nodes_tpot_path = Path(str(out_prefix) + ".nodes.parquet")
    nodes_tpot.to_parquet(str(nodes_tpot_path), index=False)
    logger.info("Saved TPOT nodes parquet: %s (%d rows)", nodes_tpot_path, len(nodes_tpot))

    # Filtered edges (both endpoints in subgraph)
    edges_full = pd.read_parquet(data_dir / "graph_snapshot.edges.parquet")
    edges_tpot = edges_full[
        edges_full["source"].astype(str).isin(sub_ids_set)
        & edges_full["target"].astype(str).isin(sub_ids_set)
    ]
    edges_tpot_path = Path(str(out_prefix) + ".edges.parquet")
    edges_tpot.to_parquet(str(edges_tpot_path), index=False)
    logger.info("Saved TPOT edges parquet: %s (%d rows)", edges_tpot_path, len(edges_tpot))


if __name__ == "__main__":
    main()
