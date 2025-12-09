"""Core health check routes."""
from __future__ import annotations

from flask import Blueprint, jsonify

core_bp = Blueprint("core", __name__)


@core_bp.route("/health", methods=["GET"])
@core_bp.route("/api/health", methods=["GET"])
def health_check():
    """Simple health check."""
    return jsonify({"status": "ok", "service": "tpot-analyzer"})
