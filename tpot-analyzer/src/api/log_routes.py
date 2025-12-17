"""Receive frontend logs and write to disk for offline inspection."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from flask import Blueprint, jsonify, request

from src.api.request_context import get_req_id

log_bp = Blueprint("frontend_log", __name__, url_prefix="/api/log")
logger = logging.getLogger(__name__)

_DEFAULT_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_FILE = Path(os.getenv("TPOT_LOG_DIR") or _DEFAULT_LOG_DIR) / "frontend.log"


@log_bp.route("", methods=["POST"])
def write_log():
    """Persist a log entry posted from the frontend."""
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    level = (data.get("level") or "INFO").upper()
    message = data.get("message") or ""
    payload = data.get("payload") or {}
    timestamp = datetime.utcnow().isoformat() + "Z"
    req_id = get_req_id()

    line = json.dumps(
        {
            "ts": timestamp,
            "req_id": req_id,
            "level": level,
            "message": message,
            "payload": payload,
        }
    )

    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as exc:  # pragma: no cover - best-effort logging
        logger.warning("Failed to persist frontend log: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({"ok": True}), 200
