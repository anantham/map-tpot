"""Counter for silent scraper failures.

Selenium scraping has dozens of `except (Stale|NoSuchElement|Timeout): pass`
blocks because the DOM is unstable. Each silent failure is a piece of data
that didn't get extracted — a missing bio, an unresolved handle, a skipped
profile field. Aggregated across a scrape, these add up to silent data quality
problems that surface much later (or never).

This tracker counts each silent except by `(operation, exception_class)` and
keeps a few sample exception messages per category. Call `summary()` at the
end of a scrape to get a structured view of what failed silently and how
often.

Usage:
    from src.shadow.silent_failures import tracker

    try:
        cell.find_element(By.CSS_SELECTOR, "div.X")
    except StaleElementReferenceException as exc:
        tracker.track("extract_handle.find_cell", exc)
        return None

    # At the end of a scrape run
    tracker.log_summary("list_members for @nick")
    tracker.reset()
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Deque, Dict, List, Tuple

LOGGER = logging.getLogger(__name__)

# Number of sample exception messages to retain per category.
_SAMPLE_LIMIT = 3


@dataclass
class _CategoryStats:
    count: int = 0
    samples: Deque[str] = field(default_factory=lambda: deque(maxlen=_SAMPLE_LIMIT))


class SilentFailureTracker:
    """Process-wide counter for silently-swallowed scraper exceptions.

    Thread-safe. Production code calls `track()` from inside except blocks;
    callers periodically call `log_summary()` and `reset()` between runs.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._stats: Dict[Tuple[str, str], _CategoryStats] = defaultdict(_CategoryStats)

    def track(self, operation: str, exc: BaseException | None = None) -> None:
        """Record a silent failure.

        `operation` should be a short, stable identifier like
        "extract_handle.stale_link". The exception class name is derived from
        `exc` (or "Unknown" if not provided).
        """
        exc_name = type(exc).__name__ if exc is not None else "Unknown"
        key = (operation, exc_name)
        message = str(exc) if exc is not None else ""
        with self._lock:
            entry = self._stats[key]
            entry.count += 1
            if message:
                entry.samples.append(message[:200])

    def snapshot(self) -> List[dict]:
        """Return current stats as a list of dicts (sorted by count desc).

        Each entry: {"operation", "exception", "count", "samples"}.
        """
        with self._lock:
            rows = [
                {
                    "operation": op,
                    "exception": exc_name,
                    "count": stats.count,
                    "samples": list(stats.samples),
                }
                for (op, exc_name), stats in self._stats.items()
            ]
        rows.sort(key=lambda r: r["count"], reverse=True)
        return rows

    def total_count(self) -> int:
        with self._lock:
            return sum(s.count for s in self._stats.values())

    def reset(self) -> None:
        with self._lock:
            self._stats.clear()

    def log_summary(self, context: str = "") -> None:
        """Log a one-line-per-category summary at INFO level.

        Emits nothing if there are zero tracked failures (so it's safe to
        call unconditionally).
        """
        rows = self.snapshot()
        if not rows:
            return
        total = sum(r["count"] for r in rows)
        header = f"silent scraper failures ({context})" if context else "silent scraper failures"
        LOGGER.info("%s: %d total across %d categories", header, total, len(rows))
        for row in rows:
            sample = row["samples"][-1] if row["samples"] else ""
            sample_str = f' last_msg="{sample}"' if sample else ""
            LOGGER.info(
                "  silent_failure operation=%s exception=%s count=%d%s",
                row["operation"],
                row["exception"],
                row["count"],
                sample_str,
            )


# Module-level singleton. Production callers `from src.shadow.silent_failures import tracker`.
tracker = SilentFailureTracker()
