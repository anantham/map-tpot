import sqlite3
import pytest
from scripts.active_learning_schema import create_tables


def test_creates_enriched_tweets_table(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    create_tables(conn)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    assert "enriched_tweets" in tables
    assert "enrichment_log" in tables
    cols = [r[1] for r in conn.execute("PRAGMA table_info(enriched_tweets)")]
    assert "tweet_id" in cols
    assert "account_id" in cols
    assert "fetch_source" in cols
    assert "fetch_query" in cols
    assert "mentions_json" in cols
    conn.close()


def test_creates_indexes(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    create_tables(conn)
    indexes = [r[1] for r in conn.execute("PRAGMA index_list(enriched_tweets)")]
    assert "idx_enriched_tweets_account" in indexes
    assert "idx_enriched_tweets_source" in indexes
    conn.close()


def test_enrichment_log_columns(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    create_tables(conn)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(enrichment_log)")]
    assert "account_id" in cols
    assert "estimated_cost" in cols
    assert "round" in cols
    assert "action" in cols
    conn.close()


def test_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    create_tables(conn)
    create_tables(conn)  # second call should not fail
    conn.close()


def test_mentions_json_default(tmp_path):
    """mentions_json should default to '[]' not NULL."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    create_tables(conn)
    conn.execute(
        "INSERT INTO enriched_tweets (tweet_id, account_id, username, text, fetch_source, fetched_at) "
        "VALUES ('t1', 'a1', 'user', 'hello', 'last_tweets', '2026-01-01')"
    )
    conn.commit()
    row = conn.execute("SELECT mentions_json FROM enriched_tweets WHERE tweet_id='t1'").fetchone()
    assert row[0] == "[]"
    conn.close()
