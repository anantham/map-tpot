"""Compatibility wrapper for the community gold store."""
from __future__ import annotations

from .base import BaseCommunityGoldStore
from .candidates import CommunityGoldCandidateMixin
from .candidate_pool import CommunityGoldCandidatePoolMixin
from .evals import CommunityGoldEvaluationMixin
from .judgments import CommunityGoldJudgmentMixin
from .methods import CommunityGoldMethodMixin
from .ontology import CommunityGoldOntologyMixin
from .predictions import CommunityGoldPredictionMixin
from .reads import CommunityGoldReadMixin
from .studies import CommunityGoldStudyMixin
from .terminal_delivery import CommunityGoldTerminalDeliveryMixin


class CommunityGoldStore(
    BaseCommunityGoldStore,
    CommunityGoldOntologyMixin,
    CommunityGoldStudyMixin,
    CommunityGoldTerminalDeliveryMixin,
    CommunityGoldJudgmentMixin,
    CommunityGoldPredictionMixin,
    CommunityGoldReadMixin,
    CommunityGoldMethodMixin,
    CommunityGoldEvaluationMixin,
    CommunityGoldCandidatePoolMixin,
    CommunityGoldCandidateMixin,
):
    """Unified community gold store composed from focused modules."""

    pass


__all__ = ["CommunityGoldStore"]
