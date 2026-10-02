"""Routes for analysis jobs and metrics."""
from __future__ import annotations

import logging
import time
from flask import Blueprint, jsonify, request, current_app

from src.api.feedback_limits import validate_feedback
from src.api.workload_validation import parse_metrics
from src.api.services.analysis_manager import AnalysisManager
from src.api.services.cache_manager import CacheManager
from src.api.services.signal_feedback_store import SignalFeedbackStore
from src.graph import load_seed_candidates

logger = logging.getLogger(__name__)

analysis_bp = Blueprint("analysis", __name__, url_prefix="/api")


def _supervisor_required():
    return jsonify({"error": "whole-graph work disabled until a bounded subprocess supervisor is implemented",
                    "code": "BOUNDED_SUPERVISOR_REQUIRED"}), 503


@analysis_bp.route("/metrics/compute", methods=["POST"])
def compute_metrics():
    try:
        parse_metrics(request.get_json(silent=True))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return _supervisor_required()


@analysis_bp.route("/metrics/presets", methods=["GET"])
def get_presets():
    """Get seed presets."""
    candidates = load_seed_candidates()
    # Return as dict for extensibility and to match test expectation
    return jsonify({"candidates": list(candidates)})


@analysis_bp.route("/metrics/performance", methods=["GET"])
def get_performance_metrics():
    """Return lightweight backend performance diagnostics for UI status panels."""
    analysis_manager: AnalysisManager = current_app.config["ANALYSIS_MANAGER"]
    cache_manager: CacheManager = current_app.config["CACHE_MANAGER"]
    start_time = float(current_app.config.get("STARTUP_TIME", time.time()))
    uptime_seconds = max(0.0, time.time() - start_time)
    return jsonify(
        {
            "uptime_seconds": round(uptime_seconds, 3),
            "analysis_status": analysis_manager.get_status().get("status", "unknown"),
            "cache": {
                "graph_entries": cache_manager.graph_cache_size(),
                "discovery_entries": cache_manager.discovery_cache_size(),
            },
        }
    )


def _parse_signal_feedback_payload(payload):
    if not isinstance(payload, dict):
        return None, "Request body must be a JSON object"
    account_id = str(payload.get("account_id") or "").strip()
    signal_name = str(payload.get("signal_name") or "").strip()
    user_label = str(payload.get("user_label") or "").strip()
    if not account_id:
        return None, "account_id is required"
    if not signal_name:
        return None, "signal_name is required"
    if user_label not in {"tpot", "not_tpot"}:
        return None, "user_label must be one of: tpot, not_tpot"
    score = payload.get("score", 0.0)
    try:
        parsed_score = float(score)
    except (TypeError, ValueError):
        return None, "score must be numeric"
    context = payload.get("context")
    context = {} if context is None else context
    if not isinstance(context, dict):
        return None, "context must be an object"
    try:
        validate_feedback(account_id, signal_name, parsed_score, user_label, context)
    except ValueError as exc:
        return None, str(exc)
    return {
        "account_id": account_id,
        "signal_name": signal_name,
        "user_label": user_label,
        "score": parsed_score,
        "context": context,
    }, None


@analysis_bp.route("/signals/feedback", methods=["POST"])
def submit_signal_feedback():
    """Store user feedback events used for discovery signal-quality diagnostics."""
    parsed, error = _parse_signal_feedback_payload(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400

    feedback_store: SignalFeedbackStore = current_app.config["SIGNAL_FEEDBACK_STORE"]
    try:
        feedback_store.add_feedback(**parsed)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except OverflowError as exc:
        return jsonify({"error": str(exc)}), 507
    return jsonify(
        {
            "status": "ok",
            "stored": True,
            "total_feedback": feedback_store.event_count(),
        }
    )


@analysis_bp.route("/signals/quality", methods=["GET"])
def get_signal_quality_report():
    """Return aggregate quality metrics over captured signal feedback events."""
    feedback_store: SignalFeedbackStore = current_app.config["SIGNAL_FEEDBACK_STORE"]
    return jsonify(feedback_store.quality_report())


@analysis_bp.route("/analysis/status", methods=["GET"])
def get_analysis_status():
    """Get status of the background analysis job."""
    manager: AnalysisManager = current_app.config["ANALYSIS_MANAGER"]
    status = manager.get_status()
    status["capabilities"] = {"whole_graph_runs": False, "reason": "bounded supervisor required"}
    return jsonify(status)


@analysis_bp.route("/analysis/run", methods=["POST"])
def run_analysis():
    return _supervisor_required()
