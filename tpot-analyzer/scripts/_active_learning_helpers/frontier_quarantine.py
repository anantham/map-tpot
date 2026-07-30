"""Fail-closed policy for the unbound historical frontier ranking."""

from __future__ import annotations


class UnverifiedFrontierRankingError(RuntimeError):
    """Raised before an unverified ranking can select acquisition targets."""


def reject_unverified_frontier_ranking(consumer: str) -> None:
    """Block automatic use until a compatible ranking receipt exists."""
    raise UnverifiedFrontierRankingError(
        f"{consumer}: frontier_ranking is quarantined because its rows are not "
        "bound to a supported propagation artifact or evaluation receipt. "
        "Use explicit account handles, or implement and validate a replacement "
        "acquisition policy before automatic selection."
    )
