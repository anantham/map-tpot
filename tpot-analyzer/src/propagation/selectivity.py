"""Selectivity-weighted co-following: score candidates by *who* vouched for them.

The existing pipeline applies TF-IDF to the **target** — down-weighting an
account because everyone follows it. This module applies the dual, on the
**source**: a follow emitted by an account that follows 760 people carries far
more information than one emitted by an account that follows 8,000.

That asymmetry is the whole point. An unweighted co-follow count says a
candidate is interesting because many seeds follow them; a selectivity-weighted
score says a candidate is interesting because *discriminating* seeds spent one of
their scarce follows on them. Empirically this matters here: a held-out test on
the dharma seeds scored the account following only 157 people highest (3.18%) and
the account following 2,617 lowest (0.19%), purely as an artefact of list length.

Direction is never symmetrised. ``seed -> candidate`` is a claim the seed made;
``candidate -> seed`` is not. Collapsing them, as the spectral layer does, throws
away exactly the signal being measured here.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional


@dataclass(frozen=True)
class Candidate:
    account_id: str
    score: float                       # selectivity-weighted vouch mass
    raw_votes: int                     # how many seeds follow them
    vouchers: tuple[str, ...]          # seed ids, most selective first
    top_voucher_weight: float

    @property
    def is_multi_vouched(self) -> bool:
        return self.raw_votes >= 2


def selectivity_weight(out_degree: int, *, floor: int = 25) -> float:
    """Weight a seed's vouch by how discriminating it is. Range (0, 1].

    ``1 / log2(2 + n)`` decays smoothly rather than in steps, so a 300-follow
    account is not treated as categorically different from a 400-follow one.
    ``floor`` guards against a near-empty list (often a scrape failure rather
    than genuine taste) scoring as maximally authoritative.
    """
    n = max(int(out_degree or 0), floor)
    return 1.0 / math.log2(2 + n)


def popularity_discount(in_degree: int, *, floor: int = 20) -> float:
    """Down-weight a candidate everybody already follows. Range (0, 1].

    Source selectivity alone is not enough, and the first live run proved it:
    scoring the interface-design seeds surfaced Karpathy, paulg and Carmack at
    the top, because discriminating people still follow celebrities. Selectivity
    says *who vouched*; this says *how much that vouch narrows the field*. Only
    the product finds a niche.

    ``floor`` matters as much as the formula. Our follow graph holds outbound
    lists for only a few thousand accounts, so an in-degree of 2 means "we barely
    observed this account", not "genuinely obscure". Without a floor the discount
    inverts into a bounty on unmeasured accounts, and the ranking fills with bare
    numeric IDs — the mirror of the celebrity problem it was added to fix.
    """
    return 1.0 / math.log2(2 + max(int(in_degree or 0), floor))


def score_candidates(
    following: Mapping[str, Iterable[str]],
    *,
    exclude: Optional[set[str]] = None,
    min_votes: int = 2,
    out_degrees: Optional[Mapping[str, int]] = None,
    in_degrees: Optional[Mapping[str, int]] = None,
) -> list[Candidate]:
    """Rank accounts vouched for by the seeds in ``following``.

    ``following`` maps seed id -> the accounts that seed follows. ``out_degrees``
    lets a caller pass the *true* following count from the profile API rather
    than the number of edges we happen to have stored — using stored edges would
    reward accounts we simply failed to scrape fully.
    """
    exclude = set(exclude or ())
    exclude |= set(following)          # seeds never rank as their own candidates

    weights = {
        seed: selectivity_weight(
            (out_degrees or {}).get(seed) or len(list(targets)))
        for seed, targets in following.items()
    }
    mass: dict[str, float] = defaultdict(float)
    votes: dict[str, list[str]] = defaultdict(list)
    for seed, targets in following.items():
        w = weights[seed]
        for target in targets:
            if target in exclude:
                continue
            discount = (popularity_discount((in_degrees or {}).get(target, 0))
                        if in_degrees is not None else 1.0)
            mass[target] += w * discount
            votes[target].append(seed)

    out = [
        Candidate(
            account_id=target,
            score=round(total, 6),
            raw_votes=len(votes[target]),
            vouchers=tuple(sorted(votes[target], key=lambda s: -weights[s])),
            top_voucher_weight=round(max(weights[s] for s in votes[target]), 6),
        )
        for target, total in mass.items()
        if len(votes[target]) >= min_votes
    ]
    out.sort(key=lambda c: (-c.score, -c.raw_votes, c.account_id))
    return out


def rank_shift(weighted: list[Candidate],
               following: Mapping[str, Iterable[str]],
               *, min_votes: int = 2) -> dict[str, int]:
    """How far each candidate moved versus a plain unweighted vote count.

    Reported so the weighting can be inspected rather than believed: if it
    changes nothing, it is not earning its place.
    """
    counts: dict[str, int] = defaultdict(int)
    seeds = set(following)
    for _, targets in following.items():
        for t in targets:
            if t not in seeds:
                counts[t] += 1
    plain = sorted((c for c in counts if counts[c] >= min_votes),
                   key=lambda c: (-counts[c], c))
    plain_rank = {c: i for i, c in enumerate(plain)}
    return {c.account_id: plain_rank.get(c.account_id, len(plain)) - i
            for i, c in enumerate(weighted)}
