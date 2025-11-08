"""Performance profiling utilities for graph analysis pipeline.

Provides context managers and decorators for timing critical operations
and collecting structured performance metrics.
"""
from __future__ import annotations

import functools
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, List
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class TimingMetric:
    """Container for a single timing measurement."""

    name: str
    duration_ms: float
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        meta_str = ", ".join(f"{k}={v}" for k, v in self.metadata.items()) if self.metadata else ""
        return f"{self.name}: {self.duration_ms:.2f}ms" + (f" ({meta_str})" if meta_str else "")


@dataclass
class PerformanceReport:
    """Aggregated performance metrics for a complete operation."""

    operation: str
    total_duration_ms: float
    phases: List[TimingMetric] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_phase(self, phase: TimingMetric) -> None:
        """Add a timing phase to the report."""
        self.phases.append(phase)

    def get_phase_breakdown(self) -> Dict[str, float]:
        """Get percentage breakdown of time spent in each phase."""
        if self.total_duration_ms == 0:
            return {}
        return {
            phase.name: (phase.duration_ms / self.total_duration_ms) * 100
            for phase in self.phases
        }

    def format_report(self, verbose: bool = False) -> str:
        """Format the performance report as a readable string."""
        lines = [
            f"\n{'=' * 60}",
            f"PERFORMANCE REPORT: {self.operation}",
            f"{'=' * 60}",
            f"Total Duration: {self.total_duration_ms:.2f}ms ({self.total_duration_ms / 1000:.3f}s)",
        ]

        if self.metadata:
            lines.append("\nMetadata:")
            for key, value in self.metadata.items():
                lines.append(f"  {key}: {value}")

        if self.phases:
            lines.append("\nPhase Breakdown:")
            breakdown = self.get_phase_breakdown()

            # Sort by duration (descending)
            sorted_phases = sorted(self.phases, key=lambda p: p.duration_ms, reverse=True)

            for phase in sorted_phases:
                pct = breakdown.get(phase.name, 0)
                lines.append(f"  [{pct:5.1f}%] {phase.name}: {phase.duration_ms:.2f}ms")

                if verbose and phase.metadata:
                    for key, value in phase.metadata.items():
                        lines.append(f"         {key}: {value}")

        lines.append("=" * 60)
        return "\n".join(lines)


class PerformanceProfiler:
    """Singleton profiler for collecting timing metrics across the application."""

    _instance = None
    _enabled = True

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._metrics = []
            cls._instance._active_reports = {}
        return cls._instance

    @classmethod
    def enable(cls) -> None:
        """Enable performance profiling."""
        cls._enabled = True

    @classmethod
    def disable(cls) -> None:
        """Disable performance profiling."""
        cls._enabled = False

    @classmethod
    def is_enabled(cls) -> bool:
        """Check if profiling is enabled."""
        return cls._enabled

    def start_report(self, operation: str, metadata: Optional[Dict[str, Any]] = None) -> PerformanceReport:
        """Start a new performance report for an operation."""
        report = PerformanceReport(
            operation=operation,
            total_duration_ms=0.0,
            metadata=metadata or {}
        )
        self._active_reports[operation] = {
            'report': report,
            'start_time': time.time()
        }
        return report

    def finish_report(self, operation: str) -> Optional[PerformanceReport]:
        """Finish and return a performance report."""
        if operation not in self._active_reports:
            logger.warning(f"No active report found for operation: {operation}")
            return None

        active = self._active_reports.pop(operation)
        report = active['report']
        start_time = active['start_time']

        report.total_duration_ms = (time.time() - start_time) * 1000
        self._metrics.append(report)

        return report

    def add_phase_to_report(self, operation: str, phase: TimingMetric) -> None:
        """Add a timing phase to an active report."""
        if operation in self._active_reports:
            self._active_reports[operation]['report'].add_phase(phase)

    def get_all_reports(self) -> List[PerformanceReport]:
        """Get all collected performance reports."""
        return self._metrics.copy()

    def clear_reports(self) -> None:
        """Clear all collected reports."""
        self._metrics.clear()
        self._active_reports.clear()

    def get_summary(self) -> Dict[str, Any]:
        """Get aggregated summary statistics."""
        if not self._metrics:
            return {}

        by_operation = defaultdict(list)
        for report in self._metrics:
            by_operation[report.operation].append(report.total_duration_ms)

        summary = {}
        for operation, durations in by_operation.items():
            summary[operation] = {
                'count': len(durations),
                'total_ms': sum(durations),
                'avg_ms': sum(durations) / len(durations),
                'min_ms': min(durations),
                'max_ms': max(durations),
            }

        return summary


# Global profiler instance
_profiler = PerformanceProfiler()


@contextmanager
def profile_operation(operation: str, metadata: Optional[Dict[str, Any]] = None, verbose: bool = True):
    """Context manager for profiling a complete operation.

    Usage:
        with profile_operation("build_graph", {"nodes": 1000}):
            # ... do work ...
            pass
    """
    if not PerformanceProfiler.is_enabled():
        yield None
        return

    report = _profiler.start_report(operation, metadata)

    try:
        yield report
    finally:
        final_report = _profiler.finish_report(operation)
        if final_report and verbose:
            logger.info(final_report.format_report())


@contextmanager
def profile_phase(phase_name: str, operation: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
    """Context manager for profiling a phase within an operation.

    Usage:
        with profile_operation("build_graph") as report:
            with profile_phase("load_data", "build_graph"):
                # ... load data ...
                pass
            with profile_phase("compute_metrics", "build_graph"):
                # ... compute metrics ...
                pass
    """
    if not PerformanceProfiler.is_enabled():
        yield
        return

    start_time = time.time()

    try:
        yield
    finally:
        duration_ms = (time.time() - start_time) * 1000
        metric = TimingMetric(
            name=phase_name,
            duration_ms=duration_ms,
            timestamp=time.time(),
            metadata=metadata or {}
        )

        if operation:
            _profiler.add_phase_to_report(operation, metric)

        logger.debug(f"Phase [{phase_name}]: {duration_ms:.2f}ms")


def profile_function(operation_name: Optional[str] = None, verbose: bool = False):
    """Decorator for profiling a function.

    Usage:
        @profile_function("compute_pagerank")
        def compute_personalized_pagerank(graph, seeds, alpha):
            # ... computation ...
            pass
    """
    def decorator(func: Callable) -> Callable:
        op_name = operation_name or f"{func.__module__}.{func.__name__}"

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not PerformanceProfiler.is_enabled():
                return func(*args, **kwargs)

            # Extract size hints from common parameters
            metadata = {}
            if args and hasattr(args[0], 'number_of_nodes'):
                metadata['nodes'] = args[0].number_of_nodes()
                metadata['edges'] = args[0].number_of_edges()

            with profile_operation(op_name, metadata, verbose=verbose):
                return func(*args, **kwargs)

        return wrapper
    return decorator


def get_profiler() -> PerformanceProfiler:
    """Get the global profiler instance."""
    return _profiler


def print_summary():
    """Print a summary of all collected performance metrics."""
    summary = _profiler.get_summary()

    if not summary:
        print("No performance metrics collected.")
        return

    print("\n" + "=" * 60)
    print("PERFORMANCE SUMMARY")
    print("=" * 60)

    for operation, stats in sorted(summary.items(), key=lambda x: x[1]['total_ms'], reverse=True):
        print(f"\n{operation}:")
        print(f"  Count: {stats['count']}")
        print(f"  Total: {stats['total_ms']:.2f}ms ({stats['total_ms'] / 1000:.3f}s)")
        print(f"  Avg: {stats['avg_ms']:.2f}ms")
        print(f"  Min/Max: {stats['min_ms']:.2f}ms / {stats['max_ms']:.2f}ms")

    print("=" * 60)
