"""Curator-only API for a method-masked frozen discovery review packet."""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from src.api.curator_auth import curator_only
from src.api.responses import error_response
from src.data.discovery_review_store import DiscoveryReviewStore, load_review_packet


logger = logging.getLogger(__name__)
discovery_review_bp = Blueprint("discovery_review", __name__, url_prefix="/api/discovery-review")


@discovery_review_bp.after_request
def _private_response(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _configured_path(name: str) -> Path:
    raw = current_app.config.get(name, os.getenv(name))
    if not raw:
        raise RuntimeError(f"{name} is not configured; discovery review is disabled")
    path = Path(raw)
    if not path.is_absolute():
        raise RuntimeError(f"{name} must be an absolute path")
    return path.resolve()


def _review_context():
    packet_path = _configured_path("TPOT_DISCOVERY_REVIEW_PACKET")
    db_path = _configured_path("TPOT_DISCOVERY_REVIEW_DB")
    if packet_path == db_path:
        raise RuntimeError("Discovery answers require a separate database, not the manifest path")
    packet = load_review_packet(packet_path)
    cached = current_app.extensions.get("discovery_review_store")
    if cached is None or cached.db_path != db_path:
        cached = DiscoveryReviewStore(db_path)
        current_app.extensions["discovery_review_store"] = cached
    return packet, cached


def _failure(exc, action):
    if isinstance(exc, ValueError):
        logger.info("Discovery review %s rejected: %s", action, exc)
        return error_response(str(exc))
    logger.exception("Discovery review %s failed", action)
    if isinstance(exc, RuntimeError):
        return error_response(str(exc), status=503)
    return error_response(
        f"Discovery review {action} failed; check packet/database configuration and the API log",
        status=500,
    )


@discovery_review_bp.route("", methods=["GET"])
@curator_only
def get_discovery_review():
    try:
        packet, store = _review_context()
        answers = store.answers_for(packet)
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        return _failure(exc, "read")
    logger.debug("Discovery review read packet=%s cards=%d answers=%d", packet.packet_id, len(packet.cards), len(answers))
    return jsonify({
        "packetId": packet.packet_id, "curator": packet.curator,
        "targetTag": packet.purpose["key"], "purpose": packet.purpose,
        "cards": packet.cards, "answers": answers,
        "completedCount": len(answers), "totalCount": len(packet.cards),
    })


@discovery_review_bp.route("/answers/<account_id>", methods=["PUT"])
@curator_only
def save_discovery_review_answer(account_id):
    try:
        packet, store = _review_context()
        answer = store.append_answer(packet, account_id, request.get_json(silent=True))
        completed_count = len(store.answers_for(packet))
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        return _failure(exc, "save")
    logger.debug("Discovery review saved packet=%s account=%s event=%s", packet.packet_id, account_id, answer["eventId"])
    return jsonify({
        "status": "appended", "packetId": packet.packet_id, "accountId": account_id,
        "answer": answer, "completedCount": completed_count, "totalCount": len(packet.cards),
    })
