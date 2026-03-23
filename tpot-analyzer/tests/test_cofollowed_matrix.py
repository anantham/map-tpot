"""Tests for scripts.build_cofollowed_matrix."""
from __future__ import annotations

import sqlite3

import pytest

from scripts.build_cofollowed_matrix import (
    build_follower_sets,
    compute_cofollowed_pairs,
    load_community_assignments,
    load_seed_accounts,
    save_pairs,
)


@pytest.fixture
def mem_db():
    """In-memory DB with test data."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE profiles (account_id TEXT PRIMARY KEY, username TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE account_following "
        "(account_id TEXT NOT NULL, following_account_id TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE community "
        "(id TEXT PRIMARY KEY, name TEXT NOT NULL, short_name TEXT, "
        "created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT '')"
    )
    conn.execute(
        "CREATE TABLE community_account "
        "(community_id TEXT NOT NULL, account_id TEXT NOT NULL, "
        "weight REAL NOT NULL, source TEXT NOT NULL, updated_at TEXT NOT NULL, "
        "PRIMARY KEY (community_id, account_id))"
    )

    # 5 seed accounts: A, B, C, D, E
    for aid, name in [("A", "alice"), ("B", "bob"), ("C", "carol"),
                       ("D", "dave"), ("E", "eve")]:
        conn.execute("INSERT INTO profiles VALUES (?, ?)", (aid, name))

    # Follow edges (all seed-to-seed):
    # A follows B, C, D
    # B follows C, D
    # C follows B, D
    # D follows B
    # E follows D
    edges = [
        ("A", "B"), ("A", "C"), ("A", "D"),
        ("B", "C"), ("B", "D"),
        ("C", "B"), ("C", "D"),
        ("D", "B"),
        ("E", "D"),
    ]
    conn.executemany(
        "INSERT INTO account_following VALUES (?, ?)", edges
    )

    # Communities
    conn.execute(
        "INSERT INTO community (id, name, short_name) VALUES "
        "('c1', 'Group Alpha', 'alpha'), ('c2', 'Group Beta', 'beta')"
    )
    # A, B, C in alpha; D, E in beta
    for aid, cid in [("A", "c1"), ("B", "c1"), ("C", "c1"),
                      ("D", "c2"), ("E", "c2")]:
        conn.execute(
            "INSERT INTO community_account VALUES (?, ?, 1.0, 'nmf', '')",
            (cid, aid),
        )

    yield conn
    conn.close()


class TestLoadSeedAccounts:
    def test_returns_all_profiles(self, mem_db):
        seeds = load_seed_accounts(mem_db)
        assert seeds == {"A", "B", "C", "D", "E"}


class TestBuildFollowerSets:
    def test_basic_follower_sets(self, mem_db):
        edges = [("A", "B"), ("A", "C"), ("B", "C"), ("C", "B"), ("X", "B")]
        seeds = {"A", "B", "C"}

        fs = build_follower_sets(edges, seeds)

        # B is followed by A, C (X excluded, not a seed)
        assert fs["B"] == {"A", "C"}
        # C is followed by A, B
        assert fs["C"] == {"A", "B"}
        # A has no seed followers in these edges
        assert "A" not in fs

    def test_non_seed_targets_excluded(self, mem_db):
        edges = [("A", "Z")]  # Z is not a seed
        seeds = {"A", "B"}
        fs = build_follower_sets(edges, seeds)
        assert "Z" not in fs


class TestComputeCofollowedPairs:
    def test_perfect_overlap(self):
        # B and C have identical follower sets
        fs = {"B": {"A", "D"}, "C": {"A", "D"}}
        pairs = compute_cofollowed_pairs(fs, min_jaccard=0.0)
        assert len(pairs) == 1
        a, b, shared, jac = pairs[0]
        assert shared == 2
        assert jac == pytest.approx(1.0)

    def test_no_overlap(self):
        fs = {"B": {"A"}, "C": {"D"}}
        pairs = compute_cofollowed_pairs(fs, min_jaccard=0.0)
        assert len(pairs) == 0  # shared = 0 → skipped

    def test_partial_overlap_jaccard(self):
        # B followers: {A, D}, C followers: {A, E}
        # shared=1 (A), union=3 (A,D,E), jaccard = 1/3
        fs = {"B": {"A", "D"}, "C": {"A", "E"}}
        pairs = compute_cofollowed_pairs(fs, min_jaccard=0.0)
        assert len(pairs) == 1
        _, _, shared, jac = pairs[0]
        assert shared == 1
        assert jac == pytest.approx(1.0 / 3.0)

    def test_min_jaccard_filter(self):
        fs = {"B": {"A", "D"}, "C": {"A", "E"}}
        # jaccard = 0.333, threshold 0.5 → no pairs
        pairs = compute_cofollowed_pairs(fs, min_jaccard=0.5)
        assert len(pairs) == 0

    def test_upper_triangle_only(self):
        """Only stores (a, b) where a < b lexicographically."""
        fs = {"Z": {"A"}, "A": {"A"}}  # both have follower A
        pairs = compute_cofollowed_pairs(fs, min_jaccard=0.0)
        assert len(pairs) == 1
        a, b, _, _ = pairs[0]
        assert a < b  # upper triangle


class TestSavePairs:
    def test_dry_run_no_table(self, mem_db):
        """Dry run should not create the table."""
        save_pairs(mem_db, [("A", "B", 5, 0.5)], dry_run=True)
        cur = mem_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='cofollowed_similarity'"
        )
        assert cur.fetchone() is None

    def test_writes_pairs(self, mem_db):
        pairs = [("A", "B", 5, 0.5), ("C", "D", 3, 0.25)]
        save_pairs(mem_db, pairs, dry_run=False)
        cur = mem_db.execute(
            "SELECT account_a, account_b, shared_followers, jaccard "
            "FROM cofollowed_similarity ORDER BY account_a"
        )
        rows = cur.fetchall()
        assert len(rows) == 2
        assert rows[0] == ("A", "B", 5, 0.5)
        assert rows[1] == ("C", "D", 3, 0.25)

    def test_overwrites_on_rerun(self, mem_db):
        """Running twice should replace, not append."""
        pairs1 = [("A", "B", 5, 0.5)]
        save_pairs(mem_db, pairs1, dry_run=False)
        pairs2 = [("C", "D", 3, 0.25)]
        save_pairs(mem_db, pairs2, dry_run=False)
        cur = mem_db.execute("SELECT COUNT(*) FROM cofollowed_similarity")
        assert cur.fetchone()[0] == 1  # only second batch


class TestLoadCommunityAssignments:
    def test_primary_assignment(self, mem_db):
        assignments = load_community_assignments(mem_db)
        assert assignments["A"] == "alpha"
        assert assignments["D"] == "beta"
        assert len(assignments) == 5

    def test_max_weight_wins(self, mem_db):
        """When account has multiple communities, highest weight wins."""
        mem_db.execute(
            "INSERT INTO community_account VALUES ('c2', 'A', 2.0, 'nmf', '')"
        )
        assignments = load_community_assignments(mem_db)
        assert assignments["A"] == "beta"  # weight 2.0 > 1.0


class TestIntegration:
    def test_full_pipeline(self, mem_db):
        """End-to-end: load edges, build sets, compute pairs, save."""
        seeds = load_seed_accounts(mem_db)
        edges = mem_db.execute(
            "SELECT account_id, following_account_id FROM account_following"
        ).fetchall()
        fs = build_follower_sets(edges, seeds)

        # B is followed by: A, C, D
        assert fs["B"] == {"A", "C", "D"}
        # C is followed by: A, B
        assert fs["C"] == {"A", "B"}
        # D is followed by: A, B, C, E
        assert fs["D"] == {"A", "B", "C", "E"}

        pairs = compute_cofollowed_pairs(fs, min_jaccard=0.0)
        assert len(pairs) > 0

        # B and D share followers {A}? No: B followers={A,C,D}, D followers={A,B,C,E}
        # B∩D = {A, C}, |B∪D| = {A,C,D,B,E} = 5, jaccard = 2/5 = 0.4
        bd_pair = [p for p in pairs if set(p[:2]) == {"B", "D"}]
        assert len(bd_pair) == 1
        _, _, shared, jac = bd_pair[0]
        assert shared == 2
        assert jac == pytest.approx(0.4)

        # Save and verify
        save_pairs(mem_db, pairs, dry_run=False)
        cur = mem_db.execute("SELECT COUNT(*) FROM cofollowed_similarity")
        assert cur.fetchone()[0] == len(pairs)
