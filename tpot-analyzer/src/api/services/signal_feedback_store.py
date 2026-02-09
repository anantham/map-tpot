"""In-memory storage and reporting for discovery signal feedback."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from threading import Lock
from time import time
from typing import Any, Dict, List


@dataclass(frozen=True)
class SignalFeedbackEvent:
    account_id: str
    signal_name: str
    score: float
    user_label: str
    context: Dict[str, Any]
    timestamp: float


class SignalFeedbackStore:
    """Thread-safe in-memory feedback store used by discovery feedback routes."""

    def __init__(self) -> None:
        self._events: List[SignalFeedbackEvent] = []
        self._lock = Lock()

    def add_feedback(
        self,
        *,
        account_id: str,
        signal_name: str,
        score: float,
        user_label: str,
        context: Dict[str, Any] | None = None,
    ) -> None:
        event = SignalFeedbackEvent(
            account_id=account_id,
            signal_name=signal_name,
            score=float(score),
            user_label=user_label,
            context=context or {},
            timestamp=time(),
        )
        with self._lock:
            self._events.append(event)

    def event_count(self) -> int:
        with self._lock:
            return len(self._events)

    def quality_report(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            events = list(self._events)

        grouped: Dict[str, List[SignalFeedbackEvent]] = {}
        for event in events:
            grouped.setdefault(event.signal_name, []).append(event)

        report: Dict[str, Dict[str, Any]] = {}
        for signal_name, signal_events in grouped.items():
            tpot_scores = [event.score for event in signal_events if event.user_label == "tpot"]
            not_tpot_scores = [event.score for event in signal_events if event.user_label == "not_tpot"]
            total = len(signal_events)
            tpot_ratio = len(tpot_scores) / total if total else 0.0
            mean_tpot = mean(tpot_scores) if tpot_scores else 0.0
            mean_not_tpot = mean(not_tpot_scores) if not_tpot_scores else 0.0
            score_separation = mean_tpot - mean_not_tpot

            if total < 5:
                quality = "low-sample"
            elif abs(score_separation) >= 0.25:
                quality = "high"
            elif abs(score_separation) >= 0.1:
                quality = "medium"
            else:
                quality = "low"

            if total < 5:
                recommended_weight_change = 0.0
            elif tpot_ratio >= 0.6 and score_separation >= 0.1:
                recommended_weight_change = 0.1
            elif tpot_ratio <= 0.4 and score_separation <= -0.1:
                recommended_weight_change = -0.1
            else:
                recommended_weight_change = 0.0

            report[signal_name] = {
                "total_feedback": total,
                "quality": quality,
                "tpot_ratio": tpot_ratio,
                "score_separation": score_separation,
                "recommended_weight_change": recommended_weight_change,
            }

        return report
