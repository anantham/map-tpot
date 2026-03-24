import sqlite3
import math
import pytest
from scripts.active_learning_schema import create_tables


def _setup_db(tmp_path):
    """Create a test DB with both tweets and enriched_tweets tables."""
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("""CREATE TABLE tweets (
        tweet_id TEXT PRIMARY KEY, account_id TEXT, username TEXT,
        full_text TEXT, created_at TEXT, reply_to_tweet_id TEXT,
        reply_to_username TEXT, favorite_count INTEGER DEFAULT 0,
        retweet_count INTEGER DEFAULT 0, lang TEXT,
        is_note_tweet INTEGER DEFAULT 0, fetched_at TEXT
    )""")
    conn.execute("""CREATE TABLE community (
        id TEXT PRIMARY KEY, name TEXT, short_name TEXT, description TEXT
    )""")
    conn.execute("INSERT INTO community VALUES ('c1','Test Community','Test-Comm','')")
    conn.execute("""CREATE TABLE tweet_tags (
        tweet_id TEXT, tag TEXT, category TEXT,
        added_by TEXT DEFAULT 'human', created_at TEXT,
        PRIMARY KEY (tweet_id, tag)
    )""")
    conn.execute("""CREATE TABLE account_community_bits (
        account_id TEXT, community_id TEXT, total_bits INTEGER,
        tweet_count INTEGER, pct REAL, updated_at TEXT,
        PRIMARY KEY (account_id, community_id)
    )""")
    create_tables(conn)  # adds enriched_tweets + enrichment_log
    conn.commit()
    return conn


def test_rollup_includes_enriched_tweets(tmp_path):
    from scripts.rollup_bits import load_bits_tags
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO tweets VALUES ('t1','acc1','u1','text','','','',0,0,'en',0,'')")
    conn.execute("INSERT INTO tweet_tags VALUES ('t1','bits:Test-Comm:+2','bits','human','')")
    conn.execute("INSERT INTO enriched_tweets (tweet_id,account_id,username,text,fetch_source,fetched_at) VALUES ('t2','acc2','u2','text','last_tweets','')")
    conn.execute("INSERT INTO tweet_tags VALUES ('t2','bits:Test-Comm:+3','bits','llm_ensemble_consensus','')")
    conn.commit()
    rows = load_bits_tags(conn)
    account_ids = {r[0] for r in rows}
    assert "acc1" in account_ids
    assert "acc2" in account_ids


def test_rollup_works_without_enriched_table(tmp_path):
    """If enriched_tweets table doesn't exist, load_bits_tags still works."""
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("""CREATE TABLE tweets (
        tweet_id TEXT PRIMARY KEY, account_id TEXT, username TEXT,
        full_text TEXT, created_at TEXT, reply_to_tweet_id TEXT,
        reply_to_username TEXT, favorite_count INTEGER DEFAULT 0,
        retweet_count INTEGER DEFAULT 0, lang TEXT,
        is_note_tweet INTEGER DEFAULT 0, fetched_at TEXT
    )""")
    conn.execute("""CREATE TABLE tweet_tags (
        tweet_id TEXT, tag TEXT, category TEXT,
        added_by TEXT DEFAULT 'human', created_at TEXT,
        PRIMARY KEY (tweet_id, tag)
    )""")
    conn.execute("INSERT INTO tweets VALUES ('t1','acc1','u1','text','','','',0,0,'en',0,'')")
    conn.execute("INSERT INTO tweet_tags VALUES ('t1','bits:Test-Comm:+2','bits','human','')")
    conn.commit()
    from scripts.rollup_bits import load_bits_tags
    rows = load_bits_tags(conn)
    assert len(rows) == 1
    assert rows[0][0] == "acc1"


def test_scoped_delete_preserves_other_accounts(tmp_path):
    from scripts.rollup_bits import scoped_delete_bits
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO account_community_bits VALUES ('keep','c1',5,2,100.0,'')")
    conn.execute("INSERT INTO account_community_bits VALUES ('delete','c1',3,1,100.0,'')")
    conn.commit()
    deleted = scoped_delete_bits(conn, account_ids=["delete"])
    assert deleted == 1
    remaining = conn.execute("SELECT account_id FROM account_community_bits").fetchall()
    assert [r[0] for r in remaining] == ["keep"]


def test_scoped_delete_empty_list(tmp_path):
    from scripts.rollup_bits import scoped_delete_bits
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO account_community_bits VALUES ('keep','c1',5,2,100.0,'')")
    conn.commit()
    deleted = scoped_delete_bits(conn, account_ids=[])
    assert deleted == 0


def test_discount_applied_for_enriched_account(tmp_path):
    from scripts.rollup_bits import compute_discount
    conn = _setup_db(tmp_path)
    for i in range(20):
        conn.execute(
            "INSERT INTO enriched_tweets (tweet_id,account_id,username,text,fetch_source,fetched_at) "
            f"VALUES ('et{i}','acc2','u2','text','last_tweets','')"
        )
    conn.commit()
    discount = compute_discount(conn, account_id="acc2")
    expected = min(1.0, math.sqrt(20 / 50))
    assert abs(discount - expected) < 0.01


def test_discount_not_applied_for_archive_account(tmp_path):
    from scripts.rollup_bits import compute_discount
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO tweets VALUES ('t1','acc1','u1','text','','','',0,0,'en',0,'')")
    conn.commit()
    discount = compute_discount(conn, account_id="acc1")
    assert discount == 1.0


def test_discount_archive_takes_priority(tmp_path):
    """Account with both archive and enriched tweets gets no discount."""
    from scripts.rollup_bits import compute_discount
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO tweets VALUES ('t1','acc1','u1','text','','','',0,0,'en',0,'')")
    conn.execute("INSERT INTO enriched_tweets (tweet_id,account_id,username,text,fetch_source,fetched_at) VALUES ('et1','acc1','u1','text','last_tweets','')")
    conn.commit()
    discount = compute_discount(conn, account_id="acc1")
    assert discount == 1.0


def test_discount_no_enriched_table(tmp_path):
    """If enriched_tweets doesn't exist, discount is 1.0."""
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("""CREATE TABLE tweets (
        tweet_id TEXT PRIMARY KEY, account_id TEXT, username TEXT,
        full_text TEXT, created_at TEXT, reply_to_tweet_id TEXT,
        reply_to_username TEXT, favorite_count INTEGER DEFAULT 0,
        retweet_count INTEGER DEFAULT 0, lang TEXT,
        is_note_tweet INTEGER DEFAULT 0, fetched_at TEXT
    )""")
    conn.commit()
    from scripts.rollup_bits import compute_discount
    discount = compute_discount(conn, account_id="acc1")
    assert discount == 1.0
