"""Tests for likes matrix and run ID identity in scripts/cluster_soft.py."""

import sqlite3

import pytest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from cluster_soft import build_likes_matrix, make_run_id


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_engagement_db(rows):
    """Create in-memory SQLite with account_engagement_agg table.

    rows: list of (source_id, target_id, like_count)
    """
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE account_engagement_agg ("
        "  source_id TEXT NOT NULL,"
        "  target_id TEXT NOT NULL,"
        "  like_count INTEGER DEFAULT 0,"
        "  PRIMARY KEY (source_id, target_id)"
        ")"
    )
    for src, tgt, cnt in rows:
        con.execute(
            "INSERT INTO account_engagement_agg (source_id, target_id, like_count) "
            "VALUES (?, ?, ?)",
            (src, tgt, cnt),
        )
    con.commit()
    return con


# ── TestBuildLikesMatrix ─────────────────────────────────────────────────────

class TestBuildLikesMatrix:

    def test_basic_shape(self):
        """3 accounts, 2 targets -> matrix is (3, 2)."""
        accounts = [("a1", "alice"), ("a2", "bob"), ("a3", "carol")]
        con = _make_engagement_db([
            ("a1", "t1", 5),
            ("a2", "t2", 3),
            ("a3", "t1", 1),
        ])
        mat, targets = build_likes_matrix(con, accounts)
        assert mat.shape == (3, 2)
        assert len(targets) == 2
        con.close()

    def test_values_correct(self):
        """Verify specific cell values match like_count."""
        accounts = [("a1", "alice"), ("a2", "bob")]
        con = _make_engagement_db([
            ("a1", "t1", 7),
            ("a1", "t2", 3),
            ("a2", "t1", 12),
        ])
        mat, targets = build_likes_matrix(con, accounts)
        dense = mat.toarray()

        # targets are sorted, so t1=col0, t2=col1
        assert targets == ["t1", "t2"]
        assert dense[0, 0] == pytest.approx(7.0)   # a1 -> t1
        assert dense[0, 1] == pytest.approx(3.0)   # a1 -> t2
        assert dense[1, 0] == pytest.approx(12.0)  # a2 -> t1
        assert dense[1, 1] == pytest.approx(0.0)   # a2 -> t2 (no edge)
        con.close()

    def test_unknown_account_ignored(self):
        """Accounts not in engagement table get zero rows."""
        accounts = [("a1", "alice"), ("a_unknown", "ghost"), ("a2", "bob")]
        con = _make_engagement_db([
            ("a1", "t1", 5),
            ("a2", "t1", 3),
        ])
        mat, targets = build_likes_matrix(con, accounts)
        dense = mat.toarray()

        # ghost (row 1) should be all zeros
        assert dense[1, :].sum() == 0.0
        # a1 and a2 should have values
        assert dense[0, 0] == pytest.approx(5.0)
        assert dense[2, 0] == pytest.approx(3.0)
        con.close()

    def test_empty_engagement(self):
        """No data -> (n, 0) matrix with empty targets."""
        accounts = [("a1", "alice"), ("a2", "bob")]
        con = _make_engagement_db([])
        mat, targets = build_likes_matrix(con, accounts)
        assert mat.shape == (2, 0)
        assert targets == []
        con.close()

    def test_missing_table(self):
        """Missing table -> (n, 0) matrix (graceful fallback)."""
        accounts = [("a1", "alice")]
        con = sqlite3.connect(":memory:")
        mat, targets = build_likes_matrix(con, accounts)
        assert mat.shape == (1, 0)
        assert targets == []
        con.close()

    def test_min_count_filter(self):
        """min_count filters out rows below threshold."""
        accounts = [("a1", "alice"), ("a2", "bob")]
        con = _make_engagement_db([
            ("a1", "t1", 5),
            ("a1", "t2", 1),
            ("a2", "t1", 2),
        ])
        mat, targets = build_likes_matrix(con, accounts, min_count=3)
        dense = mat.toarray()
        # Only a1->t1 (5) survives min_count=3
        assert "t1" in targets
        t1_col = targets.index("t1")
        assert dense[0, t1_col] == pytest.approx(5.0)
        # a2->t1=2 should be filtered out (< 3)
        assert dense[1, t1_col] == pytest.approx(0.0)
        con.close()


# ── TestRunIdIdentity ────────────────────────────────────────────────────────

class TestRunIdIdentity:

    _accounts = [("a1", "alice"), ("a2", "bob"), ("a3", "carol")]

    def test_different_signals_different_ids(self):
        """follow+rt vs follow+rt+like produce different run IDs."""
        id1 = make_run_id(14, "follow+rt", 0.6, 0.0, self._accounts)
        id2 = make_run_id(14, "follow+rt+like", 0.6, 0.4, self._accounts)
        assert id1 != id2

    def test_different_weights_different_ids(self):
        """Different like weights produce different run IDs."""
        id1 = make_run_id(14, "follow+rt+like", 0.6, 0.4, self._accounts)
        id2 = make_run_id(14, "follow+rt+like", 0.6, 0.8, self._accounts)
        assert id1 != id2

    def test_same_params_same_id(self):
        """Identical params produce identical run IDs (deterministic)."""
        id1 = make_run_id(14, "follow+rt+like", 0.6, 0.4, self._accounts)
        id2 = make_run_id(14, "follow+rt+like", 0.6, 0.4, self._accounts)
        assert id1 == id2

    def test_format_with_likes(self):
        """Run ID contains signal and like weight when like_w > 0."""
        run_id = make_run_id(14, "follow+rt+like", 0.6, 0.4, self._accounts)
        assert run_id.startswith("nmf-k14-follow+rt+like-lw0.4-")
        # Should have date and hash suffix
        parts = run_id.split("-")
        assert len(parts) >= 6

    def test_format_without_likes(self):
        """Run ID omits like weight when like_w == 0 (backwards compat)."""
        run_id = make_run_id(14, "follow+rt", 0.6, 0.0, self._accounts)
        assert run_id.startswith("nmf-k14-follow+rt-")
        assert "lw" not in run_id

    def test_different_rt_weights_different_ids(self):
        """Different RT weights produce different run IDs."""
        id1 = make_run_id(14, "follow+rt", 0.6, 0.0, self._accounts)
        id2 = make_run_id(14, "follow+rt", 0.8, 0.0, self._accounts)
        assert id1 != id2

    def test_different_k_different_ids(self):
        """Different k values produce different run IDs."""
        id1 = make_run_id(14, "follow+rt", 0.6, 0.0, self._accounts)
        id2 = make_run_id(16, "follow+rt", 0.6, 0.0, self._accounts)
        assert id1 != id2

    def test_different_accounts_different_ids(self):
        """Different account sets produce different run IDs."""
        id1 = make_run_id(14, "follow+rt", 0.6, 0.0, self._accounts)
        other_accounts = [("a1", "alice"), ("a4", "dave")]
        id2 = make_run_id(14, "follow+rt", 0.6, 0.0, other_accounts)
        assert id1 != id2
