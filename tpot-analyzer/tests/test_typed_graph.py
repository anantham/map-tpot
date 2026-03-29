"""Tests for TypedGraph — multi-relational graph with per-type sparse matrices."""
import sqlite3

import numpy as np
import pytest
import scipy.sparse as sp

from src.propagation.typed_graph import TypedGraph, DEFAULT_EDGE_WEIGHTS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_graph(node_ids=None):
    """Create a small TypedGraph for testing."""
    if node_ids is None:
        node_ids = ["a", "b", "c", "d"]
    return TypedGraph(node_ids)


def _sparse_from_edges(graph, edges):
    """Build a sparse matrix from [(src, tgt, val), ...] using graph.node_idx."""
    rows, cols, vals = [], [], []
    for src, tgt, val in edges:
        rows.append(graph.node_idx[src])
        cols.append(graph.node_idx[tgt])
        vals.append(val)
    return sp.csr_matrix(
        (np.array(vals, dtype=np.float32), (rows, cols)),
        shape=(graph.n, graph.n),
    )


def _create_test_db(tmp_path):
    """Create a minimal SQLite DB with all edge tables for from_archive tests."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))

    # Follow graph (defines the node universe)
    conn.execute("""
        CREATE TABLE account_following (
            account_id TEXT, following_account_id TEXT
        )
    """)
    conn.executemany(
        "INSERT INTO account_following VALUES (?, ?)",
        [("a", "b"), ("b", "c"), ("c", "a"), ("a", "c")],
    )

    # Quote graph
    conn.execute("""
        CREATE TABLE quote_graph (
            source_id TEXT, target_id TEXT, quote_count INTEGER, created_at TEXT
        )
    """)
    conn.executemany(
        "INSERT INTO quote_graph VALUES (?, ?, ?, '')",
        [("a", "b", 3), ("b", "c", 1), ("a", "c", 10)],
    )

    # Mention graph
    conn.execute("""
        CREATE TABLE mention_graph (
            source_id TEXT, target_id TEXT, mention_count INTEGER, created_at TEXT
        )
    """)
    conn.executemany(
        "INSERT INTO mention_graph VALUES (?, ?, ?, '')",
        [("a", "b", 5), ("a", "c", 20), ("c", "b", 2)],
    )

    # Account followers (inbound)
    conn.execute("""
        CREATE TABLE account_followers (
            account_id TEXT, follower_account_id TEXT
        )
    """)
    conn.executemany(
        "INSERT INTO account_followers VALUES (?, ?)",
        [("b", "a"), ("c", "a"), ("a", "c")],  # a follows b,c; c follows a
    )

    # Signed reply
    conn.execute("""
        CREATE TABLE signed_reply (
            replier_id TEXT, author_id TEXT, reply_count INTEGER, heuristic TEXT
        )
    """)
    conn.executemany(
        "INSERT INTO signed_reply VALUES (?, ?, ?, ?)",
        [("a", "b", 3, "direct"), ("c", "a", 1, "author_liked")],
    )

    # Engagement agg (likes + RTs)
    conn.execute("""
        CREATE TABLE account_engagement_agg (
            source_id TEXT, target_id TEXT, like_count INTEGER, rt_count INTEGER
        )
    """)
    conn.executemany(
        "INSERT INTO account_engagement_agg VALUES (?, ?, ?, ?)",
        [("a", "b", 10, 2), ("b", "c", 30, 0)],
    )

    # Cofollowed similarity
    conn.execute("""
        CREATE TABLE cofollowed_similarity (
            account_a TEXT, account_b TEXT, jaccard REAL
        )
    """)
    conn.executemany(
        "INSERT INTO cofollowed_similarity VALUES (?, ?, ?)",
        [("a", "b", 15.0), ("b", "c", 5.0)],
    )

    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Unit tests: TypedGraph core
# ---------------------------------------------------------------------------

class TestTypedGraphCore:

    def test_init_sets_up_node_mapping(self):
        g = _make_graph(["x", "y", "z"])
        assert g.n == 3
        assert g.node_idx == {"x": 0, "y": 1, "z": 2}

    def test_set_and_get(self):
        g = _make_graph()
        mat = _sparse_from_edges(g, [("a", "b", 1.0)])
        g.set("follow", mat)
        assert g.has("follow")
        assert g.get("follow") is mat
        assert not g.has("reply")
        assert g.get("reply") is None

    def test_set_rejects_wrong_shape(self):
        g = _make_graph()
        bad_mat = sp.csr_matrix((3, 3), dtype=np.float32)
        with pytest.raises(AssertionError):
            g.set("follow", bad_mat)

    def test_combine_uses_default_weights(self):
        g = _make_graph(["a", "b"])
        follow = _sparse_from_edges(g, [("a", "b", 2.0)])
        like = _sparse_from_edges(g, [("a", "b", 10.0)])
        g.set("follow", follow)
        g.set("like", like)
        combined = g.combine()
        # follow: 2.0 * 1.0 + like: 10.0 * 0.3 = 5.0
        assert combined[0, 1] == pytest.approx(5.0, abs=0.01)

    def test_combine_custom_weights(self):
        g = _make_graph(["a", "b"])
        follow = _sparse_from_edges(g, [("a", "b", 1.0)])
        quote = _sparse_from_edges(g, [("a", "b", 1.0)])
        g.set("follow", follow)
        g.set("quote", quote)
        combined = g.combine({"follow": 0.5, "quote": 2.0})
        assert combined[0, 1] == pytest.approx(2.5, abs=0.01)

    def test_combine_zero_weight_excluded(self):
        g = _make_graph(["a", "b"])
        follow = _sparse_from_edges(g, [("a", "b", 1.0)])
        follower = _sparse_from_edges(g, [("a", "b", 1.0)])
        g.set("follow", follow)
        g.set("follower", follower)
        # follower has weight 0.0 by default
        combined = g.combine()
        assert combined[0, 1] == pytest.approx(1.0, abs=0.01)

    def test_edge_summary(self):
        g = _make_graph(["a", "b", "c"])
        g.set("follow", _sparse_from_edges(g, [("a", "b", 1.0), ("b", "c", 1.0)]))
        g.set("quote", _sparse_from_edges(g, [("a", "c", 1.0)]))
        summary = g.edge_summary()
        assert summary == {"follow": 2, "quote": 1}

    def test_neighbors(self):
        g = _make_graph(["a", "b", "c"])
        g.set("follow", _sparse_from_edges(g, [("a", "b", 1.0), ("a", "c", 0.5)]))
        neighbors = g.neighbors("a", "follow")
        assert len(neighbors) == 2
        assert neighbors[0] == ("b", 1.0)  # sorted by weight desc
        assert neighbors[1] == ("c", 0.5)

    def test_neighbors_unknown_account(self):
        g = _make_graph(["a", "b"])
        assert g.neighbors("z") == []

    def test_typed_degree(self):
        g = _make_graph(["a", "b", "c"])
        g.set("follow", _sparse_from_edges(g, [("a", "b", 1.0), ("a", "c", 1.0)]))
        g.set("quote", _sparse_from_edges(g, [("a", "b", 1.0)]))
        deg = g.typed_degree("a")
        assert deg["follow"] == 2
        assert deg["quote"] == 1


# ---------------------------------------------------------------------------
# Quote edge normalization
# ---------------------------------------------------------------------------

class TestQuoteEdgeNormalization:

    def test_quote_count_normalized_to_max_1(self):
        """quote_count / 5.0, capped at 1.0"""
        g = _make_graph(["a", "b", "c"])
        # count=3 → 0.6, count=10 → 1.0 (capped)
        g.set("quote", _sparse_from_edges(g, [
            ("a", "b", min(3 / 5.0, 1.0)),
            ("a", "c", min(10 / 5.0, 1.0)),
        ]))
        mat = g.get("quote")
        ai, bi, ci = g.node_idx["a"], g.node_idx["b"], g.node_idx["c"]
        assert mat[ai, bi] == pytest.approx(0.6, abs=0.01)
        assert mat[ai, ci] == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# Mention edge normalization
# ---------------------------------------------------------------------------

class TestMentionEdgeNormalization:

    def test_mention_count_normalized_to_max_1(self):
        """mention_count / 10.0, capped at 1.0"""
        g = _make_graph(["a", "b", "c"])
        # count=5 → 0.5, count=20 → 1.0 (capped)
        g.set("mention", _sparse_from_edges(g, [
            ("a", "b", min(5 / 10.0, 1.0)),
            ("a", "c", min(20 / 10.0, 1.0)),
        ]))
        mat = g.get("mention")
        ai, bi, ci = g.node_idx["a"], g.node_idx["b"], g.node_idx["c"]
        assert mat[ai, bi] == pytest.approx(0.5, abs=0.01)
        assert mat[ai, ci] == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# Reciprocity
# ---------------------------------------------------------------------------

class TestReciprocity:

    def test_reciprocity_mutual_follows(self):
        """a follows b,c. b,c follow a. Reciprocity of a = 2/2 = 1.0"""
        g = _make_graph(["a", "b", "c"])
        # a→b, a→c (outbound)
        g.set("follow", _sparse_from_edges(g, [("a", "b", 1.0), ("a", "c", 1.0)]))
        # b→a, c→a (inbound — stored as follower→account)
        g.set("follower", _sparse_from_edges(g, [("b", "a", 1.0), ("c", "a", 1.0)]))
        assert g.reciprocity("a") == pytest.approx(1.0)

    def test_reciprocity_no_mutuals(self):
        """a follows b,c. d follows a. No overlap → 0.0"""
        g = _make_graph(["a", "b", "c", "d"])
        g.set("follow", _sparse_from_edges(g, [("a", "b", 1.0), ("a", "c", 1.0)]))
        g.set("follower", _sparse_from_edges(g, [("d", "a", 1.0)]))
        assert g.reciprocity("a") == pytest.approx(0.0)

    def test_reciprocity_partial(self):
        """a follows b. b,c follow a. 1 mutual / 2 inbound = 0.5"""
        g = _make_graph(["a", "b", "c"])
        g.set("follow", _sparse_from_edges(g, [("a", "b", 1.0)]))
        g.set("follower", _sparse_from_edges(g, [("b", "a", 1.0), ("c", "a", 1.0)]))
        assert g.reciprocity("a") == pytest.approx(0.5)

    def test_reciprocity_no_inbound(self):
        """No followers → None"""
        g = _make_graph(["a", "b"])
        g.set("follow", _sparse_from_edges(g, [("a", "b", 1.0)]))
        g.set("follower", sp.csr_matrix((2, 2), dtype=np.float32))
        assert g.reciprocity("a") is None

    def test_reciprocity_missing_matrices(self):
        """Without follower matrix → None"""
        g = _make_graph(["a", "b"])
        g.set("follow", _sparse_from_edges(g, [("a", "b", 1.0)]))
        assert g.reciprocity("a") is None

    def test_reciprocity_unknown_account(self):
        g = _make_graph(["a", "b"])
        g.set("follow", _sparse_from_edges(g, [("a", "b", 1.0)]))
        g.set("follower", _sparse_from_edges(g, [("b", "a", 1.0)]))
        assert g.reciprocity("z") is None


# ---------------------------------------------------------------------------
# from_archive integration test
# ---------------------------------------------------------------------------

class TestFromArchive:

    def test_loads_all_edge_types(self, tmp_path):
        db_path = _create_test_db(tmp_path)
        graph = TypedGraph.from_archive(db_path)

        assert graph.n == 3  # a, b, c
        summary = graph.edge_summary()
        assert summary["follow"] == 4
        assert summary["quote"] == 3
        assert summary["mention"] == 3
        assert summary["follower"] == 3
        assert summary["reply"] == 2
        assert summary["like"] == 2
        assert summary["rt"] == 1
        assert summary["cofollowed"] > 0  # undirected doubles

    def test_load_types_filter(self, tmp_path):
        db_path = _create_test_db(tmp_path)
        graph = TypedGraph.from_archive(db_path, load_types={"follow", "quote"})

        assert graph.has("follow")
        assert graph.has("quote")
        assert not graph.has("mention")
        assert not graph.has("follower")
        assert not graph.has("reply")

    def test_quote_normalization_from_db(self, tmp_path):
        db_path = _create_test_db(tmp_path)
        graph = TypedGraph.from_archive(db_path, load_types={"follow", "quote"})
        mat = graph.get("quote")
        ai = graph.node_idx["a"]
        bi = graph.node_idx["b"]
        ci = graph.node_idx["c"]
        # a→b: count=3, normalized = 3/5 = 0.6
        assert mat[ai, bi] == pytest.approx(0.6, abs=0.01)
        # a→c: count=10, normalized = min(10/5, 1) = 1.0
        assert mat[ai, ci] == pytest.approx(1.0, abs=0.01)

    def test_mention_normalization_from_db(self, tmp_path):
        db_path = _create_test_db(tmp_path)
        graph = TypedGraph.from_archive(db_path, load_types={"follow", "mention"})
        mat = graph.get("mention")
        ai = graph.node_idx["a"]
        bi = graph.node_idx["b"]
        ci = graph.node_idx["c"]
        # a→b: count=5, normalized = 5/10 = 0.5
        assert mat[ai, bi] == pytest.approx(0.5, abs=0.01)
        # a→c: count=20, normalized = min(20/10, 1) = 1.0
        assert mat[ai, ci] == pytest.approx(1.0, abs=0.01)

    def test_follower_edges_from_db(self, tmp_path):
        db_path = _create_test_db(tmp_path)
        graph = TypedGraph.from_archive(db_path, load_types={"follow", "follower"})
        mat = graph.get("follower")
        # account_followers: (b, a) means a follows b → stored as follower=a, account=b → i=a, j=b
        ai = graph.node_idx["a"]
        bi = graph.node_idx["b"]
        ci = graph.node_idx["c"]
        assert mat[ai, bi] == 1.0  # a follows b (a is follower of b)
        assert mat[ai, ci] == 1.0  # a follows c
        assert mat[ci, ai] == 1.0  # c follows a

    def test_reciprocity_from_db(self, tmp_path):
        db_path = _create_test_db(tmp_path)
        graph = TypedGraph.from_archive(db_path, load_types={"follow", "follower"})
        # a follows b,c. c follows a. So inbound to a = {c}. a follows {b,c}. Mutual = {c}. → 1/1 = 1.0
        recip_a = graph.reciprocity("a")
        assert recip_a == pytest.approx(1.0)

    def test_missing_table_graceful(self, tmp_path):
        """If a table doesn't exist, that edge type is just skipped."""
        db_path = tmp_path / "minimal.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE account_following (account_id TEXT, following_account_id TEXT)")
        conn.execute("INSERT INTO account_following VALUES ('a', 'b')")
        conn.commit()
        conn.close()

        graph = TypedGraph.from_archive(db_path)
        assert graph.has("follow")
        assert not graph.has("quote")
        assert not graph.has("mention")
        assert not graph.has("follower")

    def test_combine_with_new_edge_types(self, tmp_path):
        db_path = _create_test_db(tmp_path)
        graph = TypedGraph.from_archive(db_path)

        # Default combine includes quote (0.7) and mention (0.15) but not follower (0.0)
        combined = graph.combine()
        assert combined.nnz > 0

        # follower should NOT contribute (weight=0)
        follower_only = graph.combine({"follower": 1.0})
        quote_only = graph.combine({"quote": 1.0})
        assert quote_only.nnz > 0
        assert follower_only.nnz > 0
