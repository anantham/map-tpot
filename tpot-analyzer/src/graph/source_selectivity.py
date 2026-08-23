"""Source-side selectivity ranking for observed follow edges.

Each distinct seed-to-candidate follow contributes ``1 / effective_degree``,
where effective degree is the larger of the seed's nonnegative integer claimed
following count and its observed unique out-degree. The score is an
uncalibrated ranking signal, not a probability, confidence, or membership.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class CandidateScore:
    account_id: str
    selectivity_score: float
    raw_support: int
    supporting_seeds: tuple[str, ...]


@dataclass(frozen=True)
class SeedDiagnostic:
    seed_id: str
    observed_out_degree: int
    claimed_following_count: int | None
    effective_degree: int
    degree_unknown: bool


@dataclass(frozen=True)
class SourceSelectivityResult:
    candidates: tuple[CandidateScore, ...]
    seed_diagnostics: tuple[SeedDiagnostic, ...]


def _valid_claim(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def rank_follow_candidates(
    seed_ids: Iterable[str],
    follow_edges: Iterable[tuple[str, str]],
    claimed_following_counts: Mapping[str, int | None] | None = None,
) -> SourceSelectivityResult:
    """Rank non-seed accounts while exposing per-seed coverage assumptions.

    Duplicate observations are one relation. Self-follows are ignored. Follows
    from one seed to another count toward the source's degree but do not become
    candidates. Missing or invalid claimed counts fall back to observed degree;
    a seed with neither is marked degree-unknown. A known claimed degree does
    not imply that its outgoing neighborhood was captured.
    """
    seeds = tuple(sorted(set(seed_ids)))
    seed_set = set(seeds)
    edges = {
        (source, target)
        for source, target in follow_edges
        if source != target and source in seed_set
    }
    outgoing = {seed: set() for seed in seeds}
    for source, target in edges:
        outgoing[source].add(target)

    claims = claimed_following_counts or {}
    effective: dict[str, int] = {}
    diagnostics = []
    for seed in seeds:
        observed = len(outgoing[seed])
        claimed = _valid_claim(claims.get(seed))
        effective[seed] = max(observed, claimed or 0)
        diagnostics.append(
            SeedDiagnostic(
                seed_id=seed,
                observed_out_degree=observed,
                claimed_following_count=claimed,
                effective_degree=effective[seed],
                degree_unknown=observed == 0 and claimed is None,
            )
        )

    supporters: dict[str, set[str]] = {}
    for source, target in edges:
        if target not in seed_set:
            supporters.setdefault(target, set()).add(source)

    candidates = []
    for account_id, source_seeds in supporters.items():
        ordered_sources = tuple(sorted(source_seeds))
        candidates.append(
            CandidateScore(
                account_id=account_id,
                selectivity_score=math.fsum(
                    1 / effective[seed] for seed in ordered_sources
                ),
                raw_support=len(ordered_sources),
                supporting_seeds=ordered_sources,
            )
        )
    candidates.sort(
        key=lambda row: (-row.selectivity_score, -row.raw_support, row.account_id)
    )
    return SourceSelectivityResult(tuple(candidates), tuple(diagnostics))
