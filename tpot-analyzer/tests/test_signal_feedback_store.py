"""Unit tests for SignalFeedbackStore behavior."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.api.services.signal_feedback_store import SignalFeedbackStore


@pytest.fixture
def feedback_store(tmp_path: Path) -> SignalFeedbackStore:
    """Return a store backed by a temporary SQLite database."""
    return SignalFeedbackStore(db_path=tmp_path / "test_feedback.db")


def test_event_count_increments_with_feedback(feedback_store: SignalFeedbackStore):
    assert feedback_store.event_count() == 0
    feedback_store.add_feedback(
        account_id="user_a",
        signal_name="neighbor_overlap",
        score=0.8,
        user_label="tpot",
        context={"seed_count": 2},
    )
    assert feedback_store.event_count() == 1


def test_quality_report_groups_by_signal_name(feedback_store: SignalFeedbackStore):
    feedback_store.add_feedback(account_id="user_a", signal_name="neighbor_overlap", score=0.9, user_label="tpot", context={})
    feedback_store.add_feedback(account_id="user_b", signal_name="neighbor_overlap", score=0.1, user_label="not_tpot", context={})
    feedback_store.add_feedback(account_id="user_c", signal_name="pagerank", score=0.7, user_label="tpot", context={})

    report = feedback_store.quality_report()
    assert "neighbor_overlap" in report
    assert "pagerank" in report
    assert report["neighbor_overlap"]["total_feedback"] == 2
    assert report["pagerank"]["total_feedback"] == 1


def test_quality_report_computes_tpot_ratio_and_score_separation(feedback_store: SignalFeedbackStore):
    feedback_store.add_feedback(account_id="u1", signal_name="community", score=0.9, user_label="tpot", context={})
    feedback_store.add_feedback(account_id="u2", signal_name="community", score=0.7, user_label="tpot", context={})
    feedback_store.add_feedback(account_id="u3", signal_name="community", score=0.2, user_label="not_tpot", context={})

    report = feedback_store.quality_report()["community"]
    assert report["total_feedback"] == 3
    assert report["tpot_ratio"] == 2 / 3
    # mean(tpot)=0.8, mean(not_tpot)=0.2
    assert abs(report["score_separation"] - 0.6) < 1e-9


def test_quality_report_returns_empty_dict_when_no_feedback(feedback_store: SignalFeedbackStore):
    assert feedback_store.quality_report() == {}


# --------------------------------------------------------------------------
# Persistence test: data survives across store instances sharing the same DB
# --------------------------------------------------------------------------

def test_feedback_persists_across_store_instances(tmp_path: Path):
    """Write feedback to one store, create a new instance pointing at the same
    DB file, and verify the data is still there."""
    db_path = tmp_path / "persist_test.db"

    store_a = SignalFeedbackStore(db_path=db_path)
    store_a.add_feedback(
        account_id="alice",
        signal_name="neighbor_overlap",
        score=0.9,
        user_label="tpot",
        context={"seed_count": 3},
    )
    store_a.add_feedback(
        account_id="bob",
        signal_name="pagerank",
        score=0.2,
        user_label="not_tpot",
    )
    assert store_a.event_count() == 2

    # Simulate server restart: new store instance, same DB.
    store_b = SignalFeedbackStore(db_path=db_path)
    assert store_b.event_count() == 2

    report = store_b.quality_report()
    assert "neighbor_overlap" in report
    assert "pagerank" in report
    assert report["neighbor_overlap"]["total_feedback"] == 1
    assert report["pagerank"]["total_feedback"] == 1


def test_context_round_trips_through_sqlite(tmp_path: Path):
    """Verify that the JSON context dict survives serialisation round-trip."""
    db_path = tmp_path / "ctx_test.db"
    store = SignalFeedbackStore(db_path=db_path)
    ctx = {"seed_count": 5, "note": "strong signal"}
    store.add_feedback(
        account_id="carol",
        signal_name="community",
        score=0.75,
        user_label="tpot",
        context=ctx,
    )

    # Reload from disk
    store2 = SignalFeedbackStore(db_path=db_path)
    events = store2._events  # noqa: SLF001 — test-only access
    assert len(events) == 1
    assert events[0].context == ctx
