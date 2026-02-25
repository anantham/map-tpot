"""Composed golden curation store."""
from __future__ import annotations

from .base import BaseGoldenStore
from .evals import EvaluationMixin
from .predictions import PredictionMixin


class GoldenStore(BaseGoldenStore, PredictionMixin, EvaluationMixin):
    """Unified store composed from focused mixins."""

    pass
