"""Default-deny access and cross-process admission control for the analyst API.

The published snapshot has a separate static/public-site surface. Flask serves
private analyst data; only health and deliberate extension ingestion are public.
"""
from __future__ import annotations

import re
import os
from pathlib import Path
from threading import Lock

from src.api.filesystem_locks import FileLease, open_private_file, private_runtime_directory, try_lock
from src.config import get_snapshot_dir

from flask import g, request

from src.api.curator_auth import CuratorAuthError, require_curator_auth
from src.api.responses import error_response

PUBLIC_ENDPOINTS = frozenset({"core.health_check", "extension.ingest_feed_events"})
EXPENSIVE_ENDPOINTS = frozenset({
    "discovery.discover", "graph.get_graph_data",
    "clusters.get_clusters", "golden.ingest_predictions_run", "golden.run_eval",
    "golden.interpret_tweet",
})


class WorkloadGate:
    """One shared slot pool for all processes using the same snapshot root."""

    def __init__(self, capacity: int = 1, *, lock_root=None):
        if not 1 <= capacity <= 4:
            raise ValueError("workload concurrency must be between 1 and 4")
        self.capacity = capacity
        self.lock_root = Path(lock_root or os.getenv("SNAPSHOT_DIR") or get_snapshot_dir())
        self._legacy_leases = []
        self._lease_lock = Lock()

    def acquire_lease(self):
        with private_runtime_directory(self.lock_root) as (_, directory_fd):
            capacity_fd = open_private_file(directory_fd, "workload-capacity")
            try:
                if not try_lock(capacity_fd):
                    return None
                if os.fstat(capacity_fd).st_size > 4:
                    raise OSError("invalid workload capacity metadata")
                recorded = os.read(capacity_fd, 4)
                expected = str(self.capacity).encode("ascii")
                if not recorded:
                    os.write(capacity_fd, expected)
                elif recorded != expected:
                    raise OSError("workers disagree on global workload capacity")
            finally:
                os.close(capacity_fd)
            for slot in range(self.capacity):
                fd = open_private_file(directory_fd, f"workload-slot-{slot}")
                try:
                    acquired = try_lock(fd)
                except BaseException:
                    os.close(fd)
                    raise
                if acquired:
                    return FileLease(fd)
                os.close(fd)
        return None

    def acquire(self) -> bool:
        """Compatibility count interface for callers that do not retain leases."""
        lease = self.acquire_lease()
        if lease is None:
            return False
        with self._lease_lock:
            self._legacy_leases.append(lease)
        return True

    def release(self) -> None:
        with self._lease_lock:
            lease = self._legacy_leases.pop()
        lease.release()


def curator_gate():
    """A blueprint can reuse the same fail-closed gate when registered alone."""
    if request.method == "OPTIONS":
        return None
    try:
        require_curator_auth(request)
    except CuratorAuthError as exc:
        return error_response(str(exc), status=exc.status)
    return None


def install_security_policy(app, gate: WorkloadGate) -> None:
    @app.before_request
    def analyst_boundary():
        if request.endpoint is None or request.method == "OPTIONS":
            return None
        if request.endpoint not in PUBLIC_ENDPOINTS:
            failure = curator_gate()
            if failure is not None:
                return failure
        if request.endpoint in EXPENSIVE_ENDPOINTS:
            try:
                lease = gate.acquire_lease()
            except OSError:
                return error_response("private workload coordination unavailable", status=503)
            if lease is None:
                return error_response("analysis capacity busy; retry later", status=429)
            g.workload_lease = lease
        return None

    @app.teardown_request
    def release_workload(_exc):
        lease = g.pop("workload_lease", None)
        if lease is not None:
            lease.release()


def safe_request_id(value: str) -> str:
    """Prevent caller-controlled diagnostic fields from growing or injecting logs."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(value))[:64]
