"""Flask application factory."""
from __future__ import annotations

import json
import logging
import logging.handlers
import math
import os
import time
from pathlib import Path
from typing import Any, Optional

from flask import Flask, Response
from flask_cors import CORS

from src.api import snapshot_loader
from src.api.services.analysis_manager import AnalysisManager
from src.api.services.cache_manager import CacheManager
from src.api.routes.core import core_bp
from src.api.routes.graph import graph_bp
from src.api.routes.analysis import analysis_bp
from src.api.routes.discovery import discovery_bp
from src.api.routes.accounts import accounts_bp
from src.api.cluster_routes import cluster_bp, init_cluster_routes
from src.api.log_routes import log_bp
from src.config import get_snapshot_dir

logger = logging.getLogger(__name__)


def _sanitize_json_value(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {k: _sanitize_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_json_value(v) for v in value]
    return value


class SafeJSONEncoder(json.JSONEncoder):
    """JSON encoder that converts NaN/Infinity to null for strict JSON compliance."""

    def encode(self, o: Any) -> str:  # noqa: N802 - matches json.JSONEncoder API
        return super().encode(_sanitize_json_value(o))


def safe_jsonify(payload: Any, *, status: int = 200) -> Response:
    """Return a JSON Response that is robust to NaN/Infinity without requiring app context."""

    data = SafeJSONEncoder().encode(payload)
    return Response(data, status=status, mimetype="application/json")


def create_app(config_overrides: Optional[dict] = None) -> Flask:
    """Initialize and configure the Flask application."""
    app = Flask(__name__)
    CORS(app)  # Enable CORS for all routes by default

    # 1. Configuration
    app.config["STARTUP_TIME"] = time.time()
    if config_overrides:
        app.config.update(config_overrides)

    _configure_logging()

    # 2. Initialize Services (State Injection)
    # These replace the old module-level globals
    app.config["ANALYSIS_MANAGER"] = AnalysisManager()
    app.config["CACHE_MANAGER"] = CacheManager()

    # 2b. Load snapshot graph (used by search/autocomplete endpoints).
    # Tests patch src.api.snapshot_loader.get_snapshot_loader to inject a lightweight graph.
    try:
        loader = snapshot_loader.get_snapshot_loader()
        graph_result = loader.load_graph()
        if graph_result is not None:
            app.config["SNAPSHOT_GRAPH"] = graph_result
    except Exception as exc:
        logger.warning("Snapshot graph load skipped: %s", exc)

    # 3. Register Blueprints
    app.register_blueprint(core_bp)
    app.register_blueprint(graph_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(discovery_bp)
    app.register_blueprint(accounts_bp)
    
    # Register legacy/existing blueprints
    app.register_blueprint(log_bp)
    
    # Initialize and register cluster routes (requires data loading)
    # TODO: Refactor init_cluster_routes to not rely on globals in cluster_routes.py
    snapshot_dir = get_snapshot_dir()
    init_cluster_routes(snapshot_dir)
    app.register_blueprint(cluster_bp)

    logger.info("TPOT Analyzer API initialized")
    return app


def _configure_logging(log_dir: Path = Path("logs")) -> None:
    """Attach a rotating file handler for API diagnostics."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "api.log"
    
    log_level_name = os.getenv("API_LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    
    root = logging.getLogger()
    
    # Avoid adding duplicate handlers if re-initializing
    already_configured = any(
        isinstance(h, logging.handlers.RotatingFileHandler)
        and getattr(h, "baseFilename", "") == str(log_path.resolve())
        for h in root.handlers
    )
    if already_configured:
        return

    root.setLevel(log_level)

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=5
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s"
        )
    )
    root.addHandler(file_handler)


if __name__ == "__main__":
    # Dev server entry point
    app = create_app()
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
