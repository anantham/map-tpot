"""Composed golden curation store."""
from __future__ import annotations

from .base import BaseGoldenStore
from .evals import EvaluationMixin
from .predictions import PredictionMixin
from .tags import TagMixin


class GoldenStore(BaseGoldenStore, PredictionMixin, EvaluationMixin, TagMixin):
    """Unified store composed from focused mixins."""

    pass
