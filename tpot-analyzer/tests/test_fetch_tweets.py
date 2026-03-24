"""Tests for scripts/fetch_tweets_for_account.py."""
import sqlite3
import json
import pytest
from unittest.mock import patch, MagicMock
from scripts.fetch_tweets_for_account import (
    fetch_last_tweets, fetch_advanced_search, store_tweets,
    parse_tweet, check_budget, log_api_call, BudgetExhaustedError,
    assert_not_holdout,
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
    # Verify estimated_cost defaults to 0.05
    rows = db.execute("SELECT estimated_cost FROM enrichment_log").fetchall()
    assert rows[0][0] == 0.05


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
