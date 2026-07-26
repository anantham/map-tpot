"""Compatibility wrapper for the community gold store."""
from __future__ import annotations

from .base import BaseCommunityGoldStore
from .candidates import CommunityGoldCandidateMixin
from .candidate_pool import CommunityGoldCandidatePoolMixin
from .evals import CommunityGoldEvaluationMixin
from .methods import CommunityGoldMethodMixin
from .reads import CommunityGoldReadMixin


class CommunityGoldStore(
    BaseCommunityGoldStore,
    CommunityGoldReadMixin,
    CommunityGoldMethodMixin,
    CommunityGoldEvaluationMixin,
    CommunityGoldCandidatePoolMixin,
    CommunityGoldCandidateMixin,
):
    """Unified community gold store composed from focused modules."""

    pass


__all__ = ["CommunityGoldStore"]
