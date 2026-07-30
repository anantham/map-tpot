from __future__ import annotations

import math

from src.graph.source_selectivity import rank_follow_candidates


def test_selective_sources_rank_higher_without_duplicate_inflation() -> None:
    edges = [
        ("selective", "niche"),
        ("selective", "shared"),
        ("selective", "shared"),
        ("broad", "popular"),
        ("broad", "shared"),
    ]
    result = rank_follow_candidates(
        ["selective", "broad"],
        edges,
        {"selective": 1, "broad": 100},
    )

    candidates = {row.account_id: row for row in result.candidates}
    degrees = {row.seed_id: row for row in result.seed_diagnostics}
    assert degrees["selective"].effective_degree == 2
    assert degrees["broad"].effective_degree == 100
    assert math.isclose(candidates["niche"].selectivity_score, 1 / 2)
    assert math.isclose(candidates["popular"].selectivity_score, 1 / 100)
    assert math.isclose(candidates["shared"].selectivity_score, 1 / 2 + 1 / 100)
    assert candidates["shared"].supporting_seeds == ("broad", "selective")
    assert candidates["shared"].raw_support == 2
    assert [row.account_id for row in result.candidates] == [
        "shared",
        "niche",
        "popular",
    ]
    assert result.candidates == rank_follow_candidates(
        ["broad", "selective"], reversed(edges), {"broad": 100, "selective": 1}
    ).candidates


def test_ranking_breaks_score_ties_by_support_then_account_id() -> None:
    result = rank_follow_candidates(
        ["single", "half_a", "half_b"],
        [
            ("single", "one"),
            ("half_a", "two"),
            ("half_a", "filler_a"),
            ("half_b", "two"),
            ("half_b", "filler_b"),
        ],
    )

    assert [row.account_id for row in result.candidates] == [
        "two",
        "one",
        "filler_a",
        "filler_b",
    ]
    assert result.candidates[0].selectivity_score == 1.0
    assert result.candidates[1].selectivity_score == 1.0
    assert result.candidates[0].raw_support == 2
    assert result.candidates[1].raw_support == 1


def test_seed_targets_count_toward_degree_but_are_not_candidates() -> None:
    result = rank_follow_candidates(
        ["a", "b", "claimed_only", "unknown"],
        [("a", "a"), ("a", "b"), ("a", "candidate")],
        {"claimed_only": 5},
    )

    assert [row.account_id for row in result.candidates] == ["candidate"]
    assert math.isclose(result.candidates[0].selectivity_score, 1 / 2)
    diagnostics = {row.seed_id: row for row in result.seed_diagnostics}
    assert diagnostics["a"].observed_out_degree == 2
    assert diagnostics["a"].claimed_following_count is None
    assert diagnostics["a"].degree_unknown is False
    assert diagnostics["claimed_only"].observed_out_degree == 0
    assert diagnostics["claimed_only"].effective_degree == 5
    assert diagnostics["claimed_only"].degree_unknown is False
    assert diagnostics["unknown"].degree_unknown is True


def test_score_is_unbounded_and_invalid_claim_falls_back_to_observed_degree() -> None:
    result = rank_follow_candidates(
        ["a", "b", "c"],
        [("a", "same"), ("b", "same"), ("c", "same")],
        {"a": 0.5, "b": -1, "c": None},
    )

    assert result.candidates[0].selectivity_score == 3.0
    assert result.candidates[0].raw_support == 3
    assert all(row.claimed_following_count is None for row in result.seed_diagnostics)
    assert all(row.effective_degree == 1 for row in result.seed_diagnostics)
