"""Tests for scripts/fetch_tweets_for_account.py."""
import sqlite3
import json
import pytest
from unittest.mock import patch, MagicMock
from scripts.fetch_tweets_for_account import (
    fetch_last_tweets, fetch_advanced_search, store_tweets,
    parse_tweet, check_budget, log_api_call, BudgetExhaustedError,
    assert_not_holdout, load_archive_tweets, fetch_multi_scale,
)
from scripts.active_learning_schema import create_tables


@pytest.fixture
def db(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    create_tables(conn)
    return conn


SAMPLE_TWEET = {
    "id": "123456", "text": "test tweet", "likeCount": 10,
    "retweetCount": 2, "replyCount": 1, "viewCount": 500,
    "createdAt": "Mon Mar 20 09:00:00 +0000 2024", "lang": "en",
    "isReply": False, "inReplyToUsername": None,
    "author": {"id": "789", "userName": "testuser", "description": "bio"},
    "entities": {"user_mentions": [{"screen_name": "other"}], "urls": []},
}


def test_parse_tweet():
    result = parse_tweet(SAMPLE_TWEET, "testuser")
    assert result["tweet_id"] == "123456"
    assert result["account_id"] == "789"
    assert result["like_count"] == 10
    assert result["mentions_json"] == '["other"]'
    assert result["username"] == "testuser"


def test_parse_tweet_empty_mentions():
    tweet = {**SAMPLE_TWEET, "entities": {"user_mentions": [], "urls": []}}
    result = parse_tweet(tweet, "testuser")
    assert result["mentions_json"] == "[]"


def test_parse_tweet_no_entities():
    tweet = {**SAMPLE_TWEET}
    del tweet["entities"]
    result = parse_tweet(tweet, "testuser")
    assert result["mentions_json"] == "[]"
    assert result["has_media"] == 0


def test_store_tweets_inserts(db):
    parsed = parse_tweet(SAMPLE_TWEET, "testuser")
    count = store_tweets(db, [parsed], fetch_source="last_tweets")
    assert count == 1
    row = db.execute("SELECT * FROM enriched_tweets WHERE tweet_id='123456'").fetchone()
    assert row is not None


def test_store_tweets_dedup(db):
    parsed = parse_tweet(SAMPLE_TWEET, "testuser")
    store_tweets(db, [parsed], fetch_source="last_tweets")
    count = store_tweets(db, [parsed], fetch_source="last_tweets")
    assert count == 0


def test_store_tweets_with_query(db):
    parsed = parse_tweet(SAMPLE_TWEET, "testuser")
    store_tweets(db, [parsed], fetch_source="advanced_search", fetch_query="from:testuser meditation")
    row = db.execute("SELECT fetch_source, fetch_query FROM enriched_tweets WHERE tweet_id='123456'").fetchone()
    assert row[0] == "advanced_search"
    assert row[1] == "from:testuser meditation"


def test_check_budget_under(db):
    assert check_budget(db, limit=5.0) is True


def test_check_budget_over(db):
    db.execute(
        "INSERT INTO enrichment_log (account_id, username, round, action, estimated_cost, created_at) "
        "VALUES ('x','x',1,'test',5.01,'')"
    )
    db.commit()
    assert check_budget(db, limit=5.0) is False


def test_check_budget_raises_when_exhausted(db):
    db.execute(
        "INSERT INTO enrichment_log (account_id, username, round, action, estimated_cost, created_at) "
        "VALUES ('x','x',1,'test',5.01,'')"
    )
    db.commit()
    with pytest.raises(BudgetExhaustedError):
        check_budget(db, limit=5.0, raise_on_exceed=True)


def test_log_api_call(db):
    log_api_call(db, account_id="789", username="test", round_num=1,
                 action="last_tweets", tweets_fetched=20)
    row = db.execute("SELECT * FROM enrichment_log").fetchone()
    assert row is not None
    # Verify estimated_cost defaults to COST_PER_CALL (0.03)
    rows = db.execute("SELECT estimated_cost FROM enrichment_log").fetchall()
    assert rows[0][0] == 0.03


def test_assert_not_holdout(db):
    db.execute("CREATE TABLE IF NOT EXISTS tpot_directory_holdout (handle TEXT, account_id TEXT)")
    db.execute("INSERT INTO tpot_directory_holdout VALUES ('holdout_user', '999')")
    db.commit()
    with pytest.raises(ValueError, match="holdout"):
        assert_not_holdout(db, account_id="999")


def test_assert_not_holdout_passes_for_normal(db):
    db.execute("CREATE TABLE IF NOT EXISTS tpot_directory_holdout (handle TEXT, account_id TEXT)")
    db.commit()
    assert_not_holdout(db, account_id="123")  # should not raise


def test_load_archive_tweets_uses_top_engagement(db):
    db.execute(
        "CREATE TABLE tweets (tweet_id TEXT, account_id TEXT, full_text TEXT, like_count INTEGER, retweet_count INTEGER, reply_count INTEGER, created_at TEXT, lang TEXT)"
    )
    db.execute(
        "INSERT INTO tweets VALUES ('t-low','acct1','low engagement',1,0,0,'2026-03-01','en')"
    )
    db.execute(
        "INSERT INTO tweets VALUES ('t-high','acct1','high engagement',5,10,0,'2026-03-02','en')"
    )
    db.commit()

    parsed, inserted = load_archive_tweets(db, account_id="acct1", username="user1", limit=1)

    assert inserted == 1
    assert len(parsed) == 1
    assert parsed[0]["tweet_id"] == "t-high"
    row = db.execute(
        "SELECT tweet_id, fetch_source FROM enriched_tweets WHERE account_id='acct1'"
    ).fetchone()
    assert row == ("t-high", "archive")


def test_load_archive_tweets_supports_real_archive_schema(db):
    db.execute(
        """CREATE TABLE tweets (
            tweet_id TEXT,
            account_id TEXT,
            username TEXT,
            full_text TEXT,
            created_at TEXT,
            reply_to_tweet_id TEXT,
            reply_to_username TEXT,
            favorite_count INTEGER,
            retweet_count INTEGER,
            lang TEXT,
            is_note_tweet INTEGER,
            fetched_at TEXT
        )"""
    )
    db.execute(
        "INSERT INTO tweets VALUES ('t-low','acct1','user1','low engagement','2026-03-01',NULL,NULL,1,0,'en',0,'')"
    )
    db.execute(
        "INSERT INTO tweets VALUES ('t-high','acct1','user1','reply with favorite_count','2026-03-02','parent-1','target_user',5,3,'en',0,'')"
    )
    db.commit()

    parsed, inserted = load_archive_tweets(db, account_id='acct1', username='user1', limit=1)

    assert inserted == 1
    assert len(parsed) == 1
    assert parsed[0]["tweet_id"] == "t-high"
    assert parsed[0]["like_count"] == 5
    assert parsed[0]["reply_count"] == 0
    assert parsed[0]["is_reply"] == 1
    assert parsed[0]["in_reply_to_user"] == "target_user"


def test_fetch_multi_scale_archive_only_skips_paid_fetches(db, monkeypatch):
    db.execute(
        "CREATE TABLE tweets (tweet_id TEXT, account_id TEXT, full_text TEXT, like_count INTEGER, retweet_count INTEGER, reply_count INTEGER, created_at TEXT, lang TEXT)"
    )
    db.execute(
        "INSERT INTO tweets VALUES ('t1','acct1','archive tweet one',4,1,0,'2026-03-01','en')"
    )
    db.execute(
        "INSERT INTO tweets VALUES ('t2','acct1','archive tweet two',3,2,0,'2026-03-02','en')"
    )
    db.commit()

    def _should_not_run(*args, **kwargs):
        raise AssertionError("paid Twitter API fetch should not run in archive-only mode")

    monkeypatch.setattr("scripts.fetch_tweets_for_account.fetch_advanced_search", _should_not_run)
    monkeypatch.setattr("scripts.fetch_tweets_for_account.fetch_last_tweets", _should_not_run)

    parsed, inserted = fetch_multi_scale(
        api_key=None,
        username="user1",
        account_id="acct1",
        conn=db,
        round_num=1,
        budget_limit=0.0,
        archive_only=True,
        archive_limit=2,
    )

    assert len(parsed) == 2
    assert inserted == 2
    assert db.execute("SELECT COUNT(*) FROM enrichment_log").fetchone()[0] == 0
    assert db.execute(
        "SELECT COUNT(*) FROM enriched_tweets WHERE account_id='acct1' AND fetch_source='archive'"
    ).fetchone()[0] == 2
