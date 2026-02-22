"""Observation-aware graph weighting utilities.

This module models partial observability in follow-graph snapshots.
Missing edges are treated as unknowns by estimating node-level observation
completeness and reweighting observed edges with inverse observation probability
(IPW) under a MAR approximation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

import numpy as np
import pandas as pd
import scipy.sparse as sp


VALID_WEIGHTING_MODES = {"off", "ipw"}


@dataclass(frozen=True)
class ObservationWeightingConfig:
    """Configuration for observation-aware adjacency construction."""

    mode: str = "off"
    p_min: float = 0.01
    completeness_floor: float = 0.01

    @classmethod
    def from_settings(cls, settings: Mapping[str, object] | None) -> "ObservationWeightingConfig":
        settings = settings or {}
        raw_mode = str(settings.get("obs_weighting", "off")).strip().lower()
        mode = raw_mode if raw_mode in VALID_WEIGHTING_MODES else "off"

        raw_p_min = settings.get("obs_p_min", 0.01)
        try:
            p_min = float(raw_p_min)
        except (TypeError, ValueError):
            p_min = 0.01
        p_min = max(1e-4, min(0.5, p_min))

        raw_floor = settings.get("obs_completeness_floor", 0.01)
        try:
            completeness_floor = float(raw_floor)
        except (TypeError, ValueError):
            completeness_floor = 0.01
        completeness_floor = max(1e-4, min(0.5, completeness_floor))

        return cls(mode=mode, p_min=p_min, completeness_floor=completeness_floor)


def compute_observation_completeness(
    edges_df: pd.DataFrame,
    node_ids: np.ndarray,
    expected_following: Optional[Mapping[str, float]] = None,
    *,
    source_col: str = "source",
    completeness_floor: float = 0.01,
) -> np.ndarray:
    """Estimate per-node completeness c_u in [floor, 1].

    Completeness is estimated as observed out-degree divided by expected out-degree,
    where expected out-degree defaults to observed out-degree when unavailable.
    """
    n_nodes = len(node_ids)
    id_to_idx = {str(nid): i for i, nid in enumerate(node_ids)}

    observed_out = np.zeros(n_nodes, dtype=np.float64)
    if source_col in edges_df.columns and not edges_df.empty:
        counts = edges_df[source_col].astype(str).value_counts(dropna=True)
        for node_id, count in counts.items():
            idx = id_to_idx.get(node_id)
            if idx is not None:
                observed_out[idx] = float(count)

    expected = observed_out.copy()
    if expected_following:
        for idx, nid in enumerate(node_ids):
            raw = expected_following.get(str(nid))
            if isinstance(raw, (int, float)) and np.isfinite(raw) and raw > 0:
                expected[idx] = float(raw)

    denom = np.maximum(expected, np.maximum(observed_out, 1.0))
    completeness = observed_out / denom
    completeness = np.clip(completeness, completeness_floor, 1.0)
    return completeness


def summarize_completeness(completeness: np.ndarray) -> Dict[str, float]:
    """Return compact summary stats for completeness vector."""
    if completeness.size == 0:
        return {
            "mean": 0.0,
            "median": 0.0,
            "p10": 0.0,
            "p90": 0.0,
            "min": 0.0,
            "max": 0.0,
        }

    return {
        "mean": float(np.mean(completeness)),
        "median": float(np.median(completeness)),
        "p10": float(np.percentile(completeness, 10)),
        "p90": float(np.percentile(completeness, 90)),
        "min": float(np.min(completeness)),
        "max": float(np.max(completeness)),
    }


def build_binary_adjacency_from_edges(
    edges_df: pd.DataFrame,
    node_ids: np.ndarray,
    *,
    mutual_col: str = "mutual",
) -> sp.csr_matrix:
    """Build unweighted adjacency with optional reverse edges for mutual ties."""
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

    edges_df = edges_df.copy()
    edges_df["src_idx"] = edges_df["source"].astype(str).map(id_to_idx)
    edges_df["tgt_idx"] = edges_df["target"].astype(str).map(id_to_idx)
    valid = edges_df.dropna(subset=["src_idx", "tgt_idx"])

    rows = valid["src_idx"].astype(int).to_numpy()
    cols = valid["tgt_idx"].astype(int).to_numpy()
    data = np.ones(len(rows), dtype=np.float32)

    if mutual_col in valid.columns:
        mutual_mask = valid[mutual_col].fillna(False).astype(bool).to_numpy()
        if np.any(mutual_mask):
            rows = np.concatenate([rows, valid.loc[mutual_mask, "tgt_idx"].astype(int).to_numpy()])
            cols = np.concatenate([cols, valid.loc[mutual_mask, "src_idx"].astype(int).to_numpy()])
            data = np.concatenate([data, np.ones(int(mutual_mask.sum()), dtype=np.float32)])

    return sp.csr_matrix((data, (rows, cols)), shape=(len(node_ids), len(node_ids)), dtype=np.float32)


def build_ipw_adjacency_from_edges(
    edges_df: pd.DataFrame,
    node_ids: np.ndarray,
    completeness: np.ndarray,
    *,
    p_min: float = 0.01,
    mutual_col: str = "mutual",
) -> Tuple[sp.csr_matrix, Dict[str, float]]:
    """Build observation-aware adjacency using inverse observation weighting.

    For each observed edge (u, v), use weight w_uv = 1 / p_uv where
    p_uv = clip((c_u * c_v) / mean(c), p_min, 1.0).
    """
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

    edges_df = edges_df.copy()
    edges_df["src_idx"] = edges_df["source"].astype(str).map(id_to_idx)
    edges_df["tgt_idx"] = edges_df["target"].astype(str).map(id_to_idx)
    valid = edges_df.dropna(subset=["src_idx", "tgt_idx"])

    if valid.empty:
        adjacency = sp.csr_matrix((len(node_ids), len(node_ids)), dtype=np.float32)
        stats = {
            "mode": "ipw",
            "observed_edges": 0,
            "weighted_edges": 0,
            "clipped_pairs": 0,
            "mean_pair_p": 0.0,
            "mean_weight": 0.0,
            "max_weight": 0.0,
        }
        return adjacency, stats

    src = valid["src_idx"].astype(int).to_numpy()
    tgt = valid["tgt_idx"].astype(int).to_numpy()

    c_bar = float(np.clip(np.mean(completeness), p_min, 1.0))
    raw_pair_p = (completeness[src] * completeness[tgt]) / c_bar
    pair_p = np.clip(raw_pair_p, p_min, 1.0)
    weights = (1.0 / pair_p).astype(np.float32)

    rows = src
    cols = tgt
    data = weights

    if mutual_col in valid.columns:
        mutual_mask = valid[mutual_col].fillna(False).astype(bool).to_numpy()
        if np.any(mutual_mask):
            rows = np.concatenate([rows, valid.loc[mutual_mask, "tgt_idx"].astype(int).to_numpy()])
            cols = np.concatenate([cols, valid.loc[mutual_mask, "src_idx"].astype(int).to_numpy()])
            data = np.concatenate([data, weights[mutual_mask]])

    adjacency = sp.csr_matrix((data, (rows, cols)), shape=(len(node_ids), len(node_ids)), dtype=np.float32)
    stats = {
        "mode": "ipw",
        "observed_edges": int(len(valid)),
        "weighted_edges": int(adjacency.count_nonzero()),
        "clipped_pairs": int(np.sum(raw_pair_p < p_min)),
        "mean_pair_p": float(np.mean(pair_p)),
        "mean_weight": float(np.mean(weights)),
        "max_weight": float(np.max(weights)),
    }
    return adjacency, stats
