"""I/O utilities for propagation — save results and build adjacency from archive."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy.sparse as sp

from src.propagation.types import PropagationResult


def save_results(result: PropagationResult, output_dir: Path) -> Path:
    """Save propagation results as compressed numpy archive.

    Creates two files:
    - Timestamped archive in data/community_propagation_runs/
    - Active pointer at data/community_propagation.npz
    """
    archive_dir = output_dir / "community_propagation_runs"
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = archive_dir / f"{timestamp}.npz"

    active_path = output_dir / "community_propagation.npz"

    save_arrays = dict(
        memberships=result.memberships.astype(np.float32),
        uncertainty=result.uncertainty.astype(np.float32),
        abstain_mask=result.abstain_mask,
        labeled_mask=result.labeled_mask,
        node_ids=result.node_ids,
        community_ids=np.array(result.community_ids),
        community_names=np.array(result.community_names),
        community_colors=np.array(result.community_colors),
        converged=np.array(result.converged, dtype=bool),
        cg_iterations=np.array(result.cg_iterations, dtype=np.int32),
        mode=np.array(result.config.mode),
    )
    if result.seed_neighbor_counts is not None:
        save_arrays["seed_neighbor_counts"] = result.seed_neighbor_counts.astype(np.int16)

    np.savez_compressed(str(archive_path), **save_arrays)
    np.savez_compressed(str(active_path), **save_arrays)

    print(f"\nResults saved:")
    print(f"  Archive: {archive_path}")
    print(f"  Active:  {active_path}")
    print(f"  Size: {active_path.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"  Arrays: {list(save_arrays.keys())}")
    return active_path


def build_adjacency_from_archive(
    db_path: Path, weighted: bool = True
) -> tuple[sp.csr_matrix, list[str]]:
    """Build adjacency matrix from archive_tweets.db follow + engagement data.

    Returns (adjacency: csr_matrix, node_ids: list[str])

    The graph includes:
    - All follow edges from account_following (binary or engagement-weighted)
    - Edge weights from account_engagement_agg when available and weighted=True

    Weight formula (engagement-enriched):
      base = 1.0 (follow edge)
      + 0.6 * min(rt_count / 10, 1.0)   — retweets signal strong alignment
      + 0.4 * min(like_count / 50, 1.0)  — likes signal weaker agreement
      + 0.2 * min(reply_count / 5, 1.0)  — replies signal interaction
    """
    conn = sqlite3.connect(str(db_path))

    # 1. Get all unique node IDs from the follow graph
    print("  Loading follow edges from account_following...")
    sources = set(
        r[0] for r in conn.execute(
            "SELECT DISTINCT account_id FROM account_following"
        ).fetchall()
    )
    targets = set(
        r[0] for r in conn.execute(
            "SELECT DISTINCT following_account_id FROM account_following"
        ).fetchall()
    )
    all_nodes = sorted(sources | targets)
    node_idx = {nid: i for i, nid in enumerate(all_nodes)}
    n = len(all_nodes)
    print(f"  Unique nodes: {n:,} ({len(sources):,} sources, {len(targets):,} targets)")

    # 2. Build sparse adjacency from follow edges
    follows = conn.execute(
        "SELECT account_id, following_account_id FROM account_following"
    ).fetchall()
    print(f"  Follow edges: {len(follows):,}")

    row_indices = []
    col_indices = []
    data_values = []
    for src, tgt in follows:
        i = node_idx.get(src)
        j = node_idx.get(tgt)
        if i is not None and j is not None:
            row_indices.append(i)
            col_indices.append(j)
            data_values.append(1.0)

    adj = sp.csr_matrix(
        (np.array(data_values, dtype=np.float32), (row_indices, col_indices)),
        shape=(n, n),
    )

    # 3. Enrich with engagement weights (if available and requested)
    if weighted:
        try:
            table_exists = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='account_engagement_agg'"
            ).fetchone()[0]
            if not table_exists:
                print("  Warning: account_engagement_agg table not found, using unweighted follow graph")
            else:
                print("  Loading engagement weights from account_engagement_agg...")
                engagement = conn.execute("""
                    SELECT source_id, target_id, follow_flag, like_count, reply_count, rt_count
                    FROM account_engagement_agg
                """).fetchall()
                print(f"  Engagement pairs: {len(engagement):,}")

                enrich_rows = []
                enrich_cols = []
                enrich_vals = []
                enriched_count = 0
                for src, tgt, follow, likes, replies, rts in engagement:
                    i = node_idx.get(src)
                    j = node_idx.get(tgt)
                    if i is not None and j is not None:
                        w = 1.0 if follow else 0.0
                        w += 0.6 * min(rts / 10, 1.0) if rts else 0
                        w += 0.4 * min(likes / 50, 1.0) if likes else 0
                        w += 0.2 * min(replies / 5, 1.0) if replies else 0
                        if w > 0:
                            enrich_rows.append(i)
                            enrich_cols.append(j)
                            enrich_vals.append(w)
                            enriched_count += 1

                if enrich_vals:
                    enrich_mat = sp.csr_matrix(
                        (np.array(enrich_vals, dtype=np.float32),
                         (enrich_rows, enrich_cols)),
                        shape=(n, n),
                    )
                    adj = adj.maximum(enrich_mat).tocsr()
                    print(f"  Enriched {enriched_count:,} edges with engagement weights")
        except Exception as e:
            print(f"  Warning: engagement enrichment failed: {e}")

    conn.close()

    print(f"  Archive graph: {n:,} nodes, {adj.nnz:,} edges")
    return adj, all_nodes
