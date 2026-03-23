"""Tests for likes-enriched NMF pipeline in scripts/cluster_soft.py.

Covers:
  - build_likes_matrix() — sparse matrix from account_engagement_agg
  - make_run_id()        — deterministic hashing of run-shaping params
  - _save_run()          — Layer 1 persistence (community_run, community_membership,
                           community_definition)
"""

import sqlite3
import types

import numpy as np
import pytest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from cluster_soft import build_likes_matrix, make_run_id, _save_run
from communities.store import (
    init_db,
    save_run,
    save_memberships,
    save_definitions,
    list_runs,
    get_memberships,
    get_definitions,
)


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


# ── Fixtures ─────────────────────────────────────────────────────────────────

FIVE_ACCOUNTS = [
    ("a1", "alice"),
    ("a2", "bob"),
    ("a3", "carol"),
    ("a4", "dave"),
    ("a5", "eve"),
]

TEN_ENGAGEMENT_ROWS = [
    # (source_id, target_id, like_count)
    ("a1", "t1", 10),
    ("a1", "t2", 5),
    ("a2", "t1", 3),
    ("a2", "t3", 7),
    ("a3", "t2", 12),
    ("a3", "t4", 1),
    ("a4", "t1", 8),
    ("a4", "t3", 0),   # zero likes — should be excluded by default min_count=1
    ("a5", "t4", 6),
    ("a5", "t2", 2),
]


# ── TestBuildLikesMatrix ─────────────────────────────────────────────────────

class TestBuildLikesMatrix:
    """Tests for build_likes_matrix() — sparse matrix from account_engagement_agg."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Shared DB with 5 accounts, 10 engagement rows."""
        self.accounts = FIVE_ACCOUNTS
        self.con = _make_engagement_db(TEN_ENGAGEMENT_ROWS)
        yield
        self.con.close()

    def test_shape_matches_accounts(self):
        """Returned matrix has n_rows == len(accounts)."""
        mat, targets = build_likes_matrix(self.con, self.accounts)
        assert mat.shape[0] == len(self.accounts)

    def test_values_are_like_counts(self):
        """Specific cells have expected like_count values."""
        mat, targets = build_likes_matrix(self.con, self.accounts)
        dense = mat.toarray()

        # targets are sorted: t1, t2, t3, t4
        t1_col = targets.index("t1")
        t2_col = targets.index("t2")
        t3_col = targets.index("t3")

        # a1 (row 0) -> t1 = 10, t2 = 5
        assert dense[0, t1_col] == pytest.approx(10.0)
        assert dense[0, t2_col] == pytest.approx(5.0)
        # a2 (row 1) -> t1 = 3, t3 = 7
        assert dense[1, t1_col] == pytest.approx(3.0)
        assert dense[1, t3_col] == pytest.approx(7.0)
        # a3 (row 2) -> t2 = 12
        assert dense[2, t2_col] == pytest.approx(12.0)

    def test_missing_table_returns_empty(self):
        """If account_engagement_agg doesn't exist, returns (n, 0) matrix."""
        con = sqlite3.connect(":memory:")  # no tables at all
        mat, targets = build_likes_matrix(con, self.accounts)
        assert mat.shape == (len(self.accounts), 0)
        assert targets == []
        con.close()

    def test_zero_likes_excluded(self):
        """Engagement rows with like_count=0 don't appear in the matrix.

        Row ("a4", "t3", 0) should be excluded by the default min_count=1 filter.
        """
        mat, targets = build_likes_matrix(self.con, self.accounts)
        dense = mat.toarray()

        # a4 is row index 3
        a4_row = dense[3, :]
        # a4 -> t1=8 should be present, but a4 -> t3=0 should be absent
        if "t3" in targets:
            t3_col = targets.index("t3")
            # a4's value for t3 should be 0.0 (filtered out by min_count)
            assert a4_row[t3_col] == pytest.approx(0.0)
        # a4 -> t1=8 should still be present
        t1_col = targets.index("t1")
        assert a4_row[t1_col] == pytest.approx(8.0)

    def test_accounts_filter(self):
        """Only accounts in the input list appear as rows."""
        # Use only 2 of the 5 accounts
        subset = [("a1", "alice"), ("a3", "carol")]
        mat, targets = build_likes_matrix(self.con, subset)
        assert mat.shape[0] == 2

        dense = mat.toarray()
        # a1 -> t1 = 10 (row 0)
        t1_col = targets.index("t1")
        assert dense[0, t1_col] == pytest.approx(10.0)
        # a3 -> t2 = 12 (row 1)
        t2_col = targets.index("t2")
        assert dense[1, t2_col] == pytest.approx(12.0)

        # Engagement from a2, a4, a5 should NOT produce rows
        # (they're not in the accounts list, so they're not in account_idx)
        # Verify no stray data from other accounts leaked in
        # a2 -> t3=7 — if t3 is a target column, both rows should be 0 for t3
        if "t3" in targets:
            t3_col = targets.index("t3")
            assert dense[0, t3_col] == pytest.approx(0.0)
            assert dense[1, t3_col] == pytest.approx(0.0)


# ── TestMakeRunId ────────────────────────────────────────────────────────────

class TestMakeRunId:
    """Tests for make_run_id() — deterministic hashing of run-shaping params."""

    _accounts = [("a1", "alice"), ("a2", "bob"), ("a3", "carol")]

    def test_changes_with_k(self):
        """Different k values produce different run_ids."""
        id1 = make_run_id(14, "follow+rt", 0.6, 0.0, self._accounts)
        id2 = make_run_id(16, "follow+rt", 0.6, 0.0, self._accounts)
        assert id1 != id2

    def test_changes_with_signal(self):
        """'follow+rt' vs 'follow+rt+like' produce different run_ids."""
        id1 = make_run_id(14, "follow+rt", 0.6, 0.0, self._accounts)
        id2 = make_run_id(14, "follow+rt+like", 0.6, 0.4, self._accounts)
        assert id1 != id2

    def test_changes_with_rt_weight(self):
        """Different rt_weight produces different run_ids."""
        id1 = make_run_id(14, "follow+rt", 0.6, 0.0, self._accounts)
        id2 = make_run_id(14, "follow+rt", 0.8, 0.0, self._accounts)
        assert id1 != id2

    def test_changes_with_likes_weight(self):
        """Different likes_weight produces different run_ids."""
        id1 = make_run_id(14, "follow+rt+like", 0.6, 0.4, self._accounts)
        id2 = make_run_id(14, "follow+rt+like", 0.6, 0.8, self._accounts)
        assert id1 != id2

    def test_deterministic(self):
        """Same inputs produce same run_id."""
        id1 = make_run_id(14, "follow+rt+like", 0.6, 0.4, self._accounts)
        id2 = make_run_id(14, "follow+rt+like", 0.6, 0.4, self._accounts)
        assert id1 == id2


# ── TestSaveRun (integration) ───────────────────────────────────────────────

class TestSaveRun:
    """Integration tests for _save_run() — persists NMF results to Layer 1.

    Uses a tiny synthetic NMF result (3 accounts, 2 communities) to verify
    that community_run, community_membership, and community_definition tables
    are populated correctly.
    """

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        """Build temp DB with Layer 1 schema, then call the REAL _save_run()."""
        import cluster_soft

        self.db_path = tmp_path / "test_save.db"
        self.con = sqlite3.connect(str(self.db_path))
        self.con.execute("PRAGMA foreign_keys = ON")
        init_db(self.con)
        self.con.close()

        # Monkeypatch ARCHIVE_DB so _save_run writes to our test DB
        monkeypatch.setattr(cluster_soft, "ARCHIVE_DB", self.db_path)

        # 3 accounts, 2 communities
        self.accounts = [("a1", "alice"), ("a2", "bob"), ("a3", "carol")]

        # Synthetic W_norm: rows=accounts, cols=communities
        self.W_norm = np.array([
            [0.80, 0.20],
            [0.45, 0.55],
            [0.10, 0.90],
        ])

        # Synthetic H: rows=communities, cols=features
        # Layout: [follow_features | rt_features | like_features]
        self.nf = 3
        self.nr = 2
        self.H = np.array([
            [0.9, 0.1, 0.0,  0.8, 0.1,  0.7, 0.05],
            [0.1, 0.8, 0.2,  0.1, 0.9,  0.1, 0.6],
        ])

        self.targets_f = ["tf0", "tf1", "tf2"]
        self.targets_r = ["tr0", "tr1"]
        self.targets_l = ["tl0", "tl1"]
        self.signal = "follow+rt+like"

        # Build args namespace matching what _save_run expects
        self.args = types.SimpleNamespace(
            k=2,
            likes=True,
            likes_weight=0.4,
            rt_weight=0.6,
            threshold=0.1,
            notes="test-run",
            save=True,
        )

        # Compute expected run_id (same logic as production)
        like_w = self.args.likes_weight if self.args.likes else 0.0
        self.run_id = make_run_id(
            k=self.args.k, signal=self.signal,
            rt_w=self.args.rt_weight, like_w=like_w,
            accounts=self.accounts,
        )

        # Call the REAL _save_run — not a reimplementation
        _save_run(
            self.con,  # unused by real _save_run (opens its own via ARCHIVE_DB)
            self.args, self.accounts, self.W_norm, self.H,
            self.targets_f, self.targets_r, self.targets_l,
            self.nf, self.nr, self.signal,
        )

        # Open connection for assertions
        self.con = sqlite3.connect(str(self.db_path))
        yield
        self.con.close()

    # ── Tests ─────────────────────────────────────────────────────────────

    def test_creates_community_run_row(self):
        """community_run has exactly 1 row with correct k, signal, account_count."""
        rows = self.con.execute("SELECT * FROM community_run").fetchall()
        assert len(rows) == 1

        run = rows[0]
        # Schema: run_id, k, signal, threshold, account_count, notes, created_at
        assert run[0] == self.run_id
        assert run[1] == 2         # k
        assert run[2] == "follow+rt+like"  # signal
        assert run[4] == 3         # account_count

    def test_preserves_older_runs(self):
        """Save two runs with different run_ids; both exist in community_run."""
        # Save a second run with different params
        second_run_id = make_run_id(
            k=4, signal="follow+rt", rt_w=0.6, like_w=0.0,
            accounts=self.accounts,
        )
        save_run(
            self.con, second_run_id,
            k=4, signal="follow+rt", threshold=0.1,
            account_count=len(self.accounts), notes="second",
        )

        rows = self.con.execute("SELECT run_id FROM community_run").fetchall()
        run_ids = {r[0] for r in rows}
        assert self.run_id in run_ids
        assert second_run_id in run_ids
        assert len(run_ids) == 2

    def test_stores_signal_type(self):
        """For a likes run, signal column is 'follow+rt+like'."""
        row = self.con.execute(
            "SELECT signal FROM community_run WHERE run_id = ?",
            (self.run_id,),
        ).fetchone()
        assert row[0] == "follow+rt+like"

    def test_persists_feature_type_like(self):
        """community_definition rows include feature_type='like' entries."""
        like_rows = self.con.execute(
            "SELECT community_idx, feature_type, target, score, rank "
            "FROM community_definition WHERE run_id = ? AND feature_type = 'like'",
            (self.run_id,),
        ).fetchall()
        assert len(like_rows) > 0

        # Verify targets are from our like target list
        like_targets = {r[2] for r in like_rows}
        assert like_targets <= set(self.targets_l)

        # Verify all three feature types are present
        all_types = {
            r[0]
            for r in self.con.execute(
                "SELECT DISTINCT feature_type FROM community_definition WHERE run_id = ?",
                (self.run_id,),
            ).fetchall()
        }
        assert all_types == {"follow", "rt", "like"}

    def test_membership_weights_stored(self):
        """community_membership has correct weights for all accounts."""
        rows = self.con.execute(
            "SELECT account_id, community_idx, weight "
            "FROM community_membership WHERE run_id = ? "
            "ORDER BY account_id, community_idx",
            (self.run_id,),
        ).fetchall()

        # Build lookup: (account_id, community_idx) -> weight
        stored = {(r[0], r[1]): r[2] for r in rows}

        # All 3 accounts x 2 communities, but only weights >= 0.05 stored
        for i, (aid, _) in enumerate(self.accounts):
            for c in range(self.args.k):
                expected = float(self.W_norm[i, c])
                if expected >= 0.05:
                    assert (aid, c) in stored, f"Missing ({aid}, {c})"
                    assert stored[(aid, c)] == pytest.approx(expected, abs=1e-6)
                else:
                    assert (aid, c) not in stored, f"Unexpected ({aid}, {c}) with w={expected}"

        # Verify total count: all values in W_norm >= 0.05 (they are: 0.80, 0.20,
        # 0.45, 0.55, 0.10, 0.90 — all >= 0.05), so 6 rows expected
        assert len(rows) == 6
