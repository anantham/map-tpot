"""Account membership route (GRF-based TPOT membership probability)."""
from __future__ import annotations

import logging
import time
from typing import Dict

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


@cluster_bp.route("/accounts/<account_id>/membership", methods=["GET"])
@_require_loaded
def get_account_membership(account_id: str):
    """Return TPOT-membership probability for one account using GRF anchors."""

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
            "Need both positive and negative anchor labels for GRF membership",
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
            "probabilities": grf.probabilities,
            "uncertainty": grf.total_uncertainty,
            "entropy_uncertainty": grf.entropy_uncertainty,
            "degree_uncertainty": grf.degree_uncertainty,
            "solver": {
                "converged": grf.converged,
                "cg_info": grf.cg_info,
                "cg_iterations": grf.cg_iterations,
                "solve_ms": solve_ms,
            },
            "prior": grf.prior,
            "anchor_counts": {
                "positive": grf.n_positive_anchors,
                "negative": grf.n_negative_anchors,
            },
        }
        state._membership_cache.set(cache_key, cached)

    probabilities = cached["probabilities"]
    uncertainties = cached["uncertainty"]
    entropy_uncertainty = cached["entropy_uncertainty"]
    degree_uncertainty = cached["degree_uncertainty"]

    probability_raw = float(probabilities[node_index])
    uncertainty_graph = float(uncertainties[node_index])
    coverage = _estimate_account_coverage(node_id)
    coverage_value = float(coverage["value"])

    probability = (probability_raw * coverage_value) + (cached["prior"] * (1.0 - coverage_value))
    probability = float(np.clip(probability, 0.0, 1.0))

    uncertainty = (0.7 * uncertainty_graph) + (0.3 * (1.0 - coverage_value))
    uncertainty = float(np.clip(uncertainty, 0.0, 1.0))
    sigma = min(0.25, 0.25 * uncertainty)
    ci_low = float(max(0.0, probability - (1.96 * sigma)))
    ci_high = float(min(1.0, probability + (1.96 * sigma)))

    meta = state._node_metadata.get(node_id, {})
    return jsonify(
        {
            "accountId": node_id,
            "ego": ego,
            "engine": "grf",
            "cacheHit": cache_hit,
            "probability": probability,
            "probabilityRaw": probability_raw,
            "confidenceInterval95": [ci_low, ci_high],
            "uncertainty": uncertainty,
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
            "prior": cached["prior"],
            "username": meta.get("username"),
        }
    )
