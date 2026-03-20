"""Tests for scripts.export_public_site — public site data export pipeline.

Tests cover:
- extract_communities: SQLite community table queries
- extract_classified_accounts: community_account aggregation with weight filtering
- extract_propagated_handles: NPZ loading, abstain gate, weight filtering
- run_export: end-to-end JSON output assembly
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def community_db(tmp_path):
    """In-memory SQLite with community + community_account tables seeded."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE community (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            color TEXT,
            seeded_from_run TEXT,
            seeded_from_idx INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE community_account (
            community_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            weight REAL NOT NULL,
            source TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (community_id, account_id)
        );
    """)
    # Seed 2 communities
    conn.execute(
        "INSERT INTO community VALUES (?, ?, ?, ?, NULL, NULL, '2026-01-01', '2026-01-01')",
        ("comm-a", "Builders", "People who build things", "#9b59b6"),
    )
    conn.execute(
        "INSERT INTO community VALUES (?, ?, ?, ?, NULL, NULL, '2026-01-01', '2026-01-01')",
        ("comm-b", "Thinkers", "People who think deeply", "#e67e22"),
    )
    # Seed accounts: 3 in comm-a, 2 in comm-b, 1 shared
    conn.executemany(
        "INSERT INTO community_account VALUES (?, ?, ?, 'nmf', '2026-01-01')",
        [
            ("comm-a", "acct-1", 0.95),
            ("comm-a", "acct-2", 0.80),
            ("comm-a", "acct-3", 0.03),  # below default min_weight 0.05
            ("comm-b", "acct-2", 0.60),  # shared with comm-a
            ("comm-b", "acct-4", 0.90),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def npz_file(tmp_path):
    """Create a test NPZ with known propagation data."""
    n_nodes = 6
    n_communities = 2
    # memberships has n_communities + 1 columns (last is "none")
    memberships = np.zeros((n_nodes, n_communities + 1), dtype=np.float32)

    # Node 0: strong community 0 (0.8), not abstained
    memberships[0] = [0.8, 0.1, 0.1]
    # Node 1: strong community 1 (0.7), not abstained
    memberships[1] = [0.15, 0.7, 0.15]
    # Node 2: weak max (0.06), below abstain_threshold — should be skipped
    memberships[2] = [0.06, 0.04, 0.90]
    # Node 3: good signal, but abstain_mask=True — should be skipped
    memberships[3] = [0.5, 0.3, 0.2]
    # Node 4: classified account — should be skipped by extract_propagated_handles
    memberships[4] = [0.9, 0.05, 0.05]
    # Node 5: no username — should be skipped
    memberships[5] = [0.6, 0.3, 0.1]

    abstain_mask = np.array([False, False, False, True, False, False])
    node_ids = np.array(["node-0", "node-1", "node-2", "node-3", "acct-1", "node-5"])
    community_ids = np.array(["comm-a", "comm-b"])
    community_names = np.array(["Builders", "Thinkers"])
    community_colors = np.array(["#9b59b6", "#e67e22"])

    npz_path = tmp_path / "community_propagation.npz"
    np.savez(
        str(npz_path),
        memberships=memberships,
        abstain_mask=abstain_mask,
        node_ids=node_ids,
        community_ids=community_ids,
        community_names=community_names,
        community_colors=community_colors,
    )
    return npz_path


@pytest.fixture
def parquet_file(tmp_path):
    """Create a test parquet with account metadata."""
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({
        "node_id": ["acct-1", "acct-2", "acct-3", "acct-4", "node-0", "node-1", "node-5"],
        "username": ["alice", "bob", "charlie", "dave", "eve", "frank", None],
        "display_name": ["Alice A", "Bob B", "Charlie C", "Dave D", "Eve E", "Frank F", None],
        "num_followers": [1000.0, 500.0, float("nan"), 200.0, 50.0, 75.0, 10.0],
        "bio": ["builds stuff", "thinks deeply", None, "also thinks", "shadow eve", "shadow frank", None],
    })
    pq_path = tmp_path / "graph_snapshot.nodes.parquet"
    df.to_parquet(str(pq_path), index=False)
    return pq_path


@pytest.fixture
def config():
    return {
        "site_name": "Test Site",
        "curator": "testcurator",
        "links": {
            "curator_dm": "https://twitter.com/messages/compose?recipient_id=123",
            "community_archive": "https://github.com/community-archive",
            "repo": "https://github.com/test/repo",
        },
        "export": {
            "min_weight": 0.05,
            "abstain_threshold": 0.10,
            "output_dir": "public-site/public",
        },
    }


# ---------------------------------------------------------------------------
# Tests: extract_communities
# ---------------------------------------------------------------------------

class TestExtractCommunities:
    def test_returns_all_communities(self, community_db):
        from scripts.export_public_site import extract_communities

        result = extract_communities(community_db)
        assert len(result) == 2

    def test_community_shape(self, community_db):
        from scripts.export_public_site import extract_communities

        result = extract_communities(community_db)
        comm = next(c for c in result if c["id"] == "comm-a")
        assert comm["name"] == "Builders"
        assert comm["color"] == "#9b59b6"
        assert comm["description"] == "People who build things"
        assert "member_count" in comm

    def test_member_count_reflects_all_accounts(self, community_db):
        """member_count should count ALL community_account rows, not filtered."""
        from scripts.export_public_site import extract_communities

        result = extract_communities(community_db)
        comm_a = next(c for c in result if c["id"] == "comm-a")
        # 3 rows in community_account for comm-a (including the 0.03 weight one)
        assert comm_a["member_count"] == 3

    def test_empty_db(self, tmp_path):
        from scripts.export_public_site import extract_communities

        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE community (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
                color TEXT, seeded_from_run TEXT, seeded_from_idx INTEGER,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE community_account (
                community_id TEXT NOT NULL, account_id TEXT NOT NULL,
                weight REAL NOT NULL, source TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY (community_id, account_id)
            );
        """)
        conn.commit()
        conn.close()

        result = extract_communities(db_path)
        assert result == []


# ---------------------------------------------------------------------------
# Tests: extract_classified_accounts
# ---------------------------------------------------------------------------

class TestExtractClassifiedAccounts:
    def test_returns_distinct_accounts(self, community_db):
        from scripts.export_public_site import extract_classified_accounts

        result = extract_classified_accounts(community_db, min_weight=0.05)
        ids = [a["id"] for a in result]
        # acct-1 (0.95 in comm-a), acct-2 (0.80 in comm-a, 0.60 in comm-b),
        # acct-4 (0.90 in comm-b). acct-3 (0.03) is below min_weight.
        assert sorted(ids) == ["acct-1", "acct-2", "acct-4"]

    def test_tier_is_classified(self, community_db):
        from scripts.export_public_site import extract_classified_accounts

        result = extract_classified_accounts(community_db, min_weight=0.05)
        for acct in result:
            assert acct["tier"] == "classified"

    def test_memberships_filtered_by_weight(self, community_db):
        from scripts.export_public_site import extract_classified_accounts

        result = extract_classified_accounts(community_db, min_weight=0.05)
        acct2 = next(a for a in result if a["id"] == "acct-2")
        # acct-2 has 0.80 in comm-a and 0.60 in comm-b, both above 0.05
        assert len(acct2["memberships"]) == 2
        comm_ids = {m["community_id"] for m in acct2["memberships"]}
        assert comm_ids == {"comm-a", "comm-b"}

    def test_memberships_have_weight(self, community_db):
        from scripts.export_public_site import extract_classified_accounts

        result = extract_classified_accounts(community_db, min_weight=0.05)
        acct1 = next(a for a in result if a["id"] == "acct-1")
        assert len(acct1["memberships"]) == 1
        assert acct1["memberships"][0]["weight"] == pytest.approx(0.95, abs=0.01)

    def test_higher_min_weight_filters_more(self, community_db):
        from scripts.export_public_site import extract_classified_accounts

        result = extract_classified_accounts(community_db, min_weight=0.85)
        ids = [a["id"] for a in result]
        # Only acct-1 (0.95) and acct-4 (0.90) survive
        assert sorted(ids) == ["acct-1", "acct-4"]

    def test_account_with_all_memberships_below_threshold_excluded(self, community_db):
        """acct-3 only has weight 0.03, below 0.05 — should be excluded."""
        from scripts.export_public_site import extract_classified_accounts

        result = extract_classified_accounts(community_db, min_weight=0.05)
        ids = [a["id"] for a in result]
        assert "acct-3" not in ids


# ---------------------------------------------------------------------------
# Tests: extract_propagated_handles
# ---------------------------------------------------------------------------

class TestExtractPropagatedHandles:
    def _make_username_map(self):
        return {
            "node-0": "eve",
            "node-1": "frank",
            "node-2": "ghost",
            "node-3": "harry",
            "acct-1": "alice",
            "node-5": None,  # no username
        }

    def test_basic_extraction(self, npz_file):
        from scripts.export_public_site import extract_propagated_handles

        classified_ids = {"acct-1"}
        username_map = self._make_username_map()

        result = extract_propagated_handles(
            npz_path=npz_file,
            node_id_to_username=username_map,
            classified_ids=classified_ids,
            min_weight=0.05,
            abstain_threshold=0.10,
        )
        # node-0 ("eve"): passes all gates, strong signal
        assert "eve" in result
        # node-1 ("frank"): passes all gates
        assert "frank" in result

    def test_abstain_mask_skips_node(self, npz_file):
        from scripts.export_public_site import extract_propagated_handles

        classified_ids = set()
        username_map = self._make_username_map()

        result = extract_propagated_handles(
            npz_file, username_map, classified_ids, 0.05, 0.10,
        )
        # node-3 has abstain_mask=True
        assert "harry" not in result

    def test_low_max_weight_skips_node(self, npz_file):
        from scripts.export_public_site import extract_propagated_handles

        classified_ids = set()
        username_map = self._make_username_map()

        result = extract_propagated_handles(
            npz_file, username_map, classified_ids, 0.05, 0.10,
        )
        # node-2 max community weight is 0.06, below threshold 0.10
        assert "ghost" not in result

    def test_classified_accounts_excluded(self, npz_file):
        from scripts.export_public_site import extract_propagated_handles

        classified_ids = {"acct-1"}
        username_map = self._make_username_map()

        result = extract_propagated_handles(
            npz_file, username_map, classified_ids, 0.05, 0.10,
        )
        assert "alice" not in result

    def test_no_username_skipped(self, npz_file):
        from scripts.export_public_site import extract_propagated_handles

        classified_ids = set()
        username_map = self._make_username_map()

        result = extract_propagated_handles(
            npz_file, username_map, classified_ids, 0.05, 0.10,
        )
        # node-5 has no username (None)
        assert None not in result

    def test_individual_memberships_filtered(self, npz_file):
        from scripts.export_public_site import extract_propagated_handles

        classified_ids = set()
        username_map = self._make_username_map()

        result = extract_propagated_handles(
            npz_file, username_map, classified_ids, 0.05, 0.10,
        )
        # node-1 ("frank"): comm-a=0.15 (above 0.05), comm-b=0.7 (above 0.05)
        frank = result["frank"]
        assert len(frank["memberships"]) == 2

    def test_handles_are_lowercase(self, npz_file, tmp_path):
        """Handles in search output must be lowercase."""
        from scripts.export_public_site import extract_propagated_handles

        classified_ids = set()
        username_map = {"node-0": "EVE_UPPER"}

        result = extract_propagated_handles(
            npz_file, username_map, classified_ids, 0.05, 0.10,
        )
        assert "eve_upper" in result
        assert "EVE_UPPER" not in result

    def test_skips_nan_and_empty_usernames(self, npz_file):
        from scripts.export_public_site import extract_propagated_handles

        classified_ids = set()
        username_map = {
            "node-0": "nan",
            "node-1": "",
            "node-2": "None",
        }

        result = extract_propagated_handles(
            npz_file, username_map, classified_ids, 0.05, 0.10,
        )
        assert "nan" not in result
        assert "" not in result
        assert "none" not in result


# ---------------------------------------------------------------------------
# Tests: get_sample_tweets
# ---------------------------------------------------------------------------

class TestSampleTweets:
    """Tests for get_sample_tweets — top-N tweets by engagement."""

    def _create_db_with_tweets(self, db_path):
        """Create a test DB with a tweets table seeded with sample data."""
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE tweets (
                tweet_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                username TEXT NOT NULL,
                full_text TEXT NOT NULL,
                favorite_count INTEGER DEFAULT 0,
                retweet_count INTEGER DEFAULT 0
            );
            INSERT INTO tweets VALUES ('t1', 'acct1', 'alice', 'Top tweet by alice', 100, 20);
            INSERT INTO tweets VALUES ('t2', 'acct1', 'alice', 'Second best', 50, 10);
            INSERT INTO tweets VALUES ('t3', 'acct1', 'alice', 'Third tweet', 30, 5);
            INSERT INTO tweets VALUES ('t4', 'acct1', 'alice', 'Fourth tweet low engagement', 1, 0);
            INSERT INTO tweets VALUES ('t5', 'acct2', 'bob', 'Bob only tweet', 10, 2);
        """)
        conn.commit()
        conn.close()

    def test_returns_top_3_tweets_by_engagement(self, tmp_path):
        db_path = tmp_path / "archive_tweets.db"
        self._create_db_with_tweets(db_path)

        from scripts.export_public_site import get_sample_tweets

        tweets = get_sample_tweets(db_path, "acct1", limit=3)

        assert len(tweets) == 3
        assert tweets[0] == "Top tweet by alice"    # 100+20 = 120
        assert tweets[1] == "Second best"           # 50+10 = 60
        assert tweets[2] == "Third tweet"           # 30+5 = 35

    def test_returns_empty_for_unknown_account(self, tmp_path):
        db_path = tmp_path / "archive_tweets.db"
        self._create_db_with_tweets(db_path)

        from scripts.export_public_site import get_sample_tweets

        tweets = get_sample_tweets(db_path, "nonexistent")
        assert tweets == []

    def test_truncates_to_280_chars(self, tmp_path):
        db_path = tmp_path / "archive_tweets.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE tweets (
                tweet_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                username TEXT NOT NULL,
                full_text TEXT NOT NULL,
                favorite_count INTEGER DEFAULT 0,
                retweet_count INTEGER DEFAULT 0
            );
        """)
        long_text = "A" * 500
        conn.execute(
            "INSERT INTO tweets VALUES (?, ?, ?, ?, ?, ?)",
            ("t-long", "acct-long", "verbose", long_text, 999, 999),
        )
        conn.commit()
        conn.close()

        from scripts.export_public_site import get_sample_tweets

        tweets = get_sample_tweets(db_path, "acct-long")
        assert len(tweets) == 1
        assert len(tweets[0]) == 280
        assert tweets[0] == "A" * 280

    def test_respects_limit_parameter(self, tmp_path):
        db_path = tmp_path / "archive_tweets.db"
        self._create_db_with_tweets(db_path)

        from scripts.export_public_site import get_sample_tweets

        tweets = get_sample_tweets(db_path, "acct1", limit=1)
        assert len(tweets) == 1
        assert tweets[0] == "Top tweet by alice"

    def test_returns_empty_when_no_tweets_table(self, tmp_path):
        """Gracefully handles DB without a tweets table."""
        db_path = tmp_path / "no_tweets.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dummy (id TEXT PRIMARY KEY)")
        conn.commit()
        conn.close()

        from scripts.export_public_site import get_sample_tweets

        tweets = get_sample_tweets(db_path, "acct1")
        assert tweets == []


# ---------------------------------------------------------------------------
# Tests: run_export
# ---------------------------------------------------------------------------

class TestRunExport:
    def test_produces_data_json(self, community_db, npz_file, parquet_file, tmp_path, config):
        from scripts.export_public_site import run_export

        output_dir = tmp_path / "output"
        run_export(
            data_dir=tmp_path,
            output_dir=output_dir,
            config=config,
            db_path=community_db,
        )
        data_path = output_dir / "data.json"
        assert data_path.exists()
        data = json.loads(data_path.read_text())
        assert "communities" in data
        assert "accounts" in data
        assert "meta" in data

    def test_produces_search_json(self, community_db, npz_file, parquet_file, tmp_path, config):
        from scripts.export_public_site import run_export

        output_dir = tmp_path / "output"
        run_export(
            data_dir=tmp_path,
            output_dir=output_dir,
            config=config,
            db_path=community_db,
        )
        search_path = output_dir / "search.json"
        assert search_path.exists()
        search = json.loads(search_path.read_text())
        # Should contain classified accounts that have usernames
        assert isinstance(search, dict)

    def test_classified_accounts_enriched_with_metadata(
        self, community_db, npz_file, parquet_file, tmp_path, config,
    ):
        from scripts.export_public_site import run_export

        output_dir = tmp_path / "output"
        run_export(
            data_dir=tmp_path,
            output_dir=output_dir,
            config=config,
            db_path=community_db,
        )
        data = json.loads((output_dir / "data.json").read_text())
        acct1 = next(a for a in data["accounts"] if a["id"] == "acct-1")
        assert acct1["username"] == "alice"
        assert acct1["display_name"] == "Alice A"
        assert acct1["bio"] == "builds stuff"
        assert acct1["followers"] == 1000

    def test_nan_followers_becomes_none(
        self, community_db, npz_file, parquet_file, tmp_path, config,
    ):
        from scripts.export_public_site import run_export

        output_dir = tmp_path / "output"
        run_export(
            data_dir=tmp_path,
            output_dir=output_dir,
            config=config,
            db_path=community_db,
        )
        data = json.loads((output_dir / "data.json").read_text())
        # acct-3 has NaN followers but won't be in output because weight < 0.05
        # acct-2 ("bob") has 500 followers — check it
        acct2 = next(a for a in data["accounts"] if a["id"] == "acct-2")
        assert acct2["followers"] == 500

    def test_meta_contains_links(
        self, community_db, npz_file, parquet_file, tmp_path, config,
    ):
        from scripts.export_public_site import run_export

        output_dir = tmp_path / "output"
        run_export(
            data_dir=tmp_path,
            output_dir=output_dir,
            config=config,
            db_path=community_db,
        )
        data = json.loads((output_dir / "data.json").read_text())
        assert data["meta"]["site_name"] == "Test Site"
        assert data["meta"]["links"]["repo"] == "https://github.com/test/repo"

    def test_search_index_has_lowercase_handles(
        self, community_db, npz_file, parquet_file, tmp_path, config,
    ):
        from scripts.export_public_site import run_export

        output_dir = tmp_path / "output"
        run_export(
            data_dir=tmp_path,
            output_dir=output_dir,
            config=config,
            db_path=community_db,
        )
        search = json.loads((output_dir / "search.json").read_text())
        for handle in search.keys():
            assert handle == handle.lower(), f"Handle '{handle}' is not lowercase"

    def test_works_without_npz(self, community_db, parquet_file, tmp_path, config):
        """When NPZ doesn't exist, export classified only (no propagated)."""
        from scripts.export_public_site import run_export

        output_dir = tmp_path / "output"
        run_export(
            data_dir=tmp_path,
            output_dir=output_dir,
            config=config,
            db_path=community_db,
        )
        data = json.loads((output_dir / "data.json").read_text())
        # Should still have communities and classified accounts
        assert len(data["communities"]) == 2
        assert len(data["accounts"]) > 0
        # Search should only have classified handles
        search = json.loads((output_dir / "search.json").read_text())
        assert isinstance(search, dict)

    def test_search_includes_propagated_handles(
        self, community_db, npz_file, parquet_file, tmp_path, config,
    ):
        from scripts.export_public_site import run_export

        output_dir = tmp_path / "output"
        run_export(
            data_dir=tmp_path,
            output_dir=output_dir,
            config=config,
            db_path=community_db,
        )
        search = json.loads((output_dir / "search.json").read_text())
        # "eve" is node-0, propagated handle
        assert "eve" in search
        # "alice" is classified (acct-1)
        assert "alice" in search

    def test_propagated_entry_shape(
        self, community_db, npz_file, parquet_file, tmp_path, config,
    ):
        from scripts.export_public_site import run_export

        output_dir = tmp_path / "output"
        run_export(
            data_dir=tmp_path,
            output_dir=output_dir,
            config=config,
            db_path=community_db,
        )
        search = json.loads((output_dir / "search.json").read_text())
        eve = search.get("eve")
        assert eve is not None
        assert eve["tier"] == "propagated"
        assert "memberships" in eve
        assert len(eve["memberships"]) > 0

    def test_classified_search_entry_shape(
        self, community_db, npz_file, parquet_file, tmp_path, config,
    ):
        from scripts.export_public_site import run_export

        output_dir = tmp_path / "output"
        run_export(
            data_dir=tmp_path,
            output_dir=output_dir,
            config=config,
            db_path=community_db,
        )
        search = json.loads((output_dir / "search.json").read_text())
        alice = search.get("alice")
        assert alice is not None
        assert alice["tier"] == "classified"
        assert "memberships" in alice
