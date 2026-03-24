import sqlite3
import pytest
from scripts.assemble_context import (
    get_graph_signal,
    get_engagement_context,
    get_community_descriptions,
    get_following_overlap,
    assemble_account_context,
)


def _setup_db(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute(
        "CREATE TABLE community (id TEXT PRIMARY KEY, name TEXT, short_name TEXT, description TEXT)"
    )
    conn.execute(
        "INSERT INTO community VALUES ('c1','Test Community','Test-Comm','A test community')"
    )
    conn.execute(
        "INSERT INTO community VALUES ('c2','Other Comm','Other-Comm','Another community')"
    )
    conn.execute(
        "CREATE TABLE community_account "
        "(community_id TEXT, account_id TEXT, weight REAL, source TEXT, updated_at TEXT, "
        "PRIMARY KEY (community_id, account_id))"
    )
    conn.execute(
        "CREATE TABLE account_following (account_id TEXT, following_account_id TEXT)"
    )
    conn.execute(
        "CREATE TABLE likes "
        "(liker_account_id TEXT, liker_username TEXT, tweet_id TEXT, "
        "full_text TEXT, expanded_url TEXT, fetched_at TEXT)"
    )
    conn.commit()
    return conn


def test_graph_signal_counts_by_community(tmp_path):
    conn = _setup_db(tmp_path)
    # Seed 's1' is in community c1, and follows target 'target1'
    conn.execute("INSERT INTO community_account VALUES ('c1','s1',0.9,'nmf','')")
    conn.execute("INSERT INTO community_account VALUES ('c1','s2',0.8,'nmf','')")
    conn.execute("INSERT INTO community_account VALUES ('c2','s3',0.7,'nmf','')")
    conn.execute("INSERT INTO account_following VALUES ('s1','target1')")
    conn.execute("INSERT INTO account_following VALUES ('s2','target1')")
    conn.execute("INSERT INTO account_following VALUES ('s3','target1')")
    conn.commit()
    signal = get_graph_signal(conn, account_id="target1")
    assert "Test Community" in signal
    assert "2" in signal  # 2 seeds from c1
    assert "Other Comm" in signal


def test_graph_signal_empty_for_unknown(tmp_path):
    conn = _setup_db(tmp_path)
    signal = get_graph_signal(conn, account_id="nobody")
    assert "No seed" in signal


def test_engagement_context_from_archive(tmp_path):
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO community_account VALUES ('c1','liker1',0.9,'nmf','')")
    conn.execute("INSERT INTO likes VALUES ('liker1','liker_user','tweet123','','','')")
    conn.commit()
    ctx = get_engagement_context(conn, tweet_id="tweet123")
    assert "liker_user" in ctx
    assert "Test Community" in ctx


def test_engagement_context_empty(tmp_path):
    conn = _setup_db(tmp_path)
    ctx = get_engagement_context(conn, tweet_id="nonexistent")
    assert "No engagement" in ctx


def test_community_descriptions(tmp_path):
    conn = _setup_db(tmp_path)
    descs, names = get_community_descriptions(conn)
    assert "Test-Comm" in names
    assert "Other-Comm" in names
    assert "Test Community" in descs
    assert descs["Test Community"] == "A test community"


def test_following_overlap(tmp_path):
    conn = _setup_db(tmp_path)
    # target1 follows s1 (who is classified in c1)
    conn.execute("INSERT INTO community_account VALUES ('c1','s1',0.9,'nmf','')")
    conn.execute("INSERT INTO account_following VALUES ('target1','s1')")
    conn.commit()
    overlap = get_following_overlap(conn, account_id="target1")
    assert "1" in overlap
    assert "Test Community" in overlap


def test_following_overlap_no_data(tmp_path):
    conn = _setup_db(tmp_path)
    overlap = get_following_overlap(conn, account_id="nobody")
    assert "No following" in overlap


def test_assemble_account_context(tmp_path):
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO community_account VALUES ('c1','s1',0.9,'nmf','')")
    conn.execute("INSERT INTO account_following VALUES ('s1','target1')")
    conn.commit()
    ctx = assemble_account_context(
        conn, account_id="target1", username="targetuser", bio="test bio"
    )
    assert ctx["username"] == "targetuser"
    assert ctx["bio"] == "test bio"
    assert "graph_signal" in ctx
    assert "community_descriptions" in ctx
    assert "community_short_names" in ctx


# --- Additional behavioral tests ---


def test_graph_signal_sorted_by_count_descending(tmp_path):
    """Community with more seeds appears first in the output."""
    conn = _setup_db(tmp_path)
    # c2 gets 3 seeds, c1 gets 1 seed
    conn.execute("INSERT INTO community_account VALUES ('c1','s1',0.9,'nmf','')")
    conn.execute("INSERT INTO community_account VALUES ('c2','s2',0.9,'nmf','')")
    conn.execute("INSERT INTO community_account VALUES ('c2','s3',0.9,'nmf','')")
    conn.execute("INSERT INTO community_account VALUES ('c2','s4',0.9,'nmf','')")
    conn.execute("INSERT INTO account_following VALUES ('s1','target1')")
    conn.execute("INSERT INTO account_following VALUES ('s2','target1')")
    conn.execute("INSERT INTO account_following VALUES ('s3','target1')")
    conn.execute("INSERT INTO account_following VALUES ('s4','target1')")
    conn.commit()
    signal = get_graph_signal(conn, account_id="target1")
    other_pos = signal.index("Other Comm")
    test_pos = signal.index("Test Community")
    assert other_pos < test_pos, "Other Comm (3 seeds) should appear before Test Community (1 seed)"


def test_engagement_context_breakdown_multiple_communities(tmp_path):
    """Breakdown line correctly counts likers per community."""
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO community_account VALUES ('c1','liker1',0.9,'nmf','')")
    conn.execute("INSERT INTO community_account VALUES ('c1','liker2',0.8,'nmf','')")
    conn.execute("INSERT INTO community_account VALUES ('c2','liker3',0.7,'nmf','')")
    conn.execute("INSERT INTO likes VALUES ('liker1','user_a','tweetXYZ','','','')")
    conn.execute("INSERT INTO likes VALUES ('liker2','user_b','tweetXYZ','','','')")
    conn.execute("INSERT INTO likes VALUES ('liker3','user_c','tweetXYZ','','','')")
    conn.commit()
    ctx = get_engagement_context(conn, tweet_id="tweetXYZ")
    assert "Liked by:" in ctx
    assert "Breakdown:" in ctx
    assert "Test Community: 2" in ctx
    assert "Other Comm: 1" in ctx


def test_following_overlap_unclassified_follows_not_counted(tmp_path):
    """Follows toward unclassified accounts are not counted."""
    conn = _setup_db(tmp_path)
    # target1 follows 'unclassified_user' who is NOT in community_account
    conn.execute("INSERT INTO account_following VALUES ('target1','unclassified_user')")
    conn.commit()
    overlap = get_following_overlap(conn, account_id="target1")
    assert "No following" in overlap


def test_assemble_account_context_includes_following_overlap(tmp_path):
    """assemble_account_context includes following_overlap key."""
    conn = _setup_db(tmp_path)
    ctx = assemble_account_context(
        conn, account_id="nobody", username="nobody", bio=""
    )
    assert "following_overlap" in ctx
    assert "No following" in ctx["following_overlap"]


def test_assemble_account_context_community_short_names_type(tmp_path):
    """community_short_names is a list."""
    conn = _setup_db(tmp_path)
    ctx = assemble_account_context(
        conn, account_id="nobody", username="nobody", bio=""
    )
    assert isinstance(ctx["community_short_names"], list)
    assert "Test-Comm" in ctx["community_short_names"]
