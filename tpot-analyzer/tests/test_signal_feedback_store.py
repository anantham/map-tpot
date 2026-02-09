"""Unit tests for SignalFeedbackStore behavior."""
from __future__ import annotations

from src.api.services.signal_feedback_store import SignalFeedbackStore


def test_event_count_increments_with_feedback():
    store = SignalFeedbackStore()
    assert store.event_count() == 0
    store.add_feedback(
        account_id="user_a",
        signal_name="neighbor_overlap",
        score=0.8,
        user_label="tpot",
        context={"seed_count": 2},
    )
    assert store.event_count() == 1


def test_quality_report_groups_by_signal_name():
    store = SignalFeedbackStore()
    store.add_feedback(account_id="user_a", signal_name="neighbor_overlap", score=0.9, user_label="tpot", context={})
    store.add_feedback(account_id="user_b", signal_name="neighbor_overlap", score=0.1, user_label="not_tpot", context={})
    store.add_feedback(account_id="user_c", signal_name="pagerank", score=0.7, user_label="tpot", context={})

    report = store.quality_report()
    assert "neighbor_overlap" in report
    assert "pagerank" in report
    assert report["neighbor_overlap"]["total_feedback"] == 2
    assert report["pagerank"]["total_feedback"] == 1


def test_quality_report_computes_tpot_ratio_and_score_separation():
    store = SignalFeedbackStore()
    store.add_feedback(account_id="u1", signal_name="community", score=0.9, user_label="tpot", context={})
    store.add_feedback(account_id="u2", signal_name="community", score=0.7, user_label="tpot", context={})
    store.add_feedback(account_id="u3", signal_name="community", score=0.2, user_label="not_tpot", context={})

    report = store.quality_report()["community"]
    assert report["total_feedback"] == 3
    assert report["tpot_ratio"] == 2 / 3
    # mean(tpot)=0.8, mean(not_tpot)=0.2
    assert abs(report["score_separation"] - 0.6) < 1e-9


def test_quality_report_returns_empty_dict_when_no_feedback():
    store = SignalFeedbackStore()
    assert store.quality_report() == {}
