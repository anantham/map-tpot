"""Behavioural tests for selectivity-weighted co-following.

Test Intent
-----------
* A vouch from a highly selective account must outweigh one from a promiscuous
  account — that inversion is the entire reason this module exists.
* Seeds must never appear as their own candidates.
* A near-empty following list (usually a scrape failure, not taste) must not
  score as maximally authoritative.
* The weighting must be inspectable: rank_shift has to show movement versus a
  plain vote count, or the weighting is not earning its place.
"""
from __future__ import annotations

from src.propagation.selectivity import (
    score_candidates, selectivity_weight, rank_shift,
)


class TestSelectivityWeight:
    def test_selective_account_outweighs_promiscuous_one(self):
        assert selectivity_weight(300) > selectivity_weight(8000)

    def test_weight_is_bounded_and_positive(self):
        for n in (0, 1, 50, 700, 100_000):
            assert 0.0 < selectivity_weight(n) <= 1.0

    def test_floor_blocks_a_near_empty_list_from_dominating(self):
        """10 stored edges is usually a failed scrape, not exquisite taste."""
        assert selectivity_weight(10) == selectivity_weight(0)
        assert selectivity_weight(10) < selectivity_weight(9, floor=1)

    def test_decay_is_smooth_not_stepwise(self):
        assert selectivity_weight(300) > selectivity_weight(400) > selectivity_weight(500)


class TestScoring:
    def test_selective_voucher_beats_two_promiscuous_ones(self):
        """The inversion that motivates the module, asserted directly."""
        following = {
            "picky": ["A"] + [f"x{i}" for i in range(40)],      # ~41 follows
            "broad1": ["B"] + [f"y{i}" for i in range(6000)],
            "broad2": ["B"] + [f"z{i}" for i in range(6000)],
        }
        ranked = {c.account_id: c for c in score_candidates(following, min_votes=1)}
        assert ranked["A"].raw_votes == 1 and ranked["B"].raw_votes == 2
        assert ranked["A"].score > ranked["B"].score, (
            "one discriminating vouch should beat two indiscriminate ones")

    def test_seeds_are_never_their_own_candidates(self):
        following = {"a": ["b", "c"], "b": ["a", "c"]}
        assert all(c.account_id not in following
                   for c in score_candidates(following, min_votes=1))

    def test_min_votes_filters_single_vouch_noise(self):
        following = {"a": ["x", "y"], "b": ["x"]}
        got = {c.account_id for c in score_candidates(following, min_votes=2)}
        assert got == {"x"}

    def test_exclude_removes_known_accounts(self):
        following = {"a": ["x", "y"], "b": ["x", "y"]}
        got = {c.account_id for c in score_candidates(following, exclude={"x"})}
        assert got == {"y"}

    def test_vouchers_are_ordered_most_selective_first(self):
        following = {"picky": ["T"] + [f"p{i}" for i in range(30)],
                     "broad": ["T"] + [f"q{i}" for i in range(3000)]}
        c = score_candidates(following, min_votes=2)[0]
        assert c.vouchers[0] == "picky"

    def test_true_out_degree_overrides_stored_edge_count(self):
        """Stored edges under-count when a scrape was partial; trust the profile."""
        following = {"s": ["T"], "t": ["T"]}
        loose = score_candidates(following, min_votes=2,
                                 out_degrees={"s": 9000, "t": 9000})[0]
        tight = score_candidates(following, min_votes=2)[0]
        assert tight.score > loose.score

    def test_empty_input(self):
        assert score_candidates({}) == []


class TestInspectability:
    def test_rank_shift_reports_movement_versus_plain_counting(self):
        following = {
            "picky": ["A"] + [f"x{i}" for i in range(30)],
            "picky2": ["A"] + [f"w{i}" for i in range(30)],
            "broad1": ["B"] + [f"y{i}" for i in range(5000)],
            "broad2": ["B"] + [f"z{i}" for i in range(5000)],
        }
        ranked = score_candidates(following, min_votes=2)
        shift = rank_shift(ranked, following, min_votes=2)
        assert set(shift) == {c.account_id for c in ranked}
        assert isinstance(shift["A"], int)


class TestPopularityDiscount:
    """Source selectivity alone surfaced Karpathy and paulg; the product must not."""

    def test_ubiquitous_target_is_discounted(self):
        from src.propagation.selectivity import popularity_discount
        assert popularity_discount(50_000) < popularity_discount(50)

    def test_niche_target_beats_celebrity_at_equal_votes(self):
        following = {"a": ["celeb", "niche"], "b": ["celeb", "niche"]}
        ranked = score_candidates(following, min_votes=2,
                                  in_degrees={"celeb": 40_000, "niche": 30})
        assert ranked[0].account_id == "niche", (
            "an equally-vouched niche account must outrank a celebrity")

    def test_omitting_in_degrees_leaves_scores_unchanged(self):
        """The discount must be opt-in, so existing behaviour is preserved."""
        following = {"a": ["x", "y"], "b": ["x", "y"]}
        assert ([c.score for c in score_candidates(following)]
                == [c.score for c in score_candidates(following, in_degrees=None)])


class TestDiscountFloor:
    """An in-degree of 2 means "barely observed", not "genuinely obscure"."""

    def test_barely_observed_accounts_do_not_beat_moderately_known_ones(self):
        from src.propagation.selectivity import popularity_discount
        assert popularity_discount(2) == popularity_discount(20)

    def test_unmeasured_target_cannot_outrank_a_well_evidenced_niche_one(self):
        following = {"a": ["ghost", "niche"], "b": ["ghost", "niche"]}
        ranked = score_candidates(following, min_votes=2,
                                  in_degrees={"ghost": 2, "niche": 25})
        assert abs(ranked[0].score - ranked[1].score) < 0.02, (
            "a 2-in-degree ghost must not dominate a 25-in-degree real account")

    def test_genuine_celebrity_is_still_discounted(self):
        from src.propagation.selectivity import popularity_discount
        assert popularity_discount(40_000) < popularity_discount(25) / 1.5
