"""Service for managing background analysis jobs and state."""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Optional, Any, List

logger = logging.getLogger(__name__)


class AnalysisManager:
    """Manages global analysis state, locking, and background threads."""

    def __init__(self):
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._status = {
            "status": "idle",
            "started_at": None,
            "finished_at": None,
            "error": None,
            "log": [],
        }

    def get_status(self) -> Dict[str, Any]:
        """Get the current analysis status safely."""
        with self._lock:
            # Return a copy to prevent mutation
            return self._status.copy()

    def is_running(self) -> bool:
        """Check if an analysis job is currently running."""
        with self._lock:
            return self._status["status"] == "running"

    def start_analysis(self, target_function, *args, **kwargs) -> bool:
        """Start a new analysis job if one isn't already running.
        
        Args:
            target_function: The function to run in the background. 
                             It must accept 'manager' as its first argument 
                             to report progress.
        
        Returns:
            True if started, False if already running.
        """
        with self._lock:
            if self._status["status"] == "running":
                return False

            self._status = {
                "status": "running",
                "started_at": time.time(),
                "finished_at": None,
                "error": None,
                "log": [],
            }
            
            # Create a wrapper to handle exceptions and status updates
            def _wrapper():
                try:
                    target_function(self, *args, **kwargs)
                    with self._lock:
                        self._status["status"] = "completed"
                        self._status["finished_at"] = time.time()
                except Exception as e:
                    logger.exception("Analysis failed")
                    with self._lock:
                        self._status["status"] = "failed"
                        self._status["error"] = str(e)
                        self._status["finished_at"] = time.time()

            self._thread = threading.Thread(target=_wrapper, daemon=True)
            self._thread.start()
            return True

    def log(self, message: str) -> None:
        """Append a log message to the status."""
        with self._lock:
            entry = f"[{time.strftime('%H:%M:%S')}] {message}"
            self._status["log"].append(entry)
            # Keep log size reasonable
            if len(self._status["log"]) > 1000:
                self._status["log"] = self._status["log"][-1000:]
            logger.info(f"Analysis: {message}")

    def update_status(self, key: str, value: Any) -> None:
        """Update a specific field in the status dictionary."""
        with self._lock:
            self._status[key] = value
