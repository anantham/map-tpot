"""Account affinity route backed by an uncalibrated GRF score."""
from __future__ import annotations

import logging
import time

import numpy as np
from flask import jsonify, request

from src.api.responses import error_response

from src.api.cluster.state import (
    cluster_bp,
    _require_loaded,
    _require_ego,
    _membership_engine_enabled,
    _resolve_anchor_indices,
    _anchor_digest,
    _estimate_account_coverage,
)
from src.api.cluster import state
from src.graph.membership_grf import GRFMembershipConfig, compute_grf_membership

logger = logging.getLogger(__name__)

MEMBERSHIP_RESPONSE_SCHEMA_VERSION = "account-membership-affinity-v1"


@cluster_bp.route("/accounts/<account_id>/membership", methods=["GET"])
@_require_loaded
def get_account_membership(account_id: str):
    """Return an uncalibrated TPOT affinity for one account using GRF anchors."""

    if not _membership_engine_enabled():
        return error_response(
            "membership_engine is disabled; set settings.membership_engine=grf",
            details={"engine": state._graph_settings.get("membership_engine", "off")},
        )

    try:
        ego = _require_ego()
    except ValueError as exc:
        return error_response(str(exc))

    node_id = str(account_id)
    node_index = state._node_id_to_idx.get(node_id)
    if node_index is None:
        return error_response("Account not found in graph snapshot", status=404, details={"accountId": node_id})

    positive, negative, anchor_stats = _resolve_anchor_indices(ego)
    if not positive or not negative:
        return error_response(
            "Need both positive and negative anchor labels for GRF affinity",
            details={
                "ego": ego,
                "anchorCounts": {
                    "positive": len(positive),
                    "negative": len(negative),
                    "rows": anchor_stats.get("anchor_rows", 0),
                    "dropped": anchor_stats.get("anchors_dropped", 0),
                },
            },
        )

    prior = len(positive) / float(len(positive) + len(negative))
    cache_key = (
        ego,
        _anchor_digest(positive, negative),
        state._observation_config.mode,
        int(state._adjacency.count_nonzero()),
    )
    cached = state._membership_cache.get(cache_key)
    cache_hit = bool(cached)
    if cached is None:
        solve_start = time.time()
        grf = compute_grf_membership(
            adjacency=state._adjacency,
            positive_anchor_indices=positive,
            negative_anchor_indices=negative,
            config=GRFMembershipConfig(prior=prior),
        )
        solve_ms = int((time.time() - solve_start) * 1000)
        cached = {
            "affinities": grf.affinities,
            "uncertainty": grf.total_uncertainty,
            "entropy_uncertainty": grf.entropy_uncertainty,
            "degree_uncertainty": grf.degree_uncertainty,
            "solver": {
                "converged": grf.converged,
                "cg_info": grf.cg_info,
                "cg_iterations": grf.cg_iterations,
                "solve_ms": solve_ms,
            },
            "solver_baseline": grf.prior,
            "anchor_counts": {
                "positive": grf.n_positive_anchors,
                "negative": grf.n_negative_anchors,
            },
        }
        state._membership_cache.set(cache_key, cached)

    affinities = cached["affinities"]
    uncertainties = cached["uncertainty"]
    entropy_uncertainty = cached["entropy_uncertainty"]
    degree_uncertainty = cached["degree_uncertainty"]

    affinity = float(np.clip(affinities[node_index], 0.0, 1.0))
    uncertainty_graph = float(uncertainties[node_index])
    coverage = _estimate_account_coverage(node_id)
    coverage_value = coverage["value"]

    uncertainty = float(np.clip(uncertainty_graph, 0.0, 1.0))

    meta = state._node_metadata.get(node_id, {})
    return jsonify(
        {
            "schemaVersion": MEMBERSHIP_RESPONSE_SCHEMA_VERSION,
            "accountId": node_id,
            "ego": ego,
            "engine": "grf",
            "cacheHit": cache_hit,
            "affinity": affinity,
            "scoreSemantics": "affinity",
            "calibrated": False,
            "uncertainty": uncertainty,
            "uncertaintySemantics": "heuristic_graph_entropy_degree",
            "evidence": {
                "graph": float(1.0 - uncertainty_graph),
                "entropyUncertainty": float(entropy_uncertainty[node_index]),
                "degreeUncertainty": float(degree_uncertainty[node_index]),
                "coverage": coverage_value,
            },
            "anchorCounts": {
                **cached["anchor_counts"],
                "rows": anchor_stats.get("anchor_rows", 0),
                "dropped": anchor_stats.get("anchors_dropped", 0),
            },
            "coverage": coverage,
            "solver": cached["solver"],
            "solverBaseline": cached["solver_baseline"],
            "username": meta.get("username"),
        }
    )
