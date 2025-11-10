"""Signal pipeline with validation and observability."""

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

import numpy as np

from .signal_events import SignalEvent, SignalEventStore, SignalName, get_event_store

logger = logging.getLogger(__name__)


@dataclass
class SignalResult:
    """Result of a signal computation with metadata."""

    score: float
    metadata: Dict[str, Any]
    warnings: List[str]
    explanations: List[str]
    error: Optional[str] = None
    event_id: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Check if the result is valid."""
        return self.error is None and not np.isnan(self.score)


class SignalValidator:
    """Base class for signal validators."""

    def __init__(self, name: str, is_critical: bool = False):
        """Initialize validator.

        Args:
            name: Validator name
            is_critical: If True, runs synchronously and can block computation
        """
        self.name = name
        self.is_critical = is_critical
        self.error: Optional[str] = None

    def pre_validate(self, event: SignalEvent) -> bool:
        """Validate before computation.

        Args:
            event: The pre-compute event

        Returns:
            True if validation passes, False to block computation
        """
        return True

    def post_validate(self, event: SignalEvent) -> None:
        """Validate after computation.

        Args:
            event: The post-compute event with score
        """
        pass


class NaNValidator(SignalValidator):
    """Validator that checks for NaN values."""

    def __init__(self):
        super().__init__("nan_validator", is_critical=True)

    def post_validate(self, event: SignalEvent) -> None:
        """Check if score is NaN."""
        if event.score is not None and np.isnan(event.score):
            event.warnings.append("Score is NaN - defaulting to 0")
            event.score = 0.0


class RangeValidator(SignalValidator):
    """Validator that checks if scores are in expected range."""

    def __init__(self):
        super().__init__("range_validator", is_critical=True)

    def post_validate(self, event: SignalEvent) -> None:
        """Check if score is in [0, 1] range."""
        if event.score is not None:
            if event.score < 0:
                event.warnings.append(f"Score {event.score} is negative - clamping to 0")
                event.score = 0.0
            elif event.score > 1:
                event.warnings.append(f"Score {event.score} > 1 - clamping to 1")
                event.score = 1.0


class DistributionValidator(SignalValidator):
    """Validator that tracks score distributions."""

    def __init__(self):
        super().__init__("distribution_validator", is_critical=False)
        self.scores_by_signal: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def post_validate(self, event: SignalEvent) -> None:
        """Track score distribution."""
        if event.score is None:
            return

        with self._lock:
            if event.signal_name not in self.scores_by_signal:
                self.scores_by_signal[event.signal_name] = []

            scores = self.scores_by_signal[event.signal_name]
            scores.append(event.score)

            # Keep only recent scores to avoid memory bloat
            if len(scores) > 10000:
                self.scores_by_signal[event.signal_name] = scores[-5000:]

            # Check for distribution issues
            if len(scores) >= 100:
                std = np.std(scores[-100:])
                if std < 0.01:
                    event.warnings.append(f"Very low variance in recent scores (std={std:.4f})")

                # Check for always 0 or always 1
                recent = scores[-100:]
                if all(s < 0.01 for s in recent):
                    event.warnings.append("Signal always returning near-zero scores")
                elif all(s > 0.99 for s in recent):
                    event.warnings.append("Signal always returning near-one scores")


class EdgeCaseValidator(SignalValidator):
    """Validator that checks for edge cases."""

    def __init__(self):
        super().__init__("edge_case_validator", is_critical=True)

    def pre_validate(self, event: SignalEvent) -> bool:
        """Check for edge cases in inputs."""
        # Check for empty seeds
        if event.seeds is not None and len(event.seeds) == 0:
            self.error = "No seeds provided"
            event.warnings.append(self.error)
            return False

        # Check for missing candidate
        if event.signal_name != "composite" and not event.candidate_id:
            self.error = "No candidate ID provided"
            event.warnings.append(self.error)
            return False

        return True


class ExplainabilityLogger(SignalValidator):
    """Logs detailed explanations of score computation."""

    def __init__(self):
        super().__init__("explainability_logger", is_critical=False)

    def post_validate(self, event: SignalEvent) -> None:
        """Generate explanations for the score."""
        if event.score is None:
            return

        explanations = []

        if event.signal_name == "neighbor_overlap":
            overlap_count = event.metadata.get("overlap_count", 0)
            total_seeds = event.metadata.get("total_seeds", 1)
            explanations.append(
                f"Overlap: {overlap_count}/{total_seeds} seeds follow this account"
            )

        elif event.signal_name == "pagerank":
            raw_pr = event.metadata.get("raw_pagerank", 0)
            percentile = event.metadata.get("percentile", 0)
            explanations.append(
                f"PageRank: {raw_pr:.2e} (top {100-percentile:.1f}% of network)"
            )

        elif event.signal_name == "community":
            seed_communities = event.metadata.get("seed_communities", {})
            candidate_community = event.metadata.get("candidate_community")
            if seed_communities and candidate_community is not None:
                matching = sum(1 for c in seed_communities.values()
                             if c == candidate_community)
                explanations.append(
                    f"Community: {matching}/{len(seed_communities)} seeds in same cluster"
                )

        elif event.signal_name == "path_distance":
            min_distance = event.metadata.get("min_distance")
            if min_distance is not None:
                if min_distance == float('inf'):
                    explanations.append("Path: No connection to seeds")
                else:
                    explanations.append(f"Path: {min_distance} hops from nearest seed")

        event.metadata["explanations"] = explanations


class SignalPipeline:
    """Orchestrates signal computation with validation and events."""

    def __init__(self, event_store: Optional[SignalEventStore] = None):
        """Initialize the pipeline.

        Args:
            event_store: Event store instance, or None to use global
        """
        self.event_store = event_store or get_event_store()
        self.validators = {
            'critical': [
                NaNValidator(),
                RangeValidator(),
                EdgeCaseValidator()
            ],
            'analytical': [
                DistributionValidator(),
                ExplainabilityLogger()
            ]
        }

    def compute_with_validation(
        self,
        signal_name: SignalName,
        compute_fn: Callable,
        candidate_id: Optional[str] = None,
        seeds: Optional[List[str]] = None,
        capture_metadata: bool = True,
        **compute_kwargs
    ) -> SignalResult:
        """Compute a signal with validation and event tracking.

        Args:
            signal_name: Name of the signal being computed
            compute_fn: The actual computation function
            candidate_id: ID of the candidate being scored
            seeds: List of seed IDs
            capture_metadata: Whether to capture detailed metadata
            **compute_kwargs: Additional arguments for compute_fn

        Returns:
            SignalResult with score and metadata
        """
        event_id = str(uuid4())

        # Create pre-compute event
        pre_event = SignalEvent(
            id=event_id,
            signal_name=signal_name,
            phase="pre_compute",
            timestamp=datetime.now(),
            candidate_id=candidate_id,
            seeds=seeds,
            metadata={"args": self._serialize_args(compute_kwargs)} if capture_metadata else {}
        )

        # Run critical pre-validators
        for validator in self.validators['critical']:
            if not validator.pre_validate(pre_event):
                # Validation failed, return error result
                self.event_store.store_event(pre_event)
                return SignalResult(
                    score=0.0,
                    metadata=pre_event.metadata,
                    warnings=pre_event.warnings,
                    explanations=[],
                    error=validator.error,
                    event_id=event_id
                )

        # Store pre-compute event
        self.event_store.store_event(pre_event)

        # Compute the signal
        start_time = time.time()
        try:
            # Some functions return (score, metadata), others just score
            result = compute_fn(**compute_kwargs)
            if isinstance(result, tuple):
                score, compute_metadata = result
                if capture_metadata and isinstance(compute_metadata, dict):
                    pre_event.metadata.update(compute_metadata)
            else:
                score = result
                compute_metadata = {}

            compute_time = time.time() - start_time
            pre_event.metadata["compute_time_ms"] = compute_time * 1000

        except Exception as e:
            # Computation failed
            error_msg = f"Computation failed: {str(e)}"
            logger.error(f"{signal_name} computation failed for {candidate_id}: {e}")

            error_event = SignalEvent(
                id=event_id,
                signal_name=signal_name,
                phase="post_compute",
                timestamp=datetime.now(),
                candidate_id=candidate_id,
                seeds=seeds,
                error=error_msg,
                metadata=pre_event.metadata
            )
            self.event_store.store_event(error_event)

            return SignalResult(
                score=0.0,
                metadata=pre_event.metadata,
                warnings=[],
                explanations=[],
                error=error_msg,
                event_id=event_id
            )

        # Create post-compute event
        post_event = SignalEvent(
            id=event_id,
            signal_name=signal_name,
            phase="post_compute",
            timestamp=datetime.now(),
            candidate_id=candidate_id,
            seeds=seeds,
            score=float(score),
            metadata=pre_event.metadata
        )

        # Run critical post-validators (synchronous)
        for validator in self.validators['critical']:
            validator.post_validate(post_event)

        # Store post-compute event
        self.event_store.store_event(post_event)

        # Run analytical validators (async)
        if self.validators['analytical']:
            threading.Thread(
                target=self._run_async_validators,
                args=(post_event, self.validators['analytical']),
                daemon=True
            ).start()

        # Extract explanations
        explanations = post_event.metadata.get("explanations", [])

        return SignalResult(
            score=post_event.score,
            metadata=post_event.metadata,
            warnings=post_event.warnings,
            explanations=explanations,
            error=None,
            event_id=event_id
        )

    def _run_async_validators(
        self,
        event: SignalEvent,
        validators: List[SignalValidator]
    ) -> None:
        """Run validators asynchronously.

        Args:
            event: The event to validate
            validators: List of validators to run
        """
        try:
            for validator in validators:
                validator.post_validate(event)

            # Store validation event if any warnings were added
            if event.warnings:
                validation_event = SignalEvent(
                    id=event.id,
                    signal_name=event.signal_name,
                    phase="validation",
                    timestamp=datetime.now(),
                    candidate_id=event.candidate_id,
                    seeds=event.seeds,
                    score=event.score,
                    metadata={"validation_warnings": event.warnings},
                    warnings=event.warnings
                )
                self.event_store.store_event(validation_event)

        except Exception as e:
            logger.error(f"Async validation failed: {e}")

    def _serialize_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Serialize computation arguments for storage.

        Args:
            args: Arguments dictionary

        Returns:
            Serializable dictionary
        """
        serialized = {}
        for key, value in args.items():
            if isinstance(value, (str, int, float, bool, type(None))):
                serialized[key] = value
            elif isinstance(value, (list, tuple)):
                # Only store length for large lists
                if len(value) > 10:
                    serialized[key] = f"<{type(value).__name__} with {len(value)} items>"
                else:
                    serialized[key] = list(value)
            elif isinstance(value, dict):
                # Only store keys for large dicts
                if len(value) > 10:
                    serialized[key] = f"<dict with keys: {list(value.keys())[:5]}...>"
                else:
                    serialized[key] = value
            else:
                serialized[key] = f"<{type(value).__name__}>"

        return serialized

    def add_validator(self, validator: SignalValidator, critical: bool = False) -> None:
        """Add a custom validator to the pipeline.

        Args:
            validator: The validator to add
            critical: Whether this is a critical (blocking) validator
        """
        category = 'critical' if critical else 'analytical'
        self.validators[category].append(validator)

    def get_signal_quality_report(
        self,
        signal_name: Optional[SignalName] = None
    ) -> Dict[str, Any]:
        """Generate a quality report for signals based on feedback.

        Args:
            signal_name: Specific signal to report on, or None for all

        Returns:
            Dictionary with quality metrics per signal
        """
        feedback_stats = self.event_store.get_feedback_stats(signal_name)
        report = {}

        for sig_name, labels in feedback_stats.items():
            total_feedback = sum(l['count'] for l in labels.values())

            # Calculate precision: when score is high, is it labeled TPOT?
            tpot_high_scores = labels.get('tpot', {}).get('avg_score', 0)
            not_tpot_high_scores = labels.get('not_tpot', {}).get('avg_score', 0)

            # Simple agreement metric
            tpot_count = labels.get('tpot', {}).get('count', 0)
            not_tpot_count = labels.get('not_tpot', {}).get('count', 0)

            if total_feedback > 0:
                precision = tpot_count / total_feedback if total_feedback > 0 else 0

                # Score separation (how well does score distinguish labels)
                score_separation = abs(tpot_high_scores - not_tpot_high_scores)

                report[sig_name] = {
                    'total_feedback': total_feedback,
                    'tpot_ratio': precision,
                    'score_separation': score_separation,
                    'avg_tpot_score': tpot_high_scores,
                    'avg_not_tpot_score': not_tpot_high_scores,
                    'feedback_breakdown': labels
                }

                # Recommend weight adjustment based on separation
                if score_separation > 0.3:
                    report[sig_name]['quality'] = 'high'
                    report[sig_name]['recommended_weight_change'] = 1.1  # Increase weight
                elif score_separation > 0.1:
                    report[sig_name]['quality'] = 'medium'
                    report[sig_name]['recommended_weight_change'] = 1.0  # Keep same
                else:
                    report[sig_name]['quality'] = 'low'
                    report[sig_name]['recommended_weight_change'] = 0.9  # Decrease weight

        return report


# Global pipeline instance
_pipeline = None

def get_pipeline() -> SignalPipeline:
    """Get the global pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = SignalPipeline()
    return _pipeline