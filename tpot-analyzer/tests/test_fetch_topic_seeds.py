import sqlite3

from scripts.active_learning import select_accounts
from scripts.active_learning_schema import create_tables
from scripts.fetch_topic_seeds import run_topic_fetch


def _setup_topic_seed_db(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "topic_seed.db"))
    create_tables(conn)
    conn.execute(
        """CREATE TABLE frontier_ranking (
            account_id TEXT PRIMARY KEY,
            band TEXT,
            info_value REAL,
            top_community TEXT,
            top_weight REAL,
            degree INTEGER,
            in_holdout INTEGER DEFAULT 0,
            created_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE profiles (
            account_id TEXT PRIMARY KEY,
            username TEXT,
            bio TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE resolved_accounts (
            account_id TEXT PRIMARY KEY,
            username TEXT,
            bio TEXT
        )"""
    )
    conn.execute("CREATE TABLE tpot_directory_holdout (handle TEXT, account_id TEXT)")
    conn.commit()
    return conn


def test_run_topic_fetch_stores_parsed_tweets_and_stages_authors(tmp_path, monkeypatch):
    conn = _setup_topic_seed_db(tmp_path)

    raw_tweets = [
        {
            "id": "tweet-1",
            "text": "mechanistic interpretability is real",
            "likeCount": 12,
            "retweetCount": 3,
            "replyCount": 1,
            "viewCount": 100,
            "createdAt": "2026-04-15T00:00:00Z",
            "lang": "en",
            "author": {
                "id": "acct-1",
                "userName": "interp_user",
                "description": "researching SAEs",
            },
            "entities": {"user_mentions": [], "urls": []},
        }
    ]

    monkeypatch.setattr(
        "scripts.fetch_topic_seeds.fetch_advanced_search",
        lambda api_key, query, query_type="Top": raw_tweets,
    )

    run_topic_fetch(conn, api_key="dummy", budget=1.0, queries=['"mechanistic interpretability"'])

    stored = conn.execute(
        "SELECT tweet_id, account_id, username, fetch_source FROM enriched_tweets"
    ).fetchall()
    assert stored == [("tweet-1", "acct-1", "interp_user", "topic_seed")]

    frontier = conn.execute(
        "SELECT account_id, band, info_value, top_community FROM frontier_ranking"
    ).fetchall()
    assert frontier == [("acct-1", "topic_seed", 99.0, "AI-Safety")]

    profile = conn.execute(
        "SELECT username, bio FROM profiles WHERE account_id = 'acct-1'"
    ).fetchone()
    assert profile == ("interp_user", "researching SAEs")

    log_row = conn.execute(
        "SELECT account_id, username, round, action, tweets_fetched, query FROM enrichment_log"
    ).fetchone()
    assert log_row == (
        "__topic_seed_search__",
        "topic_seed",
        0,
        "advanced_search_topic_seed",
        1,
        '"mechanistic interpretability"',
    )

    selected = select_accounts(conn, top_n=10, round_num=1)
    assert [acct["account_id"] for acct in selected] == ["acct-1"]


def test_run_topic_fetch_skips_malformed_search_rows(tmp_path, monkeypatch):
    conn = _setup_topic_seed_db(tmp_path)

    monkeypatch.setattr(
        "scripts.fetch_topic_seeds.fetch_advanced_search",
        lambda api_key, query, query_type="Top": [
            {"id": None, "author": {"id": "acct-1", "userName": "broken"}},
            {"id": "tweet-2", "author": {"id": "", "userName": "missing_id"}},
        ],
    )

    run_topic_fetch(conn, api_key="dummy", budget=1.0, queries=['"corrigibility"'])

    assert conn.execute("SELECT COUNT(*) FROM enriched_tweets").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM frontier_ranking").fetchone()[0] == 0
