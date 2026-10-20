"""Serve the saved discovery review on loopback behind owner-authenticated Serve.

Launch with gunicorn bound to 127.0.0.1. Tailscale Serve supplies the verified
Tailscale-User-Login header and removes client attempts to spoof that header.
Only this small app is served; archive and personal-tag APIs are not registered.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parents[1]


def create_review_app(*, packet_path=None, answer_db=None, dist_dir=None,
                      owner_login=None, origin=None):
    """Create the private web app with explicit evidence and storage paths."""
    packet_path = packet_path or os.getenv("TPOT_DISCOVERY_REVIEW_PACKET")
    answer_db = answer_db or os.getenv("TPOT_DISCOVERY_REVIEW_DB")
    owner_login = owner_login or os.getenv("TPOT_DISCOVERY_REVIEW_OWNER")
    origin = origin or os.getenv("TPOT_DISCOVERY_REVIEW_ORIGIN")
    dist_dir = Path(dist_dir or ROOT / "graph-explorer/dist").resolve()
    if not all((packet_path, answer_db, owner_login, origin)):
        raise ValueError("Review requires packet, answer DB, tailnet owner and HTTPS origin")
    if not Path(packet_path).is_file():
        raise ValueError("Configured discovery packet is unavailable")
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path:
        raise ValueError("Review origin must be an HTTPS origin with no path")
    if not (dist_dir / "discovery-review.html").is_file():
        raise ValueError("Build the discovery review frontend before starting the server")
    os.environ.setdefault("TPOT_CURATOR_TOKEN", secrets.token_hex(32))
    app = Flask(__name__, static_folder=str(dist_dir / "assets"), static_url_path="/assets")
    app.config.update(
        MAX_CONTENT_LENGTH=65536,
        TPOT_DISCOVERY_REVIEW_PACKET=str(Path(packet_path).resolve()),
        TPOT_DISCOVERY_REVIEW_DB=str(Path(answer_db).resolve()),
        REVIEW_OWNER=owner_login.strip().casefold(), REVIEW_ORIGIN=origin,
    )
    from src.api.routes.discovery_review import discovery_review_bp
    app.register_blueprint(discovery_review_bp)

    @app.before_request
    def authorize_tailnet_owner():
        if request.remote_addr not in {"127.0.0.1", "::1"}:
            return jsonify({"error": "Review accepts only the local Tailscale Serve proxy"}), 403
        login = request.headers.get("Tailscale-User-Login", "").strip().casefold()
        if login != app.config["REVIEW_OWNER"]:
            return jsonify({"error": "Open this review from the owner's signed-in tailnet device"}), 403
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("Origin") != app.config["REVIEW_ORIGIN"]:
                return jsonify({"error": "Review answers must be saved from this review's own page"}), 403
        request.environ["HTTP_X_TPOT_CURATOR_TOKEN"] = os.environ["TPOT_CURATOR_TOKEN"]

    @app.after_request
    def private_response(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        )
        return response

    @app.get("/")
    @app.get("/discovery-review.html")
    def review_page():
        return send_from_directory(dist_dir, "discovery-review.html")

    @app.get("/health")
    def health():
        return jsonify({"status": "ready"})

    return app
