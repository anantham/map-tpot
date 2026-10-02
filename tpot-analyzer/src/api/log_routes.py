"""Bounded frontend diagnostics with rotating disk retention."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request

from src.api.request_context import get_req_id
from src.api.bounded_logs import append_private_log

log_bp = Blueprint("frontend_log", __name__, url_prefix="/api/log")
logger = logging.getLogger(__name__)
_DEFAULT_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_FILE = Path(os.getenv("TPOT_LOG_DIR") or _DEFAULT_LOG_DIR) / "frontend.log"
MAX_LOG_ENTRY_BYTES = 8192
MAX_LOG_FILE_BYTES = 1024 * 1024
LOG_BACKUPS = 3


@log_bp.route("", methods=["POST"])
def write_log():
    if request.content_length and request.content_length > MAX_LOG_ENTRY_BYTES:
        return jsonify({"error": "frontend log entry exceeds 8192 bytes"}), 413
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "log body must be a JSON object"}), 400
    message, level = data.get("message", ""), data.get("level", "INFO")
    if not isinstance(message, str) or not isinstance(level, str):
        return jsonify({"error": "message and level must be strings"}), 400
    if level.upper() not in {"DEBUG", "INFO", "WARN", "WARNING", "ERROR"}:
        return jsonify({"error": "unsupported log level"}), 400
    line = json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "req_id": get_req_id(),
                       "level": level.upper(), "message": message, "payload": data.get("payload", {})})
    if len(line.encode("utf-8")) > MAX_LOG_ENTRY_BYTES:
        return jsonify({"error": "frontend log entry exceeds 8192 bytes"}), 413
    try:
        append_private_log(LOG_FILE, line, max_bytes=MAX_LOG_FILE_BYTES, backups=LOG_BACKUPS)
    except BlockingIOError:
        return jsonify({"error": "frontend log capacity busy; retry later"}), 503
    except OSError:
        logger.exception("Failed to persist bounded frontend log")
        return jsonify({"error": "failed to persist log"}), 500
    return jsonify({"status": "ok"}), 200
