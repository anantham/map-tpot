"""Routes for accounts and seed management."""
from __future__ import annotations

import logging
from flask import Blueprint, jsonify, request

from src.data.shadow_store import get_shadow_store
from src.graph import (
    load_seed_candidates,
    save_seed_list,
    set_active_seed_list,
    get_seed_state,
)

logger = logging.getLogger(__name__)

accounts_bp = Blueprint("accounts", __name__, url_prefix="/api")


@accounts_bp.route("/accounts/<account_id>", methods=["GET"])
def get_account(account_id):
    """Get details for a specific account."""
    store = get_shadow_store()
    profile = store.get_profile(account_id)
    if not profile:
        return jsonify({"error": "Account not found"}), 404
    return jsonify(profile)


@accounts_bp.route("/seeds", methods=["GET"])
def get_seeds():
    """Get current seed list and candidates."""
    candidates = load_seed_candidates()
    state = get_seed_state()
    return jsonify({
        "candidates": candidates,
        "active": state.get("active_seeds", [])
    })


@accounts_bp.route("/seeds", methods=["POST"])
def update_seeds():
    """Update the active seed list."""
    data = request.json
    new_seeds = data.get("seeds", [])
    set_active_seed_list(new_seeds)
    return jsonify({"status": "updated", "count": len(new_seeds)})
