"""Flask application factory."""
from __future__ import annotations

import logging
import logging.handlers
import os
import time
from pathlib import Path
from typing import Optional

from flask import Flask
from flask_cors import CORS

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