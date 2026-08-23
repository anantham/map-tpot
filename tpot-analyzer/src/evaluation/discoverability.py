"""Fast, deterministic diagnostics for the frozen discoverability control."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import sparse

from src.evaluation.discoverability_topology import (
    build_graph_views,
    component_summary,
    reachability_summary,
)

FIXED_SEED_PRESET = "adi_tpot"
EXPECTED_EXPLORER_SEEDS = 18

@dataclass(frozen=True)
class FalsifierThresholds:
    center_node_max_pct: float = 10.0
    center_edge_min_pct: float = 90.0
    degree_one_min_pct: float = 50.0
    semantics_change_min_pp: float = 5.0
    high_degree_min: int = 51
    selection_gap_min_pp: float = 10.0

def load_fixed_seed_handles(path: Path) -> list[str]:
    """Load the fixed 18-handle explorer panel and reject semantic drift."""
    try:
        payload = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read explorer seed file {path}: {exc}") from exc
    handles = payload.get(FIXED_SEED_PRESET) if isinstance(payload, dict) else None
    if not isinstance(handles, list) or not all(isinstance(x, str) for x in handles):
        raise ValueError(f"seed preset {FIXED_SEED_PRESET!r} must be a string list")
    normalized = [x.strip().lstrip("@").lower() for x in handles]
    if len(normalized) != EXPECTED_EXPLORER_SEEDS or len(set(normalized)) != len(normalized):
        raise ValueError(
            f"seed preset {FIXED_SEED_PRESET!r} must contain exactly "
            f"{EXPECTED_EXPLORER_SEEDS} unique handles; got {len(normalized)}"
        )
    return normalized

def resolve_seed_indices(nodes: pd.DataFrame, handles: Iterable[str]) -> np.ndarray:
    """Resolve every supplied handle uniquely against the frozen nodes."""
    if not {"node_id", "username"}.issubset(nodes.columns):
        raise ValueError("nodes require node_id and username for seed resolution")
    lookup: dict[str, list[int]] = {}
    for index, username in enumerate(nodes["username"]):
        if pd.notna(username):
            lookup.setdefault(str(username).lower(), []).append(index)
    resolved, failures = [], []
    for raw in handles:
        handle = str(raw).strip().lstrip("@").lower()
        matches = lookup.get(handle, [])
        if len(matches) == 1:
            resolved.append(matches[0])
        else:
            failures.append(f"{handle}({len(matches)} matches)")
    if failures:
        raise ValueError("fixed explorer seeds did not resolve uniquely: " + ", ".join(failures))
    if not resolved:
        raise ValueError("fixed explorer seed panel is empty")
    return np.asarray(resolved, dtype=np.int64)

def _capture(nodes: pd.DataFrame, edges: pd.DataFrame, degree: np.ndarray) -> dict:
    inbound = edges["direction_label"].eq("inbound").to_numpy()
    outbound = edges["direction_label"].eq("outbound").to_numpy()
    shadow = edges["shadow"].astype(bool).to_numpy()
    if not shadow.any() or np.any(shadow & ~(inbound | outbound)):
        raise ValueError("every shadow edge requires inbound or outbound direction_label")
    centers_by_edge = np.where(inbound, edges["target"].astype(str),
                               edges["source"].astype(str))
    centers = set(centers_by_edge[inbound | outbound])
    touches = (edges["source"].astype(str).isin(centers)
               | edges["target"].astype(str).isin(centers))
    return {
        "capture_centers": len(centers),
        "capture_center_node_pct": 100.0 * len(centers) / len(nodes),
        "shadow_edges": int(shadow.sum()),
        "shadow_edges_touching_center_pct": 100.0
        * int((touches.to_numpy() & shadow).sum())
        / int(shadow.sum()),
        "all_edges_touching_center_pct": 100.0 * float(touches.mean()),
        "degree_one_nodes": int(np.count_nonzero(degree == 1)),
        "degree_one_node_pct": 100.0 * float(np.mean(degree == 1)),
    }


def _selection(
    ids: np.ndarray,
    undirected: sparse.csr_matrix,
    selected_ids: Iterable[str],
    relevance: np.ndarray,
    tau: float,
    high_degree_min: int,
) -> dict:
    selected_values = [str(value) for value in selected_ids]
    if len(selected_values) != len(set(selected_values)):
        raise ValueError("selected node IDs must be unique")
    unknown = sorted(set(selected_values) - set(ids))
    if unknown:
        raise ValueError(f"selected node IDs are absent from graph: {unknown[:5]}")
    selected = np.isin(ids, selected_values)
    relevance = np.asarray(relevance, dtype=np.float64)
    if not np.isfinite(relevance).all() or not np.isfinite(tau):
        raise ValueError("relevance values and tau must be finite")
    if relevance.shape != (len(ids),) or not selected.any() or selected.all():
        raise ValueError("relevance/selection must cover a nontrivial frozen node domain")
    core = relevance >= float(tau)
    halo = np.zeros(len(ids), dtype=bool)
    if core.any():
        halo[np.unique(undirected[np.flatnonzero(core)].indices)] = True
    expected = core | halo
    degree = np.asarray(undirected.sum(axis=1)).ravel()
    degree_one, high = degree == 1, degree >= high_degree_min

    def rate(mask: np.ndarray) -> float | None:
        return 100.0 * int((selected & mask).sum()) / int(mask.sum()) if mask.any() else None

    low_rate, high_rate = rate(degree_one), rate(high)
    gap = high_rate - low_rate if low_rate is not None and high_rate is not None else None
    return {
        "selected_nodes": int(selected.sum()),
        "core_nodes": int(core.sum()),
        "halo_only_nodes": int((expected & ~core).sum()),
        "exact_core_halo_match": bool(np.array_equal(selected, expected)),
        "degree_one_selection_pct": low_rate,
        "high_degree_min": high_degree_min,
        "high_degree_selection_pct": high_rate,
        "high_minus_degree_one_selection_pp": gap,
        "selected_degree_mean": float(degree[selected].mean()),
        "selected_degree_median": float(np.median(degree[selected])),
        "nonselected_degree_mean": float(degree[~selected].mean()),
        "nonselected_degree_median": float(np.median(degree[~selected])),
    }


def measure_frozen_discoverability(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    selected_node_ids: Iterable[str],
    relevance: np.ndarray,
    tau: float,
    seed_handles: Iterable[str],
    *,
    thresholds: FalsifierThresholds = FalsifierThresholds(),
) -> dict:
    """Measure H-D1/H-D2/H-D5 and apply their explicit falsifiers."""
    ids, directed, undirected, mutual = build_graph_views(nodes, edges)
    seeds = resolve_seed_indices(nodes, seed_handles)
    degree = np.asarray(undirected.sum(axis=1)).ravel()
    capture = _capture(nodes, edges, degree)
    components = {
        "weak": component_summary(directed, directed=True, connection="weak"),
        "strong": component_summary(directed, directed=True, connection="strong"),
        "undirected": component_summary(undirected, directed=False),
        "mutual": component_summary(mutual, directed=False),
    }
    reach = {
        "forward": reachability_summary(directed, seeds, directed=True),
        "reverse": reachability_summary(
            directed.T.tocsr(),
            seeds,
            directed=True,
        ),
        "undirected": reachability_summary(undirected, seeds, directed=False),
        "mutual": reachability_summary(mutual, seeds, directed=False),
    }
    selection = _selection(
        ids, undirected, selected_node_ids, relevance, tau, thresholds.high_degree_min
    )
    giant_delta = components["weak"]["giant_pct"] - components["mutual"]["giant_pct"]
    reach_delta = reach["undirected"]["pct"] - reach["mutual"]["pct"]
    h1_falsified = not (
        capture["capture_center_node_pct"] <= thresholds.center_node_max_pct
        and capture["shadow_edges_touching_center_pct"] >= thresholds.center_edge_min_pct
        and capture["degree_one_node_pct"] >= thresholds.degree_one_min_pct
    )
    h2_falsified = (
        max(abs(giant_delta), abs(reach_delta)) < thresholds.semantics_change_min_pp
    )
    gap = selection["high_minus_degree_one_selection_pp"]
    h5_falsified = (
        not selection["exact_core_halo_match"]
        or gap is None
        or gap < thresholds.selection_gap_min_pp
    )
    hypotheses = {
        "H-D1": {
            "falsifier": {
                "center_node_max_pct": thresholds.center_node_max_pct,
                "center_edge_min_pct": thresholds.center_edge_min_pct,
                "degree_one_min_pct": thresholds.degree_one_min_pct,
            },
            "measurements": capture,
            "falsified": h1_falsified,
        },
        "H-D2": {
            "falsifier": {
                "stable_if_both_component_and_reach_change_below_pp":
                    thresholds.semantics_change_min_pp
            },
            "measurements": {
                "components": components,
                "seed_reachability": reach,
                "weak_minus_mutual_giant_pp": giant_delta,
                "undirected_minus_mutual_seed_reach_pp": reach_delta,
            },
            "falsified": h2_falsified,
        },
        "H-D5": {
            "falsifier": {
                "requires_exact_core_halo": True,
                "selection_gap_min_pp": thresholds.selection_gap_min_pp,
            },
            "measurements": selection,
            "falsified": h5_falsified,
        },
    }
    return {
        "schema_version": 1,
        "measurement_complete": True,
        "inputs": {
            "nodes": len(nodes),
            "directed_edges": int(directed.nnz),
            "resolved_explorer_seeds": len(seeds),
            "tau": float(tau),
        },
        "hypotheses": hypotheses,
        "strict_pass": not any(value["falsified"] for value in hypotheses.values()),
        "follow_ups_not_run": [
            "top-k Personalized PageRank stability across edge semantics",
            "mutable-cache temporal holdout and low-degree recall",
            "raw scrape claimed-versus-captured list completeness",
        ],
    }


def load_and_measure_frozen(data_dir: Path, seed_file: Path) -> dict:
    """Load already-manifest-verified frozen inputs and run measurements."""
    data_dir = Path(data_dir)
    nodes = pd.read_parquet(data_dir / "graph_snapshot.nodes.parquet")
    edges = pd.read_parquet(data_dir / "graph_snapshot.edges.parquet")
    selected = pd.read_parquet(
        data_dir / "graph_snapshot_tpot.nodes.parquet", columns=["node_id"]
    )["node_id"].astype(str)
    relevance = np.load(data_dir / "tpot_relevance_scores.npy", allow_pickle=False)
    calibration = json.loads((data_dir / "tpot_calibration.json").read_text())
    return measure_frozen_discoverability(
        nodes,
        edges,
        selected,
        relevance,
        calibration["tau"],
        load_fixed_seed_handles(seed_file),
    )


def write_json_no_clobber(path: Path, payload: dict) -> None:
    """Write a result while refusing to replace an existing path."""
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(rendered)
