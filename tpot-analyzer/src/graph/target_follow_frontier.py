"""Exact-tag, source-selective follow frontier for curator feedback."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any

from src.data.account_tag_queries import load_target_tag_anchors
from src.data.follow_frontier_archive import (
    load_claimed_following_counts,
    load_follow_edges,
    load_usernames,
    open_archive_readonly,
)
from src.graph.source_selectivity import SeedDiagnostic, rank_follow_candidates


def _coverage(
    rows: tuple[SeedDiagnostic, ...],
    *,
    evaluated: bool = True,
) -> dict[str, Any]:
    observed = sum(row.observed_out_degree for row in rows)
    covered = sum(row.observed_out_degree > 0 for row in rows)
    rows_with_claims = tuple(
        row for row in rows if row.claimed_following_count is not None
    )
    fully_claimed = bool(rows) and len(rows_with_claims) == len(rows)
    claimed_effective = sum(row.effective_degree for row in rows_with_claims)
    claimed_observed = sum(row.observed_out_degree for row in rows_with_claims)
    return {
        "evaluated": evaluated,
        "anchorsWithObservedFollowing": covered,
        "anchorCoverageFraction": covered / len(rows) if rows else None,
        "observedUniqueFollowingEdges": observed,
        "claimedCountsAvailable": len(rows_with_claims),
        "claimedCountsMissing": len(rows) - len(rows_with_claims),
        "selectivityFallbackSources": sum(
            row.claimed_following_count is None and row.observed_out_degree > 0
            for row in rows
        ),
        "degreeUnknown": sum(row.degree_unknown for row in rows),
        "observedToEffectiveDegreeRatio": (
            claimed_observed / claimed_effective
            if fully_claimed and claimed_effective
            else None
        ),
    }


def _topology_diagnostics(
    positive: set[str],
    negative: set[str],
    edges: set[tuple[str, str]],
) -> dict[str, Any]:
    positive_cross = {
        (source, target)
        for source, target in edges
        if source != target and source in positive and target in positive
    }
    recovered = {target for _, target in positive_cross}
    possible = len(positive) * (len(positive) - 1)
    leaked = {target for s, target in edges if s in positive and target in negative}
    return {
        "semantics": {
            "scope": "in-sample stored anchor edges only",
            "missingness": "an unobserved edge is unknown, not an observed absence",
            "generalization": "no held-out recovery or cluster-existence claim",
        },
        "observedAnchorReachability": {
            "eligiblePositiveAnchors": len(positive),
            "positiveAnchorsReachedByPositive": len(recovered),
            "observedFraction": (
                len(recovered) / len(positive) if len(positive) >= 2 else None
            ),
        },
        "observedPositivePairLinks": {
            "possibleDirectedEdges": possible,
            "observedDirectedEdges": len(positive_cross),
            "observedFraction": (
                len(positive_cross) / possible if possible else None
            ),
        },
        "observedBoundaryCrossing": {
            "eligibleNegativeAnchors": len(negative),
            "negativeAnchorsReachedByPositive": len(leaked),
            "observedFraction": len(leaked) / len(negative) if negative else None,
        },
    }


def _status_reason(
    *,
    positive_count: int,
    covered_positive: int,
    candidate_count: int,
    negative_count: int,
    covered_negative: int,
) -> tuple[str, str]:
    if positive_count == 0:
        return "insufficient", "no_positive_anchors"
    if covered_positive == 0:
        return "insufficient", "no_observed_positive_follow_edges"
    if candidate_count == 0:
        return "insufficient", "no_non_anchor_candidates"
    if positive_count == 1:
        return "insufficient", "single_positive_anchor_only"
    if negative_count == 0:
        return "provisional", "positive_only_no_negative_anchors"
    if covered_negative == 0:
        return "provisional", "negative_anchors_have_no_observed_following"
    return "provisional", "uncalibrated_observed_follow_contrast"


def build_target_follow_frontier(
    *,
    tag_db_path: Path,
    archive_db_path: Path,
    ego: str,
    tag: str,
    limit: int,
) -> dict[str, Any]:
    """Build one mutable-archive ranking without asserting cluster existence."""
    normalized_ego = str(ego or "").strip()
    normalized_tag = str(tag or "").strip()
    anchors = load_target_tag_anchors(
        tag_db_path,
        ego=normalized_ego,
        tag=normalized_tag,
    )
    positive, negative = set(anchors.positive), set(anchors.negative)
    target = {
        "ego": normalized_ego,
        "tag": normalized_tag,
        "tagKey": normalized_tag.casefold(),
    }
    if not positive:
        return _empty_frontier(target, len(negative))

    with closing(open_archive_readonly(archive_db_path)) as conn:
        edges = load_follow_edges(conn, positive | negative)
        claims = load_claimed_following_counts(conn, positive | negative)
        positive_result = rank_follow_candidates(positive, edges, claims)
        negative_result = rank_follow_candidates(negative, edges, claims)
        all_anchors = positive | negative
        negative_scores = {row.account_id: row for row in negative_result.candidates}
        ranked = []
        for row in positive_result.candidates:
            if row.account_id in all_anchors:
                continue
            opposing = negative_scores.get(row.account_id)
            negative_score = opposing.selectivity_score if opposing else 0.0
            ranked.append((row.selectivity_score - negative_score, row, opposing))
        ranked.sort(
            key=lambda item: (
                -item[0],
                -item[1].selectivity_score,
                item[2].selectivity_score if item[2] else 0,
                item[1].account_id,
            )
        )
        usernames = load_usernames(
            conn,
            (item[1].account_id for item in ranked[:limit]),
        )

    positive_coverage = _coverage(positive_result.seed_diagnostics)
    negative_coverage = _coverage(negative_result.seed_diagnostics)
    status, reason = _status_reason(
        positive_count=len(positive),
        covered_positive=positive_coverage["anchorsWithObservedFollowing"],
        candidate_count=len(ranked),
        negative_count=len(negative),
        covered_negative=negative_coverage["anchorsWithObservedFollowing"],
    )
    candidates = [
        {
            "accountId": row.account_id,
            "username": usernames.get(row.account_id),
            "positiveScore": row.selectivity_score,
            "negativeScore": opposing.selectivity_score if opposing else 0.0,
            "contrast": contrast,
            "positiveRawSupport": row.raw_support,
            "negativeRawSupport": opposing.raw_support if opposing else 0,
            "positiveSupportingAnchors": list(row.supporting_seeds),
            "negativeSupportingAnchors": (
                list(opposing.supporting_seeds) if opposing else []
            ),
        }
        for contrast, row, opposing in ranked[:limit]
    ]
    diagnostics = _topology_diagnostics(positive, negative, set(edges))
    diagnostics.update(candidateCount=len(ranked), returnedCount=len(candidates))
    return {
        "target": target,
        "status": status,
        "reason": reason,
        "semantics": _semantics(),
        "anchors": {
            "positive": {"count": len(positive), "coverage": positive_coverage},
            "negative": {"count": len(negative), "coverage": negative_coverage},
        },
        "candidates": candidates,
        "diagnostics": diagnostics,
    }


def _semantics() -> dict[str, Any]:
    return {
        "method": "source_selectivity_contrast_v1",
        "scoreMeaning": (
            "positive selective follow support minus negative selective "
            "follow support"
        ),
        "calibrated": False,
        "archiveBinding": "mutable_local_archive_unbound",
        "statusMeaning": (
            "evidence availability for this ranking; not a claim that a "
            "social cluster exists"
        ),
        "edgeBoundary": (
            "stored directed follows without edge timestamps or source attribution"
        ),
        "denominatorFallback": (
            "when a claimed following total is absent, stored observed out-degree "
            "is used and support may be overstated"
        ),
    }


def _empty_frontier(target: dict[str, str], negative_count: int) -> dict[str, Any]:
    empty_coverage = _coverage((), evaluated=False)
    return {
        "target": target,
        "status": "insufficient",
        "reason": "no_positive_anchors",
        "semantics": _semantics(),
        "anchors": {
            "positive": {"count": 0, "coverage": empty_coverage},
            "negative": {"count": negative_count, "coverage": empty_coverage},
        },
        "candidates": [],
        "diagnostics": {
            "semantics": {
                "scope": "not evaluated because no positive anchors exist",
                "missingness": "an unobserved edge is unknown, not an observed absence",
                "generalization": "no held-out recovery or cluster-existence claim",
            },
            "observedAnchorReachability": {
                "eligiblePositiveAnchors": 0,
                "positiveAnchorsReachedByPositive": 0,
                "observedFraction": None,
            },
            "observedPositivePairLinks": {
                "possibleDirectedEdges": 0,
                "observedDirectedEdges": 0,
                "observedFraction": None,
            },
            "observedBoundaryCrossing": {
                "eligibleNegativeAnchors": negative_count,
                "negativeAnchorsReachedByPositive": 0,
                "observedFraction": None,
            },
            "candidateCount": 0,
            "returnedCount": 0,
        },
    }
