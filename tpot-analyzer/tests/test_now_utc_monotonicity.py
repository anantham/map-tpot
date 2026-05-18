"""Direct stress test of src.communities.store.now_utc().

The function is the timestamp source for community_branch.created_at,
community_snapshot.created_at, and account_note.updated_at. SQLite's
ORDER BY created_at relies on it being strictly monotonic — back-to-back
calls on Windows can otherwise collide on second resolution, breaking
snapshot ordering (the original test_list_snapshots / test_switch_branch_with_save
flakes).

This file guards the fix by asserting monotonicity under conditions that
would have broken the pre-fix implementation: tight loops, thread
contention, and ISO-8601-string lexicographic ordering.
"""
from __future__ import annotations

import threading

import pytest

from src.communities.store import now_utc


@pytest.mark.unit
def test_now_utc_returns_iso8601_string():
    value = now_utc()
    assert isinstance(value, str)
    # Format: "2026-05-17T12:34:56.123456+00:00"
    assert "T" in value
    assert "+00:00" in value or value.endswith("Z")


@pytest.mark.unit
def test_now_utc_strictly_monotonic_in_tight_loop():
    """1_000 back-to-back calls should produce 1_000 strictly increasing values
    that also lex-sort in call order (what SQLite's ORDER BY relies on).

    Before the fix: roughly 1-5% of calls collided on Windows second
    resolution. After the fix: zero collisions.
    """
    values = [now_utc() for _ in range(1_000)]
    for prev, curr in zip(values, values[1:]):
        assert curr > prev, f"Non-monotonic: {prev!r} >= {curr!r}"
    # Same-format ISO strings lex-sort iff they're chronologically ordered,
    # so monotonic + this assertion in one is sufficient.
    assert values == sorted(values)


@pytest.mark.unit
def test_now_utc_thread_safe_no_collisions_under_contention():
    """8 threads x 500 calls each = 4000 strictly distinct values.

    Catches a regression where the monotonic clamp loses the lock and two
    threads observe the same _NOW_UTC_LAST_NS.
    """
    n_threads = 8
    per_thread = 500
    all_values: list[str] = []
    lock = threading.Lock()

    def worker():
        local = [now_utc() for _ in range(per_thread)]
        with lock:
            all_values.extend(local)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(all_values) == n_threads * per_thread
    assert len(set(all_values)) == len(all_values), "duplicate timestamp under thread contention"
