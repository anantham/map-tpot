"""Tests for the SilentFailureTracker."""
from __future__ import annotations

import logging

import pytest

from src.shadow.silent_failures import SilentFailureTracker, tracker as global_tracker


@pytest.fixture
def t() -> SilentFailureTracker:
    return SilentFailureTracker()


@pytest.mark.unit
def test_track_increments_count(t):
    t.track("op.a", ValueError("boom"))
    t.track("op.a", ValueError("boom2"))
    snap = t.snapshot()
    assert len(snap) == 1
    assert snap[0]["operation"] == "op.a"
    assert snap[0]["exception"] == "ValueError"
    assert snap[0]["count"] == 2


@pytest.mark.unit
def test_separate_buckets_per_operation_and_exception(t):
    t.track("op.a", ValueError())
    t.track("op.a", TypeError())
    t.track("op.b", ValueError())
    snap = t.snapshot()
    assert len(snap) == 3
    keys = {(r["operation"], r["exception"]) for r in snap}
    assert keys == {("op.a", "ValueError"), ("op.a", "TypeError"), ("op.b", "ValueError")}


@pytest.mark.unit
def test_samples_retain_last_three_messages(t):
    for i in range(5):
        t.track("op.x", ValueError(f"msg{i}"))
    samples = t.snapshot()[0]["samples"]
    assert samples == ["msg2", "msg3", "msg4"]


@pytest.mark.unit
def test_sample_message_truncated_to_200_chars(t):
    long_msg = "x" * 500
    t.track("op.x", RuntimeError(long_msg))
    assert len(t.snapshot()[0]["samples"][0]) == 200


@pytest.mark.unit
def test_track_without_exception_uses_unknown(t):
    t.track("op.x")
    assert t.snapshot()[0]["exception"] == "Unknown"


@pytest.mark.unit
def test_snapshot_sorted_by_count_desc(t):
    t.track("op.a", ValueError())
    for _ in range(3):
        t.track("op.b", ValueError())
    for _ in range(2):
        t.track("op.c", ValueError())
    snap = t.snapshot()
    counts = [r["count"] for r in snap]
    assert counts == [3, 2, 1]


@pytest.mark.unit
def test_reset_clears_stats(t):
    t.track("op.a", ValueError())
    assert t.total_count() == 1
    t.reset()
    assert t.snapshot() == []
    assert t.total_count() == 0


@pytest.mark.unit
def test_log_summary_emits_nothing_when_empty(t, caplog):
    with caplog.at_level(logging.INFO, logger="src.shadow.silent_failures"):
        t.log_summary("test-context")
    assert caplog.records == []


@pytest.mark.unit
def test_log_summary_emits_one_line_per_category(t, caplog):
    t.track("op.a", ValueError("err1"))
    t.track("op.a", ValueError("err2"))
    t.track("op.b", TypeError())
    with caplog.at_level(logging.INFO, logger="src.shadow.silent_failures"):
        t.log_summary("for @nick")
    messages = [r.getMessage() for r in caplog.records]
    # 1 header + 2 category lines
    assert len(messages) == 3
    assert "for @nick" in messages[0]
    assert "3 total across 2 categories" in messages[0]
    assert any("op.a" in m and "count=2" in m for m in messages)
    assert any("op.b" in m and "count=1" in m for m in messages)


@pytest.mark.unit
def test_global_tracker_is_singleton():
    # Reset to avoid leak from other tests
    global_tracker.reset()
    global_tracker.track("op.singleton", RuntimeError("x"))
    assert global_tracker.total_count() == 1
    global_tracker.reset()
