"""Compatibility wrapper for the community gold store."""
from __future__ import annotations

from .base import BaseCommunityGoldStore
from .candidates import CommunityGoldCandidateMixin
from .evals import CommunityGoldEvaluationMixin
from .methods import CommunityGoldMethodMixin
from .reads import CommunityGoldReadMixin


class CommunityGoldStore(
    BaseCommunityGoldStore,
    CommunityGoldReadMixin,
    CommunityGoldMethodMixin,
    CommunityGoldEvaluationMixin,
    CommunityGoldCandidateMixin,
):
    """Unified community gold store composed from focused modules."""

    pass


__all__ = ["CommunityGoldStore"]
