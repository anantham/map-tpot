"""Tests for P6a: time-decay weighting of retweets in NMF pipeline.

Covers:
  - Decay weight computation (exp(-lambda * age_days))
  - build_retweet_matrix() with halflife_days parameter
  - make_run_id() includes halflife in hash
"""

import math
import sqlite3
from datetime import datetime, timezone, timedelta

import numpy as np
import pytest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from cluster_soft import build_retweet_matrix, make_run_id, compute_decay_weight


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_retweet_db(rows):
    """Create in-memory SQLite with retweets table.

    rows: list of (tweet_id, account_id, username, rt_of_username, created_at, fetched_at)
    """
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE retweets ("
        "  tweet_id TEXT PRIMARY KEY,"
        "  account_id TEXT NOT NULL,"
        "  username TEXT NOT NULL,"
        "  rt_of_username TEXT,"
        "  created_at TEXT,"
        "  fetched_at TEXT"
        ")"
    )
    for row in rows:
        con.execute(
            "INSERT INTO retweets (tweet_id, account_id, username, rt_of_username, created_at, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            row,
        )
    con.commit()
    return con


def _twitter_date(dt: datetime) -> str:
    """Format a datetime as Twitter's created_at format."""
    return dt.strftime("%a %b %d %H:%M:%S %z %Y")


# ── Fixtures ─────────────────────────────────────────────────────────────────

NOW = datetime(2026, 3, 22, 12, 0, 0, tzinfo=timezone.utc)

THREE_ACCOUNTS = [
    ("a1", "alice"),
    ("a2", "bob"),
    ("a3", "carol"),
]


def _build_test_rows():
    """Build retweet rows with known ages for decay testing.

    alice: 2 RTs of @target1 — one today, one 365 days ago
    bob:   1 RT of @target1 — today
    carol: 1 RT of @target2 — 730 days ago (2 years)
    """
    today = NOW
    one_year_ago = NOW - timedelta(days=365)
    two_years_ago = NOW - timedelta(days=730)

    return [
        ("t1", "a1", "alice", "target1", _twitter_date(today), "2026-03-22"),
        ("t2", "a1", "alice", "target1", _twitter_date(one_year_ago), "2026-03-22"),
        ("t3", "a2", "bob", "target1", _twitter_date(today), "2026-03-22"),
        ("t4", "a3", "carol", "target2", _twitter_date(two_years_ago), "2026-03-22"),
    ]


# ── TestComputeDecayWeight ─────────────────────────────────────────────────

class TestComputeDecayWeight:
    """Tests for compute_decay_weight() — exponential decay function."""

    def test_age_zero_gives_weight_one(self):
        """A retweet from today should have weight 1.0."""
        w = compute_decay_weight(age_days=0, halflife_days=365)
        assert w == pytest.approx(1.0)

    def test_one_halflife_gives_half(self):
        """A retweet from exactly one halflife ago should have weight ~0.5."""
        w = compute_decay_weight(age_days=365, halflife_days=365)
        assert w == pytest.approx(0.5, abs=1e-6)

    def test_two_halflives_gives_quarter(self):
        """A retweet from 2 halflives ago should have weight ~0.25."""
        w = compute_decay_weight(age_days=730, halflife_days=365)
        assert w == pytest.approx(0.25, abs=1e-6)

    def test_very_old_gives_near_zero(self):
        """A retweet from 10 halflives ago should have negligible weight."""
        w = compute_decay_weight(age_days=3650, halflife_days=365)
        assert w < 0.001

    def test_short_halflife(self):
        """With halflife=30, a 30-day-old RT has weight 0.5."""
        w = compute_decay_weight(age_days=30, halflife_days=30)
        assert w == pytest.approx(0.5, abs=1e-6)


# ── TestBuildRetweetMatrixDecay ──────────────────────────────────────────────

class TestBuildRetweetMatrixDecay:
    """Tests for build_retweet_matrix() with halflife_days parameter."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.accounts = THREE_ACCOUNTS
        self.con = _make_retweet_db(_build_test_rows())
        yield
        self.con.close()

    def test_no_decay_sums_counts(self):
        """Without decay, build_retweet_matrix sums raw counts (original behavior)."""
        mat, targets = build_retweet_matrix(self.con, self.accounts, min_count=1)
        dense = mat.toarray()

        t1_col = targets.index("target1")
        # alice has 2 RTs of target1 → count = 2
        assert dense[0, t1_col] == pytest.approx(2.0)
        # bob has 1 RT of target1 → count = 1
        assert dense[1, t1_col] == pytest.approx(1.0)

    def test_decay_reduces_old_rts(self):
        """With halflife=365, alice's 1-year-old RT gets half weight."""
        mat, targets = build_retweet_matrix(
            self.con, self.accounts, min_count=0,
            halflife_days=365, now=NOW,
        )
        dense = mat.toarray()

        t1_col = targets.index("target1")
        # alice: 1.0 (today) + 0.5 (1 year ago) = 1.5
        assert dense[0, t1_col] == pytest.approx(1.5, abs=0.05)
        # bob: 1.0 (today)
        assert dense[1, t1_col] == pytest.approx(1.0, abs=0.05)

    def test_very_old_rt_nearly_zero(self):
        """Carol's 2-year-old RT of target2 with halflife=365 gets weight ~0.25."""
        mat, targets = build_retweet_matrix(
            self.con, self.accounts, min_count=0,
            halflife_days=365, now=NOW,
        )
        dense = mat.toarray()

        t2_col = targets.index("target2")
        # carol: 0.25 (2 years ago with 1-year halflife)
        assert dense[2, t2_col] == pytest.approx(0.25, abs=0.05)

    def test_min_count_applies_after_decay(self):
        """min_count threshold applies to the decayed sum, not raw count."""
        # carol's decayed sum for target2 is ~0.25
        # With min_count=1, it should be filtered out
        mat, targets = build_retweet_matrix(
            self.con, self.accounts, min_count=1,
            halflife_days=365, now=NOW,
        )

        if "target2" in targets:
            dense = mat.toarray()
            t2_col = targets.index("target2")
            # carol's decayed weight is 0.25 < min_count=1, so should be 0
            assert dense[2, t2_col] == pytest.approx(0.0)
        # Or target2 may not appear at all — both are valid

    def test_null_created_at_excluded(self):
        """Rows with NULL created_at are excluded from decay computation."""
        rows = [
            ("t1", "a1", "alice", "target1", None, "2026-03-22"),
            ("t2", "a1", "alice", "target1", _twitter_date(NOW), "2026-03-22"),
        ]
        con = _make_retweet_db(rows)
        mat, targets = build_retweet_matrix(
            con, self.accounts, min_count=0,
            halflife_days=365, now=NOW,
        )
        dense = mat.toarray()

        t1_col = targets.index("target1")
        # Only the non-null row contributes: weight 1.0
        assert dense[0, t1_col] == pytest.approx(1.0, abs=0.05)
        con.close()


# ── TestMakeRunIdHalflife ──────────────────────────────────────────────────

class TestMakeRunIdHalflife:
    """Tests for make_run_id() — halflife changes the hash."""

    _accounts = [("a1", "alice"), ("a2", "bob")]

    def test_halflife_changes_run_id(self):
        """Different halflife values produce different run_ids."""
        id_none = make_run_id(14, "follow+rt", 0.6, 0.0, self._accounts, halflife_days=None)
        id_365 = make_run_id(14, "follow+rt_decay365", 0.6, 0.0, self._accounts, halflife_days=365)
        id_180 = make_run_id(14, "follow+rt_decay180", 0.6, 0.0, self._accounts, halflife_days=180)
        assert id_none != id_365
        assert id_365 != id_180

    def test_no_halflife_backward_compatible(self):
        """make_run_id with halflife_days=None matches original behavior."""
        id_old = make_run_id(14, "follow+rt", 0.6, 0.0, self._accounts)
        id_new = make_run_id(14, "follow+rt", 0.6, 0.0, self._accounts, halflife_days=None)
        assert id_old == id_new
