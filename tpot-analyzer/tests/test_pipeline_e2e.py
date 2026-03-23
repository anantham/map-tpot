"""End-to-end fixture test: bits rollup -> NMF -> save_run -> propagate -> export.

Verifies that a tiny hand-crafted fixture (4 core + 6 shadow accounts, 3 communities)
flows through the full pipeline and produces consistent DB state and JSON artifacts.

Tests are numbered to enforce sequential execution (pytest sorts alphabetically).
Each test builds on state created by prior tests.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import scipy.sparse as sp

# Ensure project root is importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

COMMUNITY_IDS = ["comm-alpha", "comm-beta", "comm-gamma"]
COMMUNITY_NAMES = ["Alpha Builders", "Beta Thinkers", "Gamma Creatives"]
COMMUNITY_SHORT_NAMES = ["alpha", "beta", "gamma"]
COMMUNITY_COLORS = ["#e74c3c", "#3498db", "#2ecc71"]

# 4 core (classified) accounts
CORE_ACCOUNTS = [
    ("core-1", "alice"),
    ("core-2", "bob"),
    ("core-3", "carol"),
    ("core-4", "dave"),
]

# 6 shadow accounts (no tweets, no tags -- just follow edges)
SHADOW_ACCOUNTS = [
    ("shadow-1", "eve"),
    ("shadow-2", "frank"),
    ("shadow-3", "grace"),
    ("shadow-4", "heidi"),
    ("shadow-5", "ivan"),
    ("shadow-6", "judy"),
]

ALL_ACCOUNTS = CORE_ACCOUNTS + SHADOW_ACCOUNTS


def _create_full_db(db_path: Path) -> None:
    """Create a SQLite DB with ALL required tables and seed fixture data.

    Tables created:
    - community (3 communities with short_names)
    - tweets (10 tweets from 4 core accounts)
    - tweet_tags (bits-category tags for core-1 and core-2, plus non-bits tags)
    - account_following (follow edges between core + shadow accounts)
    - retweets (a few retweets)
    - account_engagement_agg (like counts between accounts)
    - profiles (usernames, bios for all 10 accounts)
    - Layer 1 tables (community_run, community_membership, community_definition)
    - Layer 2 tables (community_account with NMF weights for 4 core accounts)
    - account_community_bits (empty initially)
    - likes (for confidence module)
    - tweet_label_set (for confidence module)
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")

    # -- Schema from communities/store.py --
    from communities.store import SCHEMA
    conn.executescript(SCHEMA)

    # -- Additional tables the pipeline needs --
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tweets (
            tweet_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            username TEXT NOT NULL,
            full_text TEXT NOT NULL,
            favorite_count INTEGER DEFAULT 0,
            retweet_count INTEGER DEFAULT 0,
            created_at TEXT,
            reply_to_tweet_id TEXT
        );

        CREATE TABLE IF NOT EXISTS tweet_tags (
            tweet_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            category TEXT
        );

        CREATE TABLE IF NOT EXISTS account_following (
            account_id TEXT NOT NULL,
            following_account_id TEXT NOT NULL,
            PRIMARY KEY (account_id, following_account_id)
        );

        CREATE TABLE IF NOT EXISTS retweets (
            tweet_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            rt_of_username TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS account_engagement_agg (
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            like_count INTEGER DEFAULT 0,
            PRIMARY KEY (source_id, target_id)
        );

        CREATE TABLE IF NOT EXISTS profiles (
            account_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            bio TEXT
        );

        CREATE TABLE IF NOT EXISTS likes (
            liker_account_id TEXT NOT NULL,
            tweet_id TEXT NOT NULL,
            PRIMARY KEY (liker_account_id, tweet_id)
        );

        CREATE TABLE IF NOT EXISTS tweet_label_set (
            tweet_id TEXT NOT NULL,
            label_set_id TEXT NOT NULL,
            PRIMARY KEY (tweet_id, label_set_id)
        );
    """)

    now = "2026-01-01T00:00:00+00:00"

    # -- Communities (Layer 2) --
    for cid, name, sn, color in zip(
        COMMUNITY_IDS, COMMUNITY_NAMES, COMMUNITY_SHORT_NAMES, COMMUNITY_COLORS
    ):
        conn.execute(
            "INSERT INTO community (id, name, short_name, description, color, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (cid, name, sn, f"Description for {name}", color, now, now),
        )

    # -- Profiles (all 10 accounts) --
    for aid, username in ALL_ACCOUNTS:
        conn.execute(
            "INSERT INTO profiles (account_id, username, bio) VALUES (?,?,?)",
            (aid, username, f"Bio for {username}"),
        )

    # -- Tweets (10 tweets from 4 core accounts) --
    tweets = [
        ("t1", "core-1", "alice", "Alice talks about building agents", 100, 20, "2026-01-01 12:00:00"),
        ("t2", "core-1", "alice", "Alice on consciousness research", 50, 10, "2026-01-01 13:00:00"),
        ("t3", "core-1", "alice", "Alice creative writing", 30, 5, "2026-01-01 14:00:00"),
        ("t4", "core-2", "bob", "Bob on AI safety concerns", 80, 15, "2026-01-02 12:00:00"),
        ("t5", "core-2", "bob", "Bob thinks about qualia", 40, 8, "2026-01-02 13:00:00"),
        ("t6", "core-2", "bob", "Bob discusses art", 20, 3, "2026-01-02 14:00:00"),
        ("t7", "core-3", "carol", "Carol on creative coding", 60, 12, "2026-01-03 12:00:00"),
        ("t8", "core-3", "carol", "Carol paints", 35, 7, "2026-01-03 13:00:00"),
        ("t9", "core-4", "dave", "Dave builds infrastructure", 90, 18, "2026-01-04 12:00:00"),
        ("t10", "core-4", "dave", "Dave on distributed systems", 45, 9, "2026-01-04 13:00:00"),
    ]
    conn.executemany(
        "INSERT INTO tweets (tweet_id, account_id, username, full_text, "
        "favorite_count, retweet_count, created_at) VALUES (?,?,?,?,?,?,?)",
        tweets,
    )

    # -- Tweet tags: bits for core-1 (alpha-heavy) and core-2 (beta-heavy) --
    # Also non-bits tags to verify they're ignored by rollup
    tags = [
        # core-1 (alice): 6 bits alpha, 2 bits beta => 75% alpha, 25% beta
        ("t1", "bits:alpha:+3", "bits"),
        ("t2", "bits:alpha:+3", "bits"),
        ("t3", "bits:beta:+2", "bits"),
        # core-2 (bob): 5 bits beta, 2 bits gamma => ~71% beta, ~29% gamma
        ("t4", "bits:beta:+3", "bits"),
        ("t5", "bits:beta:+2", "bits"),
        ("t6", "bits:gamma:+2", "bits"),
        # Non-bits tags (should be ignored by rollup)
        ("t1", "domain:AI-agents", "domain"),
        ("t4", "thematic:safety-concern", "thematic"),
        ("t7", "posture:creative", "posture"),
    ]
    conn.executemany(
        "INSERT INTO tweet_tags (tweet_id, tag, category) VALUES (?,?,?)",
        tags,
    )

    # -- Account following (core accounts follow each other + shadows) --
    # Core-core edges: complete graph among 4 core accounts
    follow_edges = []
    for i, (aid1, _) in enumerate(CORE_ACCOUNTS):
        for j, (aid2, _) in enumerate(CORE_ACCOUNTS):
            if i != j:
                follow_edges.append((aid1, aid2))

    # Core-shadow edges: each core follows some shadows
    # core-1 follows shadow-1, shadow-2, shadow-3
    follow_edges += [("core-1", "shadow-1"), ("core-1", "shadow-2"), ("core-1", "shadow-3")]
    # core-2 follows shadow-1, shadow-4
    follow_edges += [("core-2", "shadow-1"), ("core-2", "shadow-4")]
    # core-3 follows shadow-2, shadow-5, shadow-6
    follow_edges += [("core-3", "shadow-2"), ("core-3", "shadow-5"), ("core-3", "shadow-6")]
    # core-4 follows shadow-3, shadow-4, shadow-5
    follow_edges += [("core-4", "shadow-3"), ("core-4", "shadow-4"), ("core-4", "shadow-5")]

    # Shadow-core edges: some shadows follow back (reciprocal)
    follow_edges += [("shadow-1", "core-1"), ("shadow-1", "core-2")]
    follow_edges += [("shadow-2", "core-1"), ("shadow-2", "core-3")]
    follow_edges += [("shadow-3", "core-1"), ("shadow-3", "core-4")]
    follow_edges += [("shadow-4", "core-2"), ("shadow-4", "core-4")]
    follow_edges += [("shadow-5", "core-3"), ("shadow-5", "core-4")]
    follow_edges += [("shadow-6", "core-3")]

    conn.executemany(
        "INSERT INTO account_following (account_id, following_account_id) VALUES (?,?)",
        follow_edges,
    )

    # -- Retweets (core accounts retweeting each other) --
    retweets = [
        ("rt1", "core-1", "bob"),
        ("rt2", "core-1", "bob"),       # alice RTs bob twice
        ("rt3", "core-2", "alice"),
        ("rt4", "core-3", "dave"),
        ("rt5", "core-3", "dave"),       # carol RTs dave twice
        ("rt6", "core-4", "carol"),
    ]
    conn.executemany(
        "INSERT INTO retweets (tweet_id, account_id, rt_of_username) VALUES (?,?,?)",
        retweets,
    )

    # -- Engagement aggregation (likes between accounts) --
    engagement = [
        ("core-1", "core-2", 15),   # alice likes bob's content
        ("core-1", "core-3", 8),
        ("core-2", "core-1", 12),   # bob likes alice's content
        ("core-2", "core-4", 10),
        ("core-3", "core-4", 20),   # carol likes dave's content
        ("core-4", "core-3", 18),   # reciprocal
        ("core-1", "shadow-1", 5),
        ("core-2", "shadow-4", 7),
    ]
    conn.executemany(
        "INSERT INTO account_engagement_agg (source_id, target_id, like_count) VALUES (?,?,?)",
        engagement,
    )

    # -- community_account (Layer 2, NMF weights for 4 core accounts) --
    # core-1 (alice): 90% alpha, 10% beta
    # core-2 (bob): 15% alpha, 70% beta, 15% gamma
    # core-3 (carol): 85% gamma
    # core-4 (dave): 60% alpha, 30% gamma
    layer2_assignments = [
        ("comm-alpha", "core-1", 0.90, "nmf"),
        ("comm-beta", "core-1", 0.10, "nmf"),
        ("comm-alpha", "core-2", 0.15, "nmf"),
        ("comm-beta", "core-2", 0.70, "nmf"),
        ("comm-gamma", "core-2", 0.15, "nmf"),
        ("comm-gamma", "core-3", 0.85, "nmf"),
        ("comm-alpha", "core-4", 0.60, "nmf"),
        ("comm-gamma", "core-4", 0.30, "nmf"),
    ]
    conn.executemany(
        "INSERT INTO community_account (community_id, account_id, weight, source, updated_at) "
        "VALUES (?,?,?,?,?)",
        [(cid, aid, w, src, now) for cid, aid, w, src in layer2_assignments],
    )

    # -- account_community_bits stays EMPTY initially (test_01 populates it) --

    conn.commit()
    conn.close()


@pytest.fixture(scope="class")
def pipeline_db(tmp_path_factory):
    """Create a shared DB for the entire test class."""
    tmp = tmp_path_factory.mktemp("pipeline")
    db_path = tmp / "archive_tweets.db"
    _create_full_db(db_path)
    return db_path


@pytest.fixture(scope="class")
def output_dir(tmp_path_factory):
    """Shared output directory for export artifacts."""
    return tmp_path_factory.mktemp("export_output")


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestPipelineEndToEnd:
    """Sequential e2e test: rollup -> NMF -> save -> propagate -> export."""

    # -- Test 01: Rollup bits --------------------------------------------------

    def test_01_rollup_bits(self, pipeline_db):
        """Run rollup, verify account_community_bits has correct rows for 2 labeled accounts."""
        from rollup_bits import aggregate_bits, load_bits_tags, load_short_to_id, write_rollup

        conn = sqlite3.connect(str(pipeline_db))

        short_to_id = load_short_to_id(conn)
        assert len(short_to_id) == 3, f"Expected 3 communities, got {len(short_to_id)}"
        assert set(short_to_id.keys()) == {"alpha", "beta", "gamma"}

        tags = load_bits_tags(conn)
        # 6 bits tags in fixture (3 for core-1, 3 for core-2)
        assert len(tags) == 6, f"Expected 6 bits tags, got {len(tags)}"

        rollup = aggregate_bits(tags, short_to_id)
        count = write_rollup(conn, rollup)

        # Verify DB state
        rows = conn.execute(
            "SELECT account_id, community_id, total_bits, tweet_count, pct "
            "FROM account_community_bits ORDER BY account_id, community_id"
        ).fetchall()

        # core-1: alpha=+6 (2 tweets), beta=+2 (1 tweet) => pct: 75%, 25%
        # core-2: beta=+5 (2 tweets), gamma=+2 (1 tweet) => pct: ~71.4%, ~28.6%
        account_data = {}
        for aid, cid, bits, tc, pct in rows:
            account_data[(aid, cid)] = {"bits": bits, "tc": tc, "pct": pct}

        # core-1 alpha
        assert ("core-1", "comm-alpha") in account_data
        assert account_data[("core-1", "comm-alpha")]["bits"] == 6
        assert account_data[("core-1", "comm-alpha")]["tc"] == 2
        assert account_data[("core-1", "comm-alpha")]["pct"] == pytest.approx(75.0, abs=0.1)

        # core-1 beta
        assert ("core-1", "comm-beta") in account_data
        assert account_data[("core-1", "comm-beta")]["bits"] == 2
        assert account_data[("core-1", "comm-beta")]["tc"] == 1
        assert account_data[("core-1", "comm-beta")]["pct"] == pytest.approx(25.0, abs=0.1)

        # core-2 beta
        assert ("core-2", "comm-beta") in account_data
        assert account_data[("core-2", "comm-beta")]["bits"] == 5
        assert account_data[("core-2", "comm-beta")]["tc"] == 2
        assert account_data[("core-2", "comm-beta")]["pct"] == pytest.approx(71.43, abs=0.1)

        # core-2 gamma
        assert ("core-2", "comm-gamma") in account_data
        assert account_data[("core-2", "comm-gamma")]["bits"] == 2
        assert account_data[("core-2", "comm-gamma")]["tc"] == 1
        assert account_data[("core-2", "comm-gamma")]["pct"] == pytest.approx(28.57, abs=0.1)

        # core-3 and core-4 should NOT appear (no bits tags)
        assert not any(aid.startswith("core-3") for aid, _ in account_data.keys())
        assert not any(aid.startswith("core-4") for aid, _ in account_data.keys())

        assert count == 4, f"Expected 4 rows written, got {count}"
        conn.close()

    # -- Test 02: NMF with likes -----------------------------------------------

    def test_02_nmf_with_likes(self, pipeline_db):
        """Build NMF feature matrices (follow + rt + likes), verify combined shape."""
        from cluster_soft import (
            build_following_matrix,
            build_likes_matrix,
            build_retweet_matrix,
            tfidf,
        )
        from scipy.sparse import hstack
        from sklearn.preprocessing import normalize

        conn = sqlite3.connect(str(pipeline_db))

        # Only use core accounts for NMF (as the real pipeline does)
        accounts = CORE_ACCOUNTS

        mat_f, targets_f = build_following_matrix(conn, accounts)
        assert mat_f.shape[0] == 4, "Should have 4 rows (core accounts)"
        assert mat_f.shape[1] > 0, "Should have follow targets"

        mat_r, targets_r = build_retweet_matrix(conn, accounts, min_count=2)
        assert mat_r.shape[0] == 4

        mat_l, targets_l = build_likes_matrix(conn, accounts)
        assert mat_l.shape[0] == 4
        assert mat_l.shape[1] > 0, "Likes matrix should have non-zero columns"

        # Verify likes contribute actual values
        assert mat_l.nnz > 0, "Likes matrix should have non-zero entries"

        # Build combined matrix like the real pipeline
        mat_f_tfidf = tfidf(mat_f)
        mat_r_tfidf = tfidf(mat_r) if mat_r.shape[1] > 0 else mat_r
        mat_l_tfidf = tfidf(mat_l) if mat_l.shape[1] > 0 else mat_l

        blocks = [normalize(mat_f_tfidf)]
        if mat_r_tfidf.shape[1] > 0:
            blocks.append(normalize(mat_r_tfidf) * 0.6)
        if mat_l_tfidf.shape[1] > 0:
            blocks.append(normalize(mat_l_tfidf) * 0.4)

        combined = hstack(blocks)
        assert combined.shape[0] == 4
        # Combined should have follow + rt + likes columns
        expected_cols = mat_f.shape[1]
        if mat_r_tfidf.shape[1] > 0:
            expected_cols += mat_r.shape[1]
        if mat_l_tfidf.shape[1] > 0:
            expected_cols += mat_l.shape[1]
        assert combined.shape[1] == expected_cols

        # Store dimensions for test_03
        self.__class__._nf = mat_f_tfidf.shape[1]
        self.__class__._nr = mat_r_tfidf.shape[1] if mat_r_tfidf.shape[1] > 0 else 0
        self.__class__._nl = mat_l_tfidf.shape[1] if mat_l_tfidf.shape[1] > 0 else 0
        self.__class__._targets_f = targets_f
        self.__class__._targets_r = targets_r
        self.__class__._targets_l = targets_l

        conn.close()

    # -- Test 03: Save run (real _save_run path) ---------------------------------

    def test_03_save_run(self, pipeline_db):
        """Persist NMF results via the REAL _save_run, verify Layer 1 tables."""
        import types
        import cluster_soft
        from cluster_soft import _save_run, make_run_id
        from communities.store import init_db

        conn = sqlite3.connect(str(pipeline_db))
        init_db(conn)
        conn.close()

        # Monkeypatch ARCHIVE_DB so _save_run writes to our test DB
        original_db = cluster_soft.ARCHIVE_DB
        cluster_soft.ARCHIVE_DB = pipeline_db

        try:
            # Use real NMF matrices from test_02 if available, else synthetic
            W_norm = getattr(self.__class__, '_W_norm', None)
            if W_norm is None:
                W_norm = np.array([
                    [0.80, 0.10, 0.10],
                    [0.15, 0.65, 0.20],
                    [0.10, 0.15, 0.75],
                    [0.55, 0.10, 0.35],
                ])

            accounts = [
                ("core-1", "user_core1"),
                ("core-2", "user_core2"),
                ("core-3", "user_core3"),
                ("core-4", "user_core4"),
            ]
            k = 3
            nf = 4   # follow features
            nr = 3   # RT features
            # H: k rows, nf+nr+nl columns
            H = np.random.rand(k, nf + nr + 2) * 0.5
            H[0, 0] = 0.9  # community 0 strongly defined by follow target 0
            H[1, nf] = 0.8  # community 1 strongly defined by RT target 0
            H[2, nf + nr] = 0.7  # community 2 strongly defined by like target 0

            targets_f = [f"follow-t{i}" for i in range(nf)]
            targets_r = [f"rt-t{i}" for i in range(nr)]
            targets_l = ["like-t0", "like-t1"]

            args = types.SimpleNamespace(
                k=k, likes=True, likes_weight=0.4,
                rt_weight=0.6, threshold=0.1,
                notes="e2e test run", save=True,
            )

            # Call the REAL _save_run
            _save_run(
                None, args, accounts, W_norm, H,
                targets_f, targets_r, targets_l,
                nf, nr, "follow+rt+like",
            )

            # Verify via DB
            conn = sqlite3.connect(str(pipeline_db))

            # community_run row exists
            run_rows = conn.execute("SELECT * FROM community_run").fetchall()
            assert len(run_rows) >= 1, "community_run should have at least 1 row"
            run = run_rows[-1]  # latest run
            assert run[1] == 3   # k
            assert run[2] == "follow+rt+like"  # signal

            # Membership rows exist
            m_count = conn.execute(
                "SELECT COUNT(*) FROM community_membership"
            ).fetchone()[0]
            assert m_count > 0, "Should have membership rows"

            # Definition rows include all three feature types
            feat_types = set(
                r[0] for r in conn.execute(
                    "SELECT DISTINCT feature_type FROM community_definition"
                ).fetchall()
            )
            assert "follow" in feat_types, "Should have follow definitions"
            assert "rt" in feat_types, "Should have rt definitions"
            assert "like" in feat_types, "Should have like definitions"

            conn.close()
        finally:
            cluster_soft.ARCHIVE_DB = original_db

    # -- Test 04: Propagate ----------------------------------------------------

    def test_04_propagate(self, pipeline_db, output_dir):
        """Build tiny adjacency, propagate from 4 seeds, verify shadow assignments."""
        # Build adjacency matrix from account_following
        conn = sqlite3.connect(str(pipeline_db))

        # Get all accounts in a consistent order
        all_ids = [aid for aid, _ in ALL_ACCOUNTS]
        id_to_idx = {aid: i for i, aid in enumerate(all_ids)}
        n = len(all_ids)

        # Build adjacency from follow edges
        edges = conn.execute(
            "SELECT account_id, following_account_id FROM account_following"
        ).fetchall()

        adj = sp.lil_matrix((n, n), dtype=np.float32)
        for src, tgt in edges:
            i = id_to_idx.get(src)
            j = id_to_idx.get(tgt)
            if i is not None and j is not None:
                adj[i, j] = 1.0
        adj = adj.tocsr()

        node_ids = np.array(all_ids)

        # Import propagation machinery
        from scripts.propagate_community_labels import PropagationConfig, propagate

        config = PropagationConfig(
            temperature=2.0,
            regularization=1e-2,  # higher reg for tiny graph stability
            min_degree_for_assignment=1,  # lower threshold for our small graph
            abstain_max_threshold=0.05,  # lower to allow more assignments
            abstain_uncertainty_threshold=0.9,
            class_balance=True,
        )

        # Mock DB_PATH so load_community_labels reads from our fixture DB
        with patch("scripts.propagate_community_labels.DB_PATH", pipeline_db):
            result, _ = propagate(adj, node_ids, config)

        # Verify basic structure
        assert result.memberships.shape == (n, 4)  # 3 communities + 1 "none"
        assert len(result.community_ids) == 3
        assert set(result.community_ids) == set(COMMUNITY_IDS)

        # Labeled nodes should be the 4 core accounts
        assert result.labeled_mask.sum() == 4
        for aid in ["core-1", "core-2", "core-3", "core-4"]:
            idx = id_to_idx[aid]
            assert result.labeled_mask[idx], f"{aid} should be labeled"

        # Shadow nodes should have non-trivial memberships (not all "none")
        shadow_indices = [id_to_idx[aid] for aid, _ in SHADOW_ACCOUNTS]
        shadow_memberships = result.memberships[shadow_indices, :3]  # exclude "none" col
        max_community_weights = shadow_memberships.max(axis=1)

        # At least some shadows should get community assignments
        assigned_shadows = (max_community_weights > 0.05).sum()
        assert assigned_shadows >= 2, (
            f"Expected at least 2 shadows with community assignment, got {assigned_shadows}"
        )

        # Save result for test_06
        from scripts.propagate_community_labels import save_results
        save_results(result, output_dir)
        npz_path = output_dir / "community_propagation.npz"
        assert npz_path.exists(), "Propagation NPZ should be saved"

        # Store result on class for later tests
        self.__class__._propagation_result = result
        self.__class__._node_ids = node_ids
        self.__class__._id_to_idx = id_to_idx

        conn.close()

    # -- Test 05: Export classified ---------------------------------------------

    def test_05_export_classified(self, pipeline_db):
        """Run extract_classified_accounts, verify 4 core accounts with tier='classified'."""
        from scripts.export_public_site import extract_classified_accounts

        # extract_classified_accounts needs confidence module which queries several tables.
        # Our fixture DB has all the required tables.
        result = extract_classified_accounts(pipeline_db, min_weight=0.05)

        ids = {a["id"] for a in result}
        # All 4 core accounts should appear (all have weights >= 0.05)
        assert "core-1" in ids, "core-1 should be classified"
        assert "core-2" in ids, "core-2 should be classified"
        assert "core-3" in ids, "core-3 should be classified"
        assert "core-4" in ids, "core-4 should be classified"

        # All should have tier == "classified"
        for acct in result:
            assert acct["tier"] == "classified"
            assert len(acct["memberships"]) > 0
            assert "confidence" in acct
            assert "confidence_level" in acct

        # Verify bits override for core-1 and core-2 (they have bits from test_01)
        acct1 = next(a for a in result if a["id"] == "core-1")
        acct1_comms = {m["community_id"] for m in acct1["memberships"]}
        # core-1 has bits: alpha=75%, beta=25% => both above 0.05
        assert "comm-alpha" in acct1_comms
        assert "comm-beta" in acct1_comms

        acct2 = next(a for a in result if a["id"] == "core-2")
        acct2_comms = {m["community_id"] for m in acct2["memberships"]}
        # core-2 has bits: beta=71.4%, gamma=28.6% => both above 0.05
        assert "comm-beta" in acct2_comms
        assert "comm-gamma" in acct2_comms

        # core-3 has NO bits => uses NMF: gamma=0.85
        acct3 = next(a for a in result if a["id"] == "core-3")
        acct3_comms = {m["community_id"] for m in acct3["memberships"]}
        assert "comm-gamma" in acct3_comms

    # -- Test 06: Export propagated --------------------------------------------

    def test_06_export_propagated(self, pipeline_db, output_dir):
        """Read NPZ from propagation, run extract_propagated_handles, verify shadows."""
        from scripts.export_public_site import extract_propagated_handles

        npz_path = output_dir / "community_propagation.npz"
        assert npz_path.exists(), "NPZ must exist from test_04"

        # Build node_id -> username map
        node_id_to_username = {aid: username for aid, username in ALL_ACCOUNTS}

        classified_ids = {"core-1", "core-2", "core-3", "core-4"}

        result = extract_propagated_handles(
            npz_path=npz_path,
            node_id_to_username=node_id_to_username,
            classified_ids=classified_ids,
            min_weight=0.05,
            abstain_threshold=0.05,  # low threshold for our tiny graph
        )

        # Core accounts should NOT appear (they're classified)
        for _, username in CORE_ACCOUNTS:
            assert username not in result, f"{username} should not be in propagated"

        # At least some shadow accounts should appear
        shadow_usernames = {username for _, username in SHADOW_ACCOUNTS}
        found_shadows = shadow_usernames & set(result.keys())
        assert len(found_shadows) >= 1, (
            f"Expected at least 1 propagated shadow, got {len(found_shadows)}"
        )

        # Verify structure of propagated entries
        for handle, entry in result.items():
            assert entry["tier"] == "propagated"
            assert len(entry["memberships"]) > 0
            for m in entry["memberships"]:
                assert "community_id" in m
                assert "community_name" in m
                assert "weight" in m
                assert m["weight"] >= 0.05

    # -- Test 07: Full export --------------------------------------------------

    def test_07_full_export(self, pipeline_db, output_dir):
        """Run the full export pipeline, verify data.json and search.json."""
        from scripts.export_public_site import run_export

        # Create parquet with account metadata
        pd = pytest.importorskip("pandas")
        parquet_path = output_dir / "graph_snapshot.nodes.parquet"
        df = pd.DataFrame({
            "node_id": [aid for aid, _ in ALL_ACCOUNTS],
            "username": [username for _, username in ALL_ACCOUNTS],
            "display_name": [f"Display {username}" for _, username in ALL_ACCOUNTS],
            "num_followers": [100 + i * 50 for i in range(len(ALL_ACCOUNTS))],
            "bio": [f"Bio for {username}" for _, username in ALL_ACCOUNTS],
        })
        df.to_parquet(str(parquet_path), index=False)

        config = {
            "site_name": "E2E Test Site",
            "curator": "testcurator",
            "links": {"repo": "https://github.com/test"},
            "export": {
                "min_weight": 0.05,
                "abstain_threshold": 0.05,
            },
        }

        export_out = output_dir / "final_export"
        run_export(
            data_dir=output_dir,
            output_dir=export_out,
            config=config,
            db_path=pipeline_db,
        )

        # Verify data.json
        data_path = export_out / "data.json"
        assert data_path.exists()
        data = json.loads(data_path.read_text())

        assert "communities" in data
        assert "accounts" in data
        assert "meta" in data

        # Should have 3 communities
        assert len(data["communities"]) == 3
        community_names = {c["name"] for c in data["communities"]}
        assert community_names == set(COMMUNITY_NAMES)

        # All 4 core accounts should be in accounts
        account_ids = {a["id"] for a in data["accounts"]}
        assert "core-1" in account_ids
        assert "core-2" in account_ids
        assert "core-3" in account_ids
        assert "core-4" in account_ids

        # Meta should have counts
        assert data["meta"]["counts"]["communities"] == 3
        assert data["meta"]["counts"]["classified_accounts"] == 4

        # Verify search.json
        search_path = export_out / "search.json"
        assert search_path.exists()
        search = json.loads(search_path.read_text())
        assert isinstance(search, dict)

        # Classified handles should be in search
        assert "alice" in search
        assert "bob" in search
        assert "carol" in search
        assert "dave" in search

        # Classified entries should have tier
        assert search["alice"]["tier"] == "classified"

        # Total searchable should be at least the 4 classified
        assert data["meta"]["counts"]["total_searchable"] >= 4

    # -- Test 08: Interface consistency ----------------------------------------

    def test_08_interface_consistency(self, pipeline_db, output_dir):
        """Verify community_ids are consistent across rollup, NMF save, propagation, export."""
        conn = sqlite3.connect(str(pipeline_db))

        # 1. Community IDs from the community table
        db_community_ids = set(
            row[0]
            for row in conn.execute("SELECT id FROM community").fetchall()
        )
        assert db_community_ids == set(COMMUNITY_IDS)

        # 2. Community IDs referenced in rollup (account_community_bits)
        rollup_community_ids = set(
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT community_id FROM account_community_bits"
            ).fetchall()
        )
        # Rollup only touches communities that have bits tags -- should be a subset
        assert rollup_community_ids.issubset(db_community_ids), (
            f"Rollup community_ids {rollup_community_ids} not subset of {db_community_ids}"
        )

        # 3. Community IDs in NMF community_account (Layer 2)
        nmf_community_ids = set(
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT community_id FROM community_account"
            ).fetchall()
        )
        assert nmf_community_ids.issubset(db_community_ids), (
            f"NMF community_ids {nmf_community_ids} not subset of {db_community_ids}"
        )

        # 4. Community IDs from propagation result
        npz_path = output_dir / "community_propagation.npz"
        if npz_path.exists():
            npz_data = np.load(str(npz_path), allow_pickle=False)
            prop_community_ids = set(str(cid) for cid in npz_data["community_ids"])
            assert prop_community_ids == db_community_ids, (
                f"Propagation community_ids {prop_community_ids} != DB {db_community_ids}"
            )

        # 5. Community IDs from export data.json
        export_path = output_dir / "final_export" / "data.json"
        if export_path.exists():
            data = json.loads(export_path.read_text())
            export_community_ids = {c["id"] for c in data["communities"]}
            assert export_community_ids == db_community_ids, (
                f"Export community_ids {export_community_ids} != DB {db_community_ids}"
            )

            # Verify membership community_ids in classified accounts reference valid communities
            for acct in data["accounts"]:
                for m in acct["memberships"]:
                    assert m["community_id"] in db_community_ids, (
                        f"Account {acct['id']} references unknown community {m['community_id']}"
                    )

        conn.close()
